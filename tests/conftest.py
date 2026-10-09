from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.configuration import Settings
from backend.main import create_app


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(data_dir=tmp_path / "private-data", frontend_dir=tmp_path / "no-build")


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings), base_url="http://127.0.0.1:8765") as client:
        yield client


def authorization(client):
    return {"X-Studio-Token": client.get("/api/bootstrap").json()["session_token"]}
