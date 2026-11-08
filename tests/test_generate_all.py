"""Phase 7D: Generate all for any number of images, its pause summary, labels and retries."""

import time

from fastapi.testclient import TestClient

from backend.main import create_app
from tests.conftest import authorization
from tests.test_batches import post, wait_for_batch
from tests.test_generation import generation_calls
from tests.test_mapping import approve, character_with_photos, map_subjects, save_template_prompt
from tests.test_pipeline import latest_run, wait_for_run
from tests.test_preparation import ONE, add_scene, make_set, replace_with


def approved_in(client, scene_set, character, title):
    scene = add_scene(client, title, scene_set, ONE)
    mapped = map_subjects(client, scene, replace_with(character))
    approve(client, save_template_prompt(client, mapped))
    return scene


def preview(client, scene_set):
    return client.get(f"/api/scene-sets/{scene_set['id']}/generate-all").json()


def generate(client, scene_set, scenes, expect=202, **body):
    return post(
        client,
        f"/api/scene-sets/{scene_set['id']}/generate-all",
        {"scene_ids": [s["id"] for s in scenes], **body},
        expect=expect,
    )


def labels(client, scene_set):
    return client.get(f"/api/scene-sets/{scene_set['id']}/labels").json()


def label_of(found, scene):
    return found["labels"].get(scene["id"], {}).get("label")


def test_generate_all_splits_any_number_into_chained_batches(engine_client, fake, monkeypatch):
    client = engine_client
    monkeypatch.setattr("backend.pipeline.MAX_GENERATION_RUNS", 4)
    holiday = make_set(client)
    ada = character_with_photos(client, "Ada")
    fresh = [approved_in(client, holiday, ada, f"New {n}") for n in range(4)]
    earlier = approved_in(client, holiday, ada, "Earlier")
    first = post(client, "/api/batches/generation", {"items": [{"scene_id": earlier["id"]}]})
    wait_for_batch(client, first["batch"]["id"])
    add_scene(client, "Not approved", holiday, ONE)

    shown = preview(client, holiday)
    assert shown["counts"] == {"total": 6, "approved": 5, "new": 4, "more": 1, "blocked": 0}
    states = {r["title"]: r["state"] for r in shown["rows"]}
    assert states["Earlier"] == "more" and states["New 0"] == "new"
    assert shown["results"] == 1 and shown["open_run"] is None

    run = generate(client, holiday, fresh, count=2, mode="variation")
    assert (run["kind"], run["stage"], run["status"]) == ("generate", "generating", "running")
    # 8 images, at most 4 per batch (the 20-image size patched to 4), whole scenes per batch.
    assert [b["total"] for b in run["batches"]] == [4, 4]
    assert run["outcome"]["images"] == 8 and run["rules"]["mode"] == "variation"
    # One run per set at a time, whichever kind.
    assert "already in progress" in generate(client, holiday, fresh, expect=409)["detail"]
    start = post(
        client, f"/api/scene-sets/{holiday['id']}/pipeline", {"rule": "none"}, expect=409
    )
    assert "already in progress" in start["detail"]

    done = wait_for_run(client, holiday, ("finished",))
    summary = done["summary"]
    assert (summary["images"], summary["done"], summary["not_started"]) == (8, 8, 0)
    assert summary["paused"] is None and summary["retryable"] == 0
    found = labels(client, holiday)
    assert found["run"]["kind"] == "generate"
    assert [label_of(found, s) for s in fresh] == ["generated"] * 4
    assert label_of(found, earlier) is None  # not part of this run
    assert found["counts"] == {"generated": 4, "failed": 0, "not_started": 0, "interrupted": 0}
    assert len(generation_calls(fake)) == 9
    # The set's gallery: every result knows its scene set.
    results = client.get("/api/results").json()
    assert len(results) == 9 and {r["scene_set_id"] for r in results} == {holiday["id"]}
    after = preview(client, holiday)["counts"]
    assert (after["new"], after["more"]) == (0, 5)


def test_a_plan_limit_pauses_the_run_until_continue_and_retries_are_explicit(
    engine_client, fake, monkeypatch, tmp_path
):
    client = engine_client
    mode = tmp_path / "mode"
    mode.write_text("limit", encoding="utf-8")
    monkeypatch.setenv("FAKE_CLI_MODE_FILE", str(mode))
    monkeypatch.setattr("backend.pipeline.MAX_GENERATION_RUNS", 2)
    holiday = make_set(client)
    ada = character_with_photos(client, "Ada")
    scenes = [approved_in(client, holiday, ada, f"Scene {n}") for n in range(3)]
    run = generate(client, holiday, scenes)
    assert len(run["batches"]) == 2

    # The first image hits the plan limit: every batch of the run pauses, nothing is sent.
    deadline = time.monotonic() + 30
    while (s := latest_run(client, holiday)["summary"])["paused"] is None:
        assert time.monotonic() < deadline
        time.sleep(0.1)
    time.sleep(0.5)
    paused = latest_run(client, holiday)
    assert paused["status"] == "running"  # the run waits on its paused batches
    s = paused["summary"]
    assert (s["done"], s["failed"], s["not_started"]) == (0, 1, 2)
    assert s["paused"]["kind"] == "usage_limit" and s["paused"]["at"]
    assert len(generation_calls(fake)) == 1
    found = labels(client, holiday)
    assert [label_of(found, x) for x in scenes] == ["failed", "not_started", "not_started"]
    # A finished run only: Try failed again waits.
    assert "Wait until" in post(client, f"/api/pipelines/{run['id']}/retry", {}, expect=409)[
        "detail"
    ]

    # Continue on the run continues all of its paused batches with one click.
    mode.write_text("ok", encoding="utf-8")
    post(client, f"/api/pipelines/{run['id']}/continue", {}, expect=200)
    done = wait_for_run(client, holiday, ("finished",))
    assert (done["summary"]["done"], done["summary"]["retryable"]) == (2, 1)
    assert [label_of(labels(client, holiday), x) for x in scenes] == [
        "failed",
        "generated",
        "generated",
    ]
    assert len(generation_calls(fake)) == 3  # nothing was retried on its own

    again = post(client, f"/api/pipelines/{run['id']}/retry", {})
    assert again["status"] == "running"
    done = wait_for_run(client, holiday, ("finished",))
    assert (done["summary"]["images"], done["summary"]["done"]) == (3, 3)
    assert done["summary"]["retryable"] == 0
    assert labels(client, holiday)["counts"]["generated"] == 3
    assert len(generation_calls(fake)) == 4
    assert "No failed images" in post(client, f"/api/pipelines/{run['id']}/retry", {}, expect=409)[
        "detail"
    ]


def test_a_restart_pauses_generate_all_and_labels_the_running_image_interrupted(
    engine_settings, fake, monkeypatch, tmp_path
):
    gate = tmp_path / "gate"
    monkeypatch.setenv("FAKE_CLI_GATE", str(gate))
    with TestClient(create_app(engine_settings), base_url="http://127.0.0.1:8765") as client:
        holiday = make_set(client)
        ada = character_with_photos(client, "Ada")
        scenes = [approved_in(client, holiday, ada, f"Scene {n}") for n in range(2)]
        run = generate(client, holiday, scenes)
        deadline = time.monotonic() + 30
        while not generation_calls(fake) and time.monotonic() < deadline:
            time.sleep(0.05)
    gate.write_text("open")
    with TestClient(create_app(engine_settings), base_url="http://127.0.0.1:8765") as client:
        time.sleep(0.5)
        paused = latest_run(client, holiday)
        assert paused["status"] == "paused" and paused["summary"]["paused"]["kind"] == "restart"
        # The note names the kind of run that stopped.
        assert "Generate all was in progress" in paused["summary"]["paused"]["details"]
        assert "Run everything" not in paused["pause_details"]
        assert (paused["summary"]["interrupted"], paused["summary"]["not_started"]) == (1, 1)
        found = labels(client, holiday)
        assert [label_of(found, x) for x in scenes] == ["interrupted", "not_started"]
        assert len(generation_calls(fake)) == 1
        post(client, f"/api/pipelines/{run['id']}/continue", {}, expect=200)
        done = wait_for_run(client, holiday, ("finished",))
        # Interrupted images are never retried by Try failed again: the scene offers recovery.
        assert (done["summary"]["done"], done["summary"]["retryable"]) == (1, 0)
        assert [label_of(labels(client, holiday), x) for x in scenes] == [
            "interrupted",
            "generated",
        ]


def test_generate_all_refuses_what_it_cannot_do(engine_client, fake):
    client = engine_client
    holiday = make_set(client)
    other = make_set(client, "Other")
    ada = character_with_photos(client, "Ada")
    plain = add_scene(client, "Plain", holiday, ONE)
    elsewhere = approved_in(client, other, ada, "Elsewhere")
    assert "chosen twice" in generate(client, holiday, [plain, plain], expect=422)["detail"]
    refused = generate(client, holiday, [plain, elsewhere], expect=409)["detail"]
    assert "Nothing was queued" in refused and "no longer in this set" in refused
    assert latest_run(client, holiday) is None  # nothing was stored
    assert labels(client, holiday)["run"] is None
    settings = client.get("/api/engines/settings").json()
    client.put(
        "/api/engines/settings",
        headers=authorization(client),
        json={**settings, "generation_engine": "manual"},
    ).raise_for_status()
    assert "Manual generation" in generate(client, holiday, [plain], expect=409)["detail"]


def test_selected_scenes_split_into_chained_batches_beyond_the_batch_sizes(
    engine_client, fake, monkeypatch
):
    client = engine_client
    monkeypatch.setattr("backend.batches.MAX_ANALYSIS_RUNS", 2)
    monkeypatch.setattr("backend.batches.MAX_GENERATION_RUNS", 2)
    holiday = make_set(client)
    ada = character_with_photos(client, "Ada")
    raw = [add_scene(client, f"Raw {n}", holiday) for n in range(3)]
    analysed = post(client, "/api/batches/analysis", {"scene_ids": [s["id"] for s in raw]})
    assert [b["total"] for b in analysed["batches"]] == [2, 1]
    assert [b["settings"]["part"] for b in analysed["batches"]] == [1, 2]
    for batch in analysed["batches"]:
        assert wait_for_batch(client, batch["id"])["state"] == "finished"

    approved = [approved_in(client, holiday, ada, f"Ready {n}") for n in range(3)]
    queued = post(
        client,
        "/api/batches/generation",
        {"items": [{"scene_id": s["id"]} for s in approved], "count": 1},
    )
    assert [b["total"] for b in queued["batches"]] == [2, 1]
    assert queued["batch"]["id"] == queued["batches"][0]["id"]
    for batch in queued["batches"]:
        assert wait_for_batch(client, batch["id"])["state"] == "finished"
    assert len(generation_calls(fake)) == 3
