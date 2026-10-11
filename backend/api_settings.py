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

from backend.api_engines import API_ENGINES, list_models
from backend.engines import EngineError
from backend.keystore import KeyStoreError, delete_key, key_info, save_key
from backend.models import EngineJob, EngineSettings

router = APIRouter(prefix="/api")


class KeyInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    key: str = Field(min_length=1, max_length=400)


def require_engine(engine: str):
    if engine not in API_ENGINES:
        raise HTTPException(404, "Unknown API engine.")
    return API_ENGINES[engine]


def typical_usage(session, engine: str) -> dict | None:
    """Average tokens of completed analyses with this engine, for the cost dialog."""
    used = []
    for raw in session.scalars(
        select(EngineJob.settings_json).where(
            EngineJob.engine == engine,
            EngineJob.kind == "analysis",
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


def engine_data(request: Request, engine: str) -> dict:
    item = API_ENGINES[engine]
    with Session(request.app.state.engine) as session:
        typical = typical_usage(session, engine)
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
    }


@router.get("/api-engines")
def api_engines(request: Request):
    return [engine_data(request, engine) for engine in API_ENGINES]


@router.put("/api-engines/{engine}/key")
def store_key(request: Request, engine: str, body: KeyInput):
    require_engine(engine)
    try:
        save_key(request.app.state.settings, engine, body.key)
    except KeyStoreError as error:
        raise HTTPException(422, str(error)) from error
    return engine_data(request, engine)


@router.delete("/api-engines/{engine}/key")
def remove_key(request: Request, engine: str):
    item = require_engine(engine)
    with Session(request.app.state.engine) as session:
        if session.get(EngineSettings, 1).analysis_engine == engine:
            raise HTTPException(
                409, f"The {item.name} is the selected analysis engine. Choose another first."
            )
    delete_key(request.app.state.settings, engine)
    return engine_data(request, engine)


@router.post("/api-engines/{engine}/models")
async def test_key(request: Request, engine: str):
    """Check the saved key with the provider's free model list; nothing is generated."""
    require_engine(engine)
    try:
        models = await run_in_threadpool(list_models, request.app.state.settings, engine)
    except EngineError as error:
        raise HTTPException(409, error.message) from error
    return {"models": models}
