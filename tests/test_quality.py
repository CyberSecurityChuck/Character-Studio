"""Phase 6B: quality checks of results (fake CLIs and fake APIs) and generation presets."""

import json
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.main import create_app
from tests.conftest import authorization, wait_for_job
from tests.test_api_engines import KEY, api_settings, providers, save_key, select_api  # noqa: F401
from tests.test_generation import approved_scene, generation_calls, import_result
from tests.test_scenes import set_engine


def check(client, result_id, expect=202, **body):
    reply = client.post(
        f"/api/results/{result_id}/check", headers=authorization(client), json=body or None
    )
    assert reply.status_code == expect, reply.text
    return reply.json()


def fake_check_reply(subjects):
    aspects = ("camera_and_framing", "subject_positions", "poses", "head_and_gaze", "outfits",
               "environment", "lighting")
    return {
        "schema_version": 1,
        "composition": {a: {"score": 2 if a == "lighting" else 5, "note": "ok"} for a in aspects},
        "identity": [{"subject": s, "expected": e, "score": 3, "note": "Some differences."}
                     for s, e in subjects],
        "summary": "Lighting is much warmer than the Base Image.",
        "issues": ["Lighting is warmer."],
    }


@pytest.mark.parametrize("engine", ["claude_cli", "codex_cli"])
def test_cli_check_compares_the_result_with_its_approved_inputs(engine_client, fake, engine):
    client = engine_client
    set_engine(client, engine)
    _ada, scene = approved_scene(client)
    result = import_result(client, scene)["results"][0]
    queued = check(client, result["id"])
    assert queued["workflow_state"] == "checking"
    assert queued["active_job"]["kind"] == "check"
    job = wait_for_job(client, queued["active_job"]["id"])
    assert job["status"] == "completed", job
    detail = client.get(f"/api/scenes/{scene['id']}").json()
    assert detail["workflow_state"] == "approved" or detail["workflow_state"] == "generated"
    summary = detail["results"][0]["check"]
    assert summary["engine"] == engine and summary["result_id"] == result["id"]
    # The lowest score is shown, so one weak aspect is never averaged away.
    assert summary["composition_score"] == 3 and summary["identity_score"] == 4
    expected = {(i["subject"], i["expected"]) for i in summary["data"]["identity"]}
    assert ("Subject 1", "replaced") in expected

    folder = Path(job["job_folder"])
    images = sorted(folder.glob("image-*.jpg"))
    assert len(images) >= 3  # Base Image, reference photos and the result
    instruction = (folder / "instruction.txt").read_text(encoding="utf-8")
    assert "Ada" not in instruction and "Do not identify or name anyone" in instruction
    assert f"Image {len(images)}: the generated result to check." in instruction
    calls = [json.loads(line) for line in fake.read_text(encoding="utf-8").splitlines()]
    run = [c for c in calls if "--version" not in c["args"] and "status" not in c["args"]][-1]
    if engine == "codex_cli":
        assert run["args"].count("-i") == len(images) and "--output-schema" in run["args"]
        assert generation_calls(fake) == []  # a check never generates an image
    else:
        assert "--restricted" in run["args"]
    listed = client.get(f"/api/results/{result['id']}/checks").json()
    assert [c["id"] for c in listed] == [summary["id"]]


def test_checks_need_an_engine_and_a_valid_reply(engine_client, monkeypatch):
    client = engine_client
    _ada, scene = approved_scene(client)
    result = import_result(client, scene)["results"][0]
    set_engine(client, "manual")
    assert "need an analysis engine" in check(client, result["id"], expect=409)["detail"]
    set_engine(client, "claude_cli")
    monkeypatch.setenv("FAKE_CLI_MODE", "invalid")
    job = wait_for_job(client, check(client, result["id"])["active_job"]["id"])
    assert (job["status"], job["error_kind"]) == ("failed", "invalid_output")
    assert client.get(f"/api/results/{result['id']}/checks").json() == []
    missing = client.post("/api/results/missing/check", headers=authorization(client))
    assert missing.status_code == 404


def test_api_check_needs_confirmation_and_sends_every_image(api_settings, providers):  # noqa: F811
    with TestClient(create_app(api_settings), base_url="http://127.0.0.1:8765") as client:
        _ada, scene = approved_scene(client)
        result = import_result(client, scene)["results"][0]
        save_key(client, "gemini_api")
        assert select_api(client, "gemini_api").status_code == 200
        assert "charged" in check(client, result["id"], expect=409)["detail"]
        providers.next["gemini_api"] = (
            200,
            {
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {"text": json.dumps(fake_check_reply([("Subject 1", "replaced")]))}
                            ]
                        },
                        "finishReason": "STOP",
                    }
                ],
                "usageMetadata": {"promptTokenCount": 5200, "candidatesTokenCount": 400},
            },
        )
        queued = check(client, result["id"], confirm_charges=True)
        job = wait_for_job(client, queued["active_job"]["id"])
        assert job["status"] == "completed", job
        assert job["usage"]["input_tokens"] == 5200 and job["model"] == "test-model"
        [sent] = providers.posts()
        parts = sent["body"]["contents"][0]["parts"]
        labels = [p["text"] for p in parts if "text" in p and p["text"].startswith("Image ")]
        images = [p for p in parts if "inline_data" in p]
        assert len(images) == len(labels) >= 3
        assert "save_quality_check" not in json.dumps(sent["body"])  # Gemini: JSON mode
        assert "Ada" not in json.dumps(sent["body"]) and KEY not in json.dumps(sent["body"])
        summary = client.get(f"/api/scenes/{scene['id']}").json()["results"][0]["check"]
        assert summary["composition_score"] == 2 and summary["identity_score"] == 3


def test_deleting_results_and_scenes_removes_their_checks(engine_client, fake, settings):
    client = engine_client
    _ada, scene = approved_scene(client)
    first, = import_result(client, scene)["results"]
    wait_for_job(client, check(client, first["id"])["active_job"]["id"])
    second = import_result(client, scene)["results"][0]
    wait_for_job(client, check(client, second["id"])["active_job"]["id"])
    with sqlite3.connect(settings.data_dir / "studio.db") as db:
        db.execute(
            "INSERT INTO engine_jobs (id, kind, scene_id, engine, status, timeout_seconds, "
            "input_id, created_at) VALUES ('c-wait', 'check', ?, 'claude_cli', 'not_started', "
            "300, ?, 'z')",
            (scene["id"], second["id"]),
        )
    refused = client.delete(f"/api/results/{second['id']}", headers=authorization(client))
    assert refused.status_code == 409
    client.post("/api/jobs/c-wait/cancel", headers=authorization(client))
    removed = client.delete(f"/api/results/{second['id']}", headers=authorization(client))
    assert removed.status_code == 200, removed.text
    with sqlite3.connect(settings.data_dir / "studio.db") as db:
        assert db.execute("SELECT result_id FROM quality_checks").fetchall() == [(first["id"],)]
    revision = client.get(f"/api/scenes/{scene['id']}").json()["revision"]
    deleted = client.delete(
        f"/api/scenes/{scene['id']}?revision={revision}", headers=authorization(client)
    )
    assert deleted.status_code == 200, deleted.text
    with sqlite3.connect(settings.data_dir / "studio.db") as db:
        assert db.execute("SELECT count(*) FROM quality_checks").fetchone() == (0,)


def preset_body(**changes):
    return {"name": "Golden hour", "scene_changes": "Warm golden-hour light",
            "negative_additions": "harsh flash", "images": 3} | changes


def test_presets_are_saved_validated_and_recorded_with_runs(engine_client, fake):
    client = engine_client
    headers = authorization(client)
    created = client.post("/api/presets", headers=headers, json=preset_body())
    assert created.status_code == 201, created.text
    preset = created.json()
    assert preset["images"] == 3 and preset["revision"] == 1
    duplicate = client.post("/api/presets", headers=headers, json=preset_body(name="golden HOUR"))
    assert duplicate.status_code == 409
    for bad in ({"images": 0}, {"images": 11}, {"name": ""}, {"name": "two\nlines"}):
        refused = client.post("/api/presets", headers=headers, json=preset_body(**bad))
        assert refused.status_code == 422
    updated = client.put(
        f"/api/presets/{preset['id']}", headers=headers,
        json=preset_body(name="Golden hour soft", images=2, revision=1),
    ).json()
    assert updated["revision"] == 2 and updated["images"] == 2
    stale = client.put(
        f"/api/presets/{preset['id']}", headers=headers, json=preset_body(revision=1)
    )
    assert stale.status_code == 409
    assert [p["name"] for p in client.get("/api/presets").json()] == ["Golden hour soft"]

    _ada, scene = approved_scene(client)
    reply = client.post(
        f"/api/scenes/{scene['id']}/generate", headers=headers,
        json={"approval_id": scene["approval"]["current"]["id"], "preset_id": preset["id"]},
    )
    assert reply.status_code == 202, reply.text
    wait_for_job(client, reply.json()["active_job"]["id"])
    result = client.get(f"/api/scenes/{scene['id']}").json()["results"][0]
    assert result["preset"] == "Golden hour soft"
    missing = client.post(
        f"/api/scenes/{scene['id']}/generate", headers=headers,
        json={"approval_id": scene["approval"]["current"]["id"], "preset_id": "gone"},
    )
    assert missing.status_code == 409
    batch = client.post(
        "/api/batches/generation", headers=headers,
        json={"items": [{"scene_id": scene["id"]}], "count": 1, "preset_id": preset["id"]},
    ).json()["batch"]
    assert batch["settings"]["preset"] == "Golden hour soft"
    [item] = batch["items"]
    wait_for_job(client, item["job_id"])
    assert client.delete(f"/api/presets/{preset['id']}", headers=headers).status_code == 200
    assert client.get("/api/presets").json() == []
    # A deleted preset's name stays with the results made with it.
    results = client.get(f"/api/scenes/{scene['id']}").json()["results"]
    assert [r["preset"] for r in results] == ["Golden hour soft", "Golden hour soft"]
