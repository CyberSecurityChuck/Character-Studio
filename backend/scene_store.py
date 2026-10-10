"""Small scene queries shared by the scene API, the workflow rules and the job runner."""

from datetime import UTC, datetime

from sqlalchemy import func, select

from backend.models import EngineJob

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
