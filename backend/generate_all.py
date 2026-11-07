"""Generate all on a scene set (Phase 7D, D030, D039).

The seventh step of Prepare this set. The user ticks approved scenes (by default those with
no result from their current approval) and starts any number of images with one click. The
studio splits them into chained batches of at most 20 images that run one after another.

A Generate all is stored as a run like Run everything (`pipeline_runs`, rules kind
"generate"), so it shares its pause summary, per-scene labels, Continue and Try failed
again, and a restart pauses it until the user continues. Nothing is retried or continued
automatically. Each image uses its own scene's approval.
"""

import json
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.batches import MAX_IMAGES_PER_SCENE, MAX_SELECTED, average_seconds
from backend.generation import MAX_GENERATION_INSTRUCTION, generation_instruction, snapshot_of
from backend.image_api import is_image_engine, run_label
from backend.models import EngineSettings, GenerationResult, PipelineRun, Scene
from backend.pipeline import (
    ALREADY_RUNNING,
    LABELS,
    _has_result,
    _queue_generation,
    last_generation_run,
    open_run,
    run_data,
    scene_labels,
)
from backend.preparation import set_scenes
from backend.quality import preset_name
from backend.scene_store import active_job, now
from backend.scenes import image_run_settings, writing
from backend.workflow import ApprovalError, current_approval, require_valid_approval

router = APIRouter(prefix="/api")


class GenerateAllInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scene_ids: list[str] = Field(min_length=1, max_length=MAX_SELECTED)
    count: int = Field(default=1, ge=1, le=MAX_IMAGES_PER_SCENE)
    mode: Literal["generate", "variation"] = "generate"
    preset_id: str | None = Field(default=None, max_length=32)
    # Paid image engines: the user confirmed the charges for every image of this run.
    confirm_charges: bool = False


def _reason(session, scene: Scene, api: bool, engine: str) -> str | None:
    """Why this approved scene cannot be generated now, or None."""
    if active_job(session, scene.id):
        return "A run is running or waiting for it."
    try:
        approval = require_valid_approval(session, scene)
    except ApprovalError as error:
        return str(error)
    text = generation_instruction(snapshot_of(approval)["inputs"], "generate", api)
    if len(text) > MAX_GENERATION_INSTRUCTION:
        return f"Its prompt is too long to send to {run_label(engine, 'generation')}."
    return None


@router.get("/scene-sets/{scene_set_id}/generate-all")
def preview(request: Request, scene_set_id: str):
    """The set's approved scenes for the Generate step: new (no result from the current
    approval), more (already has results), busy or blocked, with the time per image."""
    with Session(request.app.state.engine) as session:
        scenes = set_scenes(session, scene_set_id)
        engine = session.get(EngineSettings, 1).generation_engine
        api = is_image_engine(engine)
        results = dict(
            session.execute(
                select(GenerationResult.scene_id, func.count())
                .where(GenerationResult.scene_id.in_([s.id for s in scenes]))
                .group_by(GenerationResult.scene_id)
            ).all()
        )
        counts = dict.fromkeys(("total", "approved", "new", "more", "blocked"), 0)
        counts["total"] = len(scenes)
        rows = []
        for scene in scenes:
            approval = current_approval(session, scene.id)
            if approval is None:
                continue
            counts["approved"] += 1
            has_results = _has_result(session, approval.id)
            reason = _reason(session, scene, api, engine)
            state = "blocked" if reason else "more" if has_results else "new"
            counts[state] += 1
            rows.append(
                {
                    "scene_id": scene.id,
                    "title": scene.title,
                    "thumbnail_url": f"/api/scenes/{scene.id}/image/thumbnail",
                    "result_count": results.get(scene.id, 0),
                    "has_results": has_results,
                    "state": state,
                    "reason": reason,
                }
            )
        running = open_run(session, scene_set_id)
        return {
            "engine": engine,
            "average_seconds": (
                average_seconds(session, "generation", engine) if engine != "manual" else None
            ),
            "counts": counts,
            "rows": rows,
            "results": sum(results.values()),
            "open_run": running.id if running else None,
        }


@router.post("/scene-sets/{scene_set_id}/generate-all", status_code=202)
def generate_all(request: Request, scene_set_id: str, body: GenerateAllInput):
    if len(set(body.scene_ids)) != len(body.scene_ids):
        raise HTTPException(422, "A scene was chosen twice.")
    with writing(request) as session:
        set_scenes(session, scene_set_id)  # refuses a set that no longer exists
        if open_run(session, scene_set_id) is not None:
            raise HTTPException(409, ALREADY_RUNNING)
        settings = session.get(EngineSettings, 1)
        engine = settings.generation_engine
        if engine == "manual":
            raise HTTPException(
                409,
                "Manual generation is selected in Studio settings. Choose an engine there to "
                "generate the set.",
            )
        image_run = (
            image_run_settings(request, session, settings, body.confirm_charges, body.preset_id)
            if is_image_engine(engine)
            else {}
        )
        stopped, chosen = [], []
        for scene_id in body.scene_ids:
            scene = session.get(Scene, scene_id)
            if scene is None or scene.scene_set_id != scene_set_id:
                title = scene.title if scene else "A scene"
                reason = "It is no longer in this set."
                stopped.append({"scene_id": scene_id, "title": title, "reason": reason})
            else:
                chosen.append(scene_id)
        stamp = now()
        rules = {
            "kind": "generate",
            "images": body.count,
            "mode": body.mode,
            "preset_id": body.preset_id,
            "preset": preset_name(session, body.preset_id),
            "generation_engine": engine,
            "analysis_engine": None,
            "image_run": image_run,
        }
        run = PipelineRun(
            id=uuid4().hex,
            scene_set_id=scene_set_id,
            status="running",
            stage="generating",
            rules_json=json.dumps(rules),
            outcome_json=json.dumps({"stopped": stopped}),
            created_at=stamp,
            updated_at=stamp,
        )
        session.add(run)
        _queue_generation(session, run, rules, chosen)
        outcome = json.loads(run.outcome_json)
        if not outcome.get("images"):
            reasons = "; ".join(f"{s['title']}: {s['reason']}" for s in outcome["stopped"][:5])
            raise HTTPException(409, f"Nothing was queued. {reasons}")
        result = run_data(session, run)
    request.app.state.runner.notify()
    return result


@router.get("/scene-sets/{scene_set_id}/labels")
def labels(request: Request, scene_set_id: str):
    """Each scene's label from the set's newest run with images, for the filter chips."""
    with Session(request.app.state.engine) as session:
        members = {s.id for s in set_scenes(session, scene_set_id)}
        run = last_generation_run(session, scene_set_id)
        if run is None:
            return {"run": None, "labels": {}, "counts": dict.fromkeys(LABELS, 0)}
        found = {k: v for k, v in scene_labels(session, run).items() if k in members}
        return {
            "run": {
                "id": run.id,
                "kind": json.loads(run.rules_json).get("kind", "everything"),
                "status": run.status,
                "created_at": run.created_at,
            },
            "labels": found,
            "counts": {
                name: sum(1 for v in found.values() if v["label"] == name) for name in LABELS
            },
        }
