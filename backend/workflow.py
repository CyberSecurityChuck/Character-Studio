"""Subject mapping, reference selection, approval snapshots and the saved workflow stage.

Approvals (PLAN.md §11, §19) are immutable snapshots of the exact inputs. An approval
is valid only while a fresh snapshot of the current inputs hashes to the same value;
any change invalidates it, with a reason, the next time the scene is refreshed.
Phase 5 must call `require_valid_approval` before any generation starts.
"""

import hashlib
import json
from dataclasses import dataclass, field
from uuid import uuid4

from sqlalchemy import select

from backend.analysis_schema import SCHEMA_VERSION, SceneAnalysisData, validate_analysis
from backend.models import (
    Approval,
    Character,
    PromptVersion,
    ReferencePhoto,
    Scene,
    SceneAnalysis,
    SubjectMapping,
)
from backend.prompting import Assignment, check_prompt
from backend.scene_store import active_job, latest, next_version, now

SNAPSHOT_VERSION = 1
AUTO_REFERENCES = 3
MAX_REFERENCES = 4
# Codex image generation was verified with the Base Image plus 2 reference photos
# (docs/PROVIDER_FINDINGS.md). Larger sets are allowed but flagged as untested.
TESTED_REFERENCE_TOTAL = 4
VIEW_ORDER = (
    "Front",
    "Left three-quarter",
    "Right three-quarter",
    "Left profile",
    "Right profile",
    "Full body",
    "Additional",
)


def digest(value) -> str:
    text = value if isinstance(value, str) else json.dumps(value, sort_keys=True)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def subjects_fingerprint(data: SceneAnalysisData) -> str:
    """Labels and boxes; mappings saved against other subjects must be checked again."""
    return digest(
        [
            [
                s.label,
                *(round(getattr(s.bounding_box, k), 4) for k in ("x", "y", "width", "height")),
            ]
            for s in data.subjects
        ]
    )


def analysis_of(row: SceneAnalysis) -> SceneAnalysisData:
    return validate_analysis(json.loads(row.structured_analysis))


def _preferred_labels(angle: str) -> list[str]:
    text = angle.lower()
    side = "Left" if "left" in text else "Right" if "right" in text else None
    if side and "profile" in text:
        return [f"{side} profile", f"{side} three-quarter"]
    if side and ("three-quarter" in text or "three quarter" in text or "3/4" in text):
        return [f"{side} three-quarter", f"{side} profile"]
    return []


def auto_references(photos: list[ReferencePhoto], primary_id, facial_angle: str) -> list[str]:
    """A useful subset, not every photo (PLAN.md §5.3).

    Primary photo first, then a front view and the viewpoint closest to the subject's
    face angle, then other distinct viewpoints. Only identity is taken from these
    photos, so the choice never changes the scene's camera angle.
    """
    chosen: list[ReferencePhoto] = [p for p in photos if p.id == primary_id][:1]
    for label in [*_preferred_labels(facial_angle), "Front", *VIEW_ORDER]:
        if len(chosen) >= AUTO_REFERENCES:
            break
        if label in {p.label for p in chosen}:
            continue
        match = next((p for p in photos if p.label == label and p not in chosen), None)
        if match:
            chosen.append(match)
    for photo in photos:
        if len(chosen) >= AUTO_REFERENCES:
            break
        if photo not in chosen:
            chosen.append(photo)
    return [p.id for p in chosen]


def character_photos(session, character_id) -> list[ReferencePhoto]:
    return list(
        session.scalars(
            select(ReferencePhoto)
            .where(ReferencePhoto.character_id == character_id)
            .order_by(ReferencePhoto.created_at, ReferencePhoto.id)
        )
    )


@dataclass
class SubjectPlan:
    label: str
    action: str
    character: Character | None
    photos: list[ReferencePhoto]
    references_auto: bool
    confirmed: bool
    images: tuple[int, ...] = ()
    problems: list[str] = field(default_factory=list)


@dataclass
class Plan:
    analysis: SceneAnalysisData
    subjects: list[SubjectPlan]
    fingerprint: str

    @property
    def assignments(self) -> list[Assignment]:
        return [Assignment(s.label, s.action, s.images) for s in self.subjects]

    @property
    def total_images(self) -> int:
        return 1 + sum(len(s.images) for s in self.subjects)

    @property
    def mapping_hash(self) -> str:
        """What the prompt depends on: actions, characters and image order (not the boxes)."""
        return digest(
            [
                [
                    s.label,
                    s.action,
                    s.character.id if s.character else None,
                    [p.id for p in s.photos],
                ]
                for s in self.subjects
            ]
        )

    @property
    def blockers(self) -> list[str]:
        problems = [p for s in self.subjects for p in s.problems]
        if any(not s.confirmed for s in self.subjects if s.action != "unresolved"):
            problems.insert(
                0,
                "The subjects changed after you assigned characters. Check the assignments "
                "and save them again.",
            )
        return problems


def build_plan(session, scene: Scene, analysis_row: SceneAnalysis) -> Plan:
    data = analysis_of(analysis_row)
    fingerprint = subjects_fingerprint(data)
    rows = {
        m.subject_label: m
        for m in session.scalars(select(SubjectMapping).where(SubjectMapping.scene_id == scene.id))
    }
    subjects, number, seen = [], 2, {}
    for subject in data.subjects:
        row = rows.get(subject.label)
        if row is None:
            plan = SubjectPlan(subject.label, "unresolved", None, [], True, True)
            plan.problems.append(f"Choose a character or Keep original for {subject.label}.")
            subjects.append(plan)
            continue
        character = session.get(Character, row.character_id) if row.character_id else None
        by_id = {p.id: p for p in character_photos(session, character.id)} if character else {}
        photos = [by_id[i] for i in json.loads(row.reference_ids) if i in by_id]
        plan = SubjectPlan(
            subject.label,
            row.action,
            character,
            photos if row.action == "replace" else [],
            row.references_auto,
            row.subjects_hash == fingerprint,
        )
        if row.action == "unresolved":
            plan.problems.append(f"Choose a character or Keep original for {subject.label}.")
        elif row.action == "replace":
            if character is None:
                plan.problems.append(f"Choose a character for {subject.label}.")
            elif not plan.photos:
                plan.problems.append(
                    f"Choose at least one reference photo of {character.name} for {subject.label}."
                )
            if character is not None:
                if character.id in seen:
                    plan.problems.append(
                        f"{character.name} is assigned to both {seen[character.id]} and "
                        f"{subject.label}. Each character can appear only once."
                    )
                seen[character.id] = subject.label
            plan.images = tuple(range(number, number + len(plan.photos)))
            number += len(plan.photos)
        subjects.append(plan)
    return Plan(data, subjects, fingerprint)


def save_mappings(session, scene: Scene, plan_fingerprint: str, entries: list[dict]) -> None:
    """Replace the scene's mappings. Callers validate entries first."""
    for row in session.scalars(select(SubjectMapping).where(SubjectMapping.scene_id == scene.id)):
        session.delete(row)
    session.flush()
    for entry in entries:
        session.add(
            SubjectMapping(
                id=uuid4().hex,
                scene_id=scene.id,
                subject_label=entry["label"],
                action=entry["action"],
                character_id=entry.get("character_id"),
                reference_ids=json.dumps(entry.get("reference_ids") or []),
                references_auto=entry.get("references_auto", True),
                subjects_hash=plan_fingerprint,
                updated_at=now(),
            )
        )
    session.flush()


# Approval snapshots ------------------------------------------------------------------


def snapshot_inputs(session, scene: Scene) -> dict | None:
    """The exact inputs an approval covers, or None when the scene cannot be approved."""
    analysis = latest(session, SceneAnalysis, scene.id)
    prompt = latest(session, PromptVersion, scene.id)
    if analysis is None or prompt is None:
        return None
    plan = build_plan(session, scene, analysis)
    return {
        "snapshot_version": SNAPSHOT_VERSION,
        "scene_id": scene.id,
        "base_image": {"path": scene.original_path, "content_hash": scene.content_hash},
        "analysis": {
            "id": analysis.id,
            "version": analysis.version,
            "content_hash": digest(analysis.structured_analysis),
        },
        "subjects_fingerprint": plan.fingerprint,
        "prompt": {
            "id": prompt.id,
            "version": prompt.version,
            "is_polished": prompt.is_polished,
            "prompt_text": prompt.prompt_text,
            "negative_prompt": prompt.negative_prompt,
        },
        "mappings": [
            {
                "subject": s.label,
                "action": s.action,
                "character_id": s.character.id if s.character else None,
                "references": [
                    {"photo_id": p.id, "content_hash": p.content_hash, "image": n}
                    for p, n in zip(s.photos, s.images, strict=True)
                ],
            }
            for s in plan.subjects
        ],
        # Generation settings arrive with Phase 5; approval covers content, not the engine.
        "settings": {},
    }


def snapshot_display(session, scene: Scene, inputs: dict) -> dict:
    """Readable context kept with the snapshot; names are not hashed, so a rename is harmless."""
    names = {}
    for entry in inputs["mappings"]:
        if entry["character_id"]:
            character = session.get(Character, entry["character_id"])
            names[entry["character_id"]] = character.name if character else "Deleted character"
    return {"scene_title": scene.title, "character_names": names}


def next_prompt_version(session, scene_id) -> int:
    """Prompt versions can be deleted; never reuse a number an approval recorded."""
    approved = [
        json.loads(snapshot)["inputs"]["prompt"]["version"]
        for snapshot in session.scalars(
            select(Approval.snapshot_json).where(Approval.scene_id == scene_id)
        )
    ]
    return max(next_version(session, PromptVersion, scene_id), max(approved, default=0) + 1)


def current_approval(session, scene_id) -> Approval | None:
    return session.scalar(
        select(Approval)
        .where(Approval.scene_id == scene_id, Approval.invalidated_at.is_(None))
        .order_by(Approval.approved_at.desc())
        .limit(1)
    )


def describe_change(old: dict, new: dict | None) -> str:
    if new is None:
        return "The analysis or the prompt is no longer available."
    reasons = []
    for keys, reason in (
        (("base_image",), "the Base Image changed"),
        (("analysis", "subjects_fingerprint"), "the analysis changed"),
        (("prompt",), "the prompt changed"),
    ):
        if any(old.get(k) != new.get(k) for k in keys):
            reasons.append(reason)
    old_map, new_map = old.get("mappings", []), new["mappings"]
    if [(m["subject"], m["action"], m["character_id"]) for m in old_map] != [
        (m["subject"], m["action"], m["character_id"]) for m in new_map
    ]:
        reasons.append("the character assignments changed")
    elif [m["references"] for m in old_map] != [m["references"] for m in new_map]:
        reasons.append("the reference photos changed")
    if not reasons:
        reasons.append("an approved input changed")
    text = ", ".join(reasons[:-1]) + (" and " if len(reasons) > 1 else "") + reasons[-1]
    return f"Approval cancelled because {text}."


def check_approval(session, scene: Scene, approval: Approval | None = None):
    """Return (approval, reason). The reason is set when the approval no longer matches."""
    approval = approval or current_approval(session, scene.id)
    if approval is None:
        return None, None
    inputs = snapshot_inputs(session, scene)
    if inputs is not None and digest(inputs) == approval.snapshot_hash:
        return approval, None
    return approval, describe_change(json.loads(approval.snapshot_json)["inputs"], inputs)


def revalidate_approval(session, scene: Scene) -> None:
    approval, reason = check_approval(session, scene)
    if approval is not None and reason:
        approval.invalidated_at = now()
        approval.invalidated_reason = reason


class ApprovalError(Exception):
    """No valid approval; the message is safe to show."""


def require_valid_approval(session, scene: Scene) -> Approval:
    """The gate every generation path must pass (PLAN.md §11 Approval Rule)."""
    approval, reason = check_approval(session, scene)
    if approval is None:
        ended = session.scalar(
            select(Approval.invalidated_reason)
            .where(Approval.scene_id == scene.id)
            .order_by(Approval.approved_at.desc())
            .limit(1)
        )
        raise ApprovalError(f"{ended + ' ' if ended else ''}Approve this scene before generating.")
    if reason:
        raise ApprovalError(f"{reason} Review and approve the scene again.")
    return approval


@dataclass
class Review:
    blockers: list[str]
    warnings: list[str]
    notes: list[str]
    plan: Plan | None
    prompt_missing: list[str]


def review(session, scene: Scene) -> Review:
    """What stands between this scene and approval."""
    analysis = latest(session, SceneAnalysis, scene.id)
    prompt = latest(session, PromptVersion, scene.id)
    blockers, warnings, notes, missing = [], [], [], []
    if active_job(session, scene.id):
        blockers.append("Wait for the running engine job to finish or cancel it.")
    if analysis is None:
        return Review([*blockers, "Analyse the scene first."], [], [], None, [])
    plan = build_plan(session, scene, analysis)
    pending = len(plan.analysis.uncertainties)
    if pending:
        blockers.append(
            f"Confirm or correct the {pending} uncertain "
            f"{'detail' if pending == 1 else 'details'} in the analysis."
        )
    blockers += plan.blockers
    if prompt is None:
        blockers.append("Save a prompt version.")
    else:
        if prompt.analysis_id != analysis.id:
            warnings.append("The saved prompt was built from an earlier analysis version.")
        if prompt.mapping_hash != plan.mapping_hash and not (
            prompt.mapping_hash is None and not plan.subjects
        ):
            warnings.append("The saved prompt was built before the current character assignments.")
        missing = check_prompt(prompt.prompt_text, plan.assignments, plan.total_images)
        warnings += missing
    references = plan.total_images - 1
    if references > TESTED_REFERENCE_TOTAL:
        notes.append(
            f"{references} reference photos will be attached. Codex image generation has been "
            "tested here with fewer; consider fewer photos per character if results ignore some."
        )
    return Review(blockers, warnings, notes, plan, missing)


def create_approval(session, scene: Scene) -> Approval:
    inputs = snapshot_inputs(session, scene)
    previous = current_approval(session, scene.id)
    if previous is not None:
        previous.invalidated_at = now()
        previous.invalidated_reason = "Replaced by a newer approval."
    approval = Approval(
        id=uuid4().hex,
        scene_id=scene.id,
        snapshot_json=json.dumps(
            {"inputs": inputs, "display": snapshot_display(session, scene, inputs)}, sort_keys=True
        ),
        snapshot_hash=digest(inputs),
        approved_at=now(),
    )
    session.add(approval)
    session.flush()
    return approval


# Workflow stage ------------------------------------------------------------------


def prompt_is_current(prompt: PromptVersion | None, analysis: SceneAnalysis, plan: Plan) -> bool:
    if prompt is None or prompt.analysis_id != analysis.id:
        return False
    return prompt.mapping_hash == plan.mapping_hash or (
        prompt.mapping_hash is None and not plan.subjects
    )


def refresh_workflow(session, scene: Scene) -> None:
    """Re-check the approval and derive the saved workflow stage; called after every change."""
    session.flush()
    revalidate_approval(session, scene)
    job = active_job(session, scene.id)
    analysis = latest(session, SceneAnalysis, scene.id)
    if job:
        state = "polishing" if job.kind == "polish" else "analysing"
    elif analysis is None:
        state = "needs_analysis"
    elif current_approval(session, scene.id) is not None:
        state = "approved"
    else:
        plan = build_plan(session, scene, analysis)
        if plan.analysis.uncertainties:
            state = "review_analysis"
        elif plan.blockers:
            state = "needs_mapping"
        elif not prompt_is_current(latest(session, PromptVersion, scene.id), analysis, plan):
            state = "analysis_ready"
        else:
            state = "prompt_saved"
    scene.workflow_state = state


def add_analysis(
    session,
    scene: Scene,
    data: SceneAnalysisData,
    source: str,
    *,
    confirmed: list | None = None,
    engine_version: str | None = None,
    raw_output_path: str | None = None,
    based_on_id: str | None = None,
    job_id: str | None = None,
) -> SceneAnalysis:
    analysis = SceneAnalysis(
        id=uuid4().hex,
        scene_id=scene.id,
        version=next_version(session, SceneAnalysis, scene.id),
        schema_version=SCHEMA_VERSION,
        structured_analysis=data.model_dump_json(),
        analysis_text=data.scene_description,
        confirmed_uncertainties=json.dumps(confirmed or []),
        source=source,
        engine_version=engine_version,
        raw_output_path=raw_output_path,
        based_on_id=based_on_id,
        job_id=job_id,
        created_at=now(),
    )
    session.add(analysis)
    session.flush()
    scene.updated_at = now()
    refresh_workflow(session, scene)
    return analysis


def scenes_using(session, character_id: str) -> set[str]:
    return set(
        session.scalars(
            select(SubjectMapping.scene_id).where(SubjectMapping.character_id == character_id)
        )
    )


def refresh_scenes(session, scene_ids) -> None:
    """After a library change, re-check the scenes that mapped the changed character."""
    for scene_id in scene_ids:
        scene = session.get(Scene, scene_id)
        if scene is not None:
            refresh_workflow(session, scene)
