"""Generation packages, the Codex generation run and result storage (PLAN.md Phase 5).

Everything sent or exported comes from an approval snapshot, never from the live scene,
so a package always matches exactly what the user approved. Files are re-checked
against the snapshot's content hashes before they are copied. Codex runs use only the
mechanics confirmed in Phase 2.5 (docs/PROVIDER_FINDINGS.md): numbered images attached
with `-i`, a read-only sandbox, the final message written with `-o`, and success decided
only by an existing, decodable image under `generated_images/<thread_id>/`.
"""

import hashlib
import json
import os
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException
from PIL import Image, ImageOps
from sqlalchemy import delete, select

from backend.configuration import Settings, asset_path
from backend.engines import EngineError, ProcessOutcome, _check_timeout, _classify, _tail
from backend.library import clean_deleted_files, decode_image, file_hash
from backend.models import (
    Approval,
    EngineJob,
    GenerationResult,
    PendingFileDeletion,
    ReferencePhoto,
    Scene,
    SceneAnalysis,
)
from backend.packages import mapping_text, write_text, write_zip
from backend.persistence import writing_session
from backend.scene_store import next_version, now
from backend.workflow import refresh_workflow

# The instruction is one command-line argument; Windows allows about 32,000 characters.
MAX_GENERATION_INSTRUCTION = 24_000
# Generated files are read whole before decoding; Codex PNGs are a few megabytes.
MAX_RESULT_BYTES = 60 * 1024 * 1024
MODES = ("generate", "variation")
RESULT_MODES = ("generate", "variation", "import", "edit")
IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".webp")
_PATHS = re.compile(r"(?:[A-Za-z]:[\\/]|/)[^\s\"'<>|*?`()\[\]]+?\.(?:png|jpe?g|webp)", re.I)

VARIATION_LINE = (
    "This is a variation request. Follow the brief exactly, but make a fresh attempt with small, "
    "natural differences in fine details such as hair strands, fabric folds and background "
    "texture. Do not change the composition, poses, framing, outfits or identities."
)


class PackageError(Exception):
    """An approved file is missing or no longer matches the approval; safe to show."""


def snapshot_of(approval: Approval) -> dict:
    return json.loads(approval.snapshot_json)


def images_in(inputs: dict) -> list[tuple[int, str]]:
    """(image number, role) for every attached image, in attachment order."""
    entries = [(1, "the Base Image (scene and composition reference)")]
    for mapping in inputs["mappings"]:
        for reference in mapping["references"]:
            entries.append((reference["image"], f"identity reference for {mapping['subject']}"))
    return sorted(entries)


def generation_instruction(inputs: dict, mode: str, api: bool = False) -> str:
    """The approved prompt wrapped with fixed instructions for Codex (D016).

    API image engines (Phase 6C) get the same brief without the Codex-specific lines.
    """
    if api:
        opening = (
            "You are the image-generation step of Character Studio, a local app. Create "
            "exactly one new image from the attached images and the brief below."
        )
    else:
        opening = (
            "You are the image-generation step of Character Studio, a local app. Use your "
            "built-in image generation to create exactly one new image from the attached "
            "images and the brief below. Do not run shell commands, do not read, create or "
            "change any files yourself, and do not ask questions."
        )
    lines = [
        opening,
        "",
        "The images are attached in this order:",
        *(f"- Image {n}: image-{n}.jpg, {role}." for n, role in images_in(inputs)),
    ]
    if mode == "variation":
        lines += ["", VARIATION_LINE]
    prompt = inputs["prompt"]
    lines += ["", "BRIEF", prompt["prompt_text"].strip()]
    if prompt["negative_prompt"].strip():
        lines += ["", "AVOID", prompt["negative_prompt"].strip()]
    if not api:
        lines += ["", "When the image has been generated, reply with only the full path of the "
                  "saved image file."]
    return "\n".join(lines)


def _clean_copy(source: Path, target: Path) -> None:
    """Upright JPEG without EXIF/GPS or other metadata (PLAN.md §22)."""
    with Image.open(source) as image:
        upright = ImageOps.exif_transpose(image).convert("RGB")
        clean = Image.new("RGB", upright.size)
        clean.paste(upright)
        clean.save(target, "JPEG", quality=95)


def write_package(
    settings: Settings, session, folder: Path, inputs: dict, names: dict[str, str] | None
) -> list[Path]:
    """Write numbered images and text files; returns the image files in attachment order."""
    base = asset_path(settings, inputs["base_image"]["path"])
    if file_hash(base) != inputs["base_image"]["content_hash"]:
        raise PackageError("The Base Image file is missing or changed. Restore it from a backup.")
    sources = {1: base}
    for mapping in inputs["mappings"]:
        for reference in mapping["references"]:
            photo = session.get(ReferencePhoto, reference["photo_id"])
            path = asset_path(settings, photo.original_path) if photo else None
            actual = file_hash(path) if path else None
            expected = reference["content_hash"]
            if actual is None or (expected and actual != expected):
                raise PackageError(
                    f"A reference photo for {mapping['subject']} is missing or changed. "
                    "Review and approve the scene again."
                )
            sources[reference["image"]] = path
    files = []
    for number in sorted(sources):
        target = folder / f"image-{number}.jpg"
        _clean_copy(sources[number], target)
        files.append(target)
    prompt = inputs["prompt"]
    write_text(folder / "prompt.txt", prompt["prompt_text"].strip() + "\n")
    write_text(folder / "negative_prompt.txt", prompt["negative_prompt"].strip() + "\n")
    write_text(folder / "mapping.txt", mapping_text(inputs, names))
    return files


def new_job_folder(settings: Settings, scene_id: str, kind: str) -> tuple[str, Path, int]:
    root = asset_path(settings, f"jobs/{scene_id}")
    root.mkdir(parents=True, exist_ok=True)
    number = 1
    while (root / f"{kind}-{number}").exists():
        number += 1
    folder = root / f"{kind}-{number}"
    folder.mkdir()
    return f"jobs/{scene_id}/{kind}-{number}", folder, number


def prepare_generation_folder(
    settings: Settings, session, scene_id: str, inputs: dict, mode: str, api: bool = False
) -> tuple[str, list[Path], str]:
    """Job folder for a run: the package without names, plus the exact instruction."""
    key, folder, _number = new_job_folder(settings, scene_id, "generation")
    files = write_package(settings, session, folder, inputs, None)
    instruction = generation_instruction(inputs, mode, api)
    write_text(folder / "instruction.txt", instruction)
    return key, files, instruction


README = """Character Studio · manual generation package

Scene: {title}
Approved: {approved_at}
Package: {number} (approval {approval})

How to use it
1. Open ChatGPT, or another image app you use, and start a new image request.
2. Attach the images in number order: image-1.jpg first, then image-2.jpg and so on.
   The prompt calls them Image 1, Image 2 and so on.
3. Paste the text of prompt.txt. If the app has a separate field for things to avoid,
   paste negative_prompt.txt there; otherwise add it after the prompt under "Avoid:".
4. Save the image it makes. In Character Studio, open this scene's Generate step, choose
   Import result and pick this package, so the result stays linked to these inputs.

mapping.txt says who is who. It is for you; you do not need to send it.
These files include private photos. Delete the package when you no longer need it.
"""


def prepare_export_folder(settings: Settings, session, scene: Scene, approval: Approval):
    """Manual bridge package (PLAN.md §12.2): files, README and one zip to download."""
    snapshot = snapshot_of(approval)
    inputs, names = snapshot["inputs"], snapshot["display"].get("character_names", {})
    key, folder, number = new_job_folder(settings, scene.id, "export")
    write_package(settings, session, folder, inputs, names)
    readme = README.format(
        title=scene.title,
        approved_at=approval.approved_at[:16].replace("T", " ") + " UTC",
        number=number,
        approval=approval.id[:12],
    )
    write_text(folder / "README.txt", readme)
    write_zip(folder)
    return key, number


def generation_command(command: list[str], job_dir: Path, images: list[Path], instruction: str):
    """Exactly the Phase 2.5 generation setup: read-only sandbox, image generation left on."""
    attached = [part for image in images for part in ("-i", str(image))]
    return [
        *command,
        "exec",
        "--skip-git-repo-check",
        "--ephemeral",
        "--ignore-user-config",
        "-s",
        "read-only",
        "-C",
        str(job_dir),
        *attached,
        "-o",
        str(job_dir / "last-message.txt"),
        "--json",
        "--",
        instruction,
    ]


def codex_images_root() -> Path:
    """Where Codex saves built-in generations (Phase 2.5): <CODEX_HOME>/generated_images."""
    home = os.environ.get("CODEX_HOME")
    return (Path(home) if home else Path.home() / ".codex") / "generated_images"


@dataclass
class RunOutput:
    thread_id: str | None
    message: str
    errors: list[str]


def read_run(job_dir: Path) -> RunOutput:
    thread_id, errors = None, []
    events = job_dir / "events.jsonl"
    if events.is_file():
        for line in events.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(event, dict):
                continue
            if event.get("type") == "thread.started" and isinstance(event.get("thread_id"), str):
                thread_id = event["thread_id"][:80]
            elif event.get("type") == "error":
                errors.append(str(event.get("message", "")))
            elif event.get("type") == "turn.failed":
                errors.append(str((event.get("error") or {}).get("message", "")))
    last = job_dir / "last-message.txt"
    message = last.read_text(encoding="utf-8", errors="replace").strip() if last.is_file() else ""
    return RunOutput(thread_id, message, errors)


def _thread_folder(thread_id: str | None) -> Path | None:
    if not thread_id or not re.fullmatch(r"[A-Za-z0-9._-]{1,80}", thread_id):
        return None
    return (codex_images_root() / thread_id).resolve()


def reported_images(output: RunOutput) -> list[Path]:
    """Image paths named in the final message that really are inside this run's folder."""
    folder = _thread_folder(output.thread_id)
    if folder is None:
        return []
    found = []
    for match in _PATHS.findall(output.message):
        try:
            path = Path(match).resolve()
        except OSError:
            continue
        if path.is_relative_to(folder) and path.is_file() and path not in found:
            found.append(path)
    return found


def saved_images(thread_id: str | None) -> list[Path]:
    """Recovery only: every image in this run's own folder (never the whole directory)."""
    folder = _thread_folder(thread_id)
    if folder is None or not folder.is_dir():
        return []
    return sorted(
        (p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in IMAGE_SUFFIXES),
        key=lambda p: (p.stat().st_mtime, p.name),
    )


def interpret_generation(job_dir: Path, outcome: ProcessOutcome) -> tuple[RunOutput, list[Path]]:
    """Return the run's output and its images, or raise EngineError. Exit codes are ignored."""
    _check_timeout("codex_cli", outcome, "export the package for manual use")
    output = read_run(job_dir)
    images = reported_images(output)
    if images:
        return output, images
    problem = (output.errors[-1] if output.errors else "") or output.message
    if output.errors or not output.message:
        raise _classify("codex_cli", problem or _tail(job_dir / "stderr.txt"))
    # Paths could contain digits such as "401"; classify only the words.
    classified = _classify("codex_cli", _PATHS.sub("", output.message))
    if classified.kind in ("signed_out", "usage_limit"):
        raise classified
    raise EngineError(
        "no_image",
        "Codex finished without producing an image, so nothing was saved. Codex said: "
        f"{output.message[:400]}",
    )


def read_image_file(path: Path) -> bytes:
    if path.stat().st_size > MAX_RESULT_BYTES:
        raise EngineError("invalid_output", "Codex produced an image file that is too large.")
    return path.read_bytes()


def run_seconds(job) -> int | None:
    """How long a finished run took, from the job's own start and finish times."""
    if job is None or not job.started_at or not job.finished_at:
        return None
    started = datetime.fromisoformat(job.started_at)
    return max(0, round((datetime.fromisoformat(job.finished_at) - started).total_seconds()))


def generation_timing(session, engine: str = "codex_cli") -> dict:
    """Average time of completed image runs with this engine on this PC (for planning)."""
    times = [
        seconds
        for job in session.scalars(
            select(EngineJob).where(
                EngineJob.kind == "generation",
                EngineJob.status == "completed",
                EngineJob.engine == engine,
            )
        )
        if (seconds := run_seconds(job)) is not None
    ]
    average = round(sum(times) / len(times)) if times else None
    return {"runs": len(times), "average_seconds": average}


def approval_boxes(session, approval: Approval | None) -> dict:
    """Subject boxes ({label: {x, y, width, height}}) of the analysis an approval covers."""
    if approval is None:
        return {}
    analysis = session.get(SceneAnalysis, snapshot_of(approval)["inputs"]["analysis"]["id"])
    if analysis is None:
        return {}
    subjects = json.loads(analysis.structured_analysis).get("subjects") or []
    return {s.get("label"): s.get("bounding_box") for s in subjects if isinstance(s, dict)}


def result_data(
    result: GenerationResult,
    approval: Approval | None,
    current_id: str | None,
    job: EngineJob | None = None,
    check: dict | None = None,
    boxes: dict | None = None,
):
    snapshot = snapshot_of(approval) if approval is not None else None
    inputs = snapshot["inputs"] if snapshot else None
    names = snapshot["display"].get("character_names", {}) if snapshot else {}
    return {
        "id": result.id,
        "scene_id": result.scene_id,
        "version": result.version,
        "approval_id": result.approval_id,
        "approval_current": result.approval_id == current_id,
        "job_id": result.job_id,
        "source": result.source,
        "mode": result.mode,
        "note": result.note,
        "media_type": result.media_type,
        "width": result.width,
        "height": result.height,
        "engine_version": result.engine_version,
        "recovered": result.recovered,
        # Only a normally finished run was timed by the studio.
        "seconds": run_seconds(job)
        if job is not None and job.kind in ("generation", "edit") and job.status == "completed"
        else None,
        "is_preferred": result.is_preferred,
        # The preset chosen when the run was started (Phase 6B), if any.
        "preset": json.loads(job.settings_json or "{}").get("preset") if job else None,
        # API image runs (Phase 6C): the size, quality and tokens the provider reported.
        "usage": json.loads(job.settings_json or "{}").get("usage") if job else None,
        # Region edits (Phase 6C-2): the edited result and what the edit asked for.
        "parent_result_id": result.parent_result_id,
        "edit": json.loads(result.edit_json) if result.edit_json else None,
        "mask_url": f"/api/results/{result.id}/mask" if result.edit_json else None,
        "editable": approval is not None
        and approval.invalidated_reason != "You withdrew this approval.",
        "check": check,
        "created_at": result.created_at,
        "image_url": f"/api/results/{result.id}/image/original",
        "thumbnail_url": f"/api/results/{result.id}/image/thumbnail",
        "prompt_version": inputs["prompt"]["version"] if inputs else None,
        "analysis_version": inputs["analysis"]["version"] if inputs else None,
        "is_polished": inputs["prompt"]["is_polished"] if inputs else False,
        "mappings": [
            {
                "subject": m["subject"],
                "action": m["action"],
                "character_name": names.get(m["character_id"]) if m["character_id"] else None,
                "images": [r["image"] for r in m["references"]],
                # Approved subject boxes, for "Use this person's area" in the edit dialog.
                "box": (boxes or {}).get(m["subject"]),
            }
            for m in (inputs["mappings"] if inputs else [])
        ],
    }


def store_result(
    engine,
    settings: Settings,
    payload: bytes,
    *,
    scene_id: str,
    approval_id: str,
    source: str,
    mode: str,
    job_id: str | None = None,
    engine_version: str | None = None,
    note: str = "",
    recovered: bool = False,
    parent_result_id: str | None = None,
    edit: dict | None = None,
) -> str:
    """Save a new result (never replacing one) with the same file journal as uploads.

    Raises HTTPException(422) for a file that is not a usable image.
    """
    extension, media_type, width, height, thumbnail = decode_image(payload, settings)
    identifier = uuid4().hex
    paths = [f"generations/{identifier}.{extension}", f"thumbnails/result-{identifier}.jpg"]
    with writing_session(engine) as session:
        session.add_all(PendingFileDeletion(path=key) for key in paths)
    try:
        with writing_session(engine) as session:
            for key, content in zip(paths, (payload, thumbnail), strict=True):
                with asset_path(settings, key).open("xb") as file:
                    file.write(content)
                    file.flush()
                    os.fsync(file.fileno())
            session.execute(delete(PendingFileDeletion).where(PendingFileDeletion.path.in_(paths)))
            session.add(
                GenerationResult(
                    id=identifier,
                    scene_id=scene_id,
                    approval_id=approval_id,
                    job_id=job_id,
                    version=next_version(session, GenerationResult, scene_id),
                    source=source,
                    mode=mode,
                    note=note,
                    original_path=paths[0],
                    thumbnail_path=paths[1],
                    media_type=media_type,
                    width=width,
                    height=height,
                    content_hash=hashlib.sha256(payload).hexdigest(),
                    engine_version=engine_version,
                    recovered=recovered,
                    parent_result_id=parent_result_id,
                    edit_json=json.dumps(edit) if edit else None,
                    is_preferred=False,
                    created_at=now(),
                )
            )
            scene = session.get(Scene, scene_id)
            if scene is not None:
                scene.updated_at = now()
                refresh_workflow(session, scene)
    except BaseException:
        clean_deleted_files(engine, settings, paths)
        raise
    return identifier


def store_codex_images(engine, settings, job, images: list[Path], recovered=False) -> list[str]:
    """Copy Codex's images into results; a file that does not decode fails the run."""
    mode = (json.loads(job.settings_json or "{}")).get("mode", "generate")
    stored = []
    for path in images:
        try:
            stored.append(
                store_result(
                    engine,
                    settings,
                    read_image_file(path),
                    scene_id=job.scene_id,
                    approval_id=job.input_id,
                    source="codex_cli",
                    mode=mode if mode in MODES else "generate",
                    job_id=job.id,
                    engine_version=job.engine_version,
                    recovered=recovered,
                )
            )
        except HTTPException as error:
            raise EngineError(
                "invalid_output", "Codex saved a file that is not a usable image."
            ) from error
    return stored


def known_hashes(session, job_id: str) -> set[str]:
    return set(
        session.scalars(
            select(GenerationResult.content_hash).where(GenerationResult.job_id == job_id)
        )
    )
