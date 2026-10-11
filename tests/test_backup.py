"""Backups and restore (PLAN.md §22): consistent, verified, and never overwriting data."""

import json
import sqlite3
import time
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend import backup
from backend.backup import BackupError, create_backup, restore_backup, verify_backup
from backend.main import create_app
from tests.conftest import authorization
from tests.test_generation import approved_scene, export, import_result


def make_backup(client) -> dict:
    started = client.post("/api/backups", headers=authorization(client))
    assert started.status_code == 202, started.text
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        state = client.get("/api/backups").json()
        if not state["running"]:
            assert state["error"] is None, state["error"]
            return state
        time.sleep(0.1)
    raise AssertionError("Backup did not finish")


def test_backup_and_restore_round_trip(settings):
    with TestClient(create_app(settings), base_url="http://127.0.0.1:8765") as client:
        ada, scene = approved_scene(client)
        export(client, scene)
        result = import_result(client, scene)["results"][0]
        image = client.get(result["image_url"]).content
        state = make_backup(client)
        [item] = state["items"]
        assert item["counts"] == {"characters": 1, "photos": 4, "scenes": 1, "results": 1}
        assert client.post(
            f"/api/backups/{item['name']}/verify", headers=authorization(client)
        ).json()["ok"]
        download = client.get(f"/api/backups/{item['name']}/download")
        assert download.status_code == 200 and download.content[:2] == b"PK"
        # Changes after the backup are not in it.
        character = client.get(f"/api/characters/{ada['id']}").json()
        client.delete(
            f"/api/characters/{ada['id']}?revision={character['revision']}",
            headers=authorization(client),
        )
    archive = settings.data_dir / "backups" / item["name"]
    with zipfile.ZipFile(archive) as zipped:
        names = set(zipped.namelist())
    assert "studio.db" in names and "manifest.json" in names
    assert not any(n.startswith("backups/") for n in names)

    restored, previous = restore_backup(archive, settings.data_dir)
    assert previous is not None and previous.name.startswith("private-data.before-restore-")
    assert (previous / "studio.db").is_file()  # Nothing was deleted.
    assert (restored / "backups" / item["name"]).is_file()  # Backups stay reachable.
    with TestClient(create_app(settings), base_url="http://127.0.0.1:8765") as client:
        assert client.get(f"/api/characters/{ada['id']}").json()["name"] == "Ada"
        detail = client.get(f"/api/scenes/{scene['id']}").json()
        # Files match their recorded hashes, so the approval is still valid.
        assert detail["approval"]["state"] == "approved"
        assert len(detail["results"]) == 1 and len(detail["exports"]) == 1
        assert client.get(detail["results"][0]["image_url"]).content == image
        assert client.get(detail["exports"][0]["download_url"]).status_code == 200


def rewrite(source: Path, target: Path, change) -> None:
    with zipfile.ZipFile(source) as old, zipfile.ZipFile(target, "w") as new:
        manifest = json.loads(old.read("manifest.json"))
        for info in old.infolist():
            data = old.read(info.filename)
            data = change(info.filename, data, manifest)
            if data is not None:
                new.writestr(info.filename, data)
        new.writestr("manifest.json", json.dumps(manifest))


def test_damaged_unsafe_or_newer_backups_are_refused(settings, tmp_path):
    with TestClient(create_app(settings), base_url="http://127.0.0.1:8765") as client:
        approved_scene(client)
        archive = create_backup(client.app.state.engine, settings)
    assert verify_backup(archive)["ok"]

    def damage(name, data, manifest):
        if name.startswith("characters/"):
            return data[:-1] + bytes([data[-1] ^ 1])
        return None if name == "manifest.json" else data

    damaged = tmp_path / "damaged.zip"
    rewrite(archive, damaged, damage)
    with pytest.raises(BackupError, match="damaged"):
        verify_backup(damaged)

    def escape(name, data, manifest):
        if name == "manifest.json":
            return None
        if name.startswith("thumbnails/") and "../evil.txt" not in manifest["files"]:
            manifest["files"]["../evil.txt"] = manifest["files"].pop(name)
            return None
        return data

    unsafe = tmp_path / "unsafe.zip"
    rewrite(archive, unsafe, escape)
    with pytest.raises(BackupError, match="do not match"):
        verify_backup(unsafe)

    # A backup from a newer studio version is refused before anything is replaced.
    newer = tmp_path / "newer.zip"
    database = tmp_path / "newer.db"

    def bump(name, data, manifest):
        if name == "studio.db":
            database.write_bytes(data)
            db = sqlite3.connect(database)
            db.execute("UPDATE alembic_version SET version_num = '9999_future'")
            db.commit()
            db.execute("PRAGMA journal_mode=DELETE")  # Fold the change into the main file.
            db.close()
            data = database.read_bytes()
            manifest["files"]["studio.db"]["sha256"] = backup._sha256(database)
        return None if name == "manifest.json" else data

    rewrite(archive, newer, bump)
    before = sorted(p.name for p in settings.data_dir.parent.iterdir())
    with pytest.raises(BackupError, match="newer version"):
        restore_backup(newer, settings.data_dir)
    assert sorted(p.name for p in settings.data_dir.parent.iterdir()) == before


def test_files_deleted_while_zipping_are_still_in_the_backup(settings, monkeypatch):
    with TestClient(create_app(settings), base_url="http://127.0.0.1:8765") as client:
        _ada, scene = approved_scene(client)
        engine = client.app.state.engine
        photo = next((settings.data_dir / "characters").iterdir())
        real_add = backup._add

        def add_then_delete(archive, source, name):
            # The user deletes a photo after the snapshot, while the zip is written.
            photo.unlink(missing_ok=True)
            return real_add(archive, source, name)

        monkeypatch.setattr(backup, "_add", add_then_delete)
        archive = create_backup(engine, settings)
    assert not photo.exists()
    assert verify_backup(archive)["ok"]
    with zipfile.ZipFile(archive) as zipped:
        assert f"characters/{photo.name}" in zipped.namelist()


def test_interrupted_backup_leftovers_are_removed_at_startup(settings):
    with TestClient(create_app(settings), base_url="http://127.0.0.1:8765"):
        pass
    folder = settings.data_dir / "backups"
    (folder / "character-studio-backup-20261011-000000.zip.partial").write_bytes(b"x")
    (folder / "character-studio-backup-20261011-000000.zip.files.partial").mkdir()
    with TestClient(create_app(settings), base_url="http://127.0.0.1:8765") as client:
        assert client.get("/api/backups").json()["items"] == []
    assert list(folder.iterdir()) == []


def test_restore_command_needs_explicit_confirmation(settings, monkeypatch):
    with TestClient(create_app(settings), base_url="http://127.0.0.1:8765") as client:
        approved_scene(client)
        make_backup(client)
    monkeypatch.setenv("STUDIO_DATA_DIR", str(settings.data_dir))
    answers = iter(["1", "no"])
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(answers))
    assert backup.main(["restore"]) == 1
    assert [p.name for p in settings.data_dir.parent.iterdir()] == ["private-data"]
    answers = iter(["1", "RESTORE"])
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(answers))
    assert backup.main(["restore"]) == 0
    names = sorted(p.name for p in settings.data_dir.parent.iterdir())
    assert names[0] == "private-data" and names[1].startswith("private-data.before-restore-")
