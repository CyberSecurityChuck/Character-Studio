"""Phase 7C-1: the approval list, the review queue's inline confirmation and Approve all."""

import sqlite3

from tests.conftest import ANALYSIS, authorization
from tests.test_batches import post
from tests.test_mapping import approve, character_with_photos, map_subjects, save_template_prompt
from tests.test_preparation import (
    BIG_SECOND,
    ONE,
    add_scene,
    fill,
    make_set,
    replace_with,
    save_table,
    scene_of,
)


def listing(client, scene_set):
    return client.get(f"/api/scene-sets/{scene_set['id']}/approval").json()


def by_title(client, scene_set):
    return {r["title"]: r for r in listing(client, scene_set)["rows"]}


def ready(client, title, scene_set, character, analysis=ONE):
    scene = add_scene(client, title, scene_set, analysis)
    return save_template_prompt(client, map_subjects(client, scene, replace_with(character)))


def item(row):
    return {
        "scene_id": row["scene_id"],
        "prompt_id": row["prompt_id"],
        "analysis_id": row["analysis_id"],
    }


def approve_all(client, scene_set, rows, **ticks):
    url = f"/api/scene-sets/{scene_set['id']}/approve-all"
    return post(client, url, {"items": [item(r) for r in rows], **ticks}, expect=200)


def make_scenes(client):
    """One scene of every kind: clean, uncertain, warning, mismatch, blocked, approved."""
    holiday = make_set(client)
    ada = character_with_photos(client, "Ada")
    ready(client, "Clean", holiday, ada)
    ready(client, "Uncertain", holiday, ada, ANALYSIS)
    warned = ready(client, "Warned", holiday, ada)
    client.post(
        f"/api/scenes/{warned['id']}/prompts",
        headers=authorization(client),
        json={
            "analysis_id": warned["analyses"][0]["id"],
            "mapping_hash": warned["mapping_hash"],
            "prompt_text": "A different picture entirely.",
            "negative_prompt": "",
            "source": "user_edit",
        },
    ).raise_for_status()
    add_scene(client, "Fresh", holiday)
    add_scene(client, "Unassigned", holiday, ONE)
    done = ready(client, "Done", holiday, ada)
    approve(client, scene_of(client, done))
    # A pair labelled as a mismatch by a fill rule (2 people, 1 character).
    pair = add_scene(client, "Pair", holiday, BIG_SECOND)
    plan = fill(client, holiday, rule="one", character_id=ada["id"], several_people="largest")
    save_table(client, holiday, [p for p in plan["proposals"] if p["scene_id"] == pair["id"]])
    save_template_prompt(client, scene_of(client, pair))
    return holiday, ada


def test_the_approval_list_tells_ready_scenes_from_blocked_ones(client):
    holiday, _ = make_scenes(client)
    rows = by_title(client, holiday)
    assert rows["Clean"]["state"] == "ready" and not (
        rows["Clean"]["uncertain"] or rows["Clean"]["warnings"] or rows["Clean"]["mismatch"]
    )
    assert rows["Uncertain"]["state"] == "ready" and rows["Uncertain"]["uncertain"] == 1
    assert rows["Warned"]["state"] == "ready" and rows["Warned"]["warnings"]
    assert rows["Pair"]["state"] == "ready" and rows["Pair"]["mismatch"] == (
        "Mismatch: 2 people, 1 character"
    )
    assert rows["Fresh"]["state"] == "blocked" and "analysed" in rows["Fresh"]["reason"]
    assert rows["Unassigned"]["state"] == "blocked" and "Choose a character" in (
        rows["Unassigned"]["reason"]
    )
    assert rows["Done"]["state"] == "approved"
    counts = listing(client, holiday)["counts"]
    assert counts == {
        "total": 7,
        "approved": 1,
        "blocked": 2,
        "ready": 4,
        "clean": 1,
        "uncertain": 1,
        "warnings": 1,
        "mismatched": 1,
    }


def test_approve_all_without_ticks_takes_only_the_clean_scenes(client):
    holiday, _ = make_scenes(client)
    rows = [r for r in listing(client, holiday)["rows"] if r["state"] == "ready"]
    result = approve_all(client, holiday, rows)
    assert [d["title"] for d in result["done"]] == ["Clean"]
    reasons = {s["title"]: s["reason"] for s in result["skipped"]}
    assert set(reasons) == {"Uncertain", "Warned", "Pair"}
    assert "accept uncertain details" in reasons["Uncertain"]
    assert "accept warnings" in reasons["Warned"]
    assert "Mismatch: 2 people, 1 character" in reasons["Pair"]
    # A refused scene is left exactly as it was.
    left = scene_of(client, {"id": next(r for r in rows if r["title"] == "Uncertain")["scene_id"]})
    assert left["workflow_state"] == "review_analysis" and len(left["analyses"]) == 1
    assert left["approval"]["state"] == "none"


def test_ticks_decide_each_risk_and_each_scene_keeps_its_own_snapshot(client):
    holiday, _ = make_scenes(client)
    rows = [r for r in listing(client, holiday)["rows"] if r["state"] == "ready"]
    uncertain = next(r for r in rows if r["title"] == "Uncertain")
    prompt_before = scene_of(client, {"id": uncertain["scene_id"]})["prompts"][0]

    result = approve_all(
        client,
        holiday,
        rows,
        accept_uncertain=True,
        accept_warnings=True,
        allow_mismatch=True,
    )
    assert sorted(d["title"] for d in result["done"]) == ["Clean", "Pair", "Uncertain", "Warned"]
    assert result["skipped"] == []

    ids = set()
    for row in rows:
        detail = scene_of(client, {"id": row["scene_id"]})
        current = detail["approval"]["current"]
        assert detail["approval"]["state"] == "approved" and current["approval_mode"] == "bulk"
        ids.add(current["id"])
    assert len(ids) == 4  # one snapshot per scene

    # Accepting the details keeps the saved prompt word for word, on the new analysis.
    after = scene_of(client, {"id": uncertain["scene_id"]})
    assert after["analyses"][0]["analysis"]["uncertainties"] == []
    assert after["analyses"][0]["confirmed_uncertainties"] == ANALYSIS["uncertainties"]
    assert after["prompts"][0]["prompt_text"] == prompt_before["prompt_text"]
    assert after["prompts"][0]["analysis_id"] == after["analyses"][0]["id"]
    assert after["approval"]["current"]["prompt_id"] == after["prompts"][0]["id"]
    # The scene that was approved earlier by hand stays "single".
    done = scene_of(client, {"id": by_title(client, holiday)["Done"]["scene_id"]})
    assert done["approval"]["current"]["approval_mode"] == "single"
    assert listing(client, holiday)["counts"]["ready"] == 0


def test_a_scene_that_changed_after_the_list_was_made_is_skipped(client):
    holiday = make_set(client)
    ada = character_with_photos(client, "Ada")
    moved = ready(client, "Moved", holiday, ada)
    busy = ready(client, "Edited", holiday, ada)
    rows = listing(client, holiday)["rows"]

    # A newer prompt for one scene; another scene approved by hand in the meantime.
    save_template_prompt(client, scene_of(client, busy))
    approve(client, scene_of(client, moved))
    result = approve_all(client, holiday, rows)
    reasons = {s["title"]: s["reason"] for s in result["skipped"]}
    assert result["done"] == []
    assert "already approved" in reasons["Moved"] and "changed since" in reasons["Edited"]


def test_a_changed_file_stops_only_its_scene(client, settings):
    holiday = make_set(client)
    ada = character_with_photos(client, "Ada")
    ready(client, "Fine", holiday, ada)
    broken = ready(client, "Broken", holiday, ada)
    rows = listing(client, holiday)["rows"]
    (original,) = sqlite3.connect(settings.data_dir / "studio.db").execute(
        "SELECT original_path FROM scenes WHERE id = ?", (broken["id"],)
    ).fetchone()
    (settings.data_dir / original).write_bytes(b"changed")
    result = approve_all(client, holiday, rows)
    assert [d["title"] for d in result["done"]] == ["Fine"]
    assert "missing or changed" in result["skipped"][0]["reason"]


def test_the_queue_confirms_details_inline_and_approves_as_single(client):
    holiday = make_set(client)
    ada = character_with_photos(client, "Ada")
    ready(client, "Shadowy", holiday, ada, ANALYSIS)
    row = by_title(client, holiday)["Shadowy"]
    scene = scene_of(client, {"id": row["scene_id"]})
    # The scene cannot be approved while details are uncertain.
    assert scene["review"]["blockers"]
    accepted = post(
        client,
        f"/api/scene-sets/{holiday['id']}/uncertain/accept",
        {
            "items": [{"scene_id": row["scene_id"], "analysis_id": row["analysis_id"]}],
            "keep_prompt": True,
        },
        expect=200,
    )
    assert accepted["done"][0]["count"] == 1
    scene = scene_of(client, {"id": row["scene_id"]})
    # The prompt stays current, so nothing else is asked.
    assert scene["workflow_state"] == "prompt_saved" and scene["review"]["blockers"] == []
    assert scene["review"]["warnings"] == []
    approved = approve(client, scene)
    assert approved["approval"]["current"]["approval_mode"] == "single"
