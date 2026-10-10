import json
import sys
import time
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


# Shared by the Phase 3 and Phase 4 engine tests.
FAKE = Path(__file__).with_name("fake_cli.py")
ANALYSIS = {
    "schema_version": 1,
    "image_properties": {
        "orientation": "landscape",
        "approximate_aspect_ratio": "4:3",
        "style": "Photographic",
    },
    "scene_description": "One person stands beside a bicycle on a quiet street.",
    "camera": {
        "height": "Chest height",
        "direction": "Frontal",
        "shot_type": "Full-body shot",
        "framing": "Subject centred with space above",
        "perspective": "Slight wide-angle",
    },
    "subjects": [
        {
            "label": "Subject 1",
            "position": "centre",
            "bounding_box": {"x": 0.4, "y": 0.2, "width": 0.2, "height": 0.7},
            "body_direction": "Facing the camera",
            "torso_orientation": "Square to camera",
            "shoulder_alignment": "Level",
            "head_direction": "Turned slightly left",
            "facial_viewing_angle": "Three-quarter left",
            "eye_direction": "Looking at the camera",
            "expression": "Gentle smile",
            "arms_and_hands": "Right hand on the handlebar",
            "legs_and_feet": "Standing, feet apart",
            "pose_summary": "Standing beside a bicycle",
            "outfit": "Blue jacket, grey trousers",
            "hairstyle": "Short",
            "accessories": "None visible",
        }
    ],
    "environment": "Residential street with trees",
    "lighting": "Soft overcast daylight",
    "color_palette": "Muted blues and greens",
    "atmosphere": "Calm",
    "composition_constraints": ["Keep the bicycle on the left of the subject"],
    "uncertainties": [{"field": "Subject 1.eye_direction", "note": "Face partly in shadow"}],
}


def wait_for_job(client, job_id, timeout=30):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job = client.get(f"/api/jobs/{job_id}").json()
        if job["status"] not in ("not_started", "running"):
            return job
        time.sleep(0.1)
    raise AssertionError("Job did not finish")


@pytest.fixture
def fake(tmp_path, monkeypatch):
    analysis = tmp_path / "analysis.json"
    analysis.write_text(json.dumps(ANALYSIS), encoding="utf-8")
    log = tmp_path / "cli-log.jsonl"
    monkeypatch.setenv("FAKE_CLI_ANALYSIS", str(analysis))
    monkeypatch.setenv("FAKE_CLI_LOG", str(log))
    monkeypatch.setenv("FAKE_CLI_MODE", "ok")
    # Variables that must never reach a CLI run.
    monkeypatch.setenv("CLAUDE_CODE_TEST_SESSION", "host-session")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "should-not-leak")
    monkeypatch.setenv("OPENAI_API_KEY", "should-not-leak")
    return log


@pytest.fixture
def engine_settings(tmp_path):
    return Settings(
        data_dir=tmp_path / "private-data",
        frontend_dir=tmp_path / "no-build",
        engine_commands={
            "claude_cli": (sys.executable, str(FAKE), "claude"),
            "codex_cli": (sys.executable, str(FAKE), "codex"),
        },
    )


@pytest.fixture
def engine_client(engine_settings, fake):
    with TestClient(create_app(engine_settings), base_url="http://127.0.0.1:8765") as client:
        yield client
