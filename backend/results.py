"""Generate, manual export and import, and the results gallery (PLAN.md Phase 5, §14).

Generate and Export both start from a valid approval (`require_valid_approval`), checked
in the same transaction that records the job. Results are never overwritten; each keeps
the approval it was made from, so its exact inputs stay readable after later edits.
"""

import hashlib
import json
import re
import zipfile
from typing import Annotated, Literal
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.background import BackgroundTask
from starlette.concurrency import run_in_threadpool

from backend.configuration import asset_path
from backend.engines import EngineError
from backend.generation import (
    MAX_GENERATION_INSTRUCTION,
    MODES,
    PackageError,
    generation_instruction,
    known_hashes,
    prepare_export_folder,
    read_image_file,
    read_run,
    result_data,
    saved_images,
    snapshot_of,
    store_result,
)
from backend.library import clean_deleted_files
from backend.models import (
    Approval,
    EngineJob,
    EngineSettings,
    GenerationResult,
    PendingFileDeletion,
    Scene,
)
from backend.scene_store import now
from backend.scenes import RECOVERABLE, require_idle, require_scene, scene_detail, visible, writing
from backend.workflow import (
    ApprovalError,
    current_approval,
    refresh_workflow,
    require_valid_approval,
)

router = APIRouter(prefix="/api")


class GenerateInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    approval_id: str = Field(max_length=32)
    mode: Literal["generate", "variation"] = "generate"


class ExportInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    approval_id: str = Field(max_length=32)


class PreferredInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    preferred: bool


def approved(session, scene: Scene, approval_id: str) -> Approval:
    """The valid approval the page was showing; anything else is refused."""
    try:
        approval = require_valid_approval(session, scene)
    except ApprovalError as error:
        raise HTTPException(409, str(error)) from error
    if approval.id != approval_id:
        raise HTTPException(409, "The approval changed in another window. Reload the scene.")
    return approval


@router.post("/scenes/{scene_id}/generate", status_code=202)
def generate(request: Request, scene_id: str, body: GenerateInput):
    """Queue one Codex image run. Runs once; never retried or repeated automatically."""
    with writing(request) as session:
        scene = require_scene(session, scene_id)
        settings = session.get(EngineSettings, 1)
        if settings.generation_engine != "codex_cli":
            raise HTTPException(
                409,
                "Manual generation is selected in Studio settings. Use Export for manual use, "
                "or choose Codex in Studio settings.",
            )
        require_idle(session, scene_id, "generating")
        approval = approved(session, scene, body.approval_id)
        instruction = generation_instruction(snapshot_of(approval)["inputs"], body.mode)
        if len(instruction) > MAX_GENERATION_INSTRUCTION:
            raise HTTPException(
                422,
                "This prompt is too long to send to Codex in one run. Shorten it, or use "
                "Export for manual use.",
            )
        session.add(
            EngineJob(
                id=uuid4().hex,
                kind="generation",
                scene_id=scene_id,
                engine="codex_cli",
                status="not_started",
                input_id=approval.id,
                settings_json=json.dumps({"mode": body.mode}),
                timeout_seconds=settings.codex_timeout,
                created_at=now(),
            )
        )
        session.flush()
        refresh_workflow(session, scene)
        result = scene_detail(request, session, scene)
    request.app.state.runner.notify()
    return result


def create_export(request, scene_id: str, body: ExportInput):
    settings = request.app.state.settings
    with writing(request) as session:
        scene = require_scene(session, scene_id)
        approval = approved(session, scene, body.approval_id)
        try:
            folder, _number = prepare_export_folder(settings, session, scene, approval)
        except PackageError as error:
            raise HTTPException(409, str(error)) from error
        stamp = now()
        job = EngineJob(
            id=uuid4().hex,
            kind="export",
            scene_id=scene_id,
            engine="manual",
            status="completed",
            input_id=approval.id,
            job_folder=folder,
            timeout_seconds=0,
            created_at=stamp,
            started_at=stamp,
            finished_at=stamp,
        )
        session.add(job)
        session.flush()
        return {"export_id": job.id, "scene": scene_detail(request, session, scene)}


@router.post("/scenes/{scene_id}/exports", status_code=201)
async def export_package(request: Request, scene_id: str, body: ExportInput):
    """Manual bridge (PLAN.md §12.2): the same files Generate would send, for any app."""
    return await run_in_threadpool(create_export, request, scene_id, body)


@router.get("/exports/{export_id}/package")
def export_download(request: Request, export_id: str):
    with Session(request.app.state.engine) as session:
        job = session.get(EngineJob, export_id)
        if job is None or job.kind != "export":
            raise HTTPException(404, "This package no longer exists.")
        scene = require_scene(session, job.scene_id)
        path = asset_path(request.app.state.settings, f"{job.job_folder}/package.zip")
        if not path.is_file():
            raise HTTPException(404, "The package file is missing. Export a new package.")
        title = re.sub(r"[^\w .-]+", "", scene.title).strip()[:60] or "Scene"
        number = job.job_folder.rsplit("-", 1)[1]
        return FileResponse(
            path, media_type="application/zip", filename=f"{title} - package {number}.zip"
        )


def import_upload(request, scene_id: str, export_id: str | None, note: str, payload: bytes):
    engine, settings = request.app.state.engine, request.app.state.settings
    with Session(engine) as session:
        scene = require_scene(session, scene_id)
        if export_id:
            job = session.get(EngineJob, export_id)
            if job is None or job.kind != "export" or job.scene_id != scene_id:
                raise HTTPException(404, "That package no longer exists. Reload the scene.")
            # Linked to the inputs that were exported, even if that approval has since ended.
            approval_id = job.input_id
        else:
            try:
                approval_id = require_valid_approval(session, scene).id
            except ApprovalError as error:
                raise HTTPException(
                    409,
                    f"{error} A result must be linked to approved inputs: choose the package "
                    "you used, or approve the scene first.",
                ) from error
    try:
        store_result(
            engine,
            settings,
            payload,
            scene_id=scene_id,
            approval_id=approval_id,
            source="manual_import",
            mode="import",
            job_id=export_id or None,
            note=note,
        )
    except HTTPException as error:
        if error.status_code == 422:
            raise HTTPException(
                422, "This image is damaged or unsupported. Choose a JPEG, PNG or WebP image."
            ) from error
        raise
    with Session(engine) as session:
        return scene_detail(request, session, require_scene(session, scene_id))


@router.post("/scenes/{scene_id}/results", status_code=201)
async def import_result(
    request: Request,
    scene_id: str,
    export_id: str | None = Query(default=None, max_length=32),
    note: str = Query(default="", max_length=120),
):
    """Import an image made elsewhere; it is linked to its package and approval."""
    if note:
        try:
            note = visible(note)
        except ValueError as error:
            raise HTTPException(422, "Describe the app without control characters.") from error
    payload = bytearray()
    limit = request.app.state.settings.max_upload_bytes
    async for chunk in request.stream():
        if len(payload) + len(chunk) > limit:
            raise HTTPException(413, f"Image exceeds the {limit // (1024 * 1024)} MB upload limit.")
        payload.extend(chunk)
    return await run_in_threadpool(
        import_upload, request, scene_id, export_id, note, bytes(payload)
    )


@router.post("/jobs/{job_id}/recover")
def recover_images(request: Request, job_id: str):
    """Look for images an unfinished Codex run saved in its own folder. Nothing is resent."""
    engine, settings = request.app.state.engine, request.app.state.settings
    with Session(engine) as session:
        job = session.get(EngineJob, job_id)
        if job is None or job.kind != "generation":
            raise HTTPException(404, "This run no longer exists.")
        if job.status not in RECOVERABLE or not job.job_folder:
            raise HTTPException(409, "Only unfinished generation runs can be checked.")
        folder = asset_path(settings, job.job_folder)
        thread_id = job.provider_request_id or read_run(folder).thread_id
        known = known_hashes(session, job.id)
        mode = json.loads(job.settings_json or "{}").get("mode", "generate")
        session.expunge(job)
    found = 0
    for path in saved_images(thread_id):
        try:
            payload = read_image_file(path)
        except (EngineError, OSError):
            continue
        if hashlib.sha256(payload).hexdigest() in known:
            continue
        try:
            store_result(
                engine,
                settings,
                payload,
                scene_id=job.scene_id,
                approval_id=job.input_id,
                source="codex_cli",
                mode=mode if mode in MODES else "generate",
                job_id=job.id,
                engine_version=job.engine_version,
                recovered=True,
            )
        except HTTPException:
            continue
        found += 1
    with writing(request) as session:
        job = session.get(EngineJob, job_id)
        if thread_id and not job.provider_request_id:
            job.provider_request_id = thread_id
        if found and job.result_id is None:
            job.result_id = session.scalar(
                select(GenerationResult.id)
                .where(GenerationResult.job_id == job_id)
                .order_by(GenerationResult.version)
                .limit(1)
            )
        scene = require_scene(session, job.scene_id)
        return {"found": found, "scene": scene_detail(request, session, scene)}


def require_result(session, result_id) -> GenerationResult:
    result = session.get(GenerationResult, result_id)
    if result is None:
        raise HTTPException(404, "This result no longer exists. Reload the page.")
    return result


@router.get("/results")
def results(request: Request):
    with Session(request.app.state.engine) as session:
        items = []
        current = {}
        for result in session.scalars(
            select(GenerationResult).order_by(GenerationResult.created_at.desc()).limit(500)
        ):
            scene = session.get(Scene, result.scene_id)
            if result.scene_id not in current:
                approval = current_approval(session, result.scene_id)
                current[result.scene_id] = approval.id if approval else None
            data = result_data(
                result,
                session.get(Approval, result.approval_id),
                current[result.scene_id],
                session.get(EngineJob, result.job_id) if result.job_id else None,
            )
            data["scene_title"] = scene.title
            data["scene_image_url"] = f"/api/scenes/{scene.id}/image/original"
            data["scene_width"], data["scene_height"] = scene.width, scene.height
            items.append(data)
        return items


@router.get("/results/{result_id}/image/{variant}")
def result_image(request: Request, result_id: str, variant: Literal["original", "thumbnail"]):
    with Session(request.app.state.engine) as session:
        result = require_result(session, result_id)
        path = asset_path(request.app.state.settings, getattr(result, f"{variant}_path"))
        if not path.is_file():
            raise HTTPException(404, "The result file is missing. Restore it from a backup.")
        return FileResponse(
            path, media_type=result.media_type if variant == "original" else "image/jpeg"
        )


@router.put("/results/{result_id}/preferred")
def set_preferred(request: Request, result_id: str, body: PreferredInput):
    """A favourite mark; a scene may have several preferred results (user's choice)."""
    with writing(request) as session:
        result = require_result(session, result_id)
        result.is_preferred = body.preferred
        return scene_detail(request, session, require_scene(session, result.scene_id))


def download_name(scene_title: str, version: int, path: str) -> str:
    title = re.sub(r"[^\w .-]+", "", scene_title).strip()[:60] or "Scene"
    return f"{title} - result {version}.{path.rsplit('.', 1)[1]}"


@router.get("/results/download")
def download_results(request: Request, id: Annotated[list[str], Query(max_length=200)]):
    """Several results in one zip (one image downloads directly from its own address)."""
    settings = request.app.state.settings
    folder = asset_path(settings, "exports")
    folder.mkdir(exist_ok=True)
    target = folder / f"results-{uuid4().hex}.zip"
    try:
        with Session(request.app.state.engine) as session, zipfile.ZipFile(target, "w") as archive:
            used = set()
            for result_id in dict.fromkeys(id):
                result = require_result(session, result_id)
                scene = session.get(Scene, result.scene_id)
                title = scene.title if scene else "Scene"
                name = download_name(title, result.version, result.original_path)
                stem, number = name, 2
                while name in used:
                    name = stem.replace(" - result", f" ({number}) - result", 1)
                    number += 1
                used.add(name)
                archive.write(asset_path(settings, result.original_path), name)
    except BaseException:
        target.unlink(missing_ok=True)
        raise
    return FileResponse(
        target,
        media_type="application/zip",
        filename="Character Studio results.zip",
        background=BackgroundTask(target.unlink, missing_ok=True),
    )


@router.delete("/results/{result_id}")
def delete_result(request: Request, result_id: str):
    with writing(request) as session:
        result = require_result(session, result_id)
        scene_id = result.scene_id
        paths = [result.original_path, result.thumbnail_path]
        for path in paths:
            session.merge(PendingFileDeletion(path=path))
        session.delete(result)
        session.flush()
        refresh_workflow(session, require_scene(session, scene_id))
    pending = clean_deleted_files(request.app.state.engine, request.app.state.settings, paths)
    with Session(request.app.state.engine) as session:
        return {
            "cleanup_pending": pending,
            "scene": scene_detail(request, session, require_scene(session, scene_id)),
        }
