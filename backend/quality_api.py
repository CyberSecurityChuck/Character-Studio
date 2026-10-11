"""Quality checks and saved generation presets (Phase 6B, DECISIONS.md D023)."""

import json
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from backend.api_engines import engine_timeout
from backend.models import EngineJob, EngineSettings, GenerationPreset, QualityCheck
from backend.quality import check_data
from backend.results import require_result
from backend.scene_store import now
from backend.scenes import (
    AnalyseInput,
    api_run_settings,
    require_idle,
    require_scene,
    scene_detail,
    writing,
)
from backend.workflow import refresh_workflow

router = APIRouter(prefix="/api")
MAX_PRESETS = 100


@router.post("/results/{result_id}/check", status_code=202)
def check_result(request: Request, result_id: str, body: AnalyseInput | None = None):
    """Queue one quality check with the selected analysis engine. Runs once, never retried."""
    with writing(request) as session:
        result = require_result(session, result_id)
        scene = require_scene(session, result.scene_id)
        settings = session.get(EngineSettings, 1)
        engine = settings.analysis_engine
        if engine == "manual":
            raise HTTPException(
                409,
                "Quality checks need an analysis engine. Choose Claude, Codex or an API engine "
                "in Studio settings.",
            )
        require_idle(session, scene.id, "checking a result")
        run = api_run_settings(request, settings, engine, bool(body and body.confirm_charges))
        session.add(
            EngineJob(
                id=uuid4().hex,
                kind="check",
                scene_id=scene.id,
                engine=engine,
                status="not_started",
                input_id=result.id,
                settings_json=json.dumps(run) if run else None,
                timeout_seconds=engine_timeout(settings, engine),
                created_at=now(),
            )
        )
        session.flush()
        refresh_workflow(session, scene)
        detail = scene_detail(request, session, scene)
    request.app.state.runner.notify()
    return detail


@router.get("/results/{result_id}/checks")
def result_checks(request: Request, result_id: str):
    with Session(request.app.state.engine) as session:
        require_result(session, result_id)
        checks = session.scalars(
            select(QualityCheck)
            .where(QualityCheck.result_id == result_id)
            .order_by(QualityCheck.created_at.desc())
        )
        return [check_data(c) for c in checks]


@router.delete("/checks/{check_id}")
def delete_check(request: Request, check_id: str):
    with writing(request) as session:
        check = session.get(QualityCheck, check_id)
        if check is None:
            raise HTTPException(404, "This check no longer exists.")
        session.delete(check)
    return {"deleted": True}


class PresetInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=60)
    scene_changes: str = Field(default="", max_length=4000)
    negative_additions: str = Field(default="", max_length=2000)
    images: int = Field(default=1, ge=1, le=10)
    revision: int | None = Field(default=None, ge=1)

    @field_validator("name")
    @classmethod
    def single_line(cls, value: str) -> str:
        if "\n" in value or "\r" in value:
            raise ValueError("Use a one-line name.")
        return value


def preset_data(preset: GenerationPreset) -> dict:
    return {
        "id": preset.id,
        "name": preset.name,
        "scene_changes": preset.scene_changes,
        "negative_additions": preset.negative_additions,
        "images": preset.images,
        "revision": preset.revision,
        "created_at": preset.created_at,
        "updated_at": preset.updated_at,
    }


def _name_taken(session, name: str, own_id: str | None = None) -> bool:
    found = session.scalar(
        select(GenerationPreset.id).where(func.lower(GenerationPreset.name) == name.lower())
    )
    return found is not None and found != own_id


@router.get("/presets")
def presets(request: Request):
    with Session(request.app.state.engine) as session:
        order = func.lower(GenerationPreset.name)
        items = session.scalars(select(GenerationPreset).order_by(order))
        return [preset_data(p) for p in items]


@router.post("/presets", status_code=201)
def create_preset(request: Request, body: PresetInput):
    with writing(request) as session:
        if session.scalar(select(func.count()).select_from(GenerationPreset)) >= MAX_PRESETS:
            raise HTTPException(409, f"You can keep up to {MAX_PRESETS} presets.")
        if _name_taken(session, body.name):
            raise HTTPException(409, f"A preset called “{body.name}” already exists.")
        stamp = now()
        preset = GenerationPreset(
            id=uuid4().hex,
            **body.model_dump(exclude={"revision"}),
            revision=1,
            created_at=stamp,
            updated_at=stamp,
        )
        session.add(preset)
        session.flush()
        return preset_data(preset)


def require_preset(session, preset_id: str) -> GenerationPreset:
    preset = session.get(GenerationPreset, preset_id)
    if preset is None:
        raise HTTPException(404, "This preset no longer exists. Reload the page.")
    return preset


@router.put("/presets/{preset_id}")
def update_preset(request: Request, preset_id: str, body: PresetInput):
    with writing(request) as session:
        preset = require_preset(session, preset_id)
        if body.revision != preset.revision:
            raise HTTPException(409, "This preset changed in another window. Reload it first.")
        if _name_taken(session, body.name, preset.id):
            raise HTTPException(409, f"A preset called “{body.name}” already exists.")
        for key, value in body.model_dump(exclude={"revision"}).items():
            setattr(preset, key, value)
        preset.revision += 1
        preset.updated_at = now()
        return preset_data(preset)


@router.delete("/presets/{preset_id}")
def delete_preset(request: Request, preset_id: str):
    """Results keep the preset name recorded with their run; nothing else changes."""
    with writing(request) as session:
        session.execute(delete(GenerationPreset).where(GenerationPreset.id == preset_id))
    return {"deleted": True}
