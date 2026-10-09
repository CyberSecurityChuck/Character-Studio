import io
import sqlite3
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from backend.library import clean_deleted_files
from backend.main import create_app
from backend.models import PendingFileDeletion
from tests.conftest import authorization


def create_character(client, name="Test character", age="Adult"):
    result = client.post(
        "/api/characters",
        headers=authorization(client),
        json={
            "name": name,
            "age_category": age,
            "notes": "Synthetic test profile",
        },
    )
    assert result.status_code == 201, result.text
    return result.json()


def picture(format="PNG"):
    stream = io.BytesIO()
    image = Image.new("RGB", (800, 600), "#aabbcc")
    exif = Image.Exif()
    exif[270] = "Private test metadata"
    image.save(stream, format, exif=exif)
    return stream.getvalue()


def upload(client, character, content=None):
    result = client.post(
        f"/api/characters/{character['id']}/photos?revision={character['revision']}",
        headers={**authorization(client), "Content-Type": "application/octet-stream"},
        content=content if content is not None else picture(),
    )
    return result


def test_library_survives_restart_and_originals_are_unchanged(settings):
    with TestClient(create_app(settings), base_url="http://127.0.0.1:8765") as client:
        c = create_character(client, "  Sample  ", "Child")
        original = picture()
        response = upload(client, c, original)
        assert response.status_code == 201, response.text
        c = response.json()
        assert c["name"] == "Sample"
        assert c["primary_photo_id"] == c["photos"][0]["id"]
        group = client.post(
            "/api/groups",
            headers=authorization(client),
            json={
                "name": "Family",
                "member_ids": [c["id"]],
            },
        ).json()
    with TestClient(create_app(settings), base_url="http://127.0.0.1:8765") as client:
        restored = client.get(f"/api/characters/{c['id']}").json()
        assert restored["group_ids"] == [group["id"]]
        assert restored["photos"] == c["photos"]
        photo = restored["photos"][0]
        result = client.get(photo["original_url"])
        assert result.content == original
        assert result.headers["cache-control"] == "no-store"
        with Image.open(io.BytesIO(client.get(photo["thumbnail_url"]).content)) as thumb:
            assert thumb.size == (480, 360)
            assert not thumb.getexif()
        assert len(client.get("/api/characters?q=sAm").json()) == 1
        assert client.get("/api/characters?q=absent").json() == []


@pytest.mark.parametrize("format", ["JPEG", "PNG", "WEBP"])
def test_supported_formats_and_primary_fallback(client, format):
    c = create_character(client)
    c = upload(client, c, picture(format)).json()
    first = c["primary_photo_id"]
    c = upload(client, c).json()
    second = c["photos"][1]["id"]
    result = client.put(
        f"/api/photos/{second}",
        headers=authorization(client),
        json={
            "revision": c["revision"],
            "label": "Left profile",
            "primary": True,
        },
    )
    c = result.json()
    assert c["primary_photo_id"] == second
    assert c["photos"][1]["label"] == "Left profile"
    c = client.delete(
        f"/api/photos/{second}?revision={c['revision']}", headers=authorization(client)
    ).json()
    assert c["primary_photo_id"] == first
    assert client.get(f"/api/photos/{second}/original").status_code == 404
    c = client.delete(
        f"/api/photos/{first}?revision={c['revision']}", headers=authorization(client)
    ).json()
    assert c["primary_photo_id"] is None
    assert c["photos"] == []


def test_photo_framing_defaults_updates_and_validation(client):
    c = upload(client, create_character(client)).json()
    photo = c["photos"][0]
    assert photo["frame"] == {"x": 0.5, "y": 0.3, "zoom": 1.0}
    path = f"/api/photos/{photo['id']}"
    frame = {"x": 0.2, "y": 0.75, "zoom": 2.5}
    body = {"revision": c["revision"], "label": "Front", "frame": frame}
    c = client.put(path, headers=authorization(client), json=body).json()
    assert c["photos"][0]["frame"] == frame
    # Omitting the frame leaves it unchanged.
    body = {"revision": c["revision"], "label": "Left profile"}
    c = client.put(path, headers=authorization(client), json=body).json()
    assert c["photos"][0]["frame"] == frame
    assert c["photos"][0]["label"] == "Left profile"
    for bad in (
        {"x": -0.1, "y": 0.5, "zoom": 1},
        {"x": 0.5, "y": 1.1, "zoom": 1},
        {"x": 0.5, "y": 0.5, "zoom": 0.5},
        {"x": 0.5, "y": 0.5, "zoom": 5},
        {"x": 0.5, "y": 0.5},
        {"x": 0.5, "y": 0.5, "zoom": 1, "extra": 1},
    ):
        body = {"revision": c["revision"], "label": "Front", "frame": bad}
        assert client.put(path, headers=authorization(client), json=body).status_code == 422
    assert client.get(f"/api/characters/{c['id']}").json()["photos"][0]["frame"] == frame


def test_library_upgrade_gives_existing_photos_default_framing(settings):
    settings.data_dir.mkdir(parents=True)
    engine = create_engine(f"sqlite:///{settings.data_dir / 'studio.db'}")
    config = Config()
    config.set_main_option("script_location", str(Path(__file__).parents[1] / "backend/migrations"))
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "0002_library")
        connection.exec_driver_sql(
            "INSERT INTO characters VALUES ('c1', 'Kept', 'Adult', '', 'p1', 0, 1, 't', 't')"
        )
        connection.exec_driver_sql(
            "INSERT INTO reference_photos VALUES ('p1', 'c1', 'Front', "
            "'characters/p1.png', 'thumbnails/p1.jpg', 'image/png', 8, 6, 't')"
        )
    engine.dispose()
    with TestClient(create_app(settings), base_url="http://127.0.0.1:8765") as client:
        kept = client.get("/api/characters/c1").json()
        assert kept["name"] == "Kept"
        assert kept["photos"][0]["label"] == "Front"
        assert kept["photos"][0]["frame"] == {"x": 0.5, "y": 0.3, "zoom": 1.0}
    with sqlite3.connect(settings.data_dir / "studio.db") as db:
        assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"


def test_edit_archive_restore_and_stale_requests(client):
    c = create_character(client)
    path = f"/api/characters/{c['id']}"
    body = {"revision": 1, "name": "Edited", "age_category": "Teen", "notes": "Updated"}
    assert client.put(path, headers=authorization(client), json=body).status_code == 200
    assert client.put(path, headers=authorization(client), json=body).status_code == 409
    assert upload(client, c).status_code == 409
    assert client.delete(path + "?revision=1", headers=authorization(client)).status_code == 409
    c = client.put(
        path + "/archive",
        headers=authorization(client),
        json={
            "revision": 2,
            "archived": True,
        },
    ).json()
    assert upload(client, c).status_code == 409
    c = client.put(
        path + "/archive",
        headers=authorization(client),
        json={
            "revision": 3,
            "archived": False,
        },
    ).json()
    assert upload(client, c).status_code == 201


def test_groups_many_to_many_and_deletion_scope(client, settings):
    a = upload(client, create_character(client, "A")).json()
    b = create_character(client, "B")
    groups = [
        client.post(
            "/api/groups",
            headers=authorization(client),
            json={
                "name": name,
                "member_ids": [a["id"], b["id"], a["id"]],
            },
        ).json()
        for name in ("Family", "Friends")
    ]
    assert len(client.get(f"/api/characters/{a['id']}").json()["group_ids"]) == 2
    g = groups[0]
    assert len(g["member_ids"]) == 2
    result = client.put(
        f"/api/groups/{g['id']}",
        headers=authorization(client),
        json={
            "name": "Renamed",
            "member_ids": [a["id"]],
            "revision": 1,
        },
    )
    assert result.status_code == 200
    assert (
        client.delete(
            f"/api/groups/{g['id']}?revision=1", headers=authorization(client)
        ).status_code
        == 409
    )
    assert (
        client.delete(
            f"/api/groups/{g['id']}?revision=2", headers=authorization(client)
        ).status_code
        == 200
    )
    assert len(client.get("/api/characters").json()) == 2
    result = client.delete(
        f"/api/characters/{a['id']}?revision={a['revision']}", headers=authorization(client)
    )
    assert result.json() == {"deleted": True, "cleanup_pending": False}
    assert client.get("/api/groups").json()[0]["member_ids"] == [b["id"]]
    assert client.get("/api/groups").json()[0]["revision"] == 2
    assert not list((settings.data_dir / "characters").iterdir())
    assert not list((settings.data_dir / "thumbnails").iterdir())


@pytest.mark.parametrize("payload", [b"not an image", b"<svg></svg>", b"", picture()[:60]])
def test_bad_uploads_leave_no_files_or_metadata(client, settings, payload):
    c = create_character(client)
    assert upload(client, c, payload).status_code == 422
    assert not list((settings.data_dir / "characters").iterdir())
    assert client.get(f"/api/characters/{c['id']}").json()["revision"] == 1


def test_upload_limits_and_animation(settings):
    configured = settings.model_copy(update={"max_upload_bytes": 1024})
    with TestClient(create_app(configured), base_url="http://127.0.0.1:8765") as client:
        assert upload(client, create_character(client), b"x" * 1025).status_code == 413
    configured = settings.model_copy(update={"max_image_pixels": 100})
    with TestClient(create_app(configured), base_url="http://127.0.0.1:8765") as client:
        assert upload(client, create_character(client)).status_code == 422
    stream = io.BytesIO()
    Image.new("RGB", (2, 2), "red").save(
        stream, "PNG", save_all=True, append_images=[Image.new("RGB", (2, 2), "blue")]
    )
    with TestClient(create_app(settings), base_url="http://127.0.0.1:8765") as client:
        assert upload(client, create_character(client), stream.getvalue()).status_code == 422


def test_invalid_inputs_and_protection(client):
    for name in (" ", "x" * 81, "bad\nname"):
        assert (
            client.post(
                "/api/characters",
                headers=authorization(client),
                json={
                    "name": name,
                    "age_category": "Adult",
                },
            ).status_code
            == 422
        )
    assert (
        client.post(
            "/api/groups",
            headers=authorization(client),
            json={
                "name": "Bad members",
                "member_ids": ["not-real"],
            },
        ).status_code
        == 404
    )
    assert client.get("/api/groups").json() == []
    assert (
        client.post("/api/characters", json={"name": "A", "age_category": "Adult"}).status_code
        == 403
    )
    c = upload(client, create_character(client)).json()
    url = c["photos"][0]["original_url"]
    assert client.get(url, headers={"Sec-Fetch-Site": "cross-site"}).status_code == 403
    assert client.get(url, headers={"Origin": "https://example.com"}).status_code == 403
    assert client.get("/api/photos/not-real/original").status_code == 404
    assert client.get("/characters/../../studio.db").status_code != 200


def test_missing_asset_has_clear_error(client, settings):
    c = upload(client, create_character(client)).json()
    next((settings.data_dir / "characters").iterdir()).unlink()
    response = client.get(c["photos"][0]["original_url"])
    assert response.status_code == 404
    assert "backup" in response.json()["detail"]


def test_phase_one_upgrade_preserves_preferences(settings):
    settings.data_dir.mkdir(parents=True)
    engine = create_engine(f"sqlite:///{settings.data_dir / 'studio.db'}")
    config = Config()
    config.set_main_option("script_location", str(Path(__file__).parents[1] / "backend/migrations"))
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "0001_foundation")
        connection.exec_driver_sql("UPDATE studio_preferences SET studio_name = 'Keep me'")
    engine.dispose()
    with TestClient(create_app(settings), base_url="http://127.0.0.1:8765") as client:
        assert client.get("/api/bootstrap").json()["preferences"]["studio_name"] == "Keep me"
        create_character(client)
    with sqlite3.connect(settings.data_dir / "studio.db") as db:
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []
        assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"


def test_failed_file_write_rolls_back(client, settings, monkeypatch):
    c = create_character(client)
    original = Path.open

    def fail_thumbnail(path, *args, **kwargs):
        if path.parent.name == "thumbnails" and args and args[0] == "xb":
            raise OSError("Synthetic disk failure")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", fail_thumbnail)
    assert upload(client, c).status_code == 503
    assert not list((settings.data_dir / "characters").iterdir())
    assert client.get(f"/api/characters/{c['id']}").json()["photos"] == []


def test_locked_deletions_are_retried_after_restart(settings, monkeypatch):
    original = Path.unlink

    def locked(path, *args, **kwargs):
        if path.parent.name == "characters":
            raise PermissionError("Synthetic locked file")
        return original(path, *args, **kwargs)

    with TestClient(create_app(settings), base_url="http://127.0.0.1:8765") as client:
        c = upload(client, create_character(client)).json()
        with monkeypatch.context() as patch:
            patch.setattr(Path, "unlink", locked)
            result = client.delete(
                f"/api/characters/{c['id']}?revision={c['revision']}", headers=authorization(client)
            )
            assert result.json()["cleanup_pending"] is True
        assert list((settings.data_dir / "characters").iterdir())
    with TestClient(create_app(settings), base_url="http://127.0.0.1:8765") as client:
        assert not list((settings.data_dir / "characters").iterdir())
        with Session(client.app.state.engine) as session:
            assert not list(session.scalars(select(PendingFileDeletion)))


def test_interrupted_upload_journal_is_cleaned_on_restart(settings):
    from backend.persistence import open_database

    engine = open_database(settings)
    path = "characters/" + "a" * 32 + ".png"
    (settings.data_dir / path).write_bytes(b"incomplete synthetic upload")
    with Session(engine) as session, session.begin():
        session.add(PendingFileDeletion(path=path))
    engine.dispose()
    with TestClient(create_app(settings), base_url="http://127.0.0.1:8765") as client:
        assert client.get("/api/characters").json() == []
        assert not (settings.data_dir / path).exists()


def test_targeted_cleanup_does_not_remove_another_upload(client, settings):
    path = "characters/" + "b" * 32 + ".png"
    (settings.data_dir / path).write_bytes(b"synthetic upload in progress")
    with Session(client.app.state.engine) as session, session.begin():
        session.add(PendingFileDeletion(path=path))
    assert clean_deleted_files(client.app.state.engine, settings, []) is False
    assert (settings.data_dir / path).exists()
