"""Scenes, analyses, prompts, character mapping, approvals and engine jobs (Phases 3-4)."""

import hashlib
import json
import os
from concurrent.futures import ThreadPoolExecutor
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import delete, select
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from backend.analysis_schema import (
    MANUAL_INSTRUCTION,
    SCHEMA_VERSION,
    AnalysisFormatError,
    BoundingBox,
    Subject,
    Uncertainty,
    parse_analysis_text,
    validate_analysis,
)
from backend.configuration import asset_path
from backend.engines import ENGINE_NAMES, engine_status
from backend.jobs import MAX_PROMPT_LENGTH, job_folder_path
from backend.library import clean_deleted_files, decode_image, file_hash
from backend.models import (
    Approval,
    Character,
    CharacterGroup,
    EngineJob,
    EngineSettings,
    PendingFileDeletion,
    PromptVersion,
    Scene,
    SceneAnalysis,
    SubjectMapping,
)
from backend.persistence import writing_session
from backend.prompting import build_prompt, check_prompt, polish_instruction
from backend.scene_store import active_job, latest, next_version, now
from backend.workflow import (
    MAX_REFERENCES,
    add_analysis,
    analysis_of,
    auto_references,
    build_plan,
    character_photos,
    check_approval,
    create_approval,
    current_approval,
    refresh_workflow,
    review,
    save_mappings,
    subjects_fingerprint,
)

router = APIRouter(prefix="/api")
# The polish instruction is passed as one command-line argument; Windows allows ~32,000.
MAX_POLISH_INSTRUCTION = 24_000


def visible(value: str) -> str:
    value = value.strip()
    if not value or any(ord(c) < 32 for c in value):
        raise ValueError("Enter visible text without control characters.")
    return value


class SceneRename(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=120)
    revision: int = Field(ge=1)
    _title = field_validator("title")(visible)


class ManualImport(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(min_length=1, max_length=200_000)


class AnalysisRevision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    analysis: dict
    confirmed_uncertainties: list[Uncertainty] = Field(default_factory=list, max_length=100)


class PromptDraftInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    analysis_id: str = Field(max_length=32)
    scene_changes: str = Field(default="", max_length=4000)


class PromptInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    analysis_id: str | None = Field(default=None, max_length=32)
    mapping_hash: str | None = Field(default=None, max_length=64)
    prompt_text: str = Field(min_length=1, max_length=MAX_PROMPT_LENGTH)
    negative_prompt: str = Field(default="", max_length=8000)
    scene_changes: str = Field(default="", max_length=4000)
    source: Literal["template", "user_edit", "restored"]


class PromptCheckInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    prompt_text: str = Field(max_length=MAX_PROMPT_LENGTH)


class MappingEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")
    label: str = Field(pattern=r"^Subject [0-9]+$", max_length=20)
    action: Literal["replace", "keep", "unresolved"]
    character_id: str | None = Field(default=None, max_length=32)
    # None lets the studio choose a useful subset; a list is the user's own choice.
    reference_ids: list[str] | None = Field(default=None, max_length=MAX_REFERENCES)


class MappingsInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revision: int = Field(ge=1)
    group_id: str | None = Field(default=None, max_length=32)
    mappings: list[MappingEntry] = Field(max_length=20)


class SubjectBoxInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    label: str = Field(pattern=r"^Subject [0-9]+$", max_length=20)
    bounding_box: BoundingBox


class SubjectsInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    analysis_id: str = Field(max_length=32)
    subjects: list[SubjectBoxInput] = Field(max_length=20)


class PolishInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    prompt_id: str = Field(max_length=32)


class PolishedInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    job_id: str = Field(max_length=32)
    prompt_text: str = Field(min_length=1, max_length=MAX_PROMPT_LENGTH)
    accept_warnings: bool = False


class ApproveInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    prompt_id: str = Field(max_length=32)
    accept_warnings: bool = False


class WithdrawInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    approval_id: str = Field(max_length=32)


class EngineSettingsUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    analysis_engine: Literal["claude_cli", "codex_cli", "manual"]
    generation_engine: Literal["codex_cli", "manual"]
    claude_timeout: int = Field(ge=30, le=1800)
    codex_timeout: int = Field(ge=30, le=1800)
    revision: int = Field(ge=1)


def writing(request):
    return writing_session(request.app.state.engine)


def require_scene(session, scene_id) -> Scene:
    scene = session.get(Scene, scene_id)
    if scene is None:
        raise HTTPException(404, "This scene no longer exists. Return to your scenes.")
    return scene


def require_idle(session, scene_id, action: str) -> None:
    if active_job(session, scene_id):
        raise HTTPException(409, f"Wait for the running engine job to finish before {action}.")


def job_data(request, job: EngineJob | None):
    if job is None:
        return None
    return {
        "id": job.id,
        "kind": job.kind,
        "scene_id": job.scene_id,
        "engine": job.engine,
        "engine_name": ENGINE_NAMES.get(job.engine, job.engine),
        "engine_version": job.engine_version,
        "status": job.status,
        "error_kind": job.error_kind,
        "error_details": job.error_details,
        "job_folder": job_folder_path(request.app.state.settings, job),
        "timeout_seconds": job.timeout_seconds,
        "result_id": job.result_id,
        "input_id": job.input_id,
        "decision": job.decision,
        "created_at": job.created_at,
        "started_at": job.started_at,
        "finished_at": job.finished_at,
    }


def analysis_data(analysis: SceneAnalysis):
    return {
        "id": analysis.id,
        "version": analysis.version,
        "schema_version": analysis.schema_version,
        "source": analysis.source,
        "engine_version": analysis.engine_version,
        "has_raw_output": analysis.raw_output_path is not None,
        "based_on_id": analysis.based_on_id,
        "job_id": analysis.job_id,
        "created_at": analysis.created_at,
        "analysis": json.loads(analysis.structured_analysis),
        "confirmed_uncertainties": json.loads(analysis.confirmed_uncertainties),
    }


def prompt_data(prompt: PromptVersion):
    return {
        "id": prompt.id,
        "version": prompt.version,
        "analysis_id": prompt.analysis_id,
        "mapping_hash": prompt.mapping_hash,
        "prompt_text": prompt.prompt_text,
        "negative_prompt": prompt.negative_prompt,
        "scene_changes": prompt.scene_changes,
        "source": prompt.source,
        "is_polished": prompt.is_polished,
        "polished_from_version_id": prompt.polished_from_version_id,
        "engine_version": prompt.engine_version,
        "created_at": prompt.created_at,
    }


def approval_data(approval: Approval):
    snapshot = json.loads(approval.snapshot_json)
    inputs, display = snapshot["inputs"], snapshot["display"]
    names = display.get("character_names", {})
    return {
        "id": approval.id,
        "approved_at": approval.approved_at,
        "invalidated_at": approval.invalidated_at,
        "invalidated_reason": approval.invalidated_reason,
        "snapshot_hash": approval.snapshot_hash,
        "analysis_version": inputs["analysis"]["version"],
        "prompt_version": inputs["prompt"]["version"],
        "is_polished": inputs["prompt"]["is_polished"],
        "mappings": [
            {
                "subject": m["subject"],
                "action": m["action"],
                "character_name": names.get(m["character_id"]) if m["character_id"] else None,
                "images": [r["image"] for r in m["references"]],
            }
            for m in inputs["mappings"]
        ],
    }


def scene_summary(request, session, scene: Scene):
    analysis = latest(session, SceneAnalysis, scene.id)
    prompt = latest(session, PromptVersion, scene.id)
    return {
        "id": scene.id,
        "title": scene.title,
        "workflow_state": scene.workflow_state,
        "width": scene.width,
        "height": scene.height,
        "revision": scene.revision,
        "created_at": scene.created_at,
        "updated_at": scene.updated_at,
        "last_opened_at": scene.last_opened_at,
        "duplicated_from": scene.duplicated_from,
        "thumbnail_url": f"/api/scenes/{scene.id}/image/thumbnail",
        "original_url": f"/api/scenes/{scene.id}/image/original",
        "analysis_version": analysis.version if analysis else None,
        "prompt_version": prompt.version if prompt else None,
        "active_job": job_data(request, active_job(session, scene.id)),
    }


def mapping_detail(session, scene: Scene):
    """Subjects with their assignments, the review checklist and the approval state."""
    result = review(session, scene)
    plan = result.plan
    subjects = []
    if plan is not None:
        described = {s.label: s for s in plan.analysis.subjects}
        for item in plan.subjects:
            subject = described[item.label]
            subjects.append(
                {
                    "label": item.label,
                    "bounding_box": subject.bounding_box.model_dump(),
                    "position": subject.position,
                    "summary": subject.pose_summary or subject.outfit,
                    "action": item.action,
                    "character_id": item.character.id if item.character else None,
                    "reference_ids": [p.id for p in item.photos],
                    "references_auto": item.references_auto,
                    "confirmed": item.confirmed,
                    "images": list(item.images),
                    "problems": item.problems,
                }
            )
    approval, reason = check_approval(session, scene)
    last = session.scalar(
        select(Approval).where(Approval.scene_id == scene.id).order_by(Approval.approved_at.desc())
    )
    prompt = latest(session, PromptVersion, scene.id)
    return {
        "mapping_group_id": scene.mapping_group_id,
        "mapping_hash": plan.mapping_hash if plan else None,
        "subjects": subjects,
        "total_images": plan.total_images if plan else 1,
        "review": {
            "blockers": result.blockers,
            "warnings": result.warnings,
            "notes": result.notes,
            "prompt_id": prompt.id if prompt else None,
        },
        "approval": {
            "state": "approved" if approval is not None and not reason else "none",
            "current": approval_data(approval) if approval is not None and not reason else None,
            # Why the most recent approval stopped applying, if it did.
            "ended_reason": reason
            or (last.invalidated_reason if last is not None and last.invalidated_at else None),
        },
        "approvals": [
            approval_data(a)
            for a in session.scalars(
                select(Approval)
                .where(Approval.scene_id == scene.id)
                .order_by(Approval.approved_at.desc())
                .limit(10)
            )
        ],
    }


def pending_polish(session, scene: Scene, prompt: PromptVersion | None):
    """A finished polish of the current prompt that the user has not decided on yet."""
    job = session.scalar(
        select(EngineJob)
        .where(EngineJob.scene_id == scene.id, EngineJob.kind == "polish")
        .order_by(EngineJob.created_at.desc())
        .limit(1)
    )
    if (
        job is None
        or job.status != "completed"
        or job.decision is not None
        or prompt is None
        or job.input_id != prompt.id
        or not job.output_text
    ):
        return None
    analysis = latest(session, SceneAnalysis, scene.id)
    plan = build_plan(session, scene, analysis) if analysis else None
    missing = check_prompt(job.output_text, plan.assignments, plan.total_images) if plan else []
    return {
        "job_id": job.id,
        "prompt_id": prompt.id,
        "prompt_version": prompt.version,
        "polished_text": job.output_text,
        "engine_version": job.engine_version,
        "missing": missing,
    }


def scene_detail(request, session, scene: Scene):
    data = scene_summary(request, session, scene)
    data["analyses"] = [
        analysis_data(a)
        for a in session.scalars(
            select(SceneAnalysis)
            .where(SceneAnalysis.scene_id == scene.id)
            .order_by(SceneAnalysis.version.desc())
        )
    ]
    prompts = list(
        session.scalars(
            select(PromptVersion)
            .where(PromptVersion.scene_id == scene.id)
            .order_by(PromptVersion.version.desc())
        )
    )
    data["prompts"] = [prompt_data(p) for p in prompts]
    data["jobs"] = [
        job_data(request, j)
        for j in session.scalars(
            select(EngineJob)
            .where(EngineJob.scene_id == scene.id)
            .order_by(EngineJob.created_at.desc())
            .limit(10)
        )
    ]
    data.update(mapping_detail(session, scene))
    data["pending_polish"] = pending_polish(session, scene, prompts[0] if prompts else None)
    return data


@router.get("/scenes")
def scenes(request: Request):
    with Session(request.app.state.engine) as session:
        return [
            scene_summary(request, session, s)
            for s in session.scalars(select(Scene).order_by(Scene.updated_at.desc(), Scene.id))
        ]


def _write_new_files(settings, paths, contents):
    for key, content in zip(paths, contents, strict=True):
        with asset_path(settings, key).open("xb") as file:
            file.write(content)
            file.flush()
            os.fsync(file.fileno())


def store_scene(request, title: str, payload: bytes):
    settings = request.app.state.settings
    extension, media_type, width, height, thumbnail = decode_image(payload, settings)
    identifier = uuid4().hex
    paths = [f"scenes/{identifier}.{extension}", f"thumbnails/scene-{identifier}.jpg"]
    # Journal intended paths first, exactly like reference photos (docs/RECOVERY.md).
    with writing(request) as session:
        session.add_all(PendingFileDeletion(path=key) for key in paths)
    try:
        with writing(request) as session:
            _write_new_files(settings, paths, (payload, thumbnail))
            session.execute(delete(PendingFileDeletion).where(PendingFileDeletion.path.in_(paths)))
            scene = Scene(
                id=identifier,
                title=title,
                original_path=paths[0],
                thumbnail_path=paths[1],
                media_type=media_type,
                width=width,
                height=height,
                content_hash=hashlib.sha256(payload).hexdigest(),
                workflow_state="needs_analysis",
                revision=1,
                created_at=now(),
                updated_at=now(),
                last_opened_at=now(),
            )
            session.add(scene)
            session.flush()
            return scene_detail(request, session, scene)
    except BaseException:
        clean_deleted_files(request.app.state.engine, settings, paths)
        raise


@router.post("/scenes", status_code=201)
async def create_scene(request: Request, title: str = Query(min_length=1, max_length=120)):
    try:
        title = visible(title)
    except ValueError as error:
        raise HTTPException(422, "Give the scene a visible title.") from error
    payload = bytearray()
    limit = request.app.state.settings.max_upload_bytes
    async for chunk in request.stream():
        if len(payload) + len(chunk) > limit:
            raise HTTPException(413, f"Image exceeds the {limit // (1024 * 1024)} MB upload limit.")
        payload.extend(chunk)
    return await run_in_threadpool(store_scene, request, title, bytes(payload))


@router.get("/scenes/{scene_id}")
def scene(request: Request, scene_id: str):
    with Session(request.app.state.engine) as session:
        return scene_detail(request, session, require_scene(session, scene_id))


@router.post("/scenes/{scene_id}/opened")
def scene_opened(request: Request, scene_id: str):
    # Recency for "Resume last scene"; not an edit, so the revision stays.
    with writing(request) as session:
        require_scene(session, scene_id).last_opened_at = now()
    return {"opened": True}


@router.put("/scenes/{scene_id}")
def rename_scene(request: Request, scene_id: str, body: SceneRename):
    with writing(request) as session:
        scene = require_scene(session, scene_id)
        if scene.revision != body.revision:
            raise HTTPException(409, "This scene changed in another window. Reload it first.")
        scene.title = body.title
        scene.revision += 1
        scene.updated_at = now()
        return scene_detail(request, session, scene)


def copy_scene(request, scene_id: str):
    settings = request.app.state.settings
    with Session(request.app.state.engine) as session:
        source = require_scene(session, scene_id)
        payload = asset_path(settings, source.original_path).read_bytes()
        thumbnail = asset_path(settings, source.thumbnail_path).read_bytes()
        extension = source.original_path.rsplit(".", 1)[1]
    identifier = uuid4().hex
    paths = [f"scenes/{identifier}.{extension}", f"thumbnails/scene-{identifier}.jpg"]
    with writing(request) as session:
        session.add_all(PendingFileDeletion(path=key) for key in paths)
    try:
        with writing(request) as session:
            source = require_scene(session, scene_id)
            _write_new_files(settings, paths, (payload, thumbnail))
            session.execute(delete(PendingFileDeletion).where(PendingFileDeletion.path.in_(paths)))
            scene = Scene(
                id=identifier,
                title=f"Copy of {source.title}"[:120],
                original_path=paths[0],
                thumbnail_path=paths[1],
                media_type=source.media_type,
                width=source.width,
                height=source.height,
                content_hash=source.content_hash,
                workflow_state="needs_analysis",
                duplicated_from=source.id,
                mapping_group_id=source.mapping_group_id,
                revision=1,
                created_at=now(),
                updated_at=now(),
                last_opened_at=now(),
            )
            session.add(scene)
            session.flush()
            # Carry over the current analysis, assignments and prompt; history and
            # approvals stay with the original, so the copy needs its own approval.
            analysis = latest(session, SceneAnalysis, source.id)
            copied = None
            if analysis is not None:
                copied = add_analysis(
                    session,
                    scene,
                    analysis_of(analysis),
                    analysis.source,
                    confirmed=json.loads(analysis.confirmed_uncertainties),
                    engine_version=analysis.engine_version,
                )
                for row in session.scalars(
                    select(SubjectMapping).where(SubjectMapping.scene_id == source.id)
                ):
                    session.add(
                        SubjectMapping(
                            id=uuid4().hex,
                            scene_id=scene.id,
                            subject_label=row.subject_label,
                            action=row.action,
                            character_id=row.character_id,
                            reference_ids=row.reference_ids,
                            references_auto=row.references_auto,
                            subjects_hash=row.subjects_hash,
                            updated_at=now(),
                        )
                    )
            prompt = latest(session, PromptVersion, source.id)
            if prompt is not None:
                session.add(
                    PromptVersion(
                        id=uuid4().hex,
                        scene_id=scene.id,
                        analysis_id=copied.id
                        if copied and analysis and prompt.analysis_id == analysis.id
                        else None,
                        version=1,
                        prompt_text=prompt.prompt_text,
                        negative_prompt=prompt.negative_prompt,
                        scene_changes=prompt.scene_changes,
                        source=prompt.source,
                        is_polished=prompt.is_polished,
                        engine_version=prompt.engine_version,
                        mapping_hash=prompt.mapping_hash,
                        created_at=now(),
                    )
                )
            refresh_workflow(session, scene)
            return scene_detail(request, session, scene)
    except BaseException:
        clean_deleted_files(request.app.state.engine, settings, paths)
        raise


@router.post("/scenes/{scene_id}/duplicate", status_code=201)
async def duplicate_scene(request: Request, scene_id: str):
    return await run_in_threadpool(copy_scene, request, scene_id)


@router.delete("/scenes/{scene_id}")
def delete_scene(request: Request, scene_id: str, revision: int = Query(ge=1)):
    with writing(request) as session:
        scene = require_scene(session, scene_id)
        if scene.revision != revision:
            raise HTTPException(409, "This scene changed in another window. Reload it first.")
        if active_job(session, scene_id):
            raise HTTPException(409, "Cancel the running engine job before deleting this scene.")
        paths = [scene.original_path, scene.thumbnail_path, f"jobs/{scene_id}"]
        for path in paths:
            session.merge(PendingFileDeletion(path=path))
        for model in (Approval, SubjectMapping, PromptVersion, SceneAnalysis, EngineJob):
            session.execute(delete(model).where(model.scene_id == scene_id))
        session.delete(scene)
    pending = clean_deleted_files(request.app.state.engine, request.app.state.settings, paths)
    return {"deleted": True, "cleanup_pending": pending}


@router.get("/scenes/{scene_id}/image/{variant}")
def scene_image(request: Request, scene_id: str, variant: Literal["original", "thumbnail"]):
    with Session(request.app.state.engine) as session:
        scene = require_scene(session, scene_id)
        path = asset_path(request.app.state.settings, getattr(scene, f"{variant}_path"))
        if not path.is_file():
            raise HTTPException(404, "The Base Image file is missing. Restore it from a backup.")
        return FileResponse(
            path, media_type=scene.media_type if variant == "original" else "image/jpeg"
        )


@router.get("/analysis/instructions")
def analysis_instructions():
    return {"schema_version": SCHEMA_VERSION, "manual_instruction": MANUAL_INSTRUCTION}


@router.post("/scenes/{scene_id}/analyses", status_code=201)
def import_analysis(request: Request, scene_id: str, body: ManualImport):
    try:
        data = parse_analysis_text(body.text)
    except AnalysisFormatError as error:
        raise HTTPException(422, str(error)) from error
    with writing(request) as session:
        scene = require_scene(session, scene_id)
        add_analysis(session, scene, data, "manual_import")
        return scene_detail(request, session, scene)


@router.post("/scenes/{scene_id}/analyses/{analysis_id}/revise", status_code=201)
def revise_analysis(request: Request, scene_id: str, analysis_id: str, body: AnalysisRevision):
    try:
        data = validate_analysis(body.analysis)
    except AnalysisFormatError as error:
        raise HTTPException(422, str(error)) from error
    with writing(request) as session:
        scene = require_scene(session, scene_id)
        base = session.get(SceneAnalysis, analysis_id)
        if base is None or base.scene_id != scene_id:
            raise HTTPException(404, "That analysis version no longer exists. Reload the scene.")
        add_analysis(
            session,
            scene,
            data,
            "user_edit",
            confirmed=[u.model_dump() for u in body.confirmed_uncertainties],
            engine_version=base.engine_version,
            based_on_id=base.id,
        )
        return scene_detail(request, session, scene)


def _side(box: BoundingBox) -> str:
    centre = box.x + box.width / 2
    return (
        "left of the frame"
        if centre < 0.36
        else "right of the frame"
        if centre > 0.64
        else ("centre of the frame")
    )


@router.put("/scenes/{scene_id}/subjects", status_code=201)
def edit_subjects(request: Request, scene_id: str, body: SubjectsInput):
    """Move, resize, add or remove subject boxes; saved as a new analysis version.

    Labels never renumber, so assignments stay attached to the same person.
    """
    labels = [s.label for s in body.subjects]
    if len(labels) != len(set(labels)):
        raise HTTPException(422, "Each subject needs its own label.")
    for item in body.subjects:
        box = item.bounding_box
        if (
            box.width < 0.01
            or box.height < 0.01
            or box.x + box.width > 1.001
            or (box.y + box.height > 1.001)
        ):
            raise HTTPException(422, f"The box for {item.label} must stay inside the image.")
    with writing(request) as session:
        scene = require_scene(session, scene_id)
        require_idle(session, scene_id, "changing the subjects")
        analysis = latest(session, SceneAnalysis, scene_id)
        if analysis is None or analysis.id != body.analysis_id:
            raise HTTPException(409, "The analysis changed in another window. Reload the scene.")
        data = analysis_of(analysis)
        existing = {s.label: s for s in data.subjects}
        subjects = []
        for item in body.subjects:
            if item.label in existing:
                subjects.append(
                    existing[item.label].model_copy(update={"bounding_box": item.bounding_box})
                )
            else:
                blank = {
                    key: "" for key in Subject.model_fields if key not in ("label", "bounding_box")
                }
                subjects.append(
                    Subject(
                        **{
                            **blank,
                            "label": item.label,
                            "bounding_box": item.bounding_box,
                            "position": _side(item.bounding_box),
                        }
                    )
                )
        subjects.sort(key=lambda s: int(s.label.split()[1]))
        old_fingerprint = subjects_fingerprint(data)
        updated = validate_analysis(
            {**data.model_dump(), "subjects": [s.model_dump() for s in subjects]}
        )
        if subjects_fingerprint(updated) == old_fingerprint:
            return scene_detail(request, session, scene)
        add_analysis(
            session,
            scene,
            updated,
            "user_edit",
            confirmed=json.loads(analysis.confirmed_uncertainties),
            engine_version=analysis.engine_version,
            based_on_id=analysis.id,
        )
        # The user moved the boxes themselves, so assignments they had confirmed still hold.
        fingerprint = subjects_fingerprint(updated)
        for row in session.scalars(
            select(SubjectMapping).where(SubjectMapping.scene_id == scene_id)
        ):
            if row.subject_label not in labels:
                session.delete(row)
            elif row.subjects_hash == old_fingerprint:
                row.subjects_hash = fingerprint
        refresh_workflow(session, scene)
        return scene_detail(request, session, scene)


@router.put("/scenes/{scene_id}/mappings")
def save_scene_mappings(request: Request, scene_id: str, body: MappingsInput):
    with writing(request) as session:
        scene = require_scene(session, scene_id)
        if scene.revision != body.revision:
            raise HTTPException(409, "This scene changed in another window. Reload it first.")
        require_idle(session, scene_id, "changing assignments")
        analysis = latest(session, SceneAnalysis, scene_id)
        if analysis is None:
            raise HTTPException(409, "Analyse the scene before assigning characters.")
        if body.group_id and session.get(CharacterGroup, body.group_id) is None:
            raise HTTPException(404, "That group no longer exists. Reload the scene.")
        data = analysis_of(analysis)
        subjects = {s.label: s for s in data.subjects}
        previous = {
            m.subject_label: m.character_id
            for m in session.scalars(
                select(SubjectMapping).where(SubjectMapping.scene_id == scene_id)
            )
        }
        entries, used = [], {}
        for entry in body.mappings:
            if entry.label not in subjects:
                raise HTTPException(422, f"{entry.label} is not in the current analysis. Reload.")
            if any(e["label"] == entry.label for e in entries):
                raise HTTPException(422, f"{entry.label} appears twice.")
            if entry.action != "replace":
                entries.append({"label": entry.label, "action": entry.action})
                continue
            character = session.get(Character, entry.character_id) if entry.character_id else None
            if character is None:
                raise HTTPException(
                    422 if not entry.character_id else 404,
                    f"Choose a character for {entry.label}."
                    if not entry.character_id
                    else "That character no longer exists. Reload the scene.",
                )
            if character.archived and previous.get(entry.label) != character.id:
                raise HTTPException(
                    409, f"Restore {character.name} in Characters before assigning."
                )
            if character.id in used:
                raise HTTPException(
                    422,
                    f"{character.name} is already assigned to {used[character.id]}. Each "
                    "character can appear only once in a scene.",
                )
            used[character.id] = entry.label
            photos = character_photos(session, character.id)
            if not photos:
                raise HTTPException(
                    422, f"{character.name} has no reference photos yet. Add one in Characters."
                )
            if entry.reference_ids is None:
                references = auto_references(
                    photos, character.primary_photo_id, subjects[entry.label].facial_viewing_angle
                )
            else:
                references = entry.reference_ids
                owned = {p.id for p in photos}
                if (
                    not references
                    or len(set(references)) != len(references)
                    or not set(references) <= owned
                ):
                    raise HTTPException(
                        422, f"Choose 1 to {MAX_REFERENCES} reference photos of {character.name}."
                    )
            entries.append(
                {
                    "label": entry.label,
                    "action": "replace",
                    "character_id": character.id,
                    "reference_ids": references,
                    "references_auto": entry.reference_ids is None,
                }
            )
        save_mappings(session, scene, subjects_fingerprint(data), entries)
        scene.mapping_group_id = body.group_id
        scene.revision += 1
        scene.updated_at = now()
        refresh_workflow(session, scene)
        return scene_detail(request, session, scene)


@router.post("/scenes/{scene_id}/analyse", status_code=202)
def analyse_scene(request: Request, scene_id: str):
    with writing(request) as session:
        scene = require_scene(session, scene_id)
        settings = session.get(EngineSettings, 1)
        engine = settings.analysis_engine
        if engine == "manual":
            raise HTTPException(
                409, "Manual analysis is selected in Studio settings. Use Do it manually."
            )
        if active_job(session, scene_id):
            raise HTTPException(409, "An engine job is already running for this scene.")
        session.add(
            EngineJob(
                id=uuid4().hex,
                kind="analysis",
                scene_id=scene_id,
                engine=engine,
                status="not_started",
                timeout_seconds=settings.claude_timeout
                if engine == "claude_cli"
                else settings.codex_timeout,
                created_at=now(),
            )
        )
        session.flush()
        refresh_workflow(session, scene)
        result = scene_detail(request, session, scene)
    request.app.state.runner.notify()
    return result


@router.get("/jobs/{job_id}")
def job(request: Request, job_id: str):
    with Session(request.app.state.engine) as session:
        item = session.get(EngineJob, job_id)
        if item is None:
            raise HTTPException(404, "This run no longer exists.")
        return job_data(request, item)


@router.post("/jobs/{job_id}/cancel")
def cancel_job(request: Request, job_id: str):
    with Session(request.app.state.engine) as session:
        if session.get(EngineJob, job_id) is None:
            raise HTTPException(404, "This run no longer exists.")
    request.app.state.runner.cancel(job_id)
    with Session(request.app.state.engine) as session:
        return job_data(request, session.get(EngineJob, job_id))


def _current_plan(session, scene):
    analysis = latest(session, SceneAnalysis, scene.id)
    return build_plan(session, scene, analysis) if analysis else None


@router.post("/scenes/{scene_id}/prompts/draft")
def draft_prompt(request: Request, scene_id: str, body: PromptDraftInput):
    with Session(request.app.state.engine) as session:
        scene = require_scene(session, scene_id)
        analysis = session.get(SceneAnalysis, body.analysis_id)
        if analysis is None or analysis.scene_id != scene_id:
            raise HTTPException(404, "That analysis version no longer exists. Reload the scene.")
        plan = build_plan(session, scene, analysis)
    prompt, negative = build_prompt(plan.analysis, body.scene_changes, plan.assignments)
    return {"prompt_text": prompt, "negative_prompt": negative, "mapping_hash": plan.mapping_hash}


@router.post("/scenes/{scene_id}/prompts/check")
def check_scene_prompt(request: Request, scene_id: str, body: PromptCheckInput):
    with Session(request.app.state.engine) as session:
        plan = _current_plan(session, require_scene(session, scene_id))
    if plan is None:
        return {"missing": []}
    return {"missing": check_prompt(body.prompt_text, plan.assignments, plan.total_images)}


@router.post("/scenes/{scene_id}/prompts", status_code=201)
def save_prompt(request: Request, scene_id: str, body: PromptInput):
    with writing(request) as session:
        scene = require_scene(session, scene_id)
        if body.analysis_id is not None:
            analysis = session.get(SceneAnalysis, body.analysis_id)
            if analysis is None or analysis.scene_id != scene_id:
                raise HTTPException(404, "That analysis version no longer exists.")
        session.add(
            PromptVersion(
                id=uuid4().hex,
                scene_id=scene_id,
                analysis_id=body.analysis_id,
                mapping_hash=body.mapping_hash,
                version=next_version(session, PromptVersion, scene_id),
                prompt_text=body.prompt_text,
                negative_prompt=body.negative_prompt,
                scene_changes=body.scene_changes,
                source=body.source,
                is_polished=False,
                created_at=now(),
            )
        )
        session.flush()
        scene.updated_at = now()
        refresh_workflow(session, scene)
        return scene_detail(request, session, scene)


@router.post("/scenes/{scene_id}/polish", status_code=202)
def polish_prompt(request: Request, scene_id: str, body: PolishInput):
    """Queue one Claude run that rewrites the saved prompt; nothing changes until accepted."""
    with writing(request) as session:
        scene = require_scene(session, scene_id)
        require_idle(session, scene_id, "polishing")
        prompt = latest(session, PromptVersion, scene_id)
        if prompt is None or prompt.id != body.prompt_id:
            raise HTTPException(409, "Save your prompt first, then polish the saved version.")
        analysis = session.get(SceneAnalysis, prompt.analysis_id) if prompt.analysis_id else None
        analysis = analysis or latest(session, SceneAnalysis, scene_id)
        if analysis is None:
            raise HTTPException(409, "Analyse the scene before polishing its prompt.")
        if len(polish_instruction(prompt.prompt_text, analysis_of(analysis))) > (
            MAX_POLISH_INSTRUCTION
        ):
            raise HTTPException(
                422,
                "This prompt is too long to polish in one run. Shorten it or edit it by hand.",
            )
        settings = session.get(EngineSettings, 1)
        session.add(
            EngineJob(
                id=uuid4().hex,
                kind="polish",
                scene_id=scene_id,
                engine="claude_cli",
                status="not_started",
                input_id=prompt.id,
                timeout_seconds=settings.claude_timeout,
                created_at=now(),
            )
        )
        session.flush()
        refresh_workflow(session, scene)
        result = scene_detail(request, session, scene)
    request.app.state.runner.notify()
    return result


def _polish_job(session, scene_id, job_id) -> EngineJob:
    job = session.get(EngineJob, job_id)
    if (
        job is None
        or job.scene_id != scene_id
        or job.kind != "polish"
        or job.status != "completed"
        or job.decision is not None
    ):
        raise HTTPException(409, "This polished prompt is no longer available. Reload the scene.")
    return job


@router.post("/scenes/{scene_id}/prompts/polished", status_code=201)
def use_polished(request: Request, scene_id: str, body: PolishedInput):
    with writing(request) as session:
        scene = require_scene(session, scene_id)
        job = _polish_job(session, scene_id, body.job_id)
        original = latest(session, PromptVersion, scene_id)
        if original is None or job.input_id != original.id:
            raise HTTPException(
                409, "The prompt changed after it was polished. Polish it again if you want to."
            )
        plan = _current_plan(session, scene)
        missing = (
            check_prompt(body.prompt_text, plan.assignments, plan.total_images) if plan else []
        )
        if missing and not body.accept_warnings:
            raise HTTPException(
                409,
                "The polished prompt is missing required elements: "
                + " ".join(missing)
                + " Keep the original, fix it by hand, or confirm that you want it anyway.",
            )
        session.add(
            PromptVersion(
                id=uuid4().hex,
                scene_id=scene_id,
                analysis_id=original.analysis_id,
                mapping_hash=original.mapping_hash,
                version=next_version(session, PromptVersion, scene_id),
                prompt_text=body.prompt_text,
                negative_prompt=original.negative_prompt,
                scene_changes=original.scene_changes,
                source="polished" if body.prompt_text == job.output_text else "user_edit",
                is_polished=True,
                polished_from_version_id=original.id,
                engine_version=job.engine_version,
                created_at=now(),
            )
        )
        job.decision = "used"
        scene.updated_at = now()
        refresh_workflow(session, scene)
        return scene_detail(request, session, scene)


@router.post("/scenes/{scene_id}/prompts/polished/{job_id}/keep-original")
def keep_original(request: Request, scene_id: str, job_id: str):
    with writing(request) as session:
        scene = require_scene(session, scene_id)
        _polish_job(session, scene_id, job_id).decision = "kept"
        return scene_detail(request, session, scene)


def approve_scene_inputs(request, scene_id: str, body: ApproveInput):
    settings = request.app.state.settings
    with writing(request) as session:
        scene = require_scene(session, scene_id)
        result = review(session, scene)
        if result.blockers:
            raise HTTPException(409, result.blockers[0])
        prompt = latest(session, PromptVersion, scene_id)
        if prompt.id != body.prompt_id:
            raise HTTPException(409, "The prompt changed. Review the latest version, then approve.")
        if result.warnings and not body.accept_warnings:
            raise HTTPException(409, "Read the warnings and confirm that you checked them.")
        # Approve what is really on disk: the files must still match their recorded hashes.
        if file_hash(asset_path(settings, scene.original_path)) != scene.content_hash:
            raise HTTPException(
                409, "The Base Image file is missing or changed. Restore it from a backup."
            )
        for subject in result.plan.subjects:
            for photo in subject.photos:
                actual = file_hash(asset_path(settings, photo.original_path))
                if actual is None or (photo.content_hash and actual != photo.content_hash):
                    raise HTTPException(
                        409,
                        f"A reference photo of {subject.character.name} is missing or changed. "
                        "Restore it or choose other photos.",
                    )
                photo.content_hash = actual
        create_approval(session, scene)
        refresh_workflow(session, scene)
        return scene_detail(request, session, scene)


@router.post("/scenes/{scene_id}/approve", status_code=201)
async def approve_scene(request: Request, scene_id: str, body: ApproveInput):
    return await run_in_threadpool(approve_scene_inputs, request, scene_id, body)


@router.post("/scenes/{scene_id}/approval/withdraw")
def withdraw_approval(request: Request, scene_id: str, body: WithdrawInput):
    with writing(request) as session:
        scene = require_scene(session, scene_id)
        approval = current_approval(session, scene_id)
        if approval is None or approval.id != body.approval_id:
            raise HTTPException(409, "This approval is no longer active. Reload the scene.")
        approval.invalidated_at = now()
        approval.invalidated_reason = "You withdrew this approval."
        refresh_workflow(session, scene)
        return scene_detail(request, session, scene)


def settings_data(item: EngineSettings):
    return {
        "analysis_engine": item.analysis_engine,
        "generation_engine": item.generation_engine,
        "claude_timeout": item.claude_timeout,
        "codex_timeout": item.codex_timeout,
        "revision": item.revision,
    }


@router.get("/engines/settings")
def engine_settings(request: Request):
    with Session(request.app.state.engine) as session:
        return settings_data(session.get(EngineSettings, 1))


@router.put("/engines/settings")
def save_engine_settings(request: Request, body: EngineSettingsUpdate):
    with writing(request) as session:
        item = session.get(EngineSettings, 1)
        if item.revision != body.revision:
            raise HTTPException(409, "Engine settings changed in another window. Reload first.")
        for key, value in body.model_dump(exclude={"revision"}).items():
            setattr(item, key, value)
        item.revision += 1
        return settings_data(item)


@router.get("/engines/status")
async def engines_status(request: Request):
    overrides = request.app.state.settings.engine_commands

    def check():
        with ThreadPoolExecutor(max_workers=2) as pool:
            return list(pool.map(lambda e: engine_status(e, overrides), ENGINE_NAMES))

    return await run_in_threadpool(check)
