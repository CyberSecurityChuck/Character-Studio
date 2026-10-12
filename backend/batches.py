"""Batch processing (PLAN.md Phase 5.5, DECISIONS.md D010 and D020).

A batch is a list of ordinary engine jobs that share a `batch_id`. Every item is queued
through the same checks as a single click (a valid approval for each generation, no
other run for the scene) and keeps its own job record and results. Items run one at a
time, only while the batch is running; a failed item never stops the batch, but a plan
limit or a sign-in problem pauses it. Nothing is retried or continued automatically.
"""

import json
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from backend.api_engines import (
    API_ENGINES,
    charge_confirmation,
    engine_timeout,
    is_api_engine,
)
from backend.engines import ENGINE_NAMES, SIGN_IN_HELP, engine_status
from backend.generation import (
    MAX_GENERATION_INSTRUCTION,
    generation_instruction,
    run_seconds,
    snapshot_of,
)
from backend.image_api import is_image_engine, run_label
from backend.keystore import key_info
from backend.models import (
    Batch,
    Character,
    CharacterGroup,
    EngineJob,
    EngineSettings,
    GenerationResult,
    GroupMember,
    Scene,
    SceneAnalysis,
    SubjectMapping,
)
from backend.quality import preset_name
from backend.scene_store import active_job, latest, now
from backend.scenes import api_run_settings, image_run_settings, writing
from backend.workflow import (
    SUGGESTED,
    ApprovalError,
    analysis_of,
    auto_references,
    character_photos,
    current_approval,
    refresh_workflow,
    require_valid_approval,
    save_mappings,
)

router = APIRouter(prefix="/api")

# Sensible sizes (PLAN.md Phase 5.5): image generation uses Codex limits 3-5x faster than
# other work (docs/PROVIDER_FINDINGS.md), so generation batches are kept smaller.
MAX_ANALYSIS_RUNS = 50
MAX_GENERATION_RUNS = 20
MAX_IMAGES_PER_SCENE = 10
CANCELLED_WITH_BATCH = "Cancelled with the rest of the batch before it started. Nothing was sent."


class AnalysisBatchInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scene_ids: list[str] = Field(min_length=1, max_length=MAX_ANALYSIS_RUNS)
    include_analysed: bool = False
    # API engines: the user confirmed that every run in the batch may be charged.
    confirm_charges: bool = False


class ChargeInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    confirm_charges: bool = False


class GenerationItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scene_id: str = Field(max_length=32)
    # The approval the page was showing, when it showed one; otherwise the current one.
    approval_id: str | None = Field(default=None, max_length=32)


class GenerationBatchInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: list[GenerationItem] = Field(min_length=1, max_length=MAX_GENERATION_RUNS)
    count: int = Field(default=1, ge=1, le=MAX_IMAGES_PER_SCENE)
    mode: str = Field(default="generate", pattern="^(generate|variation)$")
    preset_id: str | None = Field(default=None, max_length=32)
    # API image engines (Phase 6C): the user confirmed that every run may be charged.
    confirm_charges: bool = False


class GroupSuggestionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scene_ids: list[str] = Field(min_length=1, max_length=MAX_ANALYSIS_RUNS)
    group_id: str = Field(max_length=32)
    # Group members from left to right, as the user arranged them.
    order: list[str] = Field(min_length=1, max_length=20)
    replace_existing: bool = False


def _items(session, batch_id: str) -> list[EngineJob]:
    return list(
        session.scalars(
            select(EngineJob)
            .where(EngineJob.batch_id == batch_id)
            .order_by(EngineJob.created_at, EngineJob.batch_position, EngineJob.id)
        )
    )


def average_seconds(session, kind: str, engine: str) -> int | None:
    """Average time of completed runs of this kind on this PC, for the time estimate."""
    times = [
        seconds
        for job in session.scalars(
            select(EngineJob).where(
                EngineJob.kind == kind, EngineJob.engine == engine, EngineJob.status == "completed"
            )
        )
        if (seconds := run_seconds(job)) is not None
    ]
    return round(sum(times) / len(times)) if times else None


def batch_state(batch: Batch, counts: dict[str, int]) -> str:
    remaining = counts["not_started"] + counts["running"]
    if batch.status == "cancelled":
        return "cancelling" if counts["running"] else "cancelled"
    if not remaining:
        return "finished"
    if batch.status == "paused":
        return "pausing" if counts["running"] else "paused"
    return "running"


def batch_data(session, batch: Batch) -> dict:
    items = _items(session, batch.id)
    counts = {
        status: sum(1 for j in items if j.status == status)
        for status in ("not_started", "running", "completed", "failed", "cancelled", "interrupted")
    }
    retried = {json.loads(j.settings_json or "{}").get("retry_of") for j in items}
    scene_ids = {j.scene_id for j in items}
    scenes = {s.id: s for s in session.scalars(select(Scene).where(Scene.id.in_(scene_ids)))}
    versions = dict(
        session.execute(
            select(GenerationResult.id, GenerationResult.version).where(
                GenerationResult.id.in_({j.result_id for j in items if j.result_id})
            )
        ).all()
    )
    average = average_seconds(session, batch.kind, batch.engine)
    return {
        "id": batch.id,
        "kind": batch.kind,
        "engine": batch.engine,
        "engine_name": run_label(batch.engine, batch.kind),
        "status": batch.status,
        "state": batch_state(batch, counts),
        "pause_kind": batch.pause_kind,
        "pause_details": batch.pause_details,
        "settings": json.loads(batch.settings_json),
        "created_at": batch.created_at,
        "updated_at": batch.updated_at,
        "counts": counts,
        "total": len(items),
        "scene_count": len({j.scene_id for j in items}),
        "retryable": sum(1 for j in items if j.status == "failed" and j.id not in retried),
        "average_seconds": average,
        "estimate_seconds": average * counts["not_started"] if average else None,
        "items": [
            {
                "job_id": job.id,
                "position": index + 1,
                "scene_id": job.scene_id,
                "scene_title": scenes[job.scene_id].title if job.scene_id in scenes else None,
                "thumbnail_url": f"/api/scenes/{job.scene_id}/image/thumbnail",
                "status": job.status,
                "mode": json.loads(job.settings_json or "{}").get("mode"),
                "retry_of": json.loads(job.settings_json or "{}").get("retry_of"),
                "error_kind": job.error_kind,
                "error_details": job.error_details,
                "result_id": job.result_id,
                "result_version": versions.get(job.result_id),
                "seconds": run_seconds(job),
                "started_at": job.started_at,
            }
            for index, job in enumerate(items)
        ],
    }


def require_batch(session, batch_id: str) -> Batch:
    batch = session.get(Batch, batch_id)
    if batch is None:
        raise HTTPException(404, "This batch no longer exists. Reload the page.")
    return batch


def _new_batch(session, kind: str, engine: str, settings: dict) -> Batch:
    stamp = now()
    batch = Batch(
        id=uuid4().hex,
        kind=kind,
        engine=engine,
        status="running",
        settings_json=json.dumps(settings),
        created_at=stamp,
        updated_at=stamp,
    )
    session.add(batch)
    return batch


def _nothing_queued(skipped: list[dict]) -> HTTPException:
    reasons = "; ".join(f"{s['title']}: {s['reason']}" for s in skipped[:5])
    return HTTPException(409, f"Nothing was queued. {reasons}")


def _skip(skipped: list[dict], scene: Scene | None, scene_id: str, reason: str) -> None:
    skipped.append(
        {"scene_id": scene_id, "title": scene.title if scene else "A scene", "reason": reason}
    )


@router.get("/batches")
def batches(request: Request):
    """Unfinished batches first, then the most recent finished ones."""
    with Session(request.app.state.engine) as session:
        listed = [
            batch_data(session, b)
            for b in session.scalars(select(Batch).order_by(Batch.created_at.desc()).limit(30))
        ]
    done = ("finished", "cancelled")
    return [b for b in listed if b["state"] not in done] + [
        b for b in listed if b["state"] in done
    ][:10]


@router.get("/batches/timing")
def timing(request: Request):
    """Average run times on this PC, for the estimate shown before a batch starts."""
    with Session(request.app.state.engine) as session:
        return {
            "analysis": {
                e: average_seconds(session, "analysis", e) for e in [*ENGINE_NAMES, *API_ENGINES]
            },
            "generation": average_seconds(
                session, "generation", session.get(EngineSettings, 1).generation_engine
            ),
        }


@router.get("/batches/{batch_id}")
def batch(request: Request, batch_id: str):
    with Session(request.app.state.engine) as session:
        return batch_data(session, require_batch(session, batch_id))


@router.post("/batches/analysis", status_code=202)
def analyse_selected(request: Request, body: AnalysisBatchInput):
    """Queue one analysis per selected scene with the selected analysis engine."""
    if len(set(body.scene_ids)) != len(body.scene_ids):
        raise HTTPException(422, "A scene was selected twice.")
    with writing(request) as session:
        settings = session.get(EngineSettings, 1)
        engine = settings.analysis_engine
        if engine == "manual":
            raise HTTPException(
                409, "Manual analysis is selected in Studio settings, so nothing can be queued."
            )
        run = api_run_settings(request, settings, engine, body.confirm_charges)
        timeout = engine_timeout(settings, engine)
        batch = _new_batch(session, "analysis", engine, run)
        skipped, queued = [], []
        for scene_id in body.scene_ids:
            scene = session.get(Scene, scene_id)
            if scene is None:
                _skip(skipped, None, scene_id, "This scene no longer exists.")
            elif active_job(session, scene_id):
                _skip(skipped, scene, scene_id, "Another run is running or waiting for it.")
            elif not body.include_analysed and latest(session, SceneAnalysis, scene_id):
                _skip(skipped, scene, scene_id, "It already has an analysis.")
            else:
                queued.append(scene)
        if not queued:
            raise _nothing_queued(skipped)
        for position, scene in enumerate(queued):
            session.add(
                EngineJob(
                    id=uuid4().hex,
                    kind="analysis",
                    scene_id=scene.id,
                    engine=engine,
                    status="not_started",
                    settings_json=json.dumps(run) if run else None,
                    batch_id=batch.id,
                    batch_position=position,
                    timeout_seconds=timeout,
                    created_at=batch.created_at,
                )
            )
        session.flush()
        for scene in queued:
            refresh_workflow(session, scene)
        result = {"batch": batch_data(session, batch), "skipped": skipped}
    request.app.state.runner.notify()
    return result


@router.post("/batches/generation", status_code=202)
def generate_approved(request: Request, body: GenerationBatchInput):
    """Queue `count` image runs for each scene with the selected generation engine, each
    from that scene's own valid approval."""
    if len({i.scene_id for i in body.items}) != len(body.items):
        raise HTTPException(422, "A scene was selected twice.")
    total = len(body.items) * body.count
    with writing(request) as session:
        settings = session.get(EngineSettings, 1)
        engine = settings.generation_engine
        if engine == "manual":
            raise HTTPException(
                409,
                "Manual generation is selected in Studio settings. Choose an engine there to "
                "generate several scenes in a row.",
            )
        api = is_image_engine(engine)
        if total > MAX_GENERATION_RUNS:
            why = (
                "each image is charged"
                if api
                else "image generation uses your plan's allowance quickly"
            )
            raise HTTPException(
                422,
                f"That would be {total} images. A batch makes at most {MAX_GENERATION_RUNS}, "
                f"because {why}.",
            )
        run = (
            image_run_settings(request, session, settings, body.confirm_charges, body.preset_id)
            if api
            else {}
        )
        preset = preset_name(session, body.preset_id)
        batch = _new_batch(
            session,
            "generation",
            engine,
            {"count": body.count, "mode": body.mode, **run}
            | ({"preset": preset} if preset else {}),
        )
        skipped, queued = [], []
        for item in body.items:
            scene = session.get(Scene, item.scene_id)
            if scene is None:
                _skip(skipped, None, item.scene_id, "This scene no longer exists.")
                continue
            if active_job(session, scene.id):
                _skip(skipped, scene, scene.id, "Another run is running or waiting for it.")
                continue
            try:
                # One approval never covers several scenes: each scene passes its own gate.
                approval = require_valid_approval(session, scene)
            except ApprovalError as error:
                _skip(skipped, scene, scene.id, str(error))
                continue
            if item.approval_id and approval.id != item.approval_id:
                _skip(skipped, scene, scene.id, "The approval changed in another window.")
                continue
            instruction = generation_instruction(snapshot_of(approval)["inputs"], body.mode, api)
            if len(instruction) > MAX_GENERATION_INSTRUCTION:
                reason = f"Its prompt is too long to send to {run_label(engine, 'generation')}."
                _skip(skipped, scene, scene.id, reason)
                continue
            queued.append((scene, approval))
        if not queued:
            raise _nothing_queued(skipped)
        position = 0
        for scene, approval in queued:
            for _ in range(body.count):
                session.add(
                    _generation_job(
                        batch,
                        scene.id,
                        approval.id,
                        body.mode,
                        position,
                        engine_timeout(settings, engine),
                    )
                )
                position += 1
        session.flush()
        for scene, _approval in queued:
            refresh_workflow(session, scene)
        result = {"batch": batch_data(session, batch), "skipped": skipped}
    request.app.state.runner.notify()
    return result


def _generation_job(
    batch, scene_id, approval_id, mode, position, timeout, retry_of=None, stamp=None
):
    settings = {"mode": mode} | ({"retry_of": retry_of} if retry_of else {})
    chosen = json.loads(batch.settings_json)
    # API image runs keep the model, size and quality the batch was confirmed with.
    for name in ("preset", "model", "size", "quality"):
        if chosen.get(name):
            settings[name] = chosen[name]
    return EngineJob(
        id=uuid4().hex,
        kind="generation",
        scene_id=scene_id,
        engine=batch.engine,
        status="not_started",
        input_id=approval_id,
        settings_json=json.dumps(settings),
        batch_id=batch.id,
        batch_position=position,
        timeout_seconds=timeout,
        created_at=stamp or batch.created_at,
    )


def _require_generation_engine(settings: EngineSettings, batch: Batch) -> None:
    """A generation batch only continues with the engine it was started (and confirmed) with."""
    if settings.generation_engine != batch.engine:
        started = run_label(batch.engine, "generation")
        now_used = run_label(settings.generation_engine, "generation")
        raise HTTPException(
            409,
            f"This batch was started with {started}, but Studio settings now use {now_used}. "
            f"Choose {started} there to continue it, or start a new batch.",
        )


@router.post("/batches/{batch_id}/pause")
def pause(request: Request, batch_id: str):
    """Stop starting new items. A run already in progress finishes normally."""
    with writing(request) as session:
        batch = require_batch(session, batch_id)
        if batch.status != "running":
            raise HTTPException(409, "This batch is not running.")
        batch.status, batch.pause_kind, batch.pause_details = "paused", "user", None
        batch.updated_at = now()
        return batch_data(session, batch)


def _check_engine(request, engine: str) -> None:
    if is_api_engine(engine):
        if not key_info(request.app.state.settings, engine)["saved"]:
            raise HTTPException(
                409, f"No {API_ENGINES[engine].name} key is saved. Add one, then continue."
            )
        return
    status = engine_status(engine, request.app.state.settings.engine_commands)
    name = ENGINE_NAMES[engine]
    if not status["installed"]:
        raise HTTPException(409, f"{status['message']} Install it, then continue the batch.")
    if not status["signed_in"]:
        raise HTTPException(
            409, f"{name} is still signed out. {SIGN_IN_HELP[engine]}, then continue."
        )


@router.post("/batches/{batch_id}/continue")
async def continue_batch(request: Request, batch_id: str, body: ChargeInput | None = None):
    """Only the user continues a paused batch; sign-in is checked first (nothing is sent)."""
    with Session(request.app.state.engine) as session:
        engine = require_batch(session, batch_id).engine
    if is_api_engine(engine) and not (body and body.confirm_charges):
        raise HTTPException(409, charge_confirmation(engine))
    await run_in_threadpool(_check_engine, request, engine)
    with writing(request) as session:
        batch = require_batch(session, batch_id)
        if batch.status != "paused":
            raise HTTPException(409, "This batch is not paused.")
        if not session.scalar(
            select(func.count()).where(
                EngineJob.batch_id == batch.id, EngineJob.status == "not_started"
            )
        ):
            raise HTTPException(409, "Nothing is left to run in this batch.")
        if batch.kind == "generation":
            _require_generation_engine(session.get(EngineSettings, 1), batch)
        batch.status, batch.pause_kind, batch.pause_details = "running", None, None
        batch.updated_at = now()
        result = batch_data(session, batch)
    request.app.state.runner.notify()
    return result


@router.post("/batches/{batch_id}/cancel")
def cancel_remaining(request: Request, batch_id: str):
    """Cancel every item that has not started. A run in progress may still be cancelled
    on its own; it is never stopped here, because it may already have used allowance."""
    with writing(request) as session:
        batch = require_batch(session, batch_id)
        if batch.status == "cancelled":
            raise HTTPException(409, "This batch is already cancelled.")
        waiting = [j for j in _items(session, batch.id) if j.status == "not_started"]
        session.execute(
            update(EngineJob)
            .where(EngineJob.id.in_([j.id for j in waiting]))
            .values(
                status="cancelled",
                error_kind="cancelled",
                error_details=CANCELLED_WITH_BATCH,
                finished_at=now(),
            )
        )
        batch.status, batch.updated_at = "cancelled", now()
        session.flush()
        for scene_id in {j.scene_id for j in waiting}:
            scene = session.get(Scene, scene_id)
            if scene is not None:
                refresh_workflow(session, scene)
        return batch_data(session, batch)


@router.post("/batches/{batch_id}/retry", status_code=202)
def retry_failed(request: Request, batch_id: str, body: ChargeInput | None = None):
    """The user's explicit choice to run failed items once more, as new items."""
    with writing(request) as session:
        batch = require_batch(session, batch_id)
        if is_api_engine(batch.engine) and not (body and body.confirm_charges):
            raise HTTPException(409, charge_confirmation(batch.engine))
        items = _items(session, batch.id)
        if any(j.status in ("not_started", "running") for j in items):
            raise HTTPException(409, "Wait until the batch has finished, then try again.")
        retried = {json.loads(j.settings_json or "{}").get("retry_of") for j in items}
        failed = [j for j in items if j.status == "failed" and j.id not in retried]
        if not failed:
            raise HTTPException(409, "No failed items are left to try again.")
        settings = session.get(EngineSettings, 1)
        if batch.kind == "generation":
            _require_generation_engine(settings, batch)
        stamp, position = now(), max(j.batch_position or 0 for j in items) + 1
        skipped, added, scenes = [], 0, set()
        for job in failed:
            scene = session.get(Scene, job.scene_id)
            if job.scene_id not in scenes and active_job(session, job.scene_id):
                _skip(skipped, scene, job.scene_id, "Another run is running or waiting for it.")
                continue
            if batch.kind == "generation":
                try:
                    approval = require_valid_approval(session, scene)
                except ApprovalError as error:
                    _skip(skipped, scene, job.scene_id, str(error))
                    continue
                mode = json.loads(job.settings_json or "{}").get("mode", "generate")
                session.add(
                    _generation_job(
                        batch,
                        scene.id,
                        approval.id,
                        mode,
                        position,
                        engine_timeout(settings, batch.engine),
                        job.id,
                        stamp,
                    )
                )
            else:
                session.add(
                    EngineJob(
                        id=uuid4().hex,
                        kind="analysis",
                        scene_id=scene.id,
                        engine=batch.engine,
                        status="not_started",
                        # The retry runs with the model the batch was confirmed for.
                        settings_json=json.dumps(
                            {**json.loads(batch.settings_json), "retry_of": job.id}
                        ),
                        batch_id=batch.id,
                        batch_position=position,
                        timeout_seconds=job.timeout_seconds,
                        created_at=stamp,
                    )
                )
            position, added = position + 1, added + 1
            scenes.add(job.scene_id)
        if not added:
            raise _nothing_queued(skipped)
        batch.status, batch.pause_kind, batch.pause_details = "running", None, None
        batch.updated_at = stamp
        session.flush()
        for scene_id in scenes:
            refresh_workflow(session, session.get(Scene, scene_id))
        result = {"batch": batch_data(session, batch), "skipped": skipped}
    request.app.state.runner.notify()
    return result


@router.delete("/batches/{batch_id}")
def remove_batch(request: Request, batch_id: str):
    """Remove a finished batch from the list. Its runs, results and records are kept."""
    with writing(request) as session:
        batch = require_batch(session, batch_id)
        if any(j.status in ("not_started", "running") for j in _items(session, batch.id)):
            raise HTTPException(409, "Only finished or cancelled batches can be removed.")
        session.execute(
            update(EngineJob).where(EngineJob.batch_id == batch.id).values(batch_id=None)
        )
        session.delete(batch)
    return {"deleted": True}


@router.post("/scenes/suggest-group")
def suggest_group(request: Request, body: GroupSuggestionInput):
    """Suggest assignments from a group, left to right. Each scene still needs the user to
    check and save its assignments before it can be approved; nothing is sent anywhere."""
    if len(set(body.order)) != len(body.order) or len(set(body.scene_ids)) != len(body.scene_ids):
        raise HTTPException(422, "A character or scene appears twice.")
    with writing(request) as session:
        group = session.get(CharacterGroup, body.group_id)
        if group is None:
            raise HTTPException(404, "That group no longer exists. Reload the page.")
        members = set(
            session.scalars(
                select(GroupMember.character_id).where(GroupMember.group_id == group.id)
            )
        )
        if not set(body.order) <= members:
            raise HTTPException(409, "The group changed in another window. Reload the page.")
        people, left_out = [], []
        for character_id in body.order:
            character = session.get(Character, character_id)
            photos = character_photos(session, character_id)
            if character.archived or not photos:
                left_out.append(character.name)
            else:
                people.append((character, photos))
        if not people:
            raise HTTPException(409, "Nobody in this order has reference photos to use.")
        suggested, skipped = [], []
        for scene_id in body.scene_ids:
            scene = session.get(Scene, scene_id)
            analysis = latest(session, SceneAnalysis, scene_id) if scene else None
            if scene is None:
                _skip(skipped, None, scene_id, "This scene no longer exists.")
            elif active_job(session, scene_id):
                _skip(skipped, scene, scene_id, "A run is running or waiting for it.")
            elif analysis is None:
                _skip(skipped, scene, scene_id, "Analyse it first.")
            elif current_approval(session, scene_id) is not None:
                _skip(skipped, scene, scene_id, "It is approved. Withdraw the approval first.")
            elif not body.replace_existing and session.scalar(
                select(SubjectMapping.id).where(SubjectMapping.scene_id == scene_id).limit(1)
            ):
                _skip(skipped, scene, scene_id, "It already has assignments.")
            elif not (subjects := analysis_of(analysis).subjects):
                _skip(skipped, scene, scene_id, "No people were found in it.")
            else:
                ordered = sorted(
                    subjects, key=lambda s: s.bounding_box.x + s.bounding_box.width / 2
                )
                entries = [
                    {
                        "label": subject.label,
                        "action": "replace",
                        "character_id": character.id,
                        "reference_ids": auto_references(
                            photos, character.primary_photo_id, subject.facial_viewing_angle
                        ),
                        "references_auto": True,
                    }
                    for subject, (character, photos) in zip(ordered, people, strict=False)
                ]
                # Saved as suggestions: approval stays blocked until the user saves them.
                save_mappings(session, scene, SUGGESTED, entries)
                scene.mapping_group_id = group.id
                scene.revision += 1
                scene.updated_at = now()
                refresh_workflow(session, scene)
                suggested.append(
                    {
                        "scene_id": scene.id,
                        "title": scene.title,
                        "assigned": len(entries),
                        "subjects": len(subjects),
                    }
                )
        return {"suggested": suggested, "skipped": skipped, "left_out": left_out}
