"""Scene sets and the free duplicate checks of the Scenes page (Phase 7A, D030, D031)."""

import hashlib
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from backend.configuration import asset_path
from backend.duplicates import NEAR_COPY_BITS, Families, distance, fingerprint, groups
from backend.library import decode_image
from backend.models import Scene, SceneSet
from backend.scene_store import now
from backend.scenes import exact_copies, require_set, scene_summary, visible, writing

router = APIRouter(prefix="/api")


class SetInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=80)

    _visible = field_validator("name")(lambda cls, value: visible(value))


class SetRename(SetInput):
    revision: int = Field(ge=1)


class MembersInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scene_ids: list[str] = Field(min_length=1, max_length=5000)
    # None takes the scenes out of their set.
    scene_set_id: str | None = Field(default=None, max_length=32)


def set_data(session, item: SceneSet):
    return {
        "id": item.id,
        "name": item.name,
        "revision": item.revision,
        "scene_count": session.scalar(select(func.count()).where(Scene.scene_set_id == item.id)),
        "created_at": item.created_at,
        "updated_at": item.updated_at,
    }


def require_set_row(session, scene_set_id: str) -> SceneSet:
    item = session.get(SceneSet, scene_set_id)
    if item is None:
        raise HTTPException(404, "This scene set no longer exists. Reload your scenes.")
    return item


def name_taken(session, name: str, other_than: str | None = None) -> None:
    clash = session.scalar(
        select(SceneSet.id).where(
            func.lower(SceneSet.name) == name.lower(), SceneSet.id != other_than
        )
    )
    if clash:
        raise HTTPException(
            409, f"A scene set called “{name}” already exists. Choose another name."
        )


@router.get("/scene-sets")
def scene_sets(request: Request):
    with Session(request.app.state.engine) as session:
        items = session.scalars(select(SceneSet).order_by(func.lower(SceneSet.name)))
        return [set_data(session, item) for item in items]


@router.post("/scene-sets", status_code=201)
def create_set(request: Request, body: SetInput):
    with writing(request) as session:
        name_taken(session, body.name)
        item = SceneSet(
            id=uuid4().hex, name=body.name, revision=1, created_at=now(), updated_at=now()
        )
        session.add(item)
        session.flush()
        return set_data(session, item)


@router.put("/scene-sets/{scene_set_id}")
def rename_set(request: Request, scene_set_id: str, body: SetRename):
    with writing(request) as session:
        item = require_set_row(session, scene_set_id)
        if item.revision != body.revision:
            raise HTTPException(409, "This scene set changed in another window. Reload it first.")
        name_taken(session, body.name, item.id)
        item.name, item.revision, item.updated_at = body.name, item.revision + 1, now()
        session.flush()
        return set_data(session, item)


@router.delete("/scene-sets/{scene_set_id}")
def delete_set(request: Request, scene_set_id: str, revision: int = Query(ge=1)):
    """Deletes only the set; its scenes stay in the studio without a set."""
    with writing(request) as session:
        item = require_set_row(session, scene_set_id)
        if item.revision != revision:
            raise HTTPException(409, "This scene set changed in another window. Reload it first.")
        kept = session.execute(
            update(Scene).where(Scene.scene_set_id == item.id).values(scene_set_id=None)
        ).rowcount
        session.delete(item)
        return {"deleted": True, "scenes_kept": kept}


@router.put("/scene-set-members")
def move_scenes(request: Request, body: MembersInput):
    # Organising only: the scenes' revision, approvals and stage stay as they are.
    with writing(request) as session:
        require_set(session, body.scene_set_id)
        found = list(session.scalars(select(Scene).where(Scene.id.in_(set(body.scene_ids)))))
        if len(found) != len(set(body.scene_ids)):
            raise HTTPException(404, "Some of these scenes no longer exist. Reload your scenes.")
        for scene in found:
            scene.scene_set_id = body.scene_set_id
        if body.scene_set_id:
            session.get(SceneSet, body.scene_set_id).updated_at = now()
        return {"moved": len(found)}


def fill_fingerprints(request) -> None:
    """Fingerprints for scenes added before Phase 7, made once from their stored originals."""
    settings = request.app.state.settings
    with Session(request.app.state.engine) as session:
        missing = list(
            session.execute(
                select(Scene.id, Scene.original_path).where(Scene.perceptual_hash.is_(None))
            )
        )
    made = {}
    for scene_id, original in missing:
        try:
            made[scene_id] = fingerprint(asset_path(settings, original))
        except (OSError, ValueError):
            continue  # A missing or unreadable original is reported by the scene itself.
    if made:
        with writing(request) as session:
            for scene_id, value in made.items():
                scene = session.get(Scene, scene_id)
                if scene is not None and scene.perceptual_hash is None:
                    scene.perceptual_hash = value


def brief(scene: Scene, near: int | None = None):
    data = {
        "id": scene.id,
        "title": scene.title,
        "thumbnail_url": f"/api/scenes/{scene.id}/image/thumbnail",
        "created_at": scene.created_at,
    }
    if near is not None:
        data["distance"] = near
    return data


def check_upload(request, payload: bytes):
    # The same checks as a real upload, so a file that passes here can be imported.
    decode_image(payload, request.app.state.settings)
    content_hash = hashlib.sha256(payload).hexdigest()
    perceptual_hash = fingerprint(payload)
    fill_fingerprints(request)
    with Session(request.app.state.engine) as session:
        exact = exact_copies(session, content_hash)
        candidates = session.scalars(
            select(Scene).where(
                Scene.perceptual_hash.is_not(None), Scene.content_hash != content_hash
            )
        )
        near = sorted(
            (
                (bits, scene)
                for scene in candidates
                if (bits := distance(scene.perceptual_hash, perceptual_hash)) <= NEAR_COPY_BITS
            ),
            key=lambda pair: (pair[0], pair[1].created_at),
        )
        return {
            "content_hash": content_hash,
            "perceptual_hash": perceptual_hash,
            "near_copy_bits": NEAR_COPY_BITS,
            "exact": [brief(scene) for scene in exact],
            "near": [brief(scene, bits) for bits, scene in near[:5]],
        }


@router.post("/scene-imports/check")
async def check_import(request: Request):
    """Looks for exact and near copies of one image in the studio; stores nothing."""
    payload = bytearray()
    limit = request.app.state.settings.max_upload_bytes
    async for chunk in request.stream():
        if len(payload) + len(chunk) > limit:
            raise HTTPException(413, f"Image exceeds the {limit // (1024 * 1024)} MB upload limit.")
        payload.extend(chunk)
    return await run_in_threadpool(check_upload, request, bytes(payload))


def find_duplicates(request):
    fill_fingerprints(request)
    with Session(request.app.state.engine) as session:
        scenes = list(session.scalars(select(Scene).order_by(Scene.created_at, Scene.id)))
        families = Families({s.id: s.duplicated_from for s in scenes})
        by_id = {s.id: s for s in scenes}
        # Exact: one scene per family, so a scene and its own Duplicate scene copies never match.
        exact_pairs, firsts = [], {}
        for scene in scenes:
            seen = firsts.setdefault(scene.content_hash, {})
            family = families.find(scene.id)
            if family not in seen:
                seen[family] = scene.id
                if len(seen) > 1:
                    exact_pairs.append((next(iter(seen.values())), scene.id))
        near_pairs = []
        printed = [s for s in scenes if s.perceptual_hash]
        for index, first in enumerate(printed):
            for second in printed[index + 1 :]:
                if (
                    first.content_hash != second.content_hash
                    and families.find(first.id) != families.find(second.id)
                    and distance(first.perceptual_hash, second.perceptual_hash) <= NEAR_COPY_BITS
                ):
                    near_pairs.append((first.id, second.id))
        return {
            "checked": len(scenes),
            "near_copy_bits": NEAR_COPY_BITS,
            "exact": [
                [scene_summary(request, session, by_id[i]) for i in group]
                for group in groups(exact_pairs)
            ],
            "near": [
                [scene_summary(request, session, by_id[i]) for i in group]
                for group in groups(near_pairs)
            ],
        }


@router.get("/scene-duplicates")
async def scene_duplicates(request: Request):
    """Find duplicates among the scenes already in the studio (free, local, read-only)."""
    return await run_in_threadpool(find_duplicates, request)
