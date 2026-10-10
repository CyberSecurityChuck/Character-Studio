"""Local library API. Originals never leave this machine or use client-supplied paths."""

import io
import os
import shutil
import warnings
from datetime import UTC, datetime
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse
from PIL import Image, ImageOps, UnidentifiedImageError
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import delete, select
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from backend.configuration import asset_path
from backend.models import (
    Character,
    CharacterGroup,
    GroupMember,
    PendingFileDeletion,
    ReferencePhoto,
)
from backend.persistence import writing_session

router = APIRouter(prefix="/api")
PhotoLabel = Literal[
    "Front",
    "Left three-quarter",
    "Right three-quarter",
    "Left profile",
    "Right profile",
    "Full body",
    "Additional",
]


def now():
    return datetime.now(UTC).isoformat()


class CharacterInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=80)
    age_category: Literal["Adult", "Teen", "Child"]
    notes: str = Field(default="", max_length=4000)

    @field_validator("name")
    @classmethod
    def visible_name(cls, value):
        value = value.strip()
        if not value or any(ord(c) < 32 for c in value):
            raise ValueError("Enter a visible name without control characters.")
        return value


class CharacterUpdate(CharacterInput):
    revision: int = Field(ge=1)


class ArchiveInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revision: int = Field(ge=1)
    archived: bool


class PhotoFrame(BaseModel):
    model_config = ConfigDict(extra="forbid")
    x: float = Field(ge=0, le=1, allow_inf_nan=False)
    y: float = Field(ge=0, le=1, allow_inf_nan=False)
    zoom: float = Field(ge=1, le=4, allow_inf_nan=False)


class PhotoUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revision: int = Field(ge=1)
    label: PhotoLabel
    primary: bool = False
    frame: PhotoFrame | None = None


class GroupInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=80)
    member_ids: list[str] = Field(default_factory=list, max_length=1000)
    _validate_name = field_validator("name")(CharacterInput.visible_name.__func__)


class GroupUpdate(GroupInput):
    revision: int = Field(ge=1)


def writing(request):
    return writing_session(request.app.state.engine)


def require(session, model, identifier):
    value = session.get(model, identifier)
    if value is None:
        raise HTTPException(404, "This item no longer exists. Refresh the library.")
    return value


def check_revision(item, revision):
    if item.revision != revision:
        raise HTTPException(409, "This item changed in another window. Reload before editing.")


def touch(item):
    item.revision += 1
    item.updated_at = now()


def photo_data(photo):
    return {
        "id": photo.id,
        "label": photo.label,
        "width": photo.width,
        "height": photo.height,
        "created_at": photo.created_at,
        "frame": {"x": photo.frame_x, "y": photo.frame_y, "zoom": photo.frame_zoom},
        "thumbnail_url": f"/api/photos/{photo.id}/thumbnail",
        "original_url": f"/api/photos/{photo.id}/original",
    }


def character_data(session, character):
    return {
        "id": character.id,
        "name": character.name,
        "age_category": character.age_category,
        "notes": character.notes,
        "archived": character.archived,
        "primary_photo_id": character.primary_photo_id,
        "revision": character.revision,
        "created_at": character.created_at,
        "updated_at": character.updated_at,
        "photos": [
            photo_data(p)
            for p in session.scalars(
                select(ReferencePhoto)
                .where(ReferencePhoto.character_id == character.id)
                .order_by(ReferencePhoto.created_at, ReferencePhoto.id)
            )
        ],
        "group_ids": list(
            session.scalars(
                select(GroupMember.group_id).where(GroupMember.character_id == character.id)
            )
        ),
    }


def group_data(session, group):
    return {
        "id": group.id,
        "name": group.name,
        "revision": group.revision,
        "created_at": group.created_at,
        "updated_at": group.updated_at,
        "member_ids": list(
            session.scalars(
                select(GroupMember.character_id).where(GroupMember.group_id == group.id)
            )
        ),
    }


@router.get("/characters")
def characters(request: Request, q: str = Query(default="", max_length=200)):
    with Session(request.app.state.engine) as session:
        return [
            character_data(session, c)
            for c in session.scalars(select(Character).order_by(Character.created_at, Character.id))
            if q.casefold() in c.name.casefold()
        ]


@router.get("/characters/{character_id}")
def character(request: Request, character_id: str):
    with Session(request.app.state.engine) as session:
        return character_data(session, require(session, Character, character_id))


@router.post("/characters", status_code=201)
def create_character(request: Request, body: CharacterInput):
    with writing(request) as session:
        item = Character(id=uuid4().hex, **body.model_dump(), created_at=now(), updated_at=now())
        session.add(item)
        session.flush()
        return character_data(session, item)


@router.put("/characters/{character_id}")
def update_character(request: Request, character_id: str, body: CharacterUpdate):
    with writing(request) as session:
        item = require(session, Character, character_id)
        check_revision(item, body.revision)
        for key, value in body.model_dump(exclude={"revision"}).items():
            setattr(item, key, value)
        touch(item)
        return character_data(session, item)


@router.put("/characters/{character_id}/archive")
def archive_character(request: Request, character_id: str, body: ArchiveInput):
    with writing(request) as session:
        item = require(session, Character, character_id)
        check_revision(item, body.revision)
        item.archived = body.archived
        touch(item)
        return character_data(session, item)


def queue_photo_deletion(session, photo):
    for path in (photo.original_path, photo.thumbnail_path):
        session.merge(PendingFileDeletion(path=path))
    session.delete(photo)
    return [photo.original_path, photo.thumbnail_path]


def clean_deleted_files(engine, settings, paths=None):
    # Durable queue: interrupted/locked-file deletion is retried on startup.
    with Session(engine) as session, session.begin():
        query = select(PendingFileDeletion)
        if paths is not None:
            query = query.where(PendingFileDeletion.path.in_(paths))
        for item in session.scalars(query):
            try:
                target = asset_path(settings, item.path)
                # Job folders are directories; everything else is a single file.
                if target.is_dir():
                    shutil.rmtree(target)
                else:
                    target.unlink(missing_ok=True)
            except OSError:
                continue
            session.delete(item)
    with Session(engine) as session:
        return session.scalar(query.limit(1)) is not None


@router.delete("/characters/{character_id}")
def delete_character(request: Request, character_id: str, revision: int = Query(ge=1)):
    paths = []
    with writing(request) as session:
        item = require(session, Character, character_id)
        check_revision(item, revision)
        for photo in session.scalars(
            select(ReferencePhoto).where(ReferencePhoto.character_id == character_id)
        ):
            paths.extend(queue_photo_deletion(session, photo))
        # Future history tables must RESTRICT deletion or retain immutable snapshots.
        for group_id in session.scalars(
            select(GroupMember.group_id).where(GroupMember.character_id == character_id)
        ):
            touch(require(session, CharacterGroup, group_id))
        session.execute(delete(GroupMember).where(GroupMember.character_id == character_id))
        session.flush()
        session.delete(item)
    pending = clean_deleted_files(request.app.state.engine, request.app.state.settings, paths)
    return {"deleted": True, "cleanup_pending": pending}


def decode_image(payload, settings):
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(payload)) as source:
                formats = {
                    "JPEG": ("jpg", "image/jpeg"),
                    "PNG": ("png", "image/png"),
                    "WEBP": ("webp", "image/webp"),
                }
                if source.format not in formats:
                    raise HTTPException(422, "Choose a JPEG, PNG or WebP photo.")
                if source.width * source.height > settings.max_image_pixels:
                    raise HTTPException(
                        422, "This photo has too many pixels (limit: 40 megapixels)."
                    )
                if getattr(source, "n_frames", 1) != 1:
                    raise HTTPException(422, "Choose a still photo, not an animation.")
                extension, media_type = formats[source.format]
                source.verify()
            with Image.open(io.BytesIO(payload)) as source:
                source.load()
                thumbnail = ImageOps.exif_transpose(source).convert("RGB")
                width, height = thumbnail.size
                thumbnail.thumbnail((480, 480))
                # Construct a fresh image to exclude EXIF/GPS and other source metadata.
                clean = Image.new("RGB", thumbnail.size)
                clean.paste(thumbnail)
                output = io.BytesIO()
                clean.save(output, "JPEG", quality=85)
                return extension, media_type, width, height, output.getvalue()
    except (
        UnidentifiedImageError,
        OSError,
        ValueError,
        SyntaxError,
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
    ) as exc:
        raise HTTPException(
            422, "This photo is damaged or unsupported. Choose another file."
        ) from exc


def store_photo(request, character_id, revision, payload):
    settings = request.app.state.settings
    extension, media_type, width, height, thumbnail = decode_image(payload, settings)
    identifier = uuid4().hex
    paths = [f"characters/{identifier}.{extension}", f"thumbnails/{identifier}.jpg"]
    # Journal intended paths first. A crash before the metadata commit leaves a
    # durable cleanup record, never an untracked partial original/thumbnail.
    with writing(request) as session:
        item = require(session, Character, character_id)
        check_revision(item, revision)
        session.add_all(PendingFileDeletion(path=key) for key in paths)
    try:
        with writing(request) as session:
            item = require(session, Character, character_id)
            check_revision(item, revision)
            if item.archived:
                raise HTTPException(409, "Restore this character before adding photos.")
            for key, content in zip(paths, (payload, thumbnail), strict=True):
                target = asset_path(settings, key)
                with target.open("xb") as file:
                    file.write(content)
                    file.flush()
                    os.fsync(file.fileno())
            session.execute(delete(PendingFileDeletion).where(PendingFileDeletion.path.in_(paths)))
            session.add(
                ReferencePhoto(
                    id=identifier,
                    character_id=character_id,
                    label="Additional",
                    original_path=paths[0],
                    thumbnail_path=paths[1],
                    media_type=media_type,
                    width=width,
                    height=height,
                    created_at=now(),
                )
            )
            if not item.primary_photo_id:
                item.primary_photo_id = identifier
            touch(item)
            session.flush()
            result = character_data(session, item)
        return result
    except BaseException:
        clean_deleted_files(request.app.state.engine, settings, paths)
        raise


@router.post("/characters/{character_id}/photos", status_code=201)
async def upload_photo(request: Request, character_id: str, revision: int = Query(ge=1)):
    # Raw streaming body avoids multipart parser/spool files inside the source checkout.
    payload = bytearray()
    limit = request.app.state.settings.max_upload_bytes
    async for chunk in request.stream():
        if len(payload) + len(chunk) > limit:
            raise HTTPException(413, f"Photo exceeds the {limit // (1024 * 1024)} MB upload limit.")
        payload.extend(chunk)
    return await run_in_threadpool(store_photo, request, character_id, revision, bytes(payload))


@router.put("/photos/{photo_id}")
def update_photo(request: Request, photo_id: str, body: PhotoUpdate):
    with writing(request) as session:
        photo = require(session, ReferencePhoto, photo_id)
        item = require(session, Character, photo.character_id)
        check_revision(item, body.revision)
        photo.label = body.label
        if body.frame is not None:
            photo.frame_x, photo.frame_y, photo.frame_zoom = (
                body.frame.x,
                body.frame.y,
                body.frame.zoom,
            )
        if body.primary:
            item.primary_photo_id = photo.id
        touch(item)
        return character_data(session, item)


@router.delete("/photos/{photo_id}")
def delete_photo(request: Request, photo_id: str, revision: int = Query(ge=1)):
    with writing(request) as session:
        photo = require(session, ReferencePhoto, photo_id)
        item = require(session, Character, photo.character_id)
        check_revision(item, revision)
        paths = queue_photo_deletion(session, photo)
        session.flush()
        if item.primary_photo_id == photo.id:
            item.primary_photo_id = session.scalar(
                select(ReferencePhoto.id)
                .where(ReferencePhoto.character_id == item.id)
                .order_by(ReferencePhoto.created_at, ReferencePhoto.id)
                .limit(1)
            )
        touch(item)
        result = character_data(session, item)
    result["cleanup_pending"] = clean_deleted_files(
        request.app.state.engine, request.app.state.settings, paths
    )
    return result


@router.get("/photos/{photo_id}/{variant}")
def get_photo(request: Request, photo_id: str, variant: Literal["original", "thumbnail"]):
    with Session(request.app.state.engine) as session:
        photo = require(session, ReferencePhoto, photo_id)
        path = asset_path(request.app.state.settings, getattr(photo, f"{variant}_path"))
        if not path.is_file():
            raise HTTPException(404, "Photo file is missing. Restore it from your backup.")
        return FileResponse(
            path, media_type=photo.media_type if variant == "original" else "image/jpeg"
        )


@router.get("/groups")
def groups(request: Request):
    with Session(request.app.state.engine) as session:
        return [
            group_data(session, g)
            for g in session.scalars(
                select(CharacterGroup).order_by(CharacterGroup.created_at, CharacterGroup.id)
            )
        ]


def set_members(session, group_id, member_ids):
    members = set(member_ids)
    for identifier in members:
        require(session, Character, identifier)
    session.execute(delete(GroupMember).where(GroupMember.group_id == group_id))
    session.add_all(GroupMember(group_id=group_id, character_id=c) for c in members)
    session.flush()


@router.post("/groups", status_code=201)
def create_group(request: Request, body: GroupInput):
    with writing(request) as session:
        group = CharacterGroup(id=uuid4().hex, name=body.name, created_at=now(), updated_at=now())
        session.add(group)
        session.flush()
        set_members(session, group.id, body.member_ids)
        return group_data(session, group)


@router.put("/groups/{group_id}")
def update_group(request: Request, group_id: str, body: GroupUpdate):
    with writing(request) as session:
        group = require(session, CharacterGroup, group_id)
        check_revision(group, body.revision)
        group.name = body.name
        touch(group)
        set_members(session, group_id, body.member_ids)
        return group_data(session, group)


@router.delete("/groups/{group_id}")
def delete_group(request: Request, group_id: str, revision: int = Query(ge=1)):
    with writing(request) as session:
        group = require(session, CharacterGroup, group_id)
        check_revision(group, revision)
        session.execute(delete(GroupMember).where(GroupMember.group_id == group_id))
        session.delete(group)
    return {"deleted": True}
