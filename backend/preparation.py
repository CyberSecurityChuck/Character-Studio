"""Preparing a whole scene set (Phase 7B, D030, D035).

Analyse all, the Assign table with its fill rules, Draft prompts for all, optional Polish all
and the polished-prompt review. Every action works on the scenes of one set, goes through the
same checks as the single-scene action, and starts only from a user click. Nothing is
retried or continued automatically, and nothing here approves or generates anything.
"""

import json
from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.api_engines import engine_timeout
from backend.batches import MAX_ANALYSIS_RUNS, batch_data
from backend.models import (
    Batch,
    Character,
    CharacterGroup,
    EngineJob,
    EngineSettings,
    GenerationPreset,
    GroupMember,
    PromptVersion,
    Scene,
    SceneAnalysis,
    SubjectMapping,
)
from backend.prompting import build_prompt
from backend.quality import BUILTIN_BY_ID
from backend.scene_sets import require_set_row
from backend.scene_store import active_job, latest, now
from backend.scenes import (
    MappingEntry,
    _polish_job,
    api_run_settings,
    apply_polished,
    mismatch_note,
    pending_polish,
    queue_polish,
    save_assignments,
    writing,
)
from backend.workflow import (
    analysis_of,
    build_plan,
    character_photos,
    current_approval,
    largest_subject,
    left_to_right,
    next_prompt_version,
    prompt_is_current,
    refresh_workflow,
)

router = APIRouter(prefix="/api")


def set_scenes(session, scene_set_id: str) -> list[Scene]:
    require_set_row(session, scene_set_id)
    return list(
        session.scalars(
            select(Scene)
            .where(Scene.scene_set_id == scene_set_id)
            .order_by(Scene.created_at, Scene.id)
        )
    )


def skip(skipped: list[dict], scene: Scene, reason: str) -> None:
    skipped.append({"scene_id": scene.id, "title": scene.title, "reason": reason})


def append_lines(text: str, additions: str) -> str:
    """Add the preset's negative lines once each, like the Prompt step does."""
    have = {line.strip().lower() for line in text.splitlines() if line.strip()}
    extra = [
        line.strip()
        for line in additions.splitlines()
        if line.strip() and line.strip().lower() not in have
    ]
    if not extra:
        return text
    return text.rstrip() + ("\n" if text.strip() else "") + "\n".join(extra)


# What is left to do ------------------------------------------------------------------


@router.get("/scene-sets/{scene_set_id}/preparation")
def preparation(request: Request, scene_set_id: str):
    """How many scenes each preparation action would touch right now."""
    with Session(request.app.state.engine) as session:
        scenes = set_scenes(session, scene_set_id)
        counts = {
            key: 0
            for key in (
                "analyse",
                "assign",
                "assign_open",
                "draft",
                "redraft",
                "polish",
                "polish_waiting",
                "polish_running",
                "review",
                "mismatched",
                "busy",
            )
        }
        for scene in scenes:
            active = active_job(session, scene.id)
            if active is not None:
                if active.kind == "polish":
                    state = "running" if active.status == "running" else "waiting"
                    counts[f"polish_{state}"] += 1
                else:
                    counts["busy"] += 1
                continue
            analysis = latest(session, SceneAnalysis, scene.id)
            if analysis is None:
                counts["analyse"] += 1
                continue
            approved = current_approval(session, scene.id) is not None
            prompt = latest(session, PromptVersion, scene.id)
            waiting = pending_polish(session, scene, prompt) is not None
            if waiting:
                counts["review"] += 1
            if approved:
                continue
            counts["assign"] += 1
            if scene.workflow_state == "needs_mapping":
                counts["assign_open"] += 1
            if mismatch_note(scene, analysis_of(analysis)):
                counts["mismatched"] += 1
            if scene.workflow_state == "analysis_ready":
                counts["draft"] += 1
            elif scene.workflow_state == "prompt_saved":
                counts["redraft"] += 1
                if prompt is not None and not prompt.is_polished and not waiting:
                    counts["polish"] += 1
        return {"total": len(scenes), **counts}


# Analyse all ---------------------------------------------------------------------------


class AnalyseAllInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    # API engines: the user confirmed that every run may be charged (once for the whole run).
    confirm_charges: bool = False


@router.post("/scene-sets/{scene_set_id}/analyse-all", status_code=202)
def analyse_all(request: Request, scene_set_id: str, body: AnalyseAllInput):
    """Queue an analysis for every scene of the set that has none, in chained batches of 50.

    The batches run one after another (never in parallel); a plan limit pauses all of them.
    """
    with writing(request) as session:
        scenes = set_scenes(session, scene_set_id)
        settings = session.get(EngineSettings, 1)
        engine = settings.analysis_engine
        if engine == "manual":
            raise HTTPException(
                409, "Manual analysis is selected in Studio settings, so nothing can be queued."
            )
        queued, skipped = [], []
        for scene in scenes:
            if latest(session, SceneAnalysis, scene.id) is not None:
                continue
            if active_job(session, scene.id):
                skip(skipped, scene, "Another run is running or waiting for it.")
            else:
                queued.append(scene)
        if not queued:
            raise HTTPException(
                409, "Nothing to analyse: every scene in this set already has an analysis."
            )
        run = api_run_settings(request, settings, engine, body.confirm_charges)
        timeout = engine_timeout(settings, engine)
        chunks = [
            queued[i : i + MAX_ANALYSIS_RUNS] for i in range(0, len(queued), MAX_ANALYSIS_RUNS)
        ]
        base = datetime.now(UTC)
        batches = []
        for index, chunk in enumerate(chunks):
            # Strictly increasing stamps keep the runner on one batch at a time, in order.
            stamp = (base + timedelta(microseconds=index)).isoformat()
            batch = Batch(
                id=uuid4().hex,
                kind="analysis",
                engine=engine,
                status="running",
                settings_json=json.dumps(
                    {**run, "scene_set_id": scene_set_id, "part": index + 1, "of": len(chunks)}
                ),
                created_at=stamp,
                updated_at=stamp,
            )
            session.add(batch)
            for position, scene in enumerate(chunk):
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
                        created_at=stamp,
                    )
                )
            batches.append(batch)
        session.flush()
        for scene in queued:
            refresh_workflow(session, scene)
        result = {
            "batches": [batch_data(session, b) for b in batches],
            "queued": len(queued),
            "skipped": skipped,
        }
    request.app.state.runner.notify()
    return result


# Assign table -----------------------------------------------------------------------------


def row_lock(session, scene: Scene) -> str | None:
    if active_job(session, scene.id):
        return "A run is running or waiting for it."
    if current_approval(session, scene.id) is not None:
        return "Approved. Withdraw the approval in the scene to change who is assigned."
    return None


@router.get("/scene-sets/{scene_set_id}/assign")
def assign_rows(request: Request, scene_set_id: str):
    """One row per analysed scene: the people found and who each is assigned to."""
    with Session(request.app.state.engine) as session:
        scenes = set_scenes(session, scene_set_id)
        rows, waiting = [], 0
        for scene in scenes:
            analysis = latest(session, SceneAnalysis, scene.id)
            if analysis is None:
                waiting += 1
                continue
            plan = build_plan(session, scene, analysis)
            described = {s.label: s for s in plan.analysis.subjects}
            rows.append(
                {
                    "scene_id": scene.id,
                    "title": scene.title,
                    "revision": scene.revision,
                    "thumbnail_url": f"/api/scenes/{scene.id}/image/thumbnail",
                    "stage": scene.workflow_state,
                    "locked": row_lock(session, scene),
                    "mismatch": mismatch_note(scene, plan.analysis),
                    "group_id": scene.mapping_group_id,
                    "people": [
                        {
                            "label": item.label,
                            "bounding_box": described[item.label].bounding_box.model_dump(),
                            "summary": described[item.label].pose_summary
                            or described[item.label].outfit,
                            "action": item.action,
                            "character_id": item.character.id if item.character else None,
                            "confirmed": item.confirmed and not item.suggested,
                        }
                        for item in plan.subjects
                    ],
                }
            )
        return {"rows": rows, "not_analysed": waiting}


class FillInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rule: Literal["one", "group"]
    # One character for every one-person scene.
    character_id: str | None = Field(default=None, max_length=32)
    # A group, left to right, as Suggest from group does.
    group_id: str | None = Field(default=None, max_length=32)
    order: list[str] = Field(default_factory=list, max_length=20)
    # "one" only: what to do with scenes that show several people.
    several_people: Literal["skip", "largest"] = "skip"
    # Leave rows that already have someone assigned alone.
    only_empty: bool = True


def _usable(session, character_ids: list[str]) -> list[Character]:
    people = []
    for character_id in character_ids:
        character = session.get(Character, character_id)
        if character is None:
            raise HTTPException(404, "A chosen character no longer exists. Reload the page.")
        if character.archived or not character_photos(session, character_id):
            raise HTTPException(
                409, f"{character.name} cannot be used: restore them or add a reference photo."
            )
        people.append(character)
    return people


@router.post("/scene-sets/{scene_set_id}/assign/fill")
def fill_rows(request: Request, scene_set_id: str, body: FillInput):
    """Propose assignments for the rows by a rule. Nothing is saved: the user sees the
    proposal in the table, can change any row, and saves the table."""
    with Session(request.app.state.engine) as session:
        scenes = set_scenes(session, scene_set_id)
        if body.rule == "one":
            if not body.character_id:
                raise HTTPException(422, "Choose the character to fill in.")
            characters = _usable(session, [body.character_id])
        else:
            if len(set(body.order)) != len(body.order) or not body.order:
                raise HTTPException(422, "Arrange the group's characters first.")
            if body.group_id:
                members = set(
                    session.scalars(
                        select(GroupMember.character_id).where(
                            GroupMember.group_id == body.group_id
                        )
                    )
                )
                if session.get(CharacterGroup, body.group_id) is None or not (
                    set(body.order) <= members
                ):
                    raise HTTPException(
                        409, "The group changed in another window. Reload the page."
                    )
            characters = _usable(session, body.order)
        proposals, skipped = [], []
        for scene in scenes:
            analysis = latest(session, SceneAnalysis, scene.id)
            if analysis is None:
                continue
            if (reason := row_lock(session, scene)) is not None:
                skip(skipped, scene, reason)
                continue
            data = analysis_of(analysis)
            people = data.subjects
            if body.only_empty and (
                session.scalar(
                    select(SubjectMapping.id)
                    .where(
                        SubjectMapping.scene_id == scene.id, SubjectMapping.action != "unresolved"
                    )
                    .limit(1)
                )
                or (not people and scene.intended_characters is not None)
            ):
                skip(skipped, scene, "Someone is already assigned.")
                continue
            if not people:
                # Nothing to assign; saving the row labels the scene "No people found".
                proposals.append(
                    {"scene_id": scene.id, "mappings": [], "intended": len(characters)}
                )
                continue
            if body.rule == "one":
                if len(people) > 1 and body.several_people == "skip":
                    skip(skipped, scene, f"{len(people)} people: choose by hand or tick the box.")
                    continue
                biggest = largest_subject(data)
                chosen = {biggest.label: characters[0].id}
            else:
                ordered = left_to_right(data)
                chosen = {s.label: c.id for s, c in zip(ordered, characters, strict=False)}
            mappings = [
                {"label": s.label, "action": "replace", "character_id": chosen[s.label]}
                if s.label in chosen
                else {"label": s.label, "action": "keep", "character_id": None}
                for s in people
            ]
            proposals.append(
                {"scene_id": scene.id, "mappings": mappings, "intended": len(characters)}
            )
        return {"proposals": proposals, "skipped": skipped}


class AssignRow(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scene_id: str = Field(max_length=32)
    revision: int = Field(ge=1)
    mappings: list[MappingEntry] = Field(max_length=20)
    # Characters a fill rule meant to place; None when the user chose by hand.
    intended: int | None = Field(default=None, ge=0, le=20)
    group_id: str | None = Field(default=None, max_length=32)


class AssignInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rows: list[AssignRow] = Field(min_length=1, max_length=500)


@router.put("/scene-sets/{scene_set_id}/assign")
def save_assign(request: Request, scene_set_id: str, body: AssignInput):
    """Save the table: each row is checked and saved on its own, as confirmed assignments."""
    if len({r.scene_id for r in body.rows}) != len(body.rows):
        raise HTTPException(422, "A scene appears twice.")
    saved, failed = [], []
    for row in body.rows:
        try:
            with writing(request) as session:
                scene = session.get(Scene, row.scene_id)
                if scene is None or scene.scene_set_id != scene_set_id:
                    raise HTTPException(404, "This scene is no longer in the set.")
                if scene.revision != row.revision:
                    raise HTTPException(409, "It changed in another window. Reload the table.")
                if (reason := row_lock(session, scene)) is not None:
                    raise HTTPException(409, reason)
                analysis = latest(session, SceneAnalysis, scene.id)
                if analysis is None:
                    raise HTTPException(409, "Analyse the scene before assigning characters.")
                if row.group_id and session.get(CharacterGroup, row.group_id) is None:
                    raise HTTPException(404, "That group no longer exists. Reload the page.")
                save_assignments(
                    session, scene, analysis, row.mappings, row.group_id, row.intended
                )
                title = scene.title
            saved.append({"scene_id": row.scene_id, "title": title})
        except HTTPException as error:
            with Session(request.app.state.engine) as session:
                scene = session.get(Scene, row.scene_id)
                title = scene.title if scene else "A scene"
            failed.append({"scene_id": row.scene_id, "title": title, "reason": error.detail})
    return {"saved": saved, "failed": failed}


# Draft prompts for all ------------------------------------------------------------------


class DraftAllInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    preset_id: str | None = Field(default=None, max_length=32)
    # Also write a new version for scenes whose saved prompt is already current.
    replace_existing: bool = False


def preset_texts(session, preset_id: str | None) -> tuple[str, str, str | None]:
    """Scene changes, negative additions and the name of a chosen preset."""
    if not preset_id:
        return "", "", None
    if preset_id in BUILTIN_BY_ID:
        item = BUILTIN_BY_ID[preset_id]
        return item["scene_changes"], item["negative_additions"], item["name"]
    preset = session.get(GenerationPreset, preset_id)
    if preset is None:
        raise HTTPException(409, "The chosen preset no longer exists. Reload the page.")
    return preset.scene_changes, preset.negative_additions, preset.name


@router.post("/scene-sets/{scene_set_id}/draft-prompts")
def draft_all(request: Request, scene_set_id: str, body: DraftAllInput):
    """Save the studio's own template draft as the next prompt version of each ready scene.

    No engine runs. A scene is ready when its analysis has nothing uncertain and every
    person is assigned; scenes that are approved or running are left alone.
    """
    with writing(request) as session:
        scenes = set_scenes(session, scene_set_id)
        changes, negatives, preset_name = preset_texts(session, body.preset_id)
        drafted, skipped = [], []
        for scene in scenes:
            analysis = latest(session, SceneAnalysis, scene.id)
            if analysis is None:
                skip(skipped, scene, "Analyse it first.")
                continue
            if active_job(session, scene.id):
                skip(skipped, scene, "A run is running or waiting for it.")
                continue
            if current_approval(session, scene.id) is not None:
                skip(skipped, scene, "It is approved. Withdraw the approval to change its prompt.")
                continue
            plan = build_plan(session, scene, analysis)
            if plan.analysis.uncertainties:
                skip(skipped, scene, "Confirm the uncertain details in its analysis first.")
                continue
            if plan.blockers:
                skip(skipped, scene, "Assign every person first.")
                continue
            prompt = latest(session, PromptVersion, scene.id)
            if prompt_is_current(prompt, analysis, plan) and not body.replace_existing:
                skip(skipped, scene, "It already has a saved prompt.")
                continue
            text, negative = build_prompt(plan.analysis, changes, plan.assignments)
            version = next_prompt_version(session, scene.id)
            session.add(
                PromptVersion(
                    id=uuid4().hex,
                    scene_id=scene.id,
                    analysis_id=analysis.id,
                    mapping_hash=plan.mapping_hash,
                    version=version,
                    prompt_text=text,
                    negative_prompt=append_lines(negative, negatives),
                    scene_changes=changes,
                    source="template",
                    is_polished=False,
                    created_at=now(),
                )
            )
            session.flush()
            scene.updated_at = now()
            refresh_workflow(session, scene)
            drafted.append({"scene_id": scene.id, "title": scene.title, "version": version})
        return {"drafted": drafted, "skipped": skipped, "preset": preset_name}


# Polish all and its review -----------------------------------------------------------------


@router.post("/scene-sets/{scene_set_id}/polish-all", status_code=202)
def polish_all(request: Request, scene_set_id: str):
    """Queue one Claude polish run per scene with a current saved prompt. Optional: it uses
    the Claude plan's allowance once per scene. Results wait for the user's review."""
    with writing(request) as session:
        scenes = set_scenes(session, scene_set_id)
        queued, skipped = [], []
        for scene in scenes:
            prompt = latest(session, PromptVersion, scene.id)
            if scene.workflow_state != "prompt_saved" or prompt is None:
                continue
            if prompt.is_polished:
                skip(skipped, scene, "Its prompt is already polished.")
            elif pending_polish(session, scene, prompt) is not None:
                skip(skipped, scene, "A polished version is waiting for your review.")
            elif active_job(session, scene.id):
                skip(skipped, scene, "A run is running or waiting for it.")
            else:
                try:
                    queue_polish(session, scene, prompt)
                    queued.append(scene.id)
                except HTTPException as error:
                    skip(skipped, scene, str(error.detail))
        if not queued:
            raise HTTPException(
                409,
                "Nothing to polish: scenes need a current saved prompt that is not polished yet.",
            )
        result = {"queued": len(queued), "skipped": skipped}
    request.app.state.runner.notify()
    return result


@router.post("/scene-sets/{scene_set_id}/polish-all/cancel")
def cancel_polish_all(request: Request, scene_set_id: str):
    """Cancel the polish runs of this set that have not started. A running one finishes."""
    with Session(request.app.state.engine) as session:
        waiting = [
            job.id
            for scene in set_scenes(session, scene_set_id)
            for job in session.scalars(
                select(EngineJob).where(
                    EngineJob.scene_id == scene.id,
                    EngineJob.kind == "polish",
                    EngineJob.status == "not_started",
                )
            )
        ]
    for job_id in waiting:
        request.app.state.runner.cancel(job_id)
    with writing(request) as session:
        for scene in set_scenes(session, scene_set_id):
            refresh_workflow(session, scene)
    return {"cancelled": len(waiting)}


@router.get("/scene-sets/{scene_set_id}/polish-review")
def polish_review(request: Request, scene_set_id: str):
    """Each finished polish waiting for a decision, beside the prompt it would replace."""
    with Session(request.app.state.engine) as session:
        rows = []
        for scene in set_scenes(session, scene_set_id):
            prompt = latest(session, PromptVersion, scene.id)
            pending = pending_polish(session, scene, prompt)
            if pending is None:
                continue
            rows.append(
                {
                    "scene_id": scene.id,
                    "title": scene.title,
                    "thumbnail_url": f"/api/scenes/{scene.id}/image/thumbnail",
                    "job_id": pending["job_id"],
                    "prompt_version": pending["prompt_version"],
                    "current_text": prompt.prompt_text,
                    "polished_text": pending["polished_text"],
                    "missing": pending["missing"],
                }
            )
        return {"rows": rows}


class PolishDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scene_id: str = Field(max_length=32)
    job_id: str = Field(max_length=32)
    decision: Literal["use", "keep"]


class PolishDecisions(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decisions: list[PolishDecision] = Field(min_length=1, max_length=500)


@router.post("/scene-sets/{scene_set_id}/polish-review")
def decide_polish(request: Request, scene_set_id: str, body: PolishDecisions):
    """Apply the user's choices. Using a polished prompt that lost required elements is
    refused here (open the scene to fix it by hand or accept it knowingly)."""
    done, failed = [], []
    for item in body.decisions:
        try:
            with writing(request) as session:
                scene = session.get(Scene, item.scene_id)
                if scene is None or scene.scene_set_id != scene_set_id:
                    raise HTTPException(404, "This scene is no longer in the set.")
                job = _polish_job(session, scene.id, item.job_id)
                if item.decision == "keep":
                    job.decision = "kept"
                else:
                    apply_polished(session, scene, item.job_id, job.output_text, False)
                title = scene.title
            done.append({"scene_id": item.scene_id, "title": title, "decision": item.decision})
        except HTTPException as error:
            with Session(request.app.state.engine) as session:
                scene = session.get(Scene, item.scene_id)
                title = scene.title if scene else "A scene"
            failed.append({"scene_id": item.scene_id, "title": title, "reason": error.detail})
    return {"done": done, "failed": failed}
