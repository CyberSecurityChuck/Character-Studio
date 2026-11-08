"""Phase 7C-2: Run everything, stage by stage, with its stops, restart and cancel."""

import json
import time

from fastapi.testclient import TestClient

from backend.main import create_app
from tests.conftest import ANALYSIS, authorization
from tests.test_batches import analysis_calls, post, wait_for_batch
from tests.test_generation import generation_calls
from tests.test_mapping import approve, character_with_photos, map_subjects, save_template_prompt
from tests.test_preparation import BIG_SECOND, ONE, add_scene, make_set, replace_with, scene_of

ALL_IN = {"rule": "one", "let_uncertain": True}


def start(client, scene_set, expect=202, **body):
    return post(client, f"/api/scene-sets/{scene_set['id']}/pipeline", body, expect=expect)


def latest_run(client, scene_set):
    return client.get(f"/api/scene-sets/{scene_set['id']}/pipeline").json()["run"]


def wait_for_run(client, scene_set, states=("finished", "waiting", "cancelled", "paused")):
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        run = latest_run(client, scene_set)
        if run["status"] in states:
            return run
        time.sleep(0.1)
    raise AssertionError(f"Run stayed {run['status']}")


def calls(log):
    """Every CLI call in order: 'analysis' or 'generation'."""
    lines = [json.loads(x) for x in log.read_text(encoding="utf-8").splitlines()]
    kinds = []
    for c in lines:
        if "-p" in c["args"]:
            kinds.append("analysis")
        elif c["args"][:1] == ["exec"] and "--output-schema" not in c["args"]:
            kinds.append("generation")
    return kinds


def test_run_everything_goes_stage_by_stage_and_approves_as_auto(
    engine_client, fake, monkeypatch
):
    client = engine_client
    monkeypatch.setattr("backend.preparation.MAX_ANALYSIS_RUNS", 2)
    monkeypatch.setattr("backend.pipeline.MAX_GENERATION_RUNS", 4)
    holiday = make_set(client)
    ada = character_with_photos(client, "Ada")
    fresh = [add_scene(client, f"New {n}", holiday) for n in range(3)]
    # Approved earlier by hand, never generated: it is generated too and stays "single".
    earlier = save_template_prompt(
        client, map_subjects(client, add_scene(client, "Earlier", holiday, ONE), replace_with(ada))
    )
    approve(client, earlier)
    before = client.get(f"/api/scene-sets/{holiday['id']}/pipeline").json()["counts"]
    assert (before["analyse"], before["generate"]) == (3, 1)

    run = start(client, holiday, character_id=ada["id"], images=2, **ALL_IN)
    assert (run["status"], run["stage"]) == ("running", "analysing")
    assert [b["kind"] for b in run["batches"]] == ["analysis", "analysis"]  # 2 + 1, chained
    # Only one run per set at a time.
    again = start(client, holiday, expect=409, character_id=ada["id"], **ALL_IN)
    assert "already in progress" in again["detail"]

    done = wait_for_run(client, holiday, ("finished",))
    assert done["outcome"]["approved"] == 3 and done["outcome"]["stopped"] == []
    assert done["outcome"]["images"] == 8
    generation = [b for b in done["batches"] if b["kind"] == "generation"]
    assert [b["total"] for b in generation] == [4, 4]  # 20-image limit patched to 4
    assert all(b["state"] == "finished" for b in done["batches"])
    # Stage by stage: every analysis before the first image.
    order = calls(fake)
    assert order == ["analysis"] * 3 + ["generation"] * 8
    for scene in fresh:
        detail = scene_of(client, scene)
        assert detail["approval"]["current"]["approval_mode"] == "auto"
        assert len(detail["results"]) == 2
        # The uncertain detail was let through: accepted as described, prompt kept current.
        assert detail["analyses"][0]["confirmed_uncertainties"] == ANALYSIS["uncertainties"]
        assert detail["prompts"][0]["source"] == "template"
    assert scene_of(client, earlier)["approval"]["current"]["approval_mode"] == "single"
    assert len(scene_of(client, earlier)["results"]) == 2


def test_stops_keep_hand_work_and_the_opt_in_pause_waits_for_generate(engine_client, fake):
    client = engine_client
    holiday = make_set(client)
    ada = character_with_photos(client, "Ada")
    bo = character_with_photos(client, "Bo")
    add_scene(client, "Plain", holiday, ONE)
    add_scene(client, "Shadowy", holiday, ANALYSIS)
    add_scene(client, "Pair", holiday, BIG_SECOND)
    by_hand = map_subjects(client, add_scene(client, "By hand", holiday, ONE), replace_with(bo))
    edited = save_template_prompt(
        client, map_subjects(client, add_scene(client, "Edited", holiday, ONE), replace_with(ada))
    )
    client.post(
        f"/api/scenes/{edited['id']}/prompts",
        headers=authorization(client),
        json={
            "analysis_id": edited["analyses"][0]["id"],
            "mapping_hash": edited["mapping_hash"],
            "prompt_text": "Something else entirely.",
            "negative_prompt": "",
            "source": "user_edit",
        },
    ).raise_for_status()

    run = start(
        client, holiday, rule="one", character_id=ada["id"], stop_before_generating=True
    )
    # Nothing to analyse: assigned, drafted and approved by the same click.
    assert run["status"] == "waiting" and run["outcome"]["approved"] == 2
    reasons = {s["title"]: s["reason"] for s in run["outcome"]["stopped"]}
    assert set(reasons) == {"Shadowy", "Pair", "Edited"}
    assert "uncertain" in reasons["Shadowy"]
    assert "2 people" in reasons["Pair"]
    assert "warnings" in reasons["Edited"]
    # The hand assignment was kept: Bo, not the rule's Ada.
    kept = scene_of(client, by_hand)
    assert kept["subjects"][0]["character_id"] == bo["id"]
    assert kept["approval"]["current"]["approval_mode"] == "auto"
    assert scene_of(client, {"id": next(
        r["scene_id"] for r in client.get(f"/api/scene-sets/{holiday['id']}/approval").json()[
            "rows"] if r["title"] == "Shadowy"
    )})["approval"]["state"] == "none"
    time.sleep(0.5)
    assert generation_calls(fake) == []  # stopped before generating, as asked

    generating = post(client, f"/api/pipelines/{run['id']}/generate", {})
    assert generating["stage"] == "generating"
    done = wait_for_run(client, holiday, ("finished",))
    assert done["outcome"]["images"] == 2 and len(generation_calls(fake)) == 2


def test_mismatches_and_details_go_through_only_when_let_through(engine_client, fake):
    client = engine_client
    holiday = make_set(client)
    ada = character_with_photos(client, "Ada")
    add_scene(client, "Pair", holiday, BIG_SECOND)
    add_scene(client, "Shadowy", holiday, ANALYSIS)
    run = start(
        client,
        holiday,
        rule="one",
        character_id=ada["id"],
        several_people="largest",
        stop_before_generating=True,
    )
    reasons = {s["title"]: s["reason"] for s in run["outcome"]["stopped"]}
    assert "Mismatch: 2 people, 1 character" in reasons["Pair"] and "uncertain" in reasons[
        "Shadowy"
    ]
    assert run["status"] == "finished"  # every scene stopped: nothing left to generate
    run = start(
        client,
        holiday,
        rule="one",
        character_id=ada["id"],
        several_people="largest",
        let_uncertain=True,
        let_mismatch=True,
        stop_before_generating=True,
    )
    assert run["outcome"]["stopped"] == [] and run["outcome"]["approved"] == 2


def test_a_cancelled_analysis_batch_cancels_the_run(engine_client, fake, monkeypatch, tmp_path):
    client = engine_client
    monkeypatch.setenv("FAKE_CLI_GATE", str(tmp_path / "gate"))
    holiday = make_set(client)
    ada = character_with_photos(client, "Ada")
    for n in range(2):
        add_scene(client, f"New {n}", holiday)
    run = start(client, holiday, character_id=ada["id"], **ALL_IN)
    post(client, f"/api/batches/{run['batches'][0]['id']}/cancel", expect=200)
    (tmp_path / "gate").write_text("open")
    ended = wait_for_run(client, holiday, ("cancelled",))
    assert "nothing was approved or generated" in ended["outcome"]["note"]
    time.sleep(0.5)
    assert generation_calls(fake) == []


def test_restart_pauses_the_run_until_the_user_continues(
    engine_settings, fake, monkeypatch, tmp_path
):
    gate = tmp_path / "gate"
    monkeypatch.setenv("FAKE_CLI_GATE", str(gate))
    with TestClient(create_app(engine_settings), base_url="http://127.0.0.1:8765") as client:
        holiday = make_set(client)
        ada = character_with_photos(client, "Ada")
        for n in range(2):
            add_scene(client, f"New {n}", holiday)
        run = start(client, holiday, character_id=ada["id"], **ALL_IN)
        deadline = time.monotonic() + 30
        while not analysis_calls(fake) and time.monotonic() < deadline:
            time.sleep(0.05)
    gate.write_text("open")
    with TestClient(create_app(engine_settings), base_url="http://127.0.0.1:8765") as client:
        time.sleep(0.5)
        paused = latest_run(client, holiday)
        assert paused["status"] == "paused" and "Nothing continues" in paused["pause_details"]
        assert "Run everything was in progress" in paused["pause_details"]
        assert generation_calls(fake) == []
        post(client, f"/api/pipelines/{run['id']}/continue", {}, expect=200)
        wait_for_batch(client, run["batches"][0]["id"])
        done = wait_for_run(client, holiday, ("finished",))
        # The interrupted scene stops (no analysis); the other is approved and generated.
        assert done["outcome"]["approved"] == 1 and len(done["outcome"]["stopped"]) == 1
        assert "no analysis" in done["outcome"]["stopped"][0]["reason"]
        assert len(generation_calls(fake)) == 1


def test_run_everything_refuses_what_it_cannot_do(engine_client, fake):
    client = engine_client
    holiday = make_set(client)
    assert "Nothing to do" in start(client, holiday, expect=409)["detail"]
    add_scene(client, "New", holiday)
    refused = start(client, holiday, expect=422, rule="one")
    assert "Choose the character" in refused["detail"]
    settings = client.get("/api/engines/settings").json()
    client.put(
        "/api/engines/settings",
        headers=authorization(client),
        json={**settings, "generation_engine": "manual"},
    ).raise_for_status()
    assert "Manual generation" in start(client, holiday, expect=409)["detail"]
