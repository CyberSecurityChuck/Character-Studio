"""Phase 7B: Analyse all, the Assign table, mismatch labels, drafts and Polish all."""

import json
import time

from tests.conftest import ANALYSIS, authorization
from tests.test_batches import analysis_calls, post, wait_for_batch
from tests.test_library import picture
from tests.test_mapping import (
    SUBJECT_2,
    TWO_PEOPLE,
    approve,
    character_with_photos,
    map_subjects,
    save_template_prompt,
)
from tests.test_scenes import import_manual, set_engine

ONE = {**ANALYSIS, "uncertainties": []}
NOBODY = {**ANALYSIS, "subjects": [], "uncertainties": []}
# Subject 2 fills more of the frame than Subject 1 (0.14 of the picture).
BIG_SECOND = {
    **TWO_PEOPLE,
    "subjects": [
        TWO_PEOPLE["subjects"][0],
        {**SUBJECT_2, "bounding_box": {"x": 0.55, "y": 0.1, "width": 0.4, "height": 0.85}},
    ],
}


def make_set(client, name="Holiday"):
    result = client.post("/api/scene-sets", headers=authorization(client), json={"name": name})
    assert result.status_code == 201, result.text
    return result.json()


def add_scene(client, title, scene_set=None, analysis=None, character=None):
    query = f"title={title}&allow_duplicate=true"
    if scene_set:
        query += f"&scene_set_id={scene_set['id']}"
    if character:
        query += f"&import_character_id={character['id']}"
    result = client.post(
        f"/api/scenes?{query}",
        headers={**authorization(client), "Content-Type": "application/octet-stream"},
        content=picture("JPEG"),
    )
    assert result.status_code == 201, result.text
    scene = result.json()
    if analysis is not None:
        scene = import_manual(client, scene, json.dumps(analysis)).json()
    return scene


def scene_of(client, scene):
    return client.get(f"/api/scenes/{scene['id']}").json()


def counts(client, scene_set):
    return client.get(f"/api/scene-sets/{scene_set['id']}/preparation").json()


def table(client, scene_set):
    return client.get(f"/api/scene-sets/{scene_set['id']}/assign").json()


def fill(client, scene_set, expect=200, **body):
    result = client.post(
        f"/api/scene-sets/{scene_set['id']}/assign/fill", headers=authorization(client), json=body
    )
    assert result.status_code == expect, result.text
    return result.json()


def save_table(client, scene_set, proposals):
    rows = [
        {
            "scene_id": p["scene_id"],
            "revision": scene_of(client, {"id": p["scene_id"]})["revision"],
            "mappings": [
                {k: v for k, v in m.items() if v is not None or k == "action"}
                for m in p["mappings"]
            ],
            "intended": p["intended"],
        }
        for p in proposals
    ]
    result = client.put(
        f"/api/scene-sets/{scene_set['id']}/assign",
        headers=authorization(client),
        json={"rows": rows},
    )
    assert result.status_code == 200, result.text
    return result.json()


def replace_with(character):
    return [{"label": "Subject 1", "action": "replace", "character_id": character["id"]}]


def test_analyse_all_chains_batches_that_run_one_after_another(engine_client, fake, monkeypatch):
    client = engine_client
    monkeypatch.setattr("backend.preparation.MAX_ANALYSIS_RUNS", 2)
    holiday = make_set(client)
    scenes = [add_scene(client, f"Scene {n}", holiday) for n in range(5)]
    outside = add_scene(client, "Outside")
    done = add_scene(client, "Done", holiday, analysis=ONE)
    assert counts(client, holiday)["analyse"] == 5

    queued = post(client, f"/api/scene-sets/{holiday['id']}/analyse-all", {})
    batches = queued["batches"]
    assert queued["queued"] == 5 and queued["skipped"] == []
    assert [b["total"] for b in batches] == [2, 2, 1]
    parts = [(b["settings"]["part"], b["settings"]["of"]) for b in batches]
    assert parts == [(1, 3), (2, 3), (3, 3)]
    assert {b["settings"]["scene_set_id"] for b in batches} == {holiday["id"]}

    finished = [wait_for_batch(client, b["id"]) for b in batches]
    assert [b["state"] for b in finished] == ["finished"] * 3
    # One run at a time, in the order of the set, across all three batches.
    started = [(i["started_at"], i["scene_title"]) for b in finished for i in b["items"]]
    assert [title for _, title in sorted(started)] == [s["title"] for s in scenes]
    assert len(analysis_calls(fake)) == 5
    assert all(scene_of(client, s)["analysis_version"] == 1 for s in scenes)
    assert scene_of(client, outside)["analysis_version"] is None
    assert scene_of(client, done)["analysis_version"] == 1  # not analysed again
    assert counts(client, holiday)["analyse"] == 0
    again = client.post(
        f"/api/scene-sets/{holiday['id']}/analyse-all", headers=authorization(client), json={}
    )
    assert again.status_code == 409 and "Nothing to analyse" in again.json()["detail"]

    set_engine(client, "manual")
    add_scene(client, "Later", holiday)
    manual = client.post(
        f"/api/scene-sets/{holiday['id']}/analyse-all", headers=authorization(client), json={}
    )
    assert manual.status_code == 409 and "Manual analysis" in manual.json()["detail"]


def test_a_plan_limit_pauses_every_chained_batch_and_nothing_continues_alone(
    engine_client, fake, monkeypatch
):
    client = engine_client
    monkeypatch.setattr("backend.preparation.MAX_ANALYSIS_RUNS", 2)
    holiday = make_set(client)
    for n in range(4):
        add_scene(client, f"Scene {n}", holiday)
    monkeypatch.setenv("FAKE_CLI_MODE", "limit")
    batches = post(client, f"/api/scene-sets/{holiday['id']}/analyse-all", {})["batches"]
    first = wait_for_batch(client, batches[0]["id"])
    assert (first["state"], first["pause_kind"]) == ("paused", "usage_limit")
    second = client.get(f"/api/batches/{batches[1]['id']}").json()
    assert second["state"] == "paused" and second["counts"]["not_started"] == 2
    time.sleep(0.5)
    assert len(analysis_calls(fake)) == 1


def test_a_character_chosen_at_import_goes_to_the_largest_person(client):
    ada = character_with_photos(client, "Ada")
    missing = client.post(
        "/api/scenes?title=X&import_character_id=nope",
        headers={**authorization(client), "Content-Type": "application/octet-stream"},
        content=picture("JPEG"),
    )
    assert missing.status_code == 422

    scene = add_scene(client, "Two people", character=ada)
    assert scene["import_character_id"] == ada["id"] and scene["mismatch"] is None
    detail = import_manual(client, scene, json.dumps(BIG_SECOND)).json()
    subjects = {s["label"]: s for s in detail["subjects"]}
    assert (subjects["Subject 2"]["action"], subjects["Subject 2"]["character_id"]) == (
        "replace",
        ada["id"],
    )
    assert subjects["Subject 1"]["action"] == "keep"
    assert all(s["confirmed"] and not s["suggested"] for s in subjects.values())
    assert detail["import_character_id"] is None
    assert detail["mismatch"] == "Mismatch: 2 people, 1 character"
    assert detail["stage"] == "needs_check"

    # One person: no mismatch.
    one = import_manual(
        client, add_scene(client, "One person", character=ada), json.dumps(ONE)
    ).json()
    assert one["mismatch"] is None and one["workflow_state"] == "analysis_ready"

    # Nobody found: nothing assigned, labelled.
    empty = import_manual(
        client, add_scene(client, "Empty", character=ada), json.dumps(NOBODY)
    ).json()
    assert empty["mismatch"] == "No people found" and empty["subjects"] == []

    # A plain scene is never labelled.
    plain = import_manual(client, add_scene(client, "Plain"), json.dumps(BIG_SECOND)).json()
    assert plain["mismatch"] is None


def test_fill_rules_propose_and_the_table_saves_confirmed_assignments(client):
    holiday = make_set(client)
    ada = character_with_photos(client, "Ada")
    bo = character_with_photos(client, "Bo")
    cy = character_with_photos(client, "Cy")
    one_a = add_scene(client, "One A", holiday, ONE)
    one_b = add_scene(client, "One B", holiday, ONE)
    pair = add_scene(client, "Pair", holiday, BIG_SECOND)
    nobody = add_scene(client, "Nobody", holiday, NOBODY)
    add_scene(client, "Not analysed", holiday)

    rows = table(client, holiday)
    assert len(rows["rows"]) == 4 and rows["not_analysed"] == 1
    assert [len(r["people"]) for r in rows["rows"]] == [1, 1, 2, 0]
    assert all(p["action"] == "unresolved" for r in rows["rows"] for p in r["people"])

    # One character for every one-person scene; the pair is left for the user.
    plan = fill(client, holiday, rule="one", character_id=ada["id"])
    assert {p["scene_id"] for p in plan["proposals"]} == {one_a["id"], one_b["id"], nobody["id"]}
    assert [s["title"] for s in plan["skipped"]] == ["Pair"]
    assert "2 people" in plan["skipped"][0]["reason"]
    assert counts(client, holiday)["assign_open"] == 3  # nothing was saved

    # Or give the largest person in multi-person scenes the character; others keep their look.
    plan = fill(client, holiday, rule="one", character_id=ada["id"], several_people="largest")
    proposal = next(p for p in plan["proposals"] if p["scene_id"] == pair["id"])
    assert proposal["intended"] == 1
    assert {m["label"]: m["action"] for m in proposal["mappings"]} == {
        "Subject 1": "keep",
        "Subject 2": "replace",
    }
    chosen = next(m for m in proposal["mappings"] if m["action"] == "replace")
    assert chosen["character_id"] == ada["id"]

    saved = save_table(client, holiday, plan["proposals"])
    assert len(saved["saved"]) == 4 and saved["failed"] == []
    # Confirmed by saving the table: no per-scene save is needed.
    assert scene_of(client, one_a)["workflow_state"] == "analysis_ready"
    assert scene_of(client, one_a)["mismatch"] is None
    assert scene_of(client, pair)["mismatch"] == "Mismatch: 2 people, 1 character"
    assert scene_of(client, nobody)["mismatch"] == "No people found"
    assert counts(client, holiday)["mismatched"] == 2

    # Only empty rows are filled again by default.
    again = fill(client, holiday, rule="one", character_id=bo["id"], several_people="largest")
    assert again["proposals"] == [] and len(again["skipped"]) == 4
    everything = fill(client, holiday, rule="one", character_id=bo["id"], only_empty=False)
    assert len(everything["proposals"]) == 3

    # A group, left to right: more characters than people.
    order = [ada["id"], bo["id"], cy["id"]]
    group = fill(client, holiday, rule="group", order=order, only_empty=False)
    by_scene = {p["scene_id"]: p for p in group["proposals"]}
    assert {m["label"]: m["character_id"] for m in by_scene[pair["id"]]["mappings"]} == {
        "Subject 1": ada["id"],  # left of the two
        "Subject 2": bo["id"],
    }
    assert by_scene[pair["id"]]["intended"] == 3
    save_table(client, holiday, group["proposals"])
    assert scene_of(client, pair)["mismatch"] == "Mismatch: 2 people, 3 characters"
    assert scene_of(client, one_a)["mismatch"] == "Mismatch: 1 person, 3 characters"

    # Fewer characters than people: the rest keep their look.
    short = fill(client, holiday, rule="group", order=[cy["id"]], only_empty=False)
    mappings = {p["scene_id"]: p for p in short["proposals"]}[pair["id"]]["mappings"]
    assert [m["action"] for m in mappings] == ["replace", "keep"]


def test_saving_the_table_checks_each_row_on_its_own(client):
    holiday = make_set(client)
    ada = character_with_photos(client, "Ada")
    stale = add_scene(client, "Stale", holiday, ONE)
    approved = add_scene(client, "Approved", holiday, ONE)
    fine = add_scene(client, "Fine", holiday, ONE)
    # Approved scenes are locked in the table and in the fill rules.
    approved = map_subjects(client, approved, replace_with(ada))
    approved = approve(client, save_template_prompt(client, approved))
    rows = {r["scene_id"]: r for r in table(client, holiday)["rows"]}
    assert rows[approved["id"]]["locked"].startswith("Approved")
    assert rows[fine["id"]]["locked"] is None
    skipped = fill(client, holiday, rule="one", character_id=ada["id"], only_empty=False)["skipped"]
    assert [s["title"] for s in skipped] == ["Approved"]

    body = {
        "rows": [
            {
                "scene_id": stale["id"],
                "revision": 99,
                "mappings": replace_with(ada),
                "intended": None,
            },
            {
                "scene_id": approved["id"],
                "revision": approved["revision"],
                "mappings": replace_with(ada),
            },
            {
                "scene_id": fine["id"],
                "revision": fine["revision"],
                "mappings": replace_with(ada),
            },
        ]
    }
    result = client.put(
        f"/api/scene-sets/{holiday['id']}/assign", headers=authorization(client), json=body
    ).json()
    assert [s["title"] for s in result["saved"]] == ["Fine"]
    reasons = {f["title"]: f["reason"] for f in result["failed"]}
    assert "another window" in reasons["Stale"] and "Approved" in reasons["Approved"]
    # The approval was not touched by the refused row.
    assert scene_of(client, approved)["approval"]["state"] == "approved"

    # Assigning by hand clears an earlier mismatch label.
    pair = add_scene(client, "Pair", holiday, BIG_SECOND)
    plan = fill(client, holiday, rule="one", character_id=ada["id"], several_people="largest")
    proposal = next(p for p in plan["proposals"] if p["scene_id"] == pair["id"])
    save_table(client, holiday, [proposal])
    assert scene_of(client, pair)["mismatch"]
    save_table(client, holiday, [{**proposal, "intended": None}])
    assert scene_of(client, pair)["mismatch"] is None


def test_draft_prompts_for_all_uses_the_template_and_a_preset(client):
    holiday = make_set(client)
    ada = character_with_photos(client, "Ada")
    ready = add_scene(client, "Ready", holiday, ONE)
    unassigned = add_scene(client, "Unassigned", holiday, ONE)
    uncertain = add_scene(client, "Uncertain", holiday, ANALYSIS)
    add_scene(client, "Fresh", holiday)
    map_subjects(client, ready, replace_with(ada))
    map_subjects(client, uncertain, replace_with(ada))
    assert counts(client, holiday)["draft"] == 1

    url = f"/api/scene-sets/{holiday['id']}/draft-prompts"
    result = post(client, url, {"preset_id": "builtin-golden-hour"}, expect=200)
    assert [d["title"] for d in result["drafted"]] == ["Ready"]
    reasons = {s["title"]: s["reason"] for s in result["skipped"]}
    assert "Assign every person" in reasons["Unassigned"]
    assert "uncertain" in reasons["Uncertain"]
    assert reasons["Fresh"] == "Analyse it first."
    assert result["preset"] == "Golden hour portrait"

    detail = scene_of(client, ready)
    prompt = detail["prompts"][0]
    assert (prompt["source"], prompt["version"]) == ("template", 1)
    assert "golden-hour" in prompt["scene_changes"].lower()
    assert "harsh midday light" in prompt["negative_prompt"]
    assert detail["workflow_state"] == "prompt_saved" and detail["stage"] == "ready_to_approve"
    assert detail["review"]["warnings"] == []  # the draft matches the assignments
    assert scene_of(client, unassigned)["prompts"] == []

    # Already drafted scenes are left alone unless replacing is ticked; history is kept.
    again = post(client, url, {}, expect=200)
    skipped = {s["title"]: s["reason"] for s in again["skipped"]}
    assert "already has a saved prompt" in skipped["Ready"]
    redo = post(client, url, {"replace_existing": True}, expect=200)
    assert [d["version"] for d in redo["drafted"]] == [2]
    assert len(scene_of(client, ready)["prompts"]) == 2


def wait_for_polish(client, scene_set, timeout=30):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        state = counts(client, scene_set)
        if state["polish_waiting"] + state["polish_running"] == 0:
            return state
        time.sleep(0.1)
    raise AssertionError("Polish runs did not finish")


def test_polish_all_queues_runs_and_the_review_list_decides_each(engine_client, fake, monkeypatch):
    client = engine_client
    holiday = make_set(client)
    ada = character_with_photos(client, "Ada")
    bo = character_with_photos(client, "Bo")
    scenes = []
    for title, character in (("First", ada), ("Second", bo), ("Third", ada)):
        scene = add_scene(client, title, holiday, ONE)
        map_subjects(client, scene, replace_with(character))
        scenes.append(scene)
    post(client, f"/api/scene-sets/{holiday['id']}/draft-prompts", {}, expect=200)
    assert counts(client, holiday)["polish"] == 3

    queued = post(client, f"/api/scene-sets/{holiday['id']}/polish-all")
    assert queued["queued"] == 3
    state = wait_for_polish(client, holiday)
    assert state["review"] == 3 and state["polish"] == 0
    # Nothing changed by itself.
    assert all(len(scene_of(client, s)["prompts"]) == 1 for s in scenes)
    nothing = client.post(
        f"/api/scene-sets/{holiday['id']}/polish-all", headers=authorization(client)
    )
    assert nothing.status_code == 409

    review = client.get(f"/api/scene-sets/{holiday['id']}/polish-review").json()["rows"]
    assert [r["title"] for r in review] == ["First", "Second", "Third"]
    assert "Produce one new image" in review[0]["polished_text"]
    assert "Create one new photorealistic image" in review[0]["current_text"]

    decisions = [
        {"scene_id": review[0]["scene_id"], "job_id": review[0]["job_id"], "decision": "use"},
        {"scene_id": review[1]["scene_id"], "job_id": review[1]["job_id"], "decision": "keep"},
    ]
    url = f"/api/scene-sets/{holiday['id']}/polish-review"
    result = post(client, url, {"decisions": decisions}, expect=200)
    assert len(result["done"]) == 2 and result["failed"] == []
    first, second, third = (scene_of(client, s) for s in scenes)
    assert (first["prompts"][0]["is_polished"], len(first["prompts"])) == (True, 2)
    assert (len(second["prompts"]), second["pending_polish"]) == (1, None)
    assert third["pending_polish"] is not None  # still undecided
    assert counts(client, holiday)["review"] == 1

    # A polished text that lost required elements is refused in bulk.
    fourth = add_scene(client, "Fourth", holiday, ONE)
    map_subjects(client, fourth, replace_with(ada))
    post(client, f"/api/scene-sets/{holiday['id']}/draft-prompts", {}, expect=200)
    monkeypatch.setenv("FAKE_CLI_MODE", "drop")
    post(client, f"/api/scene-sets/{holiday['id']}/polish-all")
    wait_for_polish(client, holiday)
    rows = client.get(f"/api/scene-sets/{holiday['id']}/polish-review").json()["rows"]
    review = {r["title"]: r for r in rows}
    assert review["Fourth"]["missing"]
    refused = post(
        client,
        url,
        {
            "decisions": [
                {
                    "scene_id": fourth["id"],
                    "job_id": review["Fourth"]["job_id"],
                    "decision": "use",
                }
            ]
        },
        expect=200,
    )
    assert refused["done"] == []
    assert "missing required elements" in refused["failed"][0]["reason"]
    assert len(scene_of(client, fourth)["prompts"]) == 1
