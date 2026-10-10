"""Scene state shared by the scene API and the job runner."""

import json
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import func, select

from backend.analysis_schema import SCHEMA_VERSION, SceneAnalysisData
from backend.models import EngineJob, PromptVersion, Scene, SceneAnalysis

ACTIVE_STATUSES = ("not_started", "running")


def now():
    return datetime.now(UTC).isoformat()


def latest(session, model, scene_id):
    return session.scalar(
        select(model).where(model.scene_id == scene_id).order_by(model.version.desc()).limit(1)
    )


def next_version(session, model, scene_id) -> int:
    highest = session.scalar(select(func.max(model.version)).where(model.scene_id == scene_id))
    return (highest or 0) + 1


def active_job(session, scene_id):
    return session.scalar(
        select(EngineJob)
        .where(EngineJob.scene_id == scene_id, EngineJob.status.in_(ACTIVE_STATUSES))
        .order_by(EngineJob.created_at)
        .limit(1)
    )


def refresh_workflow(session, scene: Scene) -> None:
    """Derive the saved workflow stage from what exists; called after every change."""
    analysis = latest(session, SceneAnalysis, scene.id)
    prompt = latest(session, PromptVersion, scene.id)
    if active_job(session, scene.id):
        state = "analysing"
    elif analysis is None:
        state = "needs_analysis"
    elif json.loads(analysis.structured_analysis)["uncertainties"]:
        state = "review_analysis"
    elif prompt is not None and prompt.analysis_id == analysis.id:
        state = "prompt_saved"
    else:
        state = "analysis_ready"
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
