"""Quality checks of results: identity consistency and composition fidelity (Phase 6B, D023).

A check is a user-started engine run with the selected analysis engine. It compares a
result with the Base Image and the reference photos of the approval it was made from,
and returns scores (1-5, 0 = could not judge) with short notes. It is a model's opinion,
not a measurement (PLAN.md §13: do not misrepresent model accuracy), and it never
changes a result, an approval or a prompt.
"""

import json
from typing import Annotated, Literal

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from sqlalchemy import select

from backend.analysis_schema import AnalysisFormatError
from backend.configuration import Settings, asset_path
from backend.generation import PackageError, _clean_copy, new_job_folder, snapshot_of, write_package
from backend.models import (
    Approval,
    GenerationPreset,
    GenerationResult,
    PromptVersion,
    QualityCheck,
)

CHECK_SCHEMA_VERSION = 1
ASPECTS = (
    "camera_and_framing",
    "subject_positions",
    "poses",
    "head_and_gaze",
    "outfits",
    "environment",
    "lighting",
)
EXPECTATIONS = {"replace": "replaced", "keep": "kept", "unresolved": "unassigned"}
_SCORE = {"type": "integer", "minimum": 0, "maximum": 5}
_NOTE = {"type": "string"}

CHECK_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["schema_version", "composition", "identity", "summary", "issues"],
    "properties": {
        "schema_version": {"type": "integer", "const": CHECK_SCHEMA_VERSION},
        "composition": {
            "type": "object",
            "additionalProperties": False,
            "required": list(ASPECTS),
            "properties": {
                aspect: {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["score", "note"],
                    "properties": {"score": _SCORE, "note": _NOTE},
                }
                for aspect in ASPECTS
            },
        },
        "identity": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["subject", "expected", "score", "note"],
                "properties": {
                    "subject": {"type": "string", "pattern": "^Subject [0-9]+$"},
                    "expected": {"type": "string", "enum": list(EXPECTATIONS.values())},
                    "score": _SCORE,
                    "note": _NOTE,
                },
            },
        },
        "summary": {"type": "string"},
        "issues": {"type": "array", "items": {"type": "string"}},
    },
}

Note = Annotated[str, Field(max_length=1000)]
Score = Annotated[int, Field(ge=0, le=5)]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Aspect(_Strict):
    score: Score
    note: Note


class Composition(_Strict):
    camera_and_framing: Aspect
    subject_positions: Aspect
    poses: Aspect
    head_and_gaze: Aspect
    outfits: Aspect
    environment: Aspect
    lighting: Aspect


class IdentityItem(_Strict):
    subject: str = Field(pattern=r"^Subject [0-9]+$")
    expected: Literal["replaced", "kept", "unassigned"]
    score: Score
    note: Note


class CheckData(_Strict):
    schema_version: Literal[1]
    composition: Composition
    identity: list[IdentityItem] = Field(max_length=20)
    summary: Annotated[str, Field(max_length=3000)]
    issues: list[Annotated[str, Field(max_length=400)]] = Field(max_length=12)

    @field_validator("identity")
    @classmethod
    def one_entry_per_subject(cls, value):
        labels = [item.subject for item in value]
        if len(labels) != len(set(labels)):
            raise ValueError("A subject is listed twice.")
        return value


def validate_check(value: object) -> CheckData:
    """Validate a reply (JSON object or text holding one) against the check format."""
    if isinstance(value, str):
        text = value.strip()
        if "{" in text and "}" in text:
            text = text[text.index("{") : text.rindex("}") + 1]
        try:
            value = json.loads(text)
        except json.JSONDecodeError as error:
            raise AnalysisFormatError("The quality check is not valid JSON.") from error
    try:
        return CheckData.model_validate(value)
    except ValidationError as error:
        first = error.errors()[0]
        where = ".".join(str(part) for part in first["loc"]) or "the reply"
        raise AnalysisFormatError(
            f"The quality check does not match the studio format ({where}: {first['msg']})."
        ) from error


def _subject_lines(inputs: dict) -> list[str]:
    lines = []
    for mapping in inputs["mappings"]:
        subject, action = mapping["subject"], mapping["action"]
        images = [r["image"] for r in mapping["references"]]
        if action == "replace" and images:
            shown = ", ".join(f"Image {n}" for n in images)
            lines.append(
                f"- {subject}: expected \"replaced\". Should be the person shown in {shown}, in "
                f"{subject}'s place and pose from Image 1."
            )
        elif action == "keep":
            lines.append(
                f"- {subject}: expected \"kept\". Should still be the same person as {subject} in "
                "Image 1."
            )
        else:
            lines.append(
                f"- {subject}: expected \"unassigned\". Judge only whether a person is still in "
                f"{subject}'s place and pose."
            )
    return lines


def check_instruction(inputs: dict, result_image: int, scene_changes: str, files: bool) -> str:
    """The fixed check instruction. `files`: CLI runs read image-<n>.jpg in the job folder;
    API runs receive the images in order and the schema inside the instruction."""
    where = (
        f"The images are the files image-1.jpg to image-{result_image}.jpg in the current "
        "folder; read each one."
        if files
        else "The images are attached in order, each after its \"Image N:\" label."
    )
    roles = ["- Image 1: the Base Image, the intended composition."]
    for mapping in inputs["mappings"]:
        for reference in mapping["references"]:
            number, subject = reference["image"], mapping["subject"]
            roles.append(f"- Image {number}: identity reference for {subject}.")
    roles.append(f"- Image {result_image}: the generated result to check.")
    subjects = _subject_lines(inputs) or ["- (No people in the Base Image.)"]
    changes = scene_changes.strip() or "None."
    lines = [
        "You are the quality-check step of Character Studio, a local image app. Compare the "
        f"generated result (Image {result_image}) with the images it was made from and judge "
        "how closely it matches. Judge only what is visible. Do not identify or name anyone; "
        "compare appearances only.",
        "",
        where,
        *sorted(roles, key=lambda line: int(line.split()[2].rstrip(":"))),
        "",
        "People in the Base Image, labelled from left to right:",
        *subjects,
        "",
        f"Changes the user asked for (intended, not mistakes): {changes}",
        "",
        "Score every item from 1 to 5: 5 = matches very closely, 4 = close with small "
        "differences, 3 = noticeable differences, 2 = clear differences, 1 = does not match. Use "
        "0 only when it cannot be judged (for example a face is hidden or a person is missing).",
        "",
        f"composition: compare Image {result_image} with Image 1 for camera_and_framing, "
        "subject_positions, poses, head_and_gaze, outfits, environment and lighting; one short "
        "note each.",
        "identity: one entry per person listed above, with its label, the expectation given "
        f"above and a score for how well Image {result_image} meets it; one short note each.",
        "summary: a short paragraph. issues: up to 8 concrete differences worth fixing, most "
        "important first (empty if none).",
        "",
        "Be honest and specific; do not inflate scores.",
    ]
    if files:
        lines.append(
            f"Return only the JSON object matching the provided schema, with schema_version "
            f"{CHECK_SCHEMA_VERSION}. No other text."
        )
    else:
        lines += [
            f"Reply with only one JSON object, with schema_version {CHECK_SCHEMA_VERSION}, that "
            "matches this JSON Schema exactly (no extra fields, no commentary, no Markdown):",
            "",
            json.dumps(CHECK_SCHEMA, indent=2),
        ]
    return "\n".join(lines)


def prepare_check_folder(settings: Settings, session, result: GenerationResult):
    """Write the approval's images, the result and the instructions into a new job folder.

    Returns (folder key, image file names in order, CLI instruction, API instruction).
    Raises PackageError when an approved file is missing or changed.
    """
    approval = session.get(Approval, result.approval_id)
    inputs = snapshot_of(approval)["inputs"]
    prompt = session.get(PromptVersion, inputs["prompt"]["id"])
    changes = prompt.scene_changes if prompt else ""
    key, folder, _number = new_job_folder(settings, result.scene_id, "check")
    files = write_package(settings, session, folder, inputs, None)
    result_number = len(files) + 1
    source = asset_path(settings, result.original_path)
    if not source.is_file():
        raise PackageError("The result's image file is missing. Restore it from a backup.")
    _clean_copy(source, folder / f"image-{result_number}.jpg")
    names = tuple(f"image-{n}.jpg" for n in range(1, result_number + 1))
    cli = check_instruction(inputs, result_number, changes, files=True)
    api = check_instruction(inputs, result_number, changes, files=False)
    (folder / "instruction.txt").write_text(cli, encoding="utf-8")
    (folder / "schema.json").write_text(json.dumps(CHECK_SCHEMA, indent=2), encoding="utf-8")
    return key, names, cli, api


def preset_name(session, preset_id: str | None) -> str | None:
    """The name of the preset chosen for a run, recorded with it (Phase 6B)."""
    if not preset_id:
        return None
    preset = session.get(GenerationPreset, preset_id)
    if preset is None:
        raise HTTPException(409, "The chosen preset no longer exists. Reload the page.")
    return preset.name


def check_data(check: QualityCheck) -> dict:
    data = json.loads(check.data_json)
    composition = [a["score"] for a in data["composition"].values() if a["score"]]
    replaced = [i["score"] for i in data["identity"] if i["expected"] == "replaced" and i["score"]]
    return {
        "id": check.id,
        "result_id": check.result_id,
        "job_id": check.job_id,
        "engine": check.engine,
        "engine_version": check.engine_version,
        "created_at": check.created_at,
        # Lowest scores, so a single bad aspect or person is never averaged away.
        "composition_score": min(composition) if composition else None,
        "identity_score": min(replaced) if replaced else None,
        "data": data,
    }


def latest_check(session, result_id: str) -> dict | None:
    check = session.scalar(
        select(QualityCheck)
        .where(QualityCheck.result_id == result_id)
        .order_by(QualityCheck.created_at.desc())
        .limit(1)
    )
    return check_data(check) if check else None

