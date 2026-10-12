import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from backend.configuration import PROJECT_ROOT, Settings, asset_path
from backend.main import create_app
from backend.persistence import SCHEMA_REVISION, open_database
from tests.conftest import authorization


def test_health_and_provider_registry_are_honest(client):
    assert client.get("/api/health").json() == {
        "application": "character-studio",
        "status": "ok",
        "schema_revision": SCHEMA_REVISION,
    }
    data = client.get("/api/bootstrap").json()
    assert data["paid_operations_enabled"] is False
    assert {p["id"]: p["status"] for p in data["providers"]} == {
        "claude_cli": "available",
        "codex_cli": "available",
        "manual_bridge": "available",
        "gemini_api": "available",
        "anthropic_api": "unverified",
        "openai_api": "unverified",
        "gemini_image": "unverified",
        "openai_images": "unverified",
        "flux_fill": "unverified",
        "flux_3": "unverified",
    }
    # Phase 6C-1: the API image engines generate beside Codex and the manual bridge.
    assert {p["id"] for p in data["providers"] if p["generation"]} == {
        "codex_cli",
        "manual_bridge",
        "gemini_image",
        "openai_images",
    }
    assert client.get("/api/generate").status_code == 404
    assert client.post("/api/generate", headers=authorization(client)).status_code == 405


def test_saved_preferences_survive_recreation_and_migration_rerun(settings):
    with TestClient(create_app(settings), base_url="http://127.0.0.1:8765") as first:
        result = first.put(
            "/api/preferences",
            headers=authorization(first),
            json={
                "studio_name": "  Our family studio  ",
                "revision": 1,
            },
        )
        assert result.status_code == 200
        old_token = authorization(first)
    with TestClient(create_app(settings), base_url="http://127.0.0.1:8765") as second:
        preferences = second.get("/api/bootstrap").json()["preferences"]
        assert preferences == {"studio_name": "Our family studio", "revision": 2}
        assert (
            second.put(
                "/api/preferences",
                headers=old_token,
                json={
                    "studio_name": "Must not save",
                    "revision": 2,
                },
            ).status_code
            == 403
        )


def test_stale_browser_cannot_overwrite_newer_preferences(client):
    headers = authorization(client)
    assert (
        client.put(
            "/api/preferences",
            headers=headers,
            json={
                "studio_name": "First change",
                "revision": 1,
            },
        ).status_code
        == 200
    )
    assert (
        client.put(
            "/api/preferences",
            headers=headers,
            json={
                "studio_name": "Stale change",
                "revision": 1,
            },
        ).status_code
        == 409
    )
    assert client.get("/api/bootstrap").json()["preferences"]["studio_name"] == "First change"


@pytest.mark.parametrize("name", ["", "   ", "x" * 61, "bad\nname"])
def test_invalid_name_does_not_change_saved_state(client, name):
    assert (
        client.put(
            "/api/preferences",
            headers=authorization(client),
            json={
                "studio_name": name,
                "revision": 1,
            },
        ).status_code
        == 422
    )
    assert client.get("/api/bootstrap").json()["preferences"]["revision"] == 1


def test_unknown_settings_are_rejected(client):
    assert (
        client.put(
            "/api/preferences",
            headers=authorization(client),
            json={
                "studio_name": "Test",
                "revision": 1,
                "paid_operations_enabled": True,
            },
        ).status_code
        == 422
    )


def test_cross_site_reads_and_writes_are_blocked(client):
    for headers in (
        {"Origin": "https://evil.example"},
        {"Sec-Fetch-Site": "cross-site"},
        {"Origin": "null"},
    ):
        assert client.get("/api/bootstrap", headers=headers).status_code == 403
        assert (
            client.put(
                "/api/preferences",
                headers={**authorization(client), **headers},
                json={"studio_name": "Attack", "revision": 1},
            ).status_code
            == 403
        )
    assert client.get("/api/bootstrap", headers={"Host": "evil.example"}).status_code == 400
    assert (
        client.put(
            "/api/preferences",
            json={
                "studio_name": "No token",
                "revision": 1,
            },
        ).status_code
        == 403
    )


def test_same_origin_and_dev_proxy_requests_work(client):
    for origin in ("http://127.0.0.1:8765", "http://localhost:5173"):
        assert client.get("/api/bootstrap", headers={"Origin": origin}).status_code == 200
    response = client.get("/api/bootstrap")
    assert response.headers["cache-control"] == "no-store"
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]


@pytest.mark.parametrize("path", [PROJECT_ROOT, PROJECT_ROOT / "data", PROJECT_ROOT.parent])
def test_configuration_rejects_repository_overlap(path):
    with pytest.raises(ValidationError):
        Settings(data_dir=path)


def test_configuration_rejects_relative_paths_and_invalid_ports():
    with pytest.raises(ValidationError):
        Settings(data_dir=Path("private-data"))
    with pytest.raises(ValidationError):
        Settings(data_dir=Path.home() / "CharacterStudioTest", port=80)


@pytest.mark.parametrize("path", ["../secret", "/secret", "C:/secret", "..\\secret", "", "."])
def test_asset_paths_cannot_escape(settings, path):
    with pytest.raises(ValueError):
        asset_path(settings, path)


def test_relative_asset_key_roundtrip(settings):
    assert asset_path(settings, "characters/example.jpg") == (
        settings.data_dir / "characters" / "example.jpg"
    )


def test_database_enables_integrity_settings(settings):
    engine = open_database(settings)
    try:
        with engine.connect() as connection:
            assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar() == 1
            assert connection.exec_driver_sql("PRAGMA journal_mode").scalar() == "wal"
            assert connection.exec_driver_sql("PRAGMA integrity_check").scalar() == "ok"
    finally:
        engine.dispose()


def test_future_database_revision_fails_without_downgrade(settings):
    engine = open_database(settings)
    engine.dispose()
    with sqlite3.connect(settings.data_dir / "studio.db") as connection:
        connection.execute("UPDATE alembic_version SET version_num = '9999_future'")
    with pytest.raises(Exception, match="9999_future"):
        open_database(settings)
    with sqlite3.connect(settings.data_dir / "studio.db") as connection:
        assert connection.execute("SELECT version_num FROM alembic_version").fetchone()[0] == (
            "9999_future"
        )


def test_database_backup_retains_checkpoint(settings, tmp_path):
    engine = open_database(settings)
    try:
        with engine.begin() as connection:
            connection.exec_driver_sql("UPDATE studio_preferences SET studio_name = 'Checkpoint'")
        with sqlite3.connect(settings.data_dir / "studio.db") as source:
            with sqlite3.connect(tmp_path / "backup.db") as backup:
                source.backup(backup)
                assert backup.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
                assert backup.execute("SELECT studio_name FROM studio_preferences").fetchone()[
                    0
                ] == ("Checkpoint")
    finally:
        engine.dispose()


def test_missing_frontend_is_explicit(client):
    assert client.get("/").status_code == 503


def test_built_frontend_is_served_without_exposing_source(settings, tmp_path):
    frontend = tmp_path / "frontend"
    frontend.mkdir()
    (frontend / "index.html").write_text("<html><body>Studio</body></html>", encoding="utf-8")
    configured = settings.model_copy(update={"frontend_dir": frontend})
    with TestClient(create_app(configured), base_url="http://127.0.0.1:8765") as client:
        assert "Studio" in client.get("/").text
        assert client.get("/PLAN.md").status_code == 404
        assert client.get("/studio.db").status_code == 404
        assert client.get("/api/not-implemented").status_code == 404
