"""Phase 5.5: batch analysis and generation, pausing, restarts and group suggestions."""

import json
import time

from fastapi.testclient import TestClient

from backend.main import create_app
from tests.conftest import authorization
from tests.test_generation import approved_scene, generation_calls
from tests.test_library import create_character
from tests.test_mapping import approve, character_with_photos, map_subjects, two_person_scene
from tests.test_scenes import create_scene, import_manual, set_engine


def post(client, path, body=None, expect=202):
    result = client.post(path, headers=authorization(client), json=body)
    assert result.status_code == expect, result.text
    return result.json()


def wait_for_batch(client, batch_id, states=("finished", "paused", "cancelled"), timeout=30):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        batch = client.get(f"/api/batches/{batch_id}").json()
        if batch["state"] in states:
            return batch
        time.sleep(0.1)
    raise AssertionError(f"Batch stayed {batch['state']}")


def wait_for_item(client, batch_id, position, status, timeout=30):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        item = client.get(f"/api/batches/{batch_id}").json()["items"][position - 1]
        if item["status"] == status:
            return item
        time.sleep(0.05)
    raise AssertionError(f"Item {position} is {item['status']}, not {status}")


def scene_state(client, scene):
    return client.get(f"/api/scenes/{scene['id']}").json()["workflow_state"]


def analysis_calls(log):
    if not log.is_file():
        return []
    calls = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
    return [c for c in calls if "-p" in c["args"]]


def test_analyse_selected_runs_one_after_another_and_pauses_only_between_items(
    engine_client, fake, monkeypatch, tmp_path
):
    client = engine_client
    gate = tmp_path / "gate"
    monkeypatch.setenv("FAKE_CLI_GATE", str(gate))
    first, second = create_scene(client, "First"), create_scene(client, "Second")
    done = create_scene(client, "Done")
    import_manual(client, done)

    queued = post(
        client, "/api/batches/analysis", {"scene_ids": [first["id"], second["id"], done["id"]]}
    )
    batch = queued["batch"]
    assert [s["title"] for s in queued["skipped"]] == ["Done"]
    assert "already has an analysis" in queued["skipped"][0]["reason"]
    assert (batch["kind"], batch["engine"], batch["total"]) == ("analysis", "claude_cli", 2)
    assert [i["scene_title"] for i in batch["items"]] == ["First", "Second"]

    # One at a time: the second waits, visibly, while the first runs.
    wait_for_item(client, batch["id"], 1, "running")
    assert scene_state(client, first) == "analysing"
    assert scene_state(client, second) == "waiting_analysis"
    waiting = client.get(f"/api/scenes/{second['id']}").json()["active_job"]
    assert waiting["batch"]["position"] == 2 and waiting["batch"]["total"] == 2
    # A waiting scene cannot be queued again, alone or in another batch.
    again = client.post(
        "/api/batches/analysis", headers=authorization(client), json={"scene_ids": [second["id"]]}
    )
    assert again.status_code == 409 and "Nothing was queued" in again.json()["detail"]

    # Pause lets the running item finish but starts nothing new.
    paused = post(client, f"/api/batches/{batch['id']}/pause", expect=200)
    assert paused["state"] == "pausing"
    gate.write_text("open")
    paused = wait_for_batch(client, batch["id"], ("paused",))
    assert paused["pause_kind"] == "user"
    assert paused["counts"] == {**paused["counts"], "completed": 1, "not_started": 1}
    time.sleep(0.5)
    assert client.get(f"/api/batches/{batch['id']}").json()["counts"]["not_started"] == 1
    assert len(analysis_calls(fake)) == 1

    # Only the user continues it.
    post(client, f"/api/batches/{batch['id']}/continue", expect=200)
    finished = wait_for_batch(client, batch["id"])
    assert finished["state"] == "finished" and finished["counts"]["completed"] == 2
    for scene in (first, second):
        detail = client.get(f"/api/scenes/{scene['id']}").json()
        # Each analysis is reviewed per scene, with its own job record.
        assert detail["workflow_state"] == "review_analysis"
        assert detail["jobs"][0]["batch_id"] == batch["id"]
        assert detail["analyses"][0]["job_id"] == detail["jobs"][0]["id"]
    assert len(analysis_calls(fake)) == 2

    # Finished batches can be removed from the list; the runs stay.
    assert post(client, f"/api/batches/{batch['id']}/retry", expect=409)
    client.delete(f"/api/batches/{batch['id']}", headers=authorization(client))
    assert client.get(f"/api/batches/{batch['id']}").status_code == 404
    assert client.get(f"/api/scenes/{first['id']}").json()["jobs"][0]["batch_id"] is None


def test_manual_engine_and_size_limits_refuse_batches(engine_client):
    client = engine_client
    scene = create_scene(client)
    set_engine(client, "manual")
    refused = client.post(
        "/api/batches/analysis", headers=authorization(client), json={"scene_ids": [scene["id"]]}
    )
    assert refused.status_code == 409 and "Manual analysis" in refused.json()["detail"]
    _ada, approved = approved_scene(client)
    too_many = client.post(
        "/api/batches/generation",
        headers=authorization(client),
        json={"items": [{"scene_id": approved["id"]}], "count": 11},
    )
    assert too_many.status_code == 422
    settings = client.get("/api/engines/settings").json()
    client.put(
        "/api/engines/settings",
        headers=authorization(client),
        json={**settings, "generation_engine": "manual"},
    )
    manual = client.post(
        "/api/batches/generation",
        headers=authorization(client),
        json={"items": [{"scene_id": approved["id"]}], "count": 2},
    )
    assert manual.status_code == 409 and "Manual generation" in manual.json()["detail"]


def two_approved_scenes(client):
    _ada, first = approved_scene(client)
    bo = character_with_photos(client, "Bo", ("Front",))
    second = two_person_scene(client)
    second = map_subjects(
        client,
        second,
        [
            {"label": "Subject 1", "action": "keep"},
            {"label": "Subject 2", "action": "replace", "character_id": bo["id"]},
        ],
    )
    from tests.test_mapping import save_template_prompt

    return first, approve(client, save_template_prompt(client, second))


def test_generate_approved_scenes_pauses_at_the_plan_limit_and_never_retries(
    engine_client, fake, monkeypatch
):
    client = engine_client
    first, second = two_approved_scenes(client)
    unapproved = create_scene(client, "Not approved")
    monkeypatch.setenv("FAKE_CLI_MODE", "limit")
    queued = post(
        client,
        "/api/batches/generation",
        {"items": [{"scene_id": s["id"]} for s in (first, second, unapproved)], "count": 1},
    )
    batch = queued["batch"]
    assert [s["title"] for s in queued["skipped"]] == ["Not approved"]
    assert "Approve this scene" in queued["skipped"][0]["reason"]
    # Each item records its own scene's approval.
    jobs = [client.get(f"/api/jobs/{i['job_id']}").json() for i in batch["items"]]
    assert [j["input_id"] for j in jobs] == [
        first["approval"]["current"]["id"],
        second["approval"]["current"]["id"],
    ]

    paused = wait_for_batch(client, batch["id"])
    assert (paused["state"], paused["pause_kind"]) == ("paused", "usage_limit")
    assert [i["status"] for i in paused["items"]] == ["failed", "not_started"]
    assert scene_state(client, second) == "waiting_generation"
    time.sleep(0.5)
    assert len(generation_calls(fake)) == 1  # the next item was not sent

    monkeypatch.setenv("FAKE_CLI_MODE", "ok")
    post(client, f"/api/batches/{batch['id']}/continue", expect=200)
    finished = wait_for_batch(client, batch["id"])
    assert [i["status"] for i in finished["items"]] == ["failed", "completed"]
    assert finished["items"][1]["result_version"] == 1
    assert finished["retryable"] == 1
    assert len(generation_calls(fake)) == 2

    # Trying failed items again is the user's choice and makes a new item.
    retried = post(client, f"/api/batches/{batch['id']}/retry")["batch"]
    assert retried["total"] == 3 and retried["items"][2]["retry_of"] == batch["items"][0]["job_id"]
    finished = wait_for_batch(client, batch["id"])
    assert finished["items"][2]["status"] == "completed" and finished["retryable"] == 0
    assert scene_state(client, first) == "generated"
    assert len(generation_calls(fake)) == 3


def test_signed_out_pauses_before_anything_is_sent(engine_client, fake, monkeypatch):
    client = engine_client
    first, second = two_approved_scenes(client)
    monkeypatch.setenv("FAKE_CLI_MODE", "signed_out")
    batch = post(
        client,
        "/api/batches/generation",
        {"items": [{"scene_id": first["id"]}, {"scene_id": second["id"]}], "count": 2},
    )["batch"]
    assert batch["total"] == 4
    paused = wait_for_batch(client, batch["id"])
    assert (paused["state"], paused["pause_kind"]) == ("paused", "signed_out")
    # The item that found the sign-out waits again: nothing was sent, nothing failed.
    assert [i["status"] for i in paused["items"]] == ["not_started"] * 4
    assert generation_calls(fake) == []
    still = client.post(f"/api/batches/{batch['id']}/continue", headers=authorization(client))
    assert still.status_code == 409 and "still signed out" in still.json()["detail"]

    cancelled = post(client, f"/api/batches/{batch['id']}/cancel", expect=200)
    assert cancelled["state"] == "cancelled"
    assert [i["status"] for i in cancelled["items"]] == ["cancelled"] * 4
    assert scene_state(client, first) == "approved"


def test_one_failed_item_does_not_stop_the_batch(engine_client, fake, monkeypatch, tmp_path):
    client = engine_client
    first, second = two_approved_scenes(client)
    gate = tmp_path / "gate"
    monkeypatch.setenv("FAKE_CLI_GATE", str(gate))
    batch = post(
        client,
        "/api/batches/generation",
        {"items": [{"scene_id": first["id"]}, {"scene_id": second["id"]}]},
    )["batch"]
    wait_for_item(client, batch["id"], 1, "running")
    # The second scene's approval ends while it waits: it must not be sent.
    post(
        client,
        f"/api/scenes/{second['id']}/approval/withdraw",
        {"approval_id": second["approval"]["current"]["id"]},
        expect=200,
    )
    gate.write_text("open")
    finished = wait_for_batch(client, batch["id"])
    assert finished["state"] == "finished"
    assert [i["status"] for i in finished["items"]] == ["completed", "failed"]
    assert finished["items"][1]["error_kind"] == "approval_ended"
    assert len(generation_calls(fake)) == 1


def test_several_images_from_one_approval(engine_client, fake):
    client = engine_client
    _ada, scene = approved_scene(client)
    approval_id = scene["approval"]["current"]["id"]
    stale = client.post(
        "/api/batches/generation",
        headers=authorization(client),
        json={"items": [{"scene_id": scene["id"], "approval_id": "0" * 32}], "count": 3},
    )
    assert stale.status_code == 409 and "approval changed" in stale.json()["detail"]
    batch = post(
        client,
        "/api/batches/generation",
        {
            "items": [{"scene_id": scene["id"], "approval_id": approval_id}],
            "count": 3,
            "mode": "variation",
        },
    )["batch"]
    assert batch["settings"] == {"count": 3, "mode": "variation"} and batch["scene_count"] == 1
    finished = wait_for_batch(client, batch["id"])
    assert [i["result_version"] for i in finished["items"]] == [1, 2, 3]
    detail = client.get(f"/api/scenes/{scene['id']}").json()
    assert [r["mode"] for r in detail["results"]] == ["variation"] * 3
    assert {r["approval_id"] for r in detail["results"]} == {approval_id}
    assert len(generation_calls(fake)) == 3


def test_restart_pauses_the_batch_and_marks_the_running_item_interrupted(
    engine_settings, fake, monkeypatch, tmp_path
):
    gate = tmp_path / "gate"
    monkeypatch.setenv("FAKE_CLI_GATE", str(gate))
    with TestClient(create_app(engine_settings), base_url="http://127.0.0.1:8765") as client:
        scenes = [create_scene(client, f"Scene {n}") for n in (1, 2)]
        batch = post(
            client, "/api/batches/analysis", {"scene_ids": [s["id"] for s in scenes]}
        )["batch"]
        wait_for_item(client, batch["id"], 1, "running")
        deadline = time.monotonic() + 30
        while not analysis_calls(fake) and time.monotonic() < deadline:
            time.sleep(0.05)
    gate.write_text("open")
    with TestClient(create_app(engine_settings), base_url="http://127.0.0.1:8765") as client:
        time.sleep(0.5)
        after = client.get(f"/api/batches/{batch['id']}").json()
        assert (after["state"], after["pause_kind"]) == ("paused", "restart")
        assert [i["status"] for i in after["items"]] == ["interrupted", "not_started"]
        assert scene_state(client, scenes[1]) == "waiting_analysis"
        assert len(analysis_calls(fake)) == 1
        # A single click still runs at once; the paused batch waits for Continue.
        single = post(client, f"/api/scenes/{scenes[0]['id']}/analyse")
        assert single["active_job"]["batch_id"] is None
        post(client, f"/api/batches/{batch['id']}/continue", expect=200)
        finished = wait_for_batch(client, batch["id"])
        assert [i["status"] for i in finished["items"]] == ["interrupted", "completed"]


def test_group_suggestions_need_confirming_per_scene(engine_client):
    client = engine_client
    ada = character_with_photos(client, "Ada")
    bo = character_with_photos(client, "Bo")
    nobody = create_character(client, "No photos")
    group = post(
        client,
        "/api/groups",
        {"name": "Pair", "member_ids": [ada["id"], bo["id"], nobody["id"]]},
        expect=201,
    )
    scenes = [two_person_scene(client) for _ in range(3)]
    unanalysed = create_scene(client, "Not analysed")
    map_subjects(client, scenes[2], [{"label": "Subject 1", "action": "keep"},
                                     {"label": "Subject 2", "action": "keep"}])
    result = post(
        client,
        "/api/scenes/suggest-group",
        {
            "scene_ids": [s["id"] for s in [*scenes, unanalysed]],
            "group_id": group["id"],
            "order": [bo["id"], nobody["id"], ada["id"]],
        },
        expect=200,
    )
    assert [s["assigned"] for s in result["suggested"]] == [2, 2]
    assert result["left_out"] == ["No photos"]
    assert {s["reason"] for s in result["skipped"]} == {
        "It already has assignments.",
        "Analyse it first.",
    }

    detail = client.get(f"/api/scenes/{scenes[0]['id']}").json()
    # Left to right: Subject 1 (x 0.4-0.6) gets Bo, Subject 2 (x 0.7-0.9) gets Ada.
    assert [(s["character_id"], s["suggested"], s["confirmed"]) for s in detail["subjects"]] == [
        (bo["id"], True, False),
        (ada["id"], True, False),
    ]
    assert detail["mapping_group_id"] == group["id"]
    assert detail["workflow_state"] == "needs_mapping"
    assert "suggestions from a group" in detail["review"]["blockers"][0]

    # Saving the assignments is the confirmation.
    confirmed = map_subjects(
        client,
        detail,
        [
            {"label": s["label"], "action": "replace", "character_id": s["character_id"]}
            for s in detail["subjects"]
        ],
        group_id=group["id"],
    )
    assert all(s["confirmed"] and not s["suggested"] for s in confirmed["subjects"])
    assert confirmed["workflow_state"] == "analysis_ready"

    # Replacing existing assignments only when asked, and never on an approved scene.
    replaced = post(
        client,
        "/api/scenes/suggest-group",
        {
            "scene_ids": [scenes[2]["id"]],
            "group_id": group["id"],
            "order": [ada["id"]],
            "replace_existing": True,
        },
        expect=200,
    )
    assert replaced["suggested"][0]["assigned"] == 1
    _ada, approved = approved_scene(client)
    refused = client.post(
        "/api/scenes/suggest-group",
        headers=authorization(client),
        json={"scene_ids": [approved["id"]], "group_id": group["id"], "order": [ada["id"]]},
    )
    assert refused.status_code == 200
    assert refused.json()["skipped"][0]["reason"].startswith("It is approved")
