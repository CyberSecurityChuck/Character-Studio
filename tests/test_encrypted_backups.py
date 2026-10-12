"""Phase 6D: password-protected backups (encrypted, verified and restored like plain ones)."""

import json
import os
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend import backup
from backend.backup_crypto import (
    CHUNK,
    MAGIC,
    WrongPassword,
    check_password,
    decrypt_file,
    encrypt_file,
    read_header,
)
from backend.main import create_app
from tests.conftest import authorization
from tests.test_generation import approved_scene

PASSWORD = "correct horse battery staple"


def start(client, password=None, expect=202):
    body = {"password": password} if password is not None else None
    reply = client.post("/api/backups", headers=authorization(client), json=body)
    assert reply.status_code == expect, reply.text
    if expect != 202:
        return reply.json()
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        state = client.get("/api/backups").json()
        if not state["running"]:
            assert state["error"] is None, state["error"]
            return state
        time.sleep(0.1)
    raise AssertionError("Backup did not finish")


def verify(client, name, password=None):
    body = {"password": password} if password is not None else None
    return client.post(f"/api/backups/{name}/verify", headers=authorization(client),
                       json=body).json()


def test_encryption_round_trip_and_tamper_detection(tmp_path):
    plain = tmp_path / "plain.zip"
    data = os.urandom(CHUNK * 2 + 1234)  # three chunks
    plain.write_bytes(data)
    sealed = tmp_path / "sealed.csbackup"
    encrypt_file(plain, sealed, PASSWORD)
    raw = sealed.read_bytes()
    assert raw.startswith(MAGIC) and data[:4096] not in raw
    header, _raw, offset = read_header(sealed)
    assert header["cipher"] == "AES-256-GCM" and header["kdf"]["name"] == "scrypt"
    assert set(header) == {"format", "application", "kdf", "cipher", "chunk", "nonce_prefix"}

    out = tmp_path / "out.zip"
    decrypt_file(sealed, out, PASSWORD)
    assert out.read_bytes() == data

    with pytest.raises(WrongPassword):
        decrypt_file(sealed, tmp_path / "wrong.zip", PASSWORD + "!")
    assert not (tmp_path / "wrong.zip").exists()
    changed = bytearray(raw)
    changed[offset + 100] ^= 1
    (tmp_path / "changed.csbackup").write_bytes(bytes(changed))
    with pytest.raises(WrongPassword):
        decrypt_file(tmp_path / "changed.csbackup", tmp_path / "c.zip", PASSWORD)
    # Dropping the last chunk is noticed: the new last chunk was not sealed as the last.
    (tmp_path / "short.csbackup").write_bytes(raw[: offset + 2 * (CHUNK + 16)])
    with pytest.raises(WrongPassword):
        decrypt_file(tmp_path / "short.csbackup", tmp_path / "s.zip", PASSWORD)

    for bad in ("short", " leading space", "x" * 1025):
        with pytest.raises(ValueError):
            check_password(bad)


def test_protected_backup_is_listed_checked_and_restored(settings, monkeypatch):
    with TestClient(create_app(settings), base_url="http://127.0.0.1:8765") as client:
        approved_scene(client)
        refused = start(client, "too short", expect=422)
        assert "at least" in refused["detail"] and "too short" not in json.dumps(refused)
        state = start(client, PASSWORD)
        [item] = state["items"]
        assert item["name"].endswith(".csbackup") and item["encrypted"] is True
        assert item["counts"] is None and item["created_at"]
        folder = Path(state["folder"])
        assert [p.name for p in folder.iterdir()] == [item["name"]]  # no plain copy left
        content = (folder / item["name"]).read_bytes()
        assert b"manifest.json" not in content and b"studio.db" not in content
        assert PASSWORD.encode() not in content

        missing = verify(client, item["name"])
        assert missing["ok"] is False and "password" in missing["problem"]
        wrong = verify(client, item["name"], "wrong password here")
        assert wrong["ok"] is False and "password is wrong" in wrong["problem"]
        right = verify(client, item["name"], PASSWORD)
        assert right["ok"] is True and right["encrypted"] is True
        assert right["counts"]["scenes"] == 1

        # A plain backup still works alongside.
        state = start(client)
        names = [i["name"] for i in state["items"]]
        assert any(n.endswith(".zip") for n in names) and len(names) == 2
        download = client.get(f"/api/backups/{item['name']}/download")
        assert download.status_code == 200 and download.content == content
        for name in names:
            assert PASSWORD not in (folder / name).read_bytes().decode("latin-1")

    # Restore asks for the password at the console; a wrong one changes nothing.
    monkeypatch.setenv("STUDIO_DATA_DIR", str(settings.data_dir))
    source = folder / item["name"]
    monkeypatch.setattr("getpass.getpass", lambda _prompt="": "wrong password here")
    assert backup.main(["restore", str(source)]) == 1
    assert [p.name for p in settings.data_dir.parent.iterdir()] == ["private-data"]
    monkeypatch.setattr("getpass.getpass", lambda _prompt="": PASSWORD)
    monkeypatch.setattr("builtins.input", lambda _prompt="": "RESTORE")
    assert backup.main(["restore", str(source)]) == 0
    names = sorted(p.name for p in settings.data_dir.parent.iterdir())
    assert names[0] == "private-data" and names[1].startswith("private-data.before-restore-")
    with TestClient(create_app(settings), base_url="http://127.0.0.1:8765") as client:
        assert len(client.get("/api/scenes").json()) == 1
        # Every backup is still listed after the restore.
        assert len(client.get("/api/backups").json()["items"]) == 2
