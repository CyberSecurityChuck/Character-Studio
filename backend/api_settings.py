"""Studio settings for the optional API engines: keys and model lists (Phase 6A, D022).

Keys are write-only from the browser: they can be saved, replaced or removed, never read
back. "Test key" uses each provider's free model-list call; it runs only when clicked.
"""

import json

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from backend.api_engines import API_ENGINES, list_models, model_lists_of
from backend.engines import EngineError
from backend.image_api import IMAGE_ENGINES
from backend.keystore import KeyStoreError, delete_key, key_info, save_key
from backend.models import EngineJob, EngineSettings
from backend.persistence import writing_session
from backend.scene_store import now

router = APIRouter(prefix="/api")


class KeyInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    key: str = Field(min_length=1, max_length=400)


def require_engine(engine: str):
    if engine not in API_ENGINES:
        raise HTTPException(404, "Unknown API engine.")
    return API_ENGINES[engine]


def typical_usage(session, engine: str, kind: str = "analysis") -> dict | None:
    """Average tokens of completed runs of this kind with this engine, for the cost dialog."""
    used = []
    for raw in session.scalars(
        select(EngineJob.settings_json).where(
            EngineJob.engine == engine,
            EngineJob.kind == kind,
            EngineJob.status == "completed",
        )
    ):
        usage = json.loads(raw or "{}").get("usage") or {}
        tokens = (usage.get("input_tokens"), usage.get("output_tokens"))
        if all(isinstance(t, int) for t in tokens):
            used.append(tokens)
    if not used:
        return None
    return {
        "runs": len(used),
        "input_tokens": round(sum(u[0] for u in used) / len(used)),
        "output_tokens": round(sum(u[1] for u in used) / len(used)),
    }


def engine_data(request: Request, engine: str, models_error: str | None = None) -> dict:
    item = API_ENGINES[engine]
    with Session(request.app.state.engine) as session:
        typical = typical_usage(session, engine)
        typical_image = typical_usage(session, engine, "generation")
        saved = model_lists_of(session.get(EngineSettings, 1)).get(engine) or {}
    image = IMAGE_ENGINES.get(engine)
    return {
        "id": item.id,
        "name": item.name,
        "company": item.company,
        "key_help": item.key_help,
        "pricing_url": item.pricing_url,
        "suggested_model": item.suggested_model,
        "charge_note": item.charge_note,
        "key": key_info(request.app.state.settings, engine),
        "typical_usage": typical,
        # Phase 6C: engines that can also make images, and their own figures and models.
        "makes_images": image is not None,
        "image_name": image.name if image else None,
        "suggested_image_model": image.suggested_model if image else None,
        "image_charge_note": image.charge_note if image else None,
        "typical_image_usage": typical_image,
        "image_models": saved.get("image_models", []),
        # The last list the key returned, kept so the model picker is filled on every visit.
        "models": saved.get("models", []),
        "models_checked_at": saved.get("checked_at"),
        "models_error": models_error,
    }


def _store_list(request: Request, engine: str, models: tuple[list, list] | None) -> None:
    with writing_session(request.app.state.engine) as session:
        row = session.get(EngineSettings, 1)
        lists = model_lists_of(row)
        if models is None:
            lists.pop(engine, None)
        else:
            lists[engine] = {"models": models[0], "image_models": models[1], "checked_at": now()}
        row.model_lists_json = json.dumps(lists, sort_keys=True)


async def _refresh(request: Request, engine: str) -> str | None:
    """Fetch the model list with the saved key (a free call). Returns an error message."""
    try:
        models = await run_in_threadpool(list_models, request.app.state.settings, engine)
    except EngineError as error:
        return error.message
    _store_list(request, engine, models)
    return None


@router.get("/api-engines")
def api_engines(request: Request):
    return [engine_data(request, engine) for engine in API_ENGINES]


@router.put("/api-engines/{engine}/key")
async def store_key(request: Request, engine: str, body: KeyInput):
    """Save the key, then fetch its model list once so the picker is ready."""
    require_engine(engine)
    try:
        save_key(request.app.state.settings, engine, body.key)
    except KeyStoreError as error:
        raise HTTPException(422, str(error)) from error
    _store_list(request, engine, None)
    return engine_data(request, engine, await _refresh(request, engine))


@router.delete("/api-engines/{engine}/key")
def remove_key(request: Request, engine: str):
    item = require_engine(engine)
    with Session(request.app.state.engine) as session:
        row = session.get(EngineSettings, 1)
        for purpose, selected in (
            ("analysis", row.analysis_engine),
            ("generation", row.generation_engine),
        ):
            if selected == engine:
                raise HTTPException(
                    409, f"The {item.name} is the selected {purpose} engine. Choose another first."
                )
    delete_key(request.app.state.settings, engine)
    _store_list(request, engine, None)
    return engine_data(request, engine)


@router.post("/api-engines/{engine}/models")
async def test_key(request: Request, engine: str):
    """Check the saved key and refresh its model list (free); nothing is generated."""
    require_engine(engine)
    error = await _refresh(request, engine)
    if error:
        raise HTTPException(409, error)
    return engine_data(request, engine)
