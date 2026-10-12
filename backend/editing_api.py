"""Region edits of a result: options, queuing, the mask and recovery (Phase 6C-2, D027).

An edit is an engine job of kind `edit` with the edited result's id in `input_id`. It is
queued only after the same checks as a generation (an idle scene, a usable engine, the
user's charge confirmation for API engines), runs once and is never retried.
"""

import json
from pathlib import Path
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.api_engines import API_ENGINES, charge_confirmation, chosen_model, engine_timeout
from backend.configuration import Settings, asset_path
from backend.editing import (
    EDIT_OPTIONS,
    MAX_INSTRUCTION,
    EditOption,
    finish_edit,
    flux_poll_once,
    mask_box,
    read_mask,
    replaceable,
    usable_approval,
)
from backend.engines import EngineError
from backend.generation import read_image_file, saved_images, snapshot_of, store_result
from backend.image_api import IMAGE_ENGINES, options_for
from backend.keystore import key_info, load_key
from backend.models import EngineJob, EngineSettings, GenerationResult
from backend.scene_store import now
from backend.scenes import require_idle, require_scene, scene_detail, writing
from backend.workflow import refresh_workflow

router = APIRouter(prefix="/api")
MAX_MASK_TEXT = 40 * 1024 * 1024


class EditInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["fix", "replace"]
    option: Literal["codex_cli", "openai_api", "gemini_api", "flux_fill", "flux_3"]
    subject: str | None = Field(default=None, max_length=20)
    instruction: str = Field(default="", max_length=MAX_INSTRUCTION)
    # The marked area as a PNG (white = change), the result's size, base64 or a data URL.
    mask: str = Field(min_length=10, max_length=MAX_MASK_TEXT)
    # API engines only: the user confirmed that this edit may be charged.
    confirm_charges: bool = False


def option_state(settings: Settings, row: EngineSettings, option: EditOption) -> dict:
    """Whether an engine can edit now, the model it would use and why not."""
    model, reason = option.model, None
    if option.engine in API_ENGINES:
        if not key_info(settings, option.engine)["saved"]:
            reason = f"Add a {API_ENGINES[option.engine].name} key in Studio settings first."
        elif option.engine in IMAGE_ENGINES:
            model = chosen_model(row, option.engine, "generation")
            if model is None:
                reason = (
                    f"Choose an image model for {option.name} in Studio settings "
                    "(Generation engine) first."
                )
    options = options_for(row, option.engine) if option.engine in IMAGE_ENGINES else {}
    return {
        "id": option.id,
        "name": option.name,
        "engine": option.engine,
        "company": API_ENGINES[option.engine].company if option.charged else "OpenAI",
        "kinds": list(option.kinds),
        "area": option.area,
        "charged": option.charged,
        "model": model,
        "options": options,
        "available": reason is None,
        "reason": reason,
    }


@router.get("/edit-options")
def edit_options(request: Request):
    with Session(request.app.state.engine) as session:
        row = session.get(EngineSettings, 1)
        return [option_state(request.app.state.settings, row, o) for o in EDIT_OPTIONS.values()]


@router.post("/results/{result_id}/edit", status_code=202)
def edit_result(request: Request, result_id: str, body: EditInput):
    """Queue one region edit of a result. Runs once; never retried or repeated."""
    settings = request.app.state.settings
    option = EDIT_OPTIONS[body.option]
    with writing(request) as session:
        result = session.get(GenerationResult, result_id)
        if result is None:
            raise HTTPException(404, "This result no longer exists. Reload the page.")
        scene = require_scene(session, result.scene_id)
        require_idle(session, scene.id, "editing")
        try:
            approval = usable_approval(session, result)
        except ValueError as error:
            raise HTTPException(409, str(error)) from error
        if body.kind not in option.kinds:
            raise HTTPException(
                422, f"{option.name} cannot replace a person: it takes no reference photos."
            )
        row = session.get(EngineSettings, 1)
        state = option_state(settings, row, option)
        if not state["available"]:
            raise HTTPException(409, state["reason"])
        instruction = " ".join(body.instruction.split())
        subject = None
        if body.kind == "replace":
            subject = body.subject
            if subject not in replaceable(snapshot_of(approval)["inputs"]):
                raise HTTPException(
                    422, "Choose a person who was replaced with approved reference photos."
                )
        elif len(instruction) < 3:
            raise HTTPException(422, "Describe the change for the marked area.")
        if option.charged and not body.confirm_charges:
            raise HTTPException(409, charge_confirmation(option.engine))
        try:
            mask = read_mask(body.mask, (result.width, result.height))
        except ValueError as error:
            raise HTTPException(422, str(error)) from error
        job_id = uuid4().hex
        mask_key = f"masks/{job_id}.png"
        mask_file = asset_path(settings, mask_key)
        mask_file.parent.mkdir(parents=True, exist_ok=True)
        mask.save(mask_file, "PNG")
        run_settings = {
            "option": option.id,
            "kind": body.kind,
            "subject": subject,
            "instruction": instruction,
            "mask": mask_key,
            "box": mask_box(mask),
            "parent_version": result.version,
            **({"model": state["model"]} if state["model"] else {}),
            **state["options"],
        }
        session.add(
            EngineJob(
                id=job_id,
                kind="edit",
                scene_id=scene.id,
                engine=option.engine,
                status="not_started",
                input_id=result.id,
                settings_json=json.dumps(run_settings),
                timeout_seconds=engine_timeout(row, option.engine),
                created_at=now(),
            )
        )
        session.flush()
        refresh_workflow(session, scene)
        detail = scene_detail(request, session, scene)
    request.app.state.runner.notify()
    return detail


@router.get("/results/{result_id}/mask")
def result_mask(request: Request, result_id: str):
    """The area an edited result changed (white), for the viewer."""
    with Session(request.app.state.engine) as session:
        result = session.get(GenerationResult, result_id)
        edit = json.loads(result.edit_json) if result and result.edit_json else None
    if not edit or not edit.get("mask"):
        raise HTTPException(404, "This result is not an edit.")
    path = asset_path(request.app.state.settings, edit["mask"])
    if not path.is_file():
        raise HTTPException(404, "The marked area's file is missing.")
    return FileResponse(path, media_type="image/png")


def edit_record(run_settings: dict, facts: dict) -> dict:
    """What a new edit result remembers about its edit."""
    keep = ("option", "kind", "subject", "instruction", "mask", "box", "parent_version")
    return {**{k: run_settings.get(k) for k in keep}, **{k: v for k, v in facts.items()
                                                        if k != "sha256"}}


def store_edit(engine, settings: Settings, job: EngineJob, parent: GenerationResult,
               data: bytes, facts: dict, recovered: bool = False) -> str:
    run_settings = json.loads(job.settings_json or "{}")
    return store_result(
        engine,
        settings,
        data,
        scene_id=parent.scene_id,
        approval_id=parent.approval_id,
        source=job.engine,
        mode="edit",
        job_id=job.id,
        engine_version=job.engine_version,
        recovered=recovered,
        parent_result_id=parent.id,
        edit=edit_record(run_settings, facts),
    )


def edit_output(settings: Settings, job: EngineJob, folder: Path) -> bytes | None:
    """Recovery: an image the edit already received, without resending anything."""
    saved = folder / "output.png"
    if saved.is_file():
        return saved.read_bytes()
    if job.engine == "codex_cli":
        for path in saved_images(job.provider_request_id):
            try:
                return read_image_file(path)
            except (EngineError, OSError):
                continue
        return None
    submitted = folder / "submitted.json"
    if job.engine == "bfl_api" and submitted.is_file():
        polling_url = json.loads(submitted.read_text(encoding="utf-8")).get("polling_url")
        key = load_key(settings, "bfl_api")
        if isinstance(polling_url, str) and key:
            # One free status check of the task that was already submitted.
            _status, payload = flux_poll_once(settings, key, polling_url)
            return payload
    return None


def recover_edit(request: Request, job_id: str) -> dict:
    engine, settings = request.app.state.engine, request.app.state.settings
    with Session(engine) as session:
        job = session.get(EngineJob, job_id)
        parent = session.get(GenerationResult, job.input_id)
        if parent is None:
            raise HTTPException(409, "The edited result was deleted, so nothing can be kept.")
        already = session.scalar(
            select(GenerationResult.id).where(GenerationResult.job_id == job.id)
        )
        session.expunge_all()
    found = 0
    if not already:
        folder = asset_path(settings, job.job_folder)
        try:
            payload = edit_output(settings, job, folder)
        except EngineError as error:
            raise HTTPException(409, error.message) from error
        if payload is not None:
            run_settings = json.loads(job.settings_json or "{}")
            try:
                data, facts = finish_edit(
                    settings, folder, asset_path(settings, parent.original_path),
                    asset_path(settings, run_settings["mask"]), payload,
                )
            except EngineError as error:
                raise HTTPException(409, error.message) from error
            new_id = store_edit(engine, settings, job, parent, data, facts, recovered=True)
            found = 1
            with writing(request) as session:
                session.get(EngineJob, job_id).result_id = new_id
    with writing(request) as session:
        scene = require_scene(session, job.scene_id)
        return {"found": found, "scene": scene_detail(request, session, scene)}
