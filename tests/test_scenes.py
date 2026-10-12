"""Phase 3: scenes, analysis (CLI engines with a fake CLI, manual import), prompts, jobs."""

import copy
import io
import json
import sqlite3
import sys
import time
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import create_engine

from backend.analysis_schema import JSON_SCHEMA, SceneAnalysisData
from backend.engines import run_process
from backend.main import create_app
from tests.conftest import ANALYSIS, authorization, wait_for_job
from tests.test_library import picture


def create_scene(client, title="Street scene", content=None):
    result = client.post(
        f"/api/scenes?title={title}",
        headers={**authorization(client), "Content-Type": "application/octet-stream"},
        content=content if content is not None else picture("JPEG"),
    )
    assert result.status_code == 201, result.text
    return result.json()


def import_manual(client, scene, text=None):
    return client.post(
        f"/api/scenes/{scene['id']}/analyses",
        headers=authorization(client),
        json={"text": text if text is not None else json.dumps(ANALYSIS)},
    )


def set_engine(client, engine, **changes):
    current = client.get("/api/engines/settings").json()
    body = {**current, "analysis_engine": engine, **changes}
    result = client.put("/api/engines/settings", headers=authorization(client), json=body)
    assert result.status_code == 200, result.text
    return result.json()


def test_schema_models_match_the_engine_json_schema():
    def required(schema):
        return set(schema["required"])

    fields = SceneAnalysisData.model_fields
    assert required(JSON_SCHEMA) == set(fields)
    subject = JSON_SCHEMA["properties"]["subjects"]["items"]
    from backend.analysis_schema import Camera, Subject

    assert required(subject) == set(Subject.model_fields)
    assert required(JSON_SCHEMA["properties"]["camera"]) == set(Camera.model_fields)
    SceneAnalysisData.model_validate(ANALYSIS)


def test_scene_lifecycle_survives_restart(settings):
    original = picture("JPEG")
    with TestClient(create_app(settings), base_url="http://127.0.0.1:8765") as client:
        scene = create_scene(client, "Street scene", original)
        assert scene["workflow_state"] == "needs_analysis"
        assert (scene["width"], scene["height"]) == (800, 600)
        renamed = client.put(
            f"/api/scenes/{scene['id']}",
            headers=authorization(client),
            json={"title": "  Evening street ", "revision": 1},
        )
        assert renamed.json()["title"] == "Evening street"
        stale = client.put(
            f"/api/scenes/{scene['id']}",
            headers=authorization(client),
            json={"title": "Old tab", "revision": 1},
        )
        assert stale.status_code == 409
        assert import_manual(client, scene).status_code == 201
    with TestClient(create_app(settings), base_url="http://127.0.0.1:8765") as client:
        restored = client.get(f"/api/scenes/{scene['id']}").json()
        assert restored["title"] == "Evening street"
        assert restored["analyses"][0]["analysis"] == ANALYSIS
        assert restored["workflow_state"] == "review_analysis"
        assert client.get(restored["original_url"]).content == original
        with Image.open(io.BytesIO(client.get(restored["thumbnail_url"]).content)) as thumb:
            assert thumb.size == (480, 360)
        assert [s["id"] for s in client.get("/api/scenes").json()] == [scene["id"]]


def test_duplicate_and_delete_scene(client, settings):
    scene = create_scene(client)
    import_manual(client, scene)
    detail = client.get(f"/api/scenes/{scene['id']}").json()
    analysis_id = detail["analyses"][0]["id"]
    draft = client.post(
        f"/api/scenes/{scene['id']}/prompts/draft",
        headers=authorization(client),
        json={"analysis_id": analysis_id},
    ).json()
    client.post(
        f"/api/scenes/{scene['id']}/prompts",
        headers=authorization(client),
        json={**draft, "analysis_id": analysis_id, "source": "template"},
    )
    copy_result = client.post(f"/api/scenes/{scene['id']}/duplicate", headers=authorization(client))
    assert copy_result.status_code == 201
    duplicate = copy_result.json()
    assert duplicate["title"] == "Copy of Street scene"
    assert duplicate["duplicated_from"] == scene["id"]
    assert duplicate["analyses"][0]["analysis"] == ANALYSIS
    assert duplicate["prompts"][0]["analysis_id"] == duplicate["analyses"][0]["id"]
    assert client.get(duplicate["original_url"]).content == picture("JPEG")

    deleted = client.delete(f"/api/scenes/{scene['id']}?revision=1", headers=authorization(client))
    assert deleted.json() == {"deleted": True, "cleanup_pending": False}
    assert client.get(f"/api/scenes/{scene['id']}").status_code == 404
    assert client.get(duplicate["original_url"]).status_code == 200
    remaining = {p.name for p in (settings.data_dir / "scenes").iterdir()}
    assert remaining == {f"{duplicate['id']}.jpg"}


@pytest.mark.parametrize("payload", [b"", b"not an image", picture("GIF")])
def test_bad_scene_uploads_leave_nothing(client, settings, payload):
    result = client.post(
        "/api/scenes?title=Bad",
        headers={**authorization(client), "Content-Type": "application/octet-stream"},
        content=payload,
    )
    assert result.status_code == 422
    assert not any((settings.data_dir / "scenes").iterdir())
    assert client.get("/api/scenes").json() == []


def test_manual_import_validation_and_correction(client):
    scene = create_scene(client)
    fenced = import_manual(
        client, scene, "Here you go:\n```json\n" + json.dumps(ANALYSIS) + "\n```"
    )
    assert fenced.status_code == 201, fenced.text
    first = fenced.json()["analyses"][0]
    assert (first["version"], first["source"]) == (1, "manual_import")

    broken = import_manual(client, scene, "{not json")
    assert broken.status_code == 422
    assert "not valid JSON" in broken.json()["detail"]
    wrong = copy.deepcopy(ANALYSIS)
    del wrong["camera"]["height"]
    wrong["subjects"][0]["bounding_box"]["x"] = 2
    mismatch = import_manual(client, scene, json.dumps(wrong))
    assert mismatch.status_code == 422
    assert "camera.height" in mismatch.json()["detail"]
    assert "bounding_box.x" in mismatch.json()["detail"]
    extra = import_manual(client, scene, json.dumps({**ANALYSIS, "identity": "a name"}))
    assert extra.status_code == 422

    corrected = copy.deepcopy(ANALYSIS)
    corrected["subjects"][0]["eye_direction"] = "Looking at the camera (confirmed)"
    corrected["uncertainties"] = []
    revised = client.post(
        f"/api/scenes/{scene['id']}/analyses/{first['id']}/revise",
        headers=authorization(client),
        json={"analysis": corrected, "confirmed_uncertainties": ANALYSIS["uncertainties"]},
    )
    assert revised.status_code == 201, revised.text
    detail = revised.json()
    # No uncertainties left; Subject 1 still needs a character or "Keep original" (Phase 4).
    assert detail["workflow_state"] == "needs_mapping"
    newest = detail["analyses"][0]
    assert (newest["version"], newest["source"], newest["based_on_id"]) == (
        2,
        "user_edit",
        first["id"],
    )
    assert newest["confirmed_uncertainties"] == ANALYSIS["uncertainties"]
    assert detail["analyses"][1]["analysis"] == ANALYSIS
    invalid = client.post(
        f"/api/scenes/{scene['id']}/analyses/{first['id']}/revise",
        headers=authorization(client),
        json={"analysis": {"schema_version": 1}},
    )
    assert invalid.status_code == 422


def test_prompt_template_versions_and_staleness(client):
    scene = create_scene(client)
    analysis_id = import_manual(client, scene).json()["analyses"][0]["id"]
    draft = client.post(
        f"/api/scenes/{scene['id']}/prompts/draft",
        headers=authorization(client),
        json={"analysis_id": analysis_id, "scene_changes": "Make it golden hour."},
    ).json()
    prompt = draft["prompt_text"]
    for expected in (
        "Image 1: the BASE IMAGE",
        "IDENTITY LOCK",
        "COMPOSITION LOCK",
        "Subject 1 (centre)",
        "Eyes and gaze: Looking at the camera.",
        "Keep the bicycle on the left of the subject",
        "UNCERTAIN DETAILS",
        "REQUESTED CHANGES",
        "Make it golden hour.",
    ):
        assert expected in prompt
    assert "watermarks" in draft["negative_prompt"]

    def save(text, source):
        return client.post(
            f"/api/scenes/{scene['id']}/prompts",
            headers=authorization(client),
            json={
                "analysis_id": analysis_id,
                "prompt_text": text,
                "negative_prompt": draft["negative_prompt"],
                "scene_changes": "Make it golden hour.",
                "source": source,
            },
        ).json()

    first = save(prompt, "template")
    assert first["workflow_state"] == "review_analysis"
    edited = save(prompt + "\nExtra detail.", "user_edit")
    restored = save(first["prompts"][0]["prompt_text"], "restored")
    assert [p["version"] for p in restored["prompts"]] == [3, 2, 1]
    assert restored["prompts"][1]["prompt_text"].endswith("Extra detail.")
    assert edited["prompts"][0]["source"] == "user_edit"
    empty = client.post(
        f"/api/scenes/{scene['id']}/prompts",
        headers=authorization(client),
        json={"prompt_text": "", "source": "user_edit"},
    )
    assert empty.status_code == 422

    clean = copy.deepcopy(ANALYSIS)
    clean["uncertainties"] = []
    revised = client.post(
        f"/api/scenes/{scene['id']}/analyses/{analysis_id}/revise",
        headers=authorization(client),
        json={"analysis": clean},
    ).json()
    # Once the uncertainty is resolved, the unassigned subject is the next step (Phase 4).
    assert revised["workflow_state"] == "needs_mapping"


@pytest.mark.parametrize("engine", ["claude_cli", "codex_cli"])
def test_engine_analysis_runs_confined_and_records_provenance(engine_client, fake, engine):
    client = engine_client
    set_engine(client, engine)
    scene = create_scene(client, content=picture("JPEG"))
    queued = client.post(f"/api/scenes/{scene['id']}/analyse", headers=authorization(client))
    assert queued.status_code == 202, queued.text
    job = queued.json()["active_job"]
    assert job["engine"] == engine
    finished = wait_for_job(client, job["id"])
    assert finished["status"] == "completed", finished
    expected_version = "2.1.296 (Claude Code)" if engine == "claude_cli" else "codex-cli 0.162.1"
    assert finished["engine_version"] == expected_version
    detail = client.get(f"/api/scenes/{scene['id']}").json()
    analysis = detail["analyses"][0]
    assert (analysis["source"], analysis["engine_version"]) == (engine, expected_version)
    assert analysis["has_raw_output"] and analysis["job_id"] == job["id"]
    assert detail["workflow_state"] == "review_analysis"

    folder = Path(finished["job_folder"])
    assert folder.name == "analysis-1" and folder.parent.name == scene["id"]
    with Image.open(folder / "base.jpg") as base:
        assert not base.getexif()
    assert (folder / ("output.json" if engine == "claude_cli" else "events.jsonl")).is_file()

    runs = [json.loads(line) for line in fake.read_text(encoding="utf-8").splitlines()]
    assert all(not run["leaked"] for run in runs)
    analysis_run = [run for run in runs if run["args"][0] in ("-p", "exec")][-1]
    assert analysis_run["stdin_closed"]
    assert Path(analysis_run["cwd"]) == folder
    args = analysis_run["args"]
    if engine == "claude_cli":
        for flag in ("--restricted", "--strict-mcp-config", "--no-session-persistence"):
            assert flag in args
        assert args[args.index("--tools") + 1] == "Read"
        assert json.loads(args[args.index("--json-schema") + 1]) == JSON_SCHEMA
    else:
        assert args[args.index("-s") + 1] == "read-only"
        assert args[args.index("--disable") + 1] == "image_generation"
        assert args[args.index("-i") + 1] == str(folder / "base.jpg")
        assert args[-2] == "--"


@pytest.mark.parametrize(
    "mode, kind",
    [
        ("signed_out", "signed_out"),
        ("logged_out_run", "signed_out"),
        ("limit", "usage_limit"),
        ("invalid", "invalid_output"),
    ],
)
def test_engine_failures_are_reported_and_never_retried(
    engine_client, fake, monkeypatch, mode, kind
):
    client = engine_client
    monkeypatch.setenv("FAKE_CLI_MODE", mode)
    scene = create_scene(client)
    job = client.post(f"/api/scenes/{scene['id']}/analyse", headers=authorization(client))
    finished = wait_for_job(client, job.json()["active_job"]["id"])
    assert (finished["status"], finished["error_kind"]) == ("failed", kind)
    assert finished["error_details"]
    time.sleep(0.5)
    runs = [json.loads(line) for line in fake.read_text(encoding="utf-8").splitlines()]
    assert sum(run["args"][:1] == ["-p"] for run in runs) <= 1
    detail = client.get(f"/api/scenes/{scene['id']}").json()
    assert detail["analyses"] == [] and detail["workflow_state"] == "needs_analysis"
    assert [j["status"] for j in detail["jobs"]] == ["failed"]


def test_claude_text_reply_is_parsed_and_missing_cli_is_reported(
    engine_settings, fake, monkeypatch, tmp_path
):
    monkeypatch.setenv("FAKE_CLI_MODE", "text")
    with TestClient(create_app(engine_settings), base_url="http://127.0.0.1:8765") as client:
        scene = create_scene(client)
        job = client.post(f"/api/scenes/{scene['id']}/analyse", headers=authorization(client))
        assert wait_for_job(client, job.json()["active_job"]["id"])["status"] == "completed"
    missing = engine_settings.model_copy(
        update={"engine_commands": {"claude_cli": (str(tmp_path / "no-such-cli.exe"),)}}
    )
    with TestClient(create_app(missing), base_url="http://127.0.0.1:8765") as client:
        scene = create_scene(client)
        job = client.post(f"/api/scenes/{scene['id']}/analyse", headers=authorization(client))
        finished = wait_for_job(client, job.json()["active_job"]["id"])
        assert finished["error_kind"] == "not_installed"
        status = {s["engine"]: s for s in client.get("/api/engines/status").json()}
        assert status["claude_cli"]["installed"] is False


def test_cancel_stops_the_run_and_guards(engine_client, fake, monkeypatch):
    client = engine_client
    monkeypatch.setenv("FAKE_CLI_MODE", "slow")
    scene = create_scene(client)
    job = client.post(f"/api/scenes/{scene['id']}/analyse", headers=authorization(client))
    job_id = job.json()["active_job"]["id"]
    again = client.post(f"/api/scenes/{scene['id']}/analyse", headers=authorization(client))
    assert again.status_code == 409
    deadline = time.monotonic() + 20
    while client.get(f"/api/jobs/{job_id}").json()["job_folder"] is None:
        assert time.monotonic() < deadline
        time.sleep(0.1)
    time.sleep(0.5)
    blocked = client.delete(f"/api/scenes/{scene['id']}?revision=1", headers=authorization(client))
    assert blocked.status_code == 409
    started = time.monotonic()
    client.post(f"/api/jobs/{job_id}/cancel", headers=authorization(client))
    finished = wait_for_job(client, job_id)
    assert finished["status"] == "cancelled"
    assert time.monotonic() - started < 15
    assert client.get(f"/api/scenes/{scene['id']}").json()["workflow_state"] == "needs_analysis"


def test_manual_engine_setting_and_settings_validation(engine_client):
    client = engine_client
    defaults = client.get("/api/engines/settings").json()
    assert defaults == {
        "analysis_engine": "claude_cli",
        "generation_engine": "codex_cli",
        "claude_timeout": 300,
        "codex_timeout": 300,
        "api_timeout": 180,
        "models": {},
        "revision": 1,
    }
    status = {s["engine"]: s for s in client.get("/api/engines/status").json()}
    assert status["claude_cli"] == {
        "engine": "claude_cli",
        "name": "Claude",
        "installed": True,
        "version": "2.1.296 (Claude Code)",
        "signed_in": True,
        "plan": "Pro",
        "message": "",
    }
    assert "private@example.com" not in json.dumps(status)
    assert status["codex_cli"]["plan"] == "ChatGPT"
    set_engine(client, "manual")
    scene = create_scene(client)
    refused = client.post(f"/api/scenes/{scene['id']}/analyse", headers=authorization(client))
    assert refused.status_code == 409
    for change in ({"claude_timeout": 5}, {"analysis_engine": "api"}, {"revision": 1}):
        body = {**client.get("/api/engines/settings").json(), **change}
        result = client.put("/api/engines/settings", headers=authorization(client), json=body)
        assert result.status_code in (409, 422)


def test_restart_marks_unfinished_runs_without_resuming(settings):
    with TestClient(create_app(settings), base_url="http://127.0.0.1:8765") as client:
        scene = create_scene(client)
    with sqlite3.connect(settings.data_dir / "studio.db") as db:
        for job_id, status in (("j-running", "running"), ("j-waiting", "not_started")):
            db.execute(
                "INSERT INTO engine_jobs (id, kind, scene_id, engine, status, timeout_seconds, "
                "created_at) VALUES (?, 'analysis', ?, 'claude_cli', ?, 300, 't')",
                (job_id, scene["id"], status),
            )
        db.execute("UPDATE scenes SET workflow_state = 'analysing'")
    with TestClient(create_app(settings), base_url="http://127.0.0.1:8765") as client:
        running = client.get("/api/jobs/j-running").json()
        waiting = client.get("/api/jobs/j-waiting").json()
        assert (running["status"], running["error_kind"]) == ("interrupted", "interrupted")
        assert "check its job folder" in running["error_details"]
        assert (waiting["status"], waiting["error_kind"]) == ("cancelled", "not_started")
        assert client.get(f"/api/scenes/{scene['id']}").json()["workflow_state"] == (
            "needs_analysis"
        )


def test_process_timeout_is_enforced(tmp_path):
    started = time.monotonic()
    outcome = run_process(
        [sys.executable, "-c", "import time; time.sleep(60)"],
        tmp_path,
        tmp_path / "out.txt",
        timeout=1,
    )
    assert outcome.timed_out and not outcome.cancelled
    assert time.monotonic() - started < 15


def test_upgrade_from_library_schema_adds_default_engine_settings(settings):
    settings.data_dir.mkdir(parents=True)
    engine = create_engine(f"sqlite:///{settings.data_dir / 'studio.db'}")
    config = Config()
    config.set_main_option("script_location", str(Path(__file__).parents[1] / "backend/migrations"))
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "0003_photo_framing")
        connection.exec_driver_sql(
            "INSERT INTO characters VALUES ('c1', 'Kept', 'Adult', '', NULL, 0, 1, 't', 't')"
        )
    engine.dispose()
    with TestClient(create_app(settings), base_url="http://127.0.0.1:8765") as client:
        assert client.get("/api/characters/c1").json()["name"] == "Kept"
        assert client.get("/api/engines/settings").json()["analysis_engine"] == "claude_cli"
        assert client.get("/api/scenes").json() == []
