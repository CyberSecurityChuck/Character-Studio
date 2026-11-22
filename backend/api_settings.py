"""Studio settings for the optional API engines: keys and model lists (Phase 6A, D022).

Keys are write-only from the browser: they can be saved, replaced or removed, never read
back. "Test key" uses each provider's free model-list call; it runs only when clicked.

Phase 8B (D041, D042): several keys per provider, each with a name. Each engine panel
chooses the key its runs use (saved with the panel, like the CLI accounts); FLUX's key
is chosen here directly, since region editing has no panel of its own.
"""

import json

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from backend import keystore
from backend.api_engines import API_ENGINES, list_models, model_lists_of
from backend.engines import EngineError
from backend.image_api import IMAGE_ENGINES
from backend.keystore import KeyStoreError
from backend.models import EngineJob, EngineSettings
from backend.persistence import writing_session
from backend.scene_store import now

router = APIRouter(prefix="/api")


class NewKeyInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    label: str = Field(min_length=1, max_length=200)
    key: str = Field(min_length=1, max_length=400)


class KeyChange(BaseModel):
    """Rename a key, replace it, or both; the key itself is never sent back."""

    model_config = ConfigDict(extra="forbid")
    label: str | None = Field(default=None, min_length=1, max_length=200)
    key: str | None = Field(default=None, min_length=1, max_length=400)


class ChooseKeyInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    key_id: str = Field(min_length=1, max_length=40)
    # analysis or generation; none chooses it for every purpose of the provider.
    purpose: str | None = Field(default=None, max_length=20)


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


def waiting_on(session, engine: str, key_id: str) -> int:
    """Runs queued or in progress on this key (they keep it once queued)."""
    jobs = session.scalars(
        select(EngineJob.settings_json).where(
            EngineJob.engine == engine, EngineJob.status.in_(("not_started", "running"))
        )
    )
    return sum(1 for raw in jobs if keystore.recorded(raw)[0] == key_id)


def engine_data(request: Request, engine: str, models_error: str | None = None) -> dict:
    item = API_ENGINES[engine]
    settings = request.app.state.settings
    listed = keystore.keys(settings, engine)
    with Session(request.app.state.engine) as session:
        typical = typical_usage(session, engine)
        typical_image = typical_usage(session, engine, "generation")
        saved = model_lists_of(session.get(EngineSettings, 1)).get(engine) or {}
        busy = {k["id"]: waiting_on(session, engine, k["id"]) for k in listed}
    image = IMAGE_ENGINES.get(engine)
    return {
        "id": item.id,
        "name": item.name,
        "company": item.company,
        "key_help": item.key_help,
        "pricing_url": item.pricing_url,
        "suggested_model": item.suggested_model,
        "charge_note": item.charge_note,
        # Whether any key is saved; `keys` lists them by name (never the key itself).
        "key": keystore.key_info(settings, engine),
        "keys": [
            {
                "id": k["id"],
                "label": k["label"],
                "saved_at": k["saved_at"],
                "waiting": busy[k["id"]],
            }
            for k in listed
        ],
        # The key new runs use, per purpose (Phase 8B), as saved with the engine panels.
        "active": {
            purpose: (keystore.active(settings, engine, purpose) or {}).get("id")
            for purpose in keystore.PURPOSES[engine]
        },
        # Phase 8C: each panel's fallback list, so a charge confirmation can name its keys.
        "fallback": {
            purpose: keystore.fallback_of(settings, engine, purpose)
            for purpose in keystore.PURPOSES[engine]
        },
        "typical_usage": typical,
        # Phase 6C: engines that can also make images, and their own figures and models.
        "makes_images": image is not None,
        "image_name": image.name if image else None,
        "suggested_image_model": image.suggested_model if image else None,
        "image_charge_note": image.charge_note if image else None,
        "typical_image_usage": typical_image,
        "image_models": saved.get("image_models", []),
        # The last list a key returned, kept so the model picker is filled on every visit.
        "models": saved.get("models", []),
        "models_checked_at": saved.get("checked_at"),
        "models_listed_by": saved.get("listed_by"),
        "models_error": models_error,
    }


def _store_list(request: Request, engine: str, models: tuple[list, list] | None, by=None) -> None:
    with writing_session(request.app.state.engine) as session:
        row = session.get(EngineSettings, 1)
        lists = model_lists_of(row)
        if models is None:
            lists.pop(engine, None)
        else:
            lists[engine] = {
                "models": models[0],
                "image_models": models[1],
                "checked_at": now(),
                "listed_by": by,
            }
        row.model_lists_json = json.dumps(lists, sort_keys=True)


async def _refresh(request: Request, engine: str, key: dict) -> str | None:
    """Fetch the model list with one saved key (a free call). Returns an error message."""
    try:
        models = await run_in_threadpool(
            list_models, request.app.state.settings, engine, key["id"]
        )
    except EngineError as error:
        return error.message
    _store_list(request, engine, models, key["label"])
    return None


def _require_key(request: Request, engine: str, key_id: str) -> dict:
    key = keystore.find(request.app.state.settings, engine, key_id)
    if key is None:
        raise HTTPException(404, "That key no longer exists. Reload the page.")
    return key


@router.get("/api-engines")
def api_engines(request: Request):
    return [engine_data(request, engine) for engine in API_ENGINES]


@router.post("/api-engines/{engine}/keys", status_code=201)
async def add_key(request: Request, engine: str, body: NewKeyInput):
    """Save a new key under a name, then fetch its model list once so the picker is ready."""
    require_engine(engine)
    try:
        key = keystore.add_key(request.app.state.settings, engine, body.label, body.key)
    except KeyStoreError as error:
        raise HTTPException(422, str(error)) from error
    error = await _refresh(request, engine, key)
    return {"key_id": key["id"], **engine_data(request, engine, error)}


@router.put("/api-engines/{engine}/keys/{key_id}")
async def change_key(request: Request, engine: str, key_id: str, body: KeyChange):
    """Rename a key or put a new key in its place (then its model list is fetched again).
    Runs already queued on it keep its id, so a replaced key is used for them too."""
    require_engine(engine)
    settings = request.app.state.settings
    _require_key(request, engine, key_id)
    try:
        if body.label is not None:
            keystore.rename_key(settings, engine, key_id, body.label)
        if body.key is not None:
            keystore.replace_key(settings, engine, key_id, body.key)
    except KeyStoreError as error:
        raise HTTPException(422, str(error)) from error
    error = None
    if body.key is not None:
        error = await _refresh(request, engine, _require_key(request, engine, key_id))
    return engine_data(request, engine, error)


@router.put("/api-engines/{engine}/active")
def choose_key(request: Request, engine: str, body: ChooseKeyInput):
    """Use this key for new runs (FLUX's key, and "Also use for future runs")."""
    require_engine(engine)
    try:
        keystore.choose_key(request.app.state.settings, engine, body.key_id, body.purpose)
    except KeyStoreError as error:
        raise HTTPException(409, str(error)) from error
    return engine_data(request, engine)


@router.delete("/api-engines/{engine}/keys/{key_id}")
def remove_key(request: Request, engine: str, key_id: str):
    """Remove a key from this PC (it stays valid at the provider until revoked there).

    Refused while runs wait or run on it, and while it is the key an engine panel's
    selected engine uses: choose another key or engine there first.
    """
    item = require_engine(engine)
    settings = request.app.state.settings
    key = _require_key(request, engine, key_id)
    with Session(request.app.state.engine) as session:
        busy = waiting_on(session, engine, key_id)
        row = session.get(EngineSettings, 1)
        selected = {"analysis": row.analysis_engine, "generation": row.generation_engine}
    if busy:
        runs = "1 run is" if busy == 1 else f"{busy} runs are"
        raise HTTPException(
            409,
            f"{runs} waiting or in progress on the key “{key['label']}”. Let them "
            "finish, cancel them or continue them with another key first.",
        )
    others = len(keystore.keys(settings, engine)) > 1
    for purpose in keystore.PURPOSES[engine]:
        if selected.get(purpose) != engine:
            continue
        if (keystore.active(settings, engine, purpose) or {}).get("id") != key_id:
            continue
        panel = "Analysis" if purpose == "analysis" else "Generation"
        if others:
            raise HTTPException(
                409,
                f"The {panel} engine panel uses this key. Choose another key there and save "
                "first.",
            )
        raise HTTPException(
            409, f"The {item.name} is the selected {purpose} engine. Choose another first."
        )
    try:
        keystore.delete_key(settings, engine, key_id)
    except KeyStoreError as error:
        raise HTTPException(409, str(error)) from error
    if not keystore.keys(settings, engine):
        _store_list(request, engine, None)
    return engine_data(request, engine)


@router.post("/api-engines/{engine}/keys/{key_id}/test")
async def test_key(request: Request, engine: str, key_id: str):
    """Check a saved key and refresh the model list (free); nothing is generated."""
    require_engine(engine)
    error = await _refresh(request, engine, _require_key(request, engine, key_id))
    if error:
        raise HTTPException(409, error)
    return engine_data(request, engine)
