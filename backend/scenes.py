"""Scenes, versioned analyses and prompts, engine jobs and engine settings (Phase 3)."""

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
    Uncertainty,
    parse_analysis_text,
    validate_analysis,
)
from backend.configuration import asset_path
from backend.engines import ENGINE_NAMES, engine_status
from backend.jobs import job_folder_path
from backend.library import clean_deleted_files, decode_image
from backend.models import (
    EngineJob,
    EngineSettings,
    PendingFileDeletion,
    PromptVersion,
    Scene,
    SceneAnalysis,
)
from backend.persistence import writing_session
from backend.prompting import build_prompt
from backend.scene_store import (
    active_job,
    add_analysis,
    latest,
    next_version,
    now,
    refresh_workflow,
)

router = APIRouter(prefix="/api")


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
    prompt_text: str = Field(min_length=1, max_length=40_000)
    negative_prompt: str = Field(default="", max_length=8000)
    scene_changes: str = Field(default="", max_length=4000)
    source: Literal["template", "user_edit", "restored"]


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
        "prompt_text": prompt.prompt_text,
        "negative_prompt": prompt.negative_prompt,
        "scene_changes": prompt.scene_changes,
        "source": prompt.source,
        "is_polished": prompt.is_polished,
        "created_at": prompt.created_at,
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
    data["prompts"] = [
        prompt_data(p)
        for p in session.scalars(
            select(PromptVersion)
            .where(PromptVersion.scene_id == scene.id)
            .order_by(PromptVersion.version.desc())
        )
    ]
    data["jobs"] = [
        job_data(request, j)
        for j in session.scalars(
            select(EngineJob)
            .where(EngineJob.scene_id == scene.id)
            .order_by(EngineJob.created_at.desc())
            .limit(10)
        )
    ]
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
                revision=1,
                created_at=now(),
                updated_at=now(),
                last_opened_at=now(),
            )
            session.add(scene)
            session.flush()
            # Carry over the current analysis and prompt; history stays with the original.
            analysis = latest(session, SceneAnalysis, source.id)
            copied = None
            if analysis is not None:
                copied = add_analysis(
                    session,
                    scene,
                    validate_analysis(json.loads(analysis.structured_analysis)),
                    analysis.source,
                    confirmed=json.loads(analysis.confirmed_uncertainties),
                    engine_version=analysis.engine_version,
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
                        created_at=now(),
                    )
                )
                session.flush()
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
            raise HTTPException(409, "Cancel the running analysis before deleting this scene.")
        paths = [scene.original_path, scene.thumbnail_path, f"jobs/{scene_id}"]
        for path in paths:
            session.merge(PendingFileDeletion(path=path))
        for model in (PromptVersion, SceneAnalysis, EngineJob):
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
            raise HTTPException(409, "An analysis is already running for this scene.")
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


@router.post("/scenes/{scene_id}/prompts/draft")
def draft_prompt(request: Request, scene_id: str, body: PromptDraftInput):
    with Session(request.app.state.engine) as session:
        require_scene(session, scene_id)
        analysis = session.get(SceneAnalysis, body.analysis_id)
        if analysis is None or analysis.scene_id != scene_id:
            raise HTTPException(404, "That analysis version no longer exists. Reload the scene.")
        data = validate_analysis(json.loads(analysis.structured_analysis))
    prompt, negative = build_prompt(data, body.scene_changes)
    return {"prompt_text": prompt, "negative_prompt": negative}


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
