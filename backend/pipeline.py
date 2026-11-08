"""Run everything on a scene set: the full auto-pipeline (Phase 7C-2, D030, D037).

One user click sets the rules and starts the run. It goes stage by stage: every analysis
first (chained batches of 50), then every scene is assigned, drafted and approved at once
(no engine runs for that), then every generation (chained batches of 20 images). Each scene
picks up where it is: what the user decided by hand is kept, the rules only fill what is
empty. Scenes with uncertain details or a people/character mismatch stop at Needs your
check unless the user let them through; scenes with prompt warnings always stop.

The run is stored server-side. It moves on only when all of its analysis batches have
finished; a plan limit pauses its batches as always, a restart pauses the run itself, and
only the user continues either. Nothing is retried. Approvals made here record "auto".
"""

import json
import threading
from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from backend.api_engines import charge_confirmation, engine_timeout, is_api_engine
from backend.batches import (
    MAX_GENERATION_RUNS,
    MAX_IMAGES_PER_SCENE,
    _check_engine,
    _generation_job,
    _require_generation_engine,
    batch_state,
    cancel_waiting,
    retry_batch,
)
from backend.generation import MAX_GENERATION_INSTRUCTION, generation_instruction, snapshot_of
from backend.image_api import is_image_engine, run_label
from backend.models import (
    Batch,
    EngineJob,
    EngineSettings,
    GenerationResult,
    PipelineRun,
    PromptVersion,
    Scene,
    SceneAnalysis,
)
from backend.persistence import writing_session
from backend.preparation import (
    _usable,
    accept_scene_details,
    draft_scene,
    has_assignment,
    preset_texts,
    queue_analysis_batches,
    rule_mappings,
    set_scenes,
)
from backend.quality import preset_name
from backend.scene_store import active_job, latest, now
from backend.scenes import (
    MappingEntry,
    api_run_settings,
    approve_in_session,
    image_run_settings,
    save_assignments,
    writing,
)
from backend.workflow import (
    ApprovalError,
    analysis_of,
    build_plan,
    current_approval,
    mismatch_note,
    prompt_is_current,
    refresh_workflow,
    require_valid_approval,
    review,
)

router = APIRouter(prefix="/api")

OPEN = ("running", "paused", "waiting")
ALREADY_RUNNING = (
    "A run is already in progress for this set (Run everything or Generate all). "
    "Wait for it to finish, or cancel it, first."
)
RESTART_MESSAGE = (
    "The studio stopped while Run everything was in progress. Nothing continues on its own: "
    "click Continue when you are ready."
)
GENERATE_RESTART_MESSAGE = (
    "The studio stopped while Generate all was in progress. Nothing continues on its own: "
    "click Continue when you are ready."
)
RESTART_MESSAGES = (RESTART_MESSAGE, GENERATE_RESTART_MESSAGE)
# Moving a run on happens in one place at a time, whether the runner or a click does it.
_advancing = threading.Lock()


class RunInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    # Who people nobody is assigned to yet get: nobody (they stop), one character, a group.
    rule: Literal["none", "one", "group"] = "none"
    character_id: str | None = Field(default=None, max_length=32)
    several_people: Literal["skip", "largest"] = "skip"
    group_id: str | None = Field(default=None, max_length=32)
    order: list[str] = Field(default_factory=list, max_length=20)
    preset_id: str | None = Field(default=None, max_length=32)
    images: int = Field(default=1, ge=1, le=MAX_IMAGES_PER_SCENE)
    let_uncertain: bool = False
    let_mismatch: bool = False
    stop_before_generating: bool = False
    # Paid engines: the user confirmed the charges for the whole run.
    confirm_charges: bool = False


class ChargeInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    confirm_charges: bool = False


class Stop(Exception):
    """This scene stops at Needs your check; the message says why."""


# Reading a run --------------------------------------------------------------------------


def run_batches(session, run_id: str, kind: str | None = None) -> list[Batch]:
    query = select(Batch).where(Batch.settings_json.like(f'%"pipeline_id": "{run_id}"%'))
    if kind:
        query = query.where(Batch.kind == kind)
    return list(session.scalars(query.order_by(Batch.created_at)))


def _left(session, batch: Batch) -> int:
    return session.scalar(
        select(func.count()).where(
            EngineJob.batch_id == batch.id, EngineJob.status.in_(("not_started", "running"))
        )
    )


def _counts(session, batch: Batch) -> dict[str, int]:
    rows = session.execute(
        select(EngineJob.status, func.count())
        .where(EngineJob.batch_id == batch.id)
        .group_by(EngineJob.status)
    ).all()
    counts = dict.fromkeys(
        ("not_started", "running", "completed", "failed", "cancelled", "interrupted"), 0
    )
    counts.update(dict(rows))
    return counts


def run_data(session, run: PipelineRun) -> dict:
    rules = json.loads(run.rules_json)
    batches = []
    for batch in run_batches(session, run.id):
        counts = _counts(session, batch)
        batches.append(
            {
                "id": batch.id,
                "kind": batch.kind,
                "state": batch_state(batch, counts),
                "pause_kind": batch.pause_kind,
                "total": sum(counts.values()),
                "done": counts["completed"],
                "failed": counts["failed"] + counts["interrupted"],
                "cancelled": counts["cancelled"],
            }
        )
    return {
        "id": run.id,
        # "everything" (Run everything, 7C-2) or "generate" (Generate all, 7D).
        "kind": rules.get("kind", "everything"),
        "scene_set_id": run.scene_set_id,
        "status": run.status,
        "stage": run.stage,
        "pause_details": run.pause_details,
        "rules": {k: v for k, v in rules.items() if k not in ("analysis_run", "image_run")},
        "outcome": json.loads(run.outcome_json or "{}"),
        "batches": batches,
        "summary": generation_summary(session, run),
        "created_at": run.created_at,
        "updated_at": run.updated_at,
    }


# What a run's images came to (Phase 7D) ----------------------------------------------------

# A scene's label after a generation run, worst first: what still needs the user comes first.
LABELS = ("generated", "failed", "not_started", "interrupted")


def live_jobs(session, batches: list[Batch]) -> list[EngineJob]:
    """The batches' items, leaving out failed items that were tried again (the new item counts)."""
    if not batches:
        return []
    jobs = list(
        session.scalars(select(EngineJob).where(EngineJob.batch_id.in_([b.id for b in batches])))
    )
    retried = {json.loads(j.settings_json or "{}").get("retry_of") for j in jobs}
    return [j for j in jobs if j.id not in retried]


def generation_summary(session, run: PipelineRun) -> dict | None:
    """Images done, failed, interrupted and not started, and why and when the run paused."""
    batches = run_batches(session, run.id, "generation")
    if not batches:
        return None
    jobs = live_jobs(session, batches)

    def count(*statuses: str) -> int:
        return sum(1 for j in jobs if j.status in statuses)

    paused = None
    if run.status == "paused":
        kind = "restart" if run.pause_details in RESTART_MESSAGES else "engine"
        paused = {"kind": kind, "details": run.pause_details, "at": run.updated_at}
    else:
        for batch in batches:
            if batch.status == "paused" and _left(session, batch):
                paused = {"kind": batch.pause_kind, "details": batch.pause_details,
                          "at": batch.updated_at}
                break
    left = count("running", "not_started")
    return {
        "images": len(jobs),
        "done": count("completed"),
        "failed": count("failed"),
        "interrupted": count("interrupted"),
        "running": count("running"),
        # Cancelled items never started either.
        "not_started": count("not_started", "cancelled"),
        "paused": paused,
        "retryable": count("failed") if not left and run.status == "finished" else 0,
    }


def scene_labels(session, run: PipelineRun) -> dict[str, dict]:
    """Generated, Failed, Not started or Interrupted per scene of the run (running while one
    of its images is being made), with how many of its images were made."""
    by_scene: dict[str, list[EngineJob]] = {}
    for job in live_jobs(session, run_batches(session, run.id, "generation")):
        by_scene.setdefault(job.scene_id, []).append(job)
    labels = {}
    for scene_id, jobs in by_scene.items():
        statuses = {j.status for j in jobs}
        if "running" in statuses:
            label = "running"
        elif "interrupted" in statuses:
            label = "interrupted"
        elif "failed" in statuses:
            label = "failed"
        elif statuses & {"not_started", "cancelled"}:
            label = "not_started"
        else:
            label = "generated"
        made = sum(1 for j in jobs if j.status == "completed")
        labels[scene_id] = {"label": label, "made": made, "total": len(jobs)}
    return labels


def last_generation_run(session, scene_set_id: str) -> PipelineRun | None:
    """The set's newest run that has queued images (Run everything or Generate all)."""
    for run in session.scalars(
        select(PipelineRun)
        .where(PipelineRun.scene_set_id == scene_set_id)
        .order_by(PipelineRun.created_at.desc())
        .limit(20)
    ):
        if run_batches(session, run.id, "generation"):
            return run
    return None


def open_run(session, scene_set_id: str) -> PipelineRun | None:
    return session.scalar(
        select(PipelineRun)
        .where(PipelineRun.scene_set_id == scene_set_id, PipelineRun.status.in_(OPEN))
        .limit(1)
    )


def require_run(session, run_id: str) -> PipelineRun:
    run = session.get(PipelineRun, run_id)
    if run is None:
        raise HTTPException(404, "This run no longer exists. Reload the page.")
    return run


def _has_result(session, approval_id: str) -> bool:
    return bool(
        session.scalar(
            select(GenerationResult.id).where(GenerationResult.approval_id == approval_id).limit(1)
        )
    )


@router.get("/scene-sets/{scene_set_id}/pipeline")
def pipeline(request: Request, scene_set_id: str):
    """What Run everything would do to the set now, and its latest run."""
    with Session(request.app.state.engine) as session:
        scenes = set_scenes(session, scene_set_id)
        counts = dict.fromkeys(("total", "analyse", "prepare", "generate", "done", "busy"), 0)
        counts["total"] = len(scenes)
        for scene in scenes:
            approval = current_approval(session, scene.id)
            if active_job(session, scene.id):
                counts["busy"] += 1
            elif approval is not None:
                counts["done" if _has_result(session, approval.id) else "generate"] += 1
            elif latest(session, SceneAnalysis, scene.id) is None:
                counts["analyse"] += 1
            else:
                counts["prepare"] += 1
        settings = session.get(EngineSettings, 1)
        last = session.scalar(
            select(PipelineRun)
            .where(PipelineRun.scene_set_id == scene_set_id)
            .order_by(PipelineRun.created_at.desc())
            .limit(1)
        )
        return {
            "counts": counts,
            "analysis_engine": settings.analysis_engine,
            "generation_engine": settings.generation_engine,
            "run": run_data(session, last) if last else None,
        }


# Starting a run -------------------------------------------------------------------------


@router.post("/scene-sets/{scene_set_id}/pipeline", status_code=202)
def start(request: Request, scene_set_id: str, body: RunInput):
    with writing(request) as session:
        scenes = set_scenes(session, scene_set_id)
        if open_run(session, scene_set_id) is not None:
            raise HTTPException(409, ALREADY_RUNNING)
        if body.rule == "one":
            if not body.character_id:
                raise HTTPException(422, "Choose the character for people nobody is assigned to.")
            _usable(session, [body.character_id])
        elif body.rule == "group":
            if not body.order or len(set(body.order)) != len(body.order):
                raise HTTPException(422, "Arrange the group's characters first.")
            _usable(session, body.order)
        preset_texts(session, body.preset_id)  # refuses a preset that no longer exists
        settings = session.get(EngineSettings, 1)
        analysis_engine, generation_engine = settings.analysis_engine, settings.generation_engine
        to_analyse = [
            s
            for s in scenes
            if latest(session, SceneAnalysis, s.id) is None and not active_job(session, s.id)
        ]
        others = [s for s in scenes if s not in to_analyse]
        if not to_analyse and not any(
            (a := current_approval(session, s.id)) is None or not _has_result(session, a.id)
            for s in others
        ):
            raise HTTPException(409, "Nothing to do: every scene in this set already has results.")
        if to_analyse and analysis_engine == "manual":
            raise HTTPException(
                409,
                "Manual analysis is selected in Studio settings, so the scenes without an "
                "analysis cannot be analysed. Choose an engine there first.",
            )
        if generation_engine == "manual":
            raise HTTPException(
                409,
                "Manual generation is selected in Studio settings. Choose an engine there to "
                "use Run everything.",
            )
        analysis_run = (
            api_run_settings(request, settings, analysis_engine, body.confirm_charges)
            if to_analyse
            else {}
        )
        image_run = (
            image_run_settings(request, session, settings, body.confirm_charges, body.preset_id)
            if is_image_engine(generation_engine)
            else {}
        )
        stamp = now()
        run = PipelineRun(
            id=uuid4().hex,
            scene_set_id=scene_set_id,
            status="running",
            stage="analysing",
            rules_json=json.dumps(
                {
                    **body.model_dump(exclude={"confirm_charges"}),
                    "preset": preset_name(session, body.preset_id),
                    "analysis_engine": analysis_engine if to_analyse else None,
                    "generation_engine": generation_engine,
                    "analysis_run": analysis_run,
                    "image_run": image_run,
                }
            ),
            outcome_json=json.dumps({"analyse": len(to_analyse)}),
            created_at=stamp,
            updated_at=stamp,
        )
        session.add(run)
        if to_analyse:
            queue_analysis_batches(
                session, settings, to_analyse, analysis_run, scene_set_id, {"pipeline_id": run.id}
            )
        run_id = run.id
    if not to_analyse:
        # Nothing to analyse: assign, draft and approve now, as the same click.
        advance_run(request.app.state.engine, request.app.state.settings, run_id)
    request.app.state.runner.notify()
    with Session(request.app.state.engine) as session:
        return run_data(session, require_run(session, run_id))


# Moving a run on ------------------------------------------------------------------------


def advance_pipelines(engine, settings) -> None:
    """Called by the job runner: move on every running run whose stage has finished."""
    with Session(engine) as session:
        ids = list(session.scalars(select(PipelineRun.id).where(PipelineRun.status == "running")))
    for run_id in ids:
        advance_run(engine, settings, run_id)


def advance_run(engine, settings, run_id: str) -> None:
    with _advancing:
        with writing_session(engine) as session:
            run = session.get(PipelineRun, run_id)
            if run is None or run.status != "running":
                return
            if run.stage == "generating":
                batches = run_batches(session, run.id, "generation")
                if all(_left(session, b) == 0 for b in batches):
                    run.status, run.updated_at = "finished", now()
                return
            analyses = run_batches(session, run.id, "analysis")
            if any(b.status == "cancelled" for b in analyses):
                run.status, run.updated_at = "cancelled", now()
                _note(run, "An analysis batch was cancelled, so nothing was approved or generated.")
                return
            if any(_left(session, b) for b in analyses):
                return  # still analysing, or paused until the user continues a batch
            rules = json.loads(run.rules_json)
            scene_set_id = run.scene_set_id
        to_generate = _approve_stage(engine, settings, run_id, scene_set_id, rules)
        with writing_session(engine) as session:
            run = session.get(PipelineRun, run_id)
            if run.status != "running":
                return
            if not to_generate:
                run.status, run.stage, run.updated_at = "finished", "generating", now()
            elif rules["stop_before_generating"]:
                run.status, run.updated_at = "waiting", now()
            else:
                _queue_generation(session, run, rules, to_generate)


def _note(run: PipelineRun, text: str) -> None:
    outcome = json.loads(run.outcome_json or "{}")
    outcome["note"] = text
    run.outcome_json = json.dumps(outcome)


def _approve_stage(engine, settings, run_id: str, scene_set_id: str, rules: dict) -> list[str]:
    """Assign, draft and approve every scene of the set, each in its own transaction."""
    with Session(engine) as session:
        scene_ids = [s.id for s in set_scenes(session, scene_set_id)]
        changes, negatives, _name = preset_texts(session, rules.get("preset_id"))
    approved, stopped, to_generate, done = [], [], [], 0
    for scene_id in scene_ids:
        title = "A scene"
        try:
            with writing_session(engine) as session:
                scene = session.get(Scene, scene_id)
                if scene is None or scene.scene_set_id != scene_set_id:
                    continue
                title = scene.title
                result = _prepare_scene(settings, session, scene, rules, changes, negatives)
        except (Stop, HTTPException) as error:
            reason = error.detail if isinstance(error, HTTPException) else str(error)
            stopped.append({"scene_id": scene_id, "title": title, "reason": reason})
            continue
        if result == "done":
            done += 1
            continue
        if result == "approved":
            approved.append(scene_id)
        to_generate.append(scene_id)
    with writing_session(engine) as session:
        run = session.get(PipelineRun, run_id)
        outcome = json.loads(run.outcome_json or "{}")
        outcome.update(
            approved=len(approved), stopped=stopped, already_done=done, generate=len(to_generate)
        )
        run.outcome_json, run.updated_at = json.dumps(outcome), now()
    return to_generate


def _prepare_scene(settings, session, scene: Scene, rules, changes, negatives) -> str:
    """Take one scene as far as approval. Returns done, approved or ready (approved before)."""
    if active_job(session, scene.id):
        raise Stop("A run is running or waiting for it.")
    approval = current_approval(session, scene.id)
    if approval is not None:
        return "done" if _has_result(session, approval.id) else "ready"
    analysis = latest(session, SceneAnalysis, scene.id)
    if analysis is None:
        raise Stop("It has no analysis: its run failed or was cancelled.")
    data = analysis_of(analysis)
    if data.uncertainties:
        if not rules["let_uncertain"]:
            count = len(data.uncertainties)
            raise Stop(
                f"{count} uncertain {'detail' if count == 1 else 'details'} to check "
                "(uncertain details were not let through)."
            )
        accept_scene_details(session, scene, analysis.id, keep_prompt=True)
        analysis = latest(session, SceneAnalysis, scene.id)
        data = analysis_of(analysis)
    plan = build_plan(session, scene, analysis)
    if plan.blockers and rules["rule"] != "none" and not has_assignment(
        session, scene, data.subjects
    ):
        if rules["rule"] == "one":
            characters = _usable(session, [rules["character_id"]])
        else:
            characters = _usable(session, rules["order"])
        mappings = rule_mappings(data, rules["rule"], characters, rules["several_people"])
        if mappings is None:
            raise Stop(
                f"{len(data.subjects)} people: the rule only assigns one-person scenes. "
                "Choose by hand."
            )
        entries = [MappingEntry(**{k: v for k, v in m.items() if v is not None}) for m in mappings]
        group_id = rules["group_id"] if rules["rule"] == "group" else None
        save_assignments(session, scene, analysis, entries, group_id, len(characters))
        plan = build_plan(session, scene, analysis)
    if plan.blockers:
        raise Stop(plan.blockers[0])
    mismatch = mismatch_note(scene, data)
    if mismatch and not rules["let_mismatch"]:
        raise Stop(f"{mismatch} (mismatches were not let through).")
    prompt = latest(session, PromptVersion, scene.id)
    if not prompt_is_current(prompt, analysis, plan):
        if prompt is not None and (prompt.source != "template" or prompt.is_polished):
            # Never replace a prompt the user wrote or polished.
            raise Stop("Its saved prompt was made for an earlier analysis or other assignments.")
        draft_scene(session, scene, analysis, plan, changes, negatives)
    checked = review(session, scene)
    if checked.warnings:
        raise Stop(f"Its prompt has warnings: {checked.warnings[0]}")
    prompt = latest(session, PromptVersion, scene.id)
    approve_in_session(settings, session, scene, prompt.id, False, mode="auto")
    return "approved"


def _queue_generation(session, run: PipelineRun, rules: dict, scene_ids: list[str]) -> None:
    """Queue `images` runs per scene in chained batches of at most 20 images."""
    settings = session.get(EngineSettings, 1)
    engine = settings.generation_engine
    if engine != rules["generation_engine"]:
        started = run_label(rules["generation_engine"], "generation")
        run.status, run.updated_at = "paused", now()
        run.pause_details = (
            f"Run everything was started with {started}, but Studio settings now use "
            f"{run_label(engine, 'generation')}. Choose {started} there, then continue."
        )
        return
    api = is_image_engine(engine)
    mode = rules.get("mode", "generate")  # Generate all may ask for variations (Phase 7D)
    queued, stopped = [], []
    for scene_id in scene_ids:
        scene = session.get(Scene, scene_id)
        if scene is None:
            continue
        reason = None
        if active_job(session, scene.id):
            reason = "A run is running or waiting for it."
        else:
            try:
                approval = require_valid_approval(session, scene)
                text = generation_instruction(snapshot_of(approval)["inputs"], mode, api)
                if len(text) > MAX_GENERATION_INSTRUCTION:
                    reason = f"Its prompt is too long to send to {run_label(engine, 'generation')}."
            except ApprovalError as error:
                reason = str(error)
        if reason:
            stopped.append({"scene_id": scene.id, "title": scene.title, "reason": reason})
        else:
            queued.append((scene, approval))
    images = rules["images"]
    per_batch = max(1, MAX_GENERATION_RUNS // images)
    chunks = [queued[i : i + per_batch] for i in range(0, len(queued), per_batch)]
    base = datetime.now(UTC)
    timeout = engine_timeout(settings, engine)
    for index, chunk in enumerate(chunks):
        stamp = (base + timedelta(microseconds=index)).isoformat()
        batch = Batch(
            id=uuid4().hex,
            kind="generation",
            engine=engine,
            status="running",
            settings_json=json.dumps(
                {
                    "count": images,
                    "mode": mode,
                    **rules["image_run"],
                    **({"preset": rules["preset"]} if rules.get("preset") else {}),
                    "scene_set_id": run.scene_set_id,
                    "pipeline_id": run.id,
                    "part": index + 1,
                    "of": len(chunks),
                }
            ),
            created_at=stamp,
            updated_at=stamp,
        )
        session.add(batch)
        position = 0
        for scene, approval in chunk:
            for _ in range(images):
                session.add(
                    _generation_job(
                        batch, scene.id, approval.id, mode, position, timeout, stamp=stamp
                    )
                )
                position += 1
    session.flush()
    for scene, _approval in queued:
        refresh_workflow(session, scene)
    outcome = json.loads(run.outcome_json or "{}")
    outcome["images"] = len(queued) * images
    outcome["stopped"] = [*outcome.get("stopped", []), *stopped]
    run.outcome_json = json.dumps(outcome)
    run.stage, run.updated_at = "generating", now()
    if not queued:
        run.status = "finished"


# The user's buttons on a run ------------------------------------------------------------


@router.post("/pipelines/{run_id}/generate", status_code=202)
def generate(request: Request, run_id: str, body: ChargeInput | None = None):
    """A run that stopped before generating, as the user asked: start its images now."""
    with writing(request) as session:
        run = require_run(session, run_id)
        if run.status != "waiting":
            raise HTTPException(409, "This run is not waiting to generate.")
        rules = json.loads(run.rules_json)
        engine = rules["generation_engine"]
        if is_image_engine(engine) and not (body and body.confirm_charges):
            raise HTTPException(409, charge_confirmation(engine))
        scenes = set_scenes(session, run.scene_set_id)
        ready = [
            s.id
            for s in scenes
            if (a := current_approval(session, s.id)) is not None
            and not _has_result(session, a.id)
            and not active_job(session, s.id)
        ]
        if not ready:
            raise HTTPException(409, "No approved scene is waiting for images any more.")
        run.status = "running"
        _queue_generation(session, run, rules, ready)
        result = run_data(session, run)
    request.app.state.runner.notify()
    return result


@router.post("/pipelines/{run_id}/continue")
async def continue_run(request: Request, run_id: str, body: ChargeInput | None = None):
    """Only the user continues a run that a restart (or an engine change) paused, or a run
    whose batches a plan limit, a sign-out or the user paused (one click for all of them)."""
    with Session(request.app.state.engine) as session:
        run = require_run(session, run_id)
        paused = [
            b for b in run_batches(session, run_id) if b.status == "paused" and _left(session, b)
        ]
        if not _continuable(run, paused):
            raise HTTPException(409, "This run is not paused.")
        engines = {b.engine for b in paused}
    if any(is_api_engine(e) for e in engines) and not (body and body.confirm_charges):
        raise HTTPException(409, charge_confirmation(next(e for e in engines if is_api_engine(e))))
    for engine in engines:
        await run_in_threadpool(_check_engine, request, engine)
    with writing(request) as session:
        run = require_run(session, run_id)
        paused = [
            b for b in run_batches(session, run_id) if b.status == "paused" and _left(session, b)
        ]
        if not _continuable(run, paused):
            raise HTTPException(409, "This run is not paused.")
        images = [b for b in paused if b.kind == "generation"]
        if images:
            _require_generation_engine(session.get(EngineSettings, 1), images[0])
        for batch in paused:
            batch.status, batch.pause_kind, batch.pause_details = "running", None, None
            batch.updated_at = now()
        run.status, run.pause_details, run.updated_at = "running", None, now()
    await run_in_threadpool(
        advance_run, request.app.state.engine, request.app.state.settings, run_id
    )
    request.app.state.runner.notify()
    with Session(request.app.state.engine) as session:
        return run_data(session, require_run(session, run_id))


def _continuable(run: PipelineRun, paused: list[Batch]) -> bool:
    return run.status == "paused" or (run.status == "running" and bool(paused))


@router.post("/pipelines/{run_id}/retry", status_code=202)
def retry(request: Request, run_id: str, body: ChargeInput | None = None):
    """Try failed again for a whole run: the user's explicit choice, never automatic. Each
    failed image is queued once more as a new item in its own batch."""
    with writing(request) as session:
        run = require_run(session, run_id)
        if run.status != "finished":
            raise HTTPException(409, "Wait until the run has finished, then try again.")
        engine = json.loads(run.rules_json)["generation_engine"]
        if is_image_engine(engine) and not (body and body.confirm_charges):
            raise HTTPException(409, charge_confirmation(engine))
        added, skipped = 0, []
        for batch in run_batches(session, run.id, "generation"):
            if any(j.status == "failed" for j in live_jobs(session, [batch])):
                more, missed = retry_batch(session, batch)
                added, skipped = added + more, skipped + missed
        if not added:
            reasons = "; ".join(f"{s['title']}: {s['reason']}" for s in skipped[:5])
            raise HTTPException(409, f"No failed images are left to try again. {reasons}".strip())
        run.status, run.updated_at = "running", now()
        result = run_data(session, run) | {"skipped": skipped}
    request.app.state.runner.notify()
    return result


@router.post("/pipelines/{run_id}/cancel")
def cancel(request: Request, run_id: str):
    """Stop the run: nothing that has not started runs. A run in progress finishes."""
    with writing(request) as session:
        run = require_run(session, run_id)
        if run.status not in OPEN:
            raise HTTPException(409, "This run has already ended.")
        for batch in run_batches(session, run_id):
            if batch.status != "cancelled" and _left(session, batch):
                cancel_waiting(session, batch)
        run.status, run.updated_at = "cancelled", now()
        _note(run, "You cancelled the run. Everything finished before that is kept.")
        return run_data(session, run)


def pause_on_restart(session) -> None:
    """At start-up: a run that was moving waits for the user's Continue."""
    for run in session.scalars(select(PipelineRun).where(PipelineRun.status == "running")):
        kind = json.loads(run.rules_json).get("kind", "everything")
        message = GENERATE_RESTART_MESSAGE if kind == "generate" else RESTART_MESSAGE
        run.status, run.pause_details, run.updated_at = "paused", message, now()
