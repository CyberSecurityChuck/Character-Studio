"""Phase 4: subject mapping, reference selection, approvals and "Polish prompt"."""

import copy
import json
import sqlite3
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from backend.main import create_app
from backend.models import Scene
from backend.prompting import Assignment, check_prompt
from backend.workflow import ApprovalError, auto_references, require_valid_approval
from tests.conftest import ANALYSIS, authorization, wait_for_job
from tests.test_library import create_character, upload
from tests.test_scenes import create_scene, import_manual

SUBJECT_2 = {
    **ANALYSIS["subjects"][0],
    "label": "Subject 2",
    "position": "right",
    "bounding_box": {"x": 0.7, "y": 0.2, "width": 0.2, "height": 0.7},
    "facial_viewing_angle": "Left profile",
}
TWO_PEOPLE = {
    **ANALYSIS,
    "scene_description": "Two people beside a bicycle.",
    "subjects": [ANALYSIS["subjects"][0], SUBJECT_2],
    "uncertainties": [],
}


def character_with_photos(client, name, labels=("Front",)):
    character = create_character(client, name)
    for label in labels:
        character = upload(client, character).json()
        photo = character["photos"][-1]
        character = client.put(
            f"/api/photos/{photo['id']}",
            headers=authorization(client),
            json={"revision": character["revision"], "label": label},
        ).json()
    return character


def two_person_scene(client):
    scene = create_scene(client, "Two people")
    detail = import_manual(client, scene, json.dumps(TWO_PEOPLE)).json()
    return detail


def map_subjects(client, scene, mappings, group_id=None, expect=200):
    result = client.put(
        f"/api/scenes/{scene['id']}/mappings",
        headers=authorization(client),
        json={"revision": scene["revision"], "group_id": group_id, "mappings": mappings},
    )
    assert result.status_code == expect, result.text
    return result.json()


def save_template_prompt(client, scene):
    analysis_id = scene["analyses"][0]["id"]
    draft = client.post(
        f"/api/scenes/{scene['id']}/prompts/draft",
        headers=authorization(client),
        json={"analysis_id": analysis_id},
    ).json()
    result = client.post(
        f"/api/scenes/{scene['id']}/prompts",
        headers=authorization(client),
        json={
            "analysis_id": analysis_id,
            "mapping_hash": draft["mapping_hash"],
            "prompt_text": draft["prompt_text"],
            "negative_prompt": draft["negative_prompt"],
            "source": "template",
        },
    )
    assert result.status_code == 201, result.text
    return result.json()


def approve(client, scene, expect=201, **extra):
    result = client.post(
        f"/api/scenes/{scene['id']}/approve",
        headers=authorization(client),
        json={"prompt_id": scene["review"]["prompt_id"], **extra},
    )
    assert result.status_code == expect, result.text
    return result.json()


def ready_scene(client):
    """Two subjects: Subject 1 -> Ada (auto references), Subject 2 kept; prompt saved."""
    ada = character_with_photos(client, "Ada", ("Front", "Left profile", "Full body", "Additional"))
    scene = two_person_scene(client)
    scene = map_subjects(
        client,
        scene,
        [
            {"label": "Subject 1", "action": "replace", "character_id": ada["id"]},
            {"label": "Subject 2", "action": "keep"},
        ],
    )
    return ada, save_template_prompt(client, scene)


def test_check_prompt_and_reference_selection_rules():
    roles = [Assignment("Subject 1", "replace", (2, 3)), Assignment("Subject 2", "keep")]
    good = (
        "Image 1 is the Base Image. Subject 1: identity only from Image 2 and Image 3.\n"
        "Subject 2: keep this person unchanged."
    )
    assert check_prompt(good, roles, 3) == []
    swapped = "Image 1. Subject 12 uses Image 2 and Image 3. Subject 2 stays. Image 9."
    missing = check_prompt(swapped, roles, 3)
    assert any("Subject 1 is not linked" in m for m in missing)
    assert any("keep Subject 2" in m for m in missing)
    assert any("Image 9" in m for m in missing)
    # Listing the attached images is not the identity instruction itself (review fix).
    listed_only = (
        "Image 1 is the Base Image.\n- Image 2 and Image 3: identity references for Subject 1.\n"
        "Subject 2: keep this person unchanged."
    )
    assert check_prompt(listed_only, roles, 3) == [
        "The instruction that Subject 1's identity comes only from Image 2 and Image 3 is missing."
    ]

    class Photo:
        def __init__(self, identifier, label):
            self.id, self.label = identifier, label

    photos = [
        Photo("a", "Additional"),
        Photo("b", "Front"),
        Photo("c", "Right profile"),
        Photo("d", "Left three-quarter"),
        Photo("e", "Front"),
    ]
    assert auto_references(photos, "a", "Left three-quarter view") == ["a", "d", "b"]
    assert auto_references(photos, "a", "Facing the camera") == ["a", "b", "d"]
    assert auto_references(photos[:2], "b", "") == ["b", "a"]


def test_multiple_people_are_mapped_with_numbered_references(client):
    ada, scene = ready_scene(client)
    subjects = {s["label"]: s for s in scene["subjects"]}
    first, second = subjects["Subject 1"], subjects["Subject 2"]
    assert (first["action"], first["character_id"], first["references_auto"]) == (
        "replace",
        ada["id"],
        True,
    )
    # A useful subset, not every photo: primary (Front), the view closest to the subject's
    # face angle ("Three-quarter left" -> Left profile), then another distinct view.
    by_label = {p["label"]: p["id"] for p in ada["photos"]}
    assert first["reference_ids"] == [
        by_label["Front"],
        by_label["Left profile"],
        by_label["Full body"],
    ]
    assert first["images"] == [2, 3, 4] and second["images"] == []
    assert scene["total_images"] == 4
    prompt = scene["prompts"][0]["prompt_text"]
    assert "- Image 2, Image 3 and Image 4: identity references for Subject 1" in prompt
    assert (
        "Subject 1: take this person's identity only from Image 2, Image 3 and Image 4." in prompt
    )
    assert "Subject 2: keep original." in prompt
    assert "Ada" not in prompt  # character names never leave the studio in the prompt
    assert scene["workflow_state"] == "prompt_saved"
    assert scene["review"]["blockers"] == [] and scene["review"]["warnings"] == []

    # Manual override keeps the user's order; it decides the image numbers.
    chosen = [by_label["Left profile"], by_label["Front"]]
    scene = map_subjects(
        client,
        scene,
        [
            {"label": "Subject 1", "action": "keep"},
            {
                "label": "Subject 2",
                "action": "replace",
                "character_id": ada["id"],
                "reference_ids": chosen,
            },
        ],
    )
    subjects = {s["label"]: s for s in scene["subjects"]}
    assert subjects["Subject 2"]["reference_ids"] == chosen
    assert subjects["Subject 2"]["references_auto"] is False
    assert subjects["Subject 2"]["images"] == [2, 3]
    # The saved prompt now describes other assignments, so it is out of date.
    assert scene["workflow_state"] == "analysis_ready"
    assert any("before the current character" in w for w in scene["review"]["warnings"])


def test_mapping_validation_keeps_identities_separate(client):
    ada = character_with_photos(client, "Ada")
    bo = character_with_photos(client, "Bo")
    nophoto = create_character(client, "No photos")
    scene = two_person_scene(client)

    def attempt(mappings, expect):
        result = client.put(
            f"/api/scenes/{scene['id']}/mappings",
            headers=authorization(client),
            json={"revision": scene["revision"], "mappings": mappings},
        )
        assert result.status_code == expect, result.text
        return result.json()["detail"]

    both = [
        {"label": "Subject 1", "action": "replace", "character_id": ada["id"]},
        {"label": "Subject 2", "action": "replace", "character_id": ada["id"]},
    ]
    assert "only once" in attempt(both, 422)
    one = {"label": "Subject 1", "action": "replace"}
    assert "photos" in attempt([{**one, "character_id": nophoto["id"]}], 422)
    assert "Choose a character" in attempt([one], 422)
    assert attempt(
        [{**one, "character_id": ada["id"], "reference_ids": [bo["photos"][0]["id"]]}], 422
    )
    assert attempt([{"label": "Subject 9", "action": "keep"}], 422)
    many = [ada["photos"][0]["id"]] * 5
    attempt([{**one, "character_id": ada["id"], "reference_ids": many}], 422)
    archived = client.put(
        f"/api/characters/{bo['id']}/archive",
        headers=authorization(client),
        json={"revision": bo["revision"], "archived": True},
    )
    assert archived.status_code == 200
    assert "Restore Bo" in attempt([{**one, "character_id": bo["id"]}], 409)
    stale = client.put(
        f"/api/scenes/{scene['id']}/mappings",
        headers=authorization(client),
        json={"revision": scene["revision"] + 5, "mappings": []},
    )
    assert stale.status_code == 409

    # Group selection is stored only to narrow the pickers; it assigns nobody.
    group = client.post(
        "/api/groups",
        headers=authorization(client),
        json={"name": "Pair", "member_ids": [ada["id"], bo["id"]]},
    ).json()
    saved = map_subjects(client, scene, [], group_id=group["id"])
    assert saved["mapping_group_id"] == group["id"]
    assert all(s["action"] == "unresolved" for s in saved["subjects"])
    assert saved["workflow_state"] == "needs_mapping"
    client.delete(f"/api/groups/{group['id']}?revision=1", headers=authorization(client))
    assert client.get(f"/api/scenes/{scene['id']}").json()["mapping_group_id"] is None


def test_reanalysis_needs_mapping_check_but_box_edits_do_not(client):
    ada, scene = ready_scene(client)
    # The user corrects the boxes: assignments stay confirmed; labels never renumber.
    edited = client.put(
        f"/api/scenes/{scene['id']}/subjects",
        headers=authorization(client),
        json={
            "analysis_id": scene["analyses"][0]["id"],
            "subjects": [
                {
                    "label": "Subject 1",
                    "bounding_box": {"x": 0.1, "y": 0.1, "width": 0.3, "height": 0.8},
                },
                {
                    "label": "Subject 3",
                    "bounding_box": {"x": 0.75, "y": 0.3, "width": 0.2, "height": 0.6},
                },
            ],
        },
    )
    assert edited.status_code == 201, edited.text
    scene = edited.json()
    newest = scene["analyses"][0]
    assert (newest["version"], newest["source"]) == (2, "user_edit")
    labels = [s["label"] for s in newest["analysis"]["subjects"]]
    assert labels == ["Subject 1", "Subject 3"]
    assert newest["analysis"]["subjects"][1]["position"] == "right of the frame"
    subjects = {s["label"]: s for s in scene["subjects"]}
    assert subjects["Subject 1"]["confirmed"] and subjects["Subject 1"]["character_id"] == ada["id"]
    assert subjects["Subject 3"]["action"] == "unresolved"
    assert scene["workflow_state"] == "needs_mapping"
    outside = client.put(
        f"/api/scenes/{scene['id']}/subjects",
        headers=authorization(client),
        json={
            "analysis_id": newest["id"],
            "subjects": [
                {
                    "label": "Subject 1",
                    "bounding_box": {"x": 0.9, "y": 0, "width": 0.5, "height": 1},
                }
            ],
        },
    )
    assert outside.status_code == 422

    # A fresh analysis may number people differently, so assignments must be checked again.
    moved = copy.deepcopy(TWO_PEOPLE)
    moved["subjects"][0]["bounding_box"]["x"] = 0.05
    scene = import_manual(client, scene, json.dumps(moved)).json()
    subjects = {s["label"]: s for s in scene["subjects"]}
    assert subjects["Subject 1"]["confirmed"] is False
    assert "subjects changed" in scene["review"]["blockers"][0]
    scene = map_subjects(
        client, scene, [{"label": "Subject 1", "action": "replace", "character_id": ada["id"]}]
    )
    assert {s["label"]: s for s in scene["subjects"]}["Subject 1"]["confirmed"] is True


def test_approval_snapshot_blocks_and_invalidates(client, settings):
    scene = two_person_scene(client)
    blocked = approve(client, {**scene, "review": {"prompt_id": "none"}}, expect=409)
    assert "Choose a character or Keep original" in blocked["detail"]
    with Session(client.app.state.engine) as session:
        with pytest.raises(ApprovalError):
            require_valid_approval(session, session.get(Scene, scene["id"]))

    ada, scene = ready_scene(client)
    approved = approve(client, scene)
    assert approved["workflow_state"] == "approved"
    assert approved["approval"]["state"] == "approved"
    current = approved["approval"]["current"]
    assert current["prompt_version"] == 1 and current["analysis_version"] == 1
    assert current["mappings"][0] == {
        "subject": "Subject 1",
        "action": "replace",
        "character_name": "Ada",
        "images": [2, 3, 4],
    }
    with Session(client.app.state.engine) as session:
        assert require_valid_approval(session, session.get(Scene, scene["id"])).id == current["id"]
    raw = sqlite3.connect(settings.data_dir / "studio.db")
    snapshot = json.loads(
        raw.execute(
            "SELECT snapshot_json FROM approvals WHERE id = ?", (current["id"],)
        ).fetchone()[0]
    )
    raw.close()
    inputs = snapshot["inputs"]
    assert inputs["base_image"]["content_hash"] and inputs["prompt"]["negative_prompt"]
    assert all(r["content_hash"] for r in inputs["mappings"][0]["references"])

    # Renaming the character is harmless: names are not approved inputs.
    renamed = client.put(
        f"/api/characters/{ada['id']}",
        headers=authorization(client),
        json={"name": "Ada L.", "age_category": "Adult", "notes": "", "revision": ada["revision"]},
    )
    assert renamed.status_code == 200
    assert client.get(f"/api/scenes/{scene['id']}").json()["workflow_state"] == "approved"

    # Any approved input change cancels the approval, with a reason.
    detail = client.get(f"/api/scenes/{scene['id']}").json()
    edited = client.post(
        f"/api/scenes/{scene['id']}/prompts",
        headers=authorization(client),
        json={
            **{
                k: detail["prompts"][0][k]
                for k in ("analysis_id", "mapping_hash", "negative_prompt")
            },
            "prompt_text": detail["prompts"][0]["prompt_text"] + "\nSoft focus.",
            "source": "user_edit",
        },
    ).json()
    assert edited["workflow_state"] == "prompt_saved"
    assert edited["approval"]["state"] == "none"
    assert "the prompt changed" in edited["approval"]["ended_reason"]
    assert edited["approvals"][0]["invalidated_at"]
    with Session(client.app.state.engine) as session:
        with pytest.raises(ApprovalError, match="the prompt changed"):
            require_valid_approval(session, session.get(Scene, scene["id"]))

    again = approve(client, edited)
    photo = next(
        p
        for p in client.get(f"/api/characters/{ada['id']}").json()["photos"]
        if p["label"] == "Full body"
    )
    character = client.get(f"/api/characters/{ada['id']}").json()
    client.delete(
        f"/api/photos/{photo['id']}?revision={character['revision']}", headers=authorization(client)
    )
    after_photo = client.get(f"/api/scenes/{scene['id']}").json()
    assert after_photo["approval"]["state"] == "none"
    assert "reference photos changed" in after_photo["approval"]["ended_reason"]
    assert photo["id"] not in after_photo["subjects"][0]["reference_ids"]
    assert again["approvals"][0]["id"] == after_photo["approvals"][0]["id"]

    # Withdraw, then deleting the character clears the assignment and keeps the history.
    resaved = save_template_prompt(client, after_photo)
    approved = approve(client, resaved)
    withdrawn = client.post(
        f"/api/scenes/{scene['id']}/approval/withdraw",
        headers=authorization(client),
        json={"approval_id": approved["approval"]["current"]["id"]},
    ).json()
    assert withdrawn["approval"]["ended_reason"] == "You withdrew this approval."
    character = client.get(f"/api/characters/{ada['id']}").json()
    assert character["assigned_scene_count"] == 1
    client.delete(
        f"/api/characters/{ada['id']}?revision={character['revision']}",
        headers=authorization(client),
    )
    gone = client.get(f"/api/scenes/{scene['id']}").json()
    assert gone["subjects"][0]["action"] == "unresolved"
    assert gone["workflow_state"] == "needs_mapping"
    assert len(gone["approvals"]) == 3


def test_warnings_need_confirmation_and_files_are_verified(client, settings):
    ada, scene = ready_scene(client)
    detail = client.post(
        f"/api/scenes/{scene['id']}/prompts",
        headers=authorization(client),
        json={
            "analysis_id": scene["analyses"][0]["id"],
            "mapping_hash": scene["mapping_hash"],
            "prompt_text": "Recreate Image 1 with Subject 1.",
            "source": "user_edit",
        },
    ).json()
    assert any("Subject 1 is not linked" in w for w in detail["review"]["warnings"])
    assert any("keep Subject 2" in w for w in detail["review"]["warnings"])
    assert "warnings" in approve(client, detail, expect=409)["detail"]
    stale_prompt = approve(
        client, {**detail, "review": {"prompt_id": scene["review"]["prompt_id"]}}, expect=409
    )
    assert "prompt changed" in stale_prompt["detail"]

    base = settings.data_dir / "scenes" / f"{scene['id']}.jpg"
    original = base.read_bytes()
    base.write_bytes(original + b"tampered")
    assert "Base Image" in approve(client, detail, expect=409, accept_warnings=True)["detail"]
    base.write_bytes(original)
    assert approve(client, detail, accept_warnings=True)["workflow_state"] == "approved"


def test_approval_survives_restart_and_detects_offline_changes(settings):
    with TestClient(create_app(settings), base_url="http://127.0.0.1:8765") as client:
        _, scene = ready_scene(client)
        approve(client, scene)
    with TestClient(create_app(settings), base_url="http://127.0.0.1:8765") as client:
        restored = client.get(f"/api/scenes/{scene['id']}").json()
        assert restored["workflow_state"] == "approved"
        assert restored["approval"]["state"] == "approved"
    with sqlite3.connect(settings.data_dir / "studio.db") as db:
        db.execute("UPDATE prompt_versions SET prompt_text = prompt_text || ' changed'")
    with TestClient(create_app(settings), base_url="http://127.0.0.1:8765") as client:
        restored = client.get(f"/api/scenes/{scene['id']}").json()
        assert restored["workflow_state"] != "approved"
        assert "the prompt changed" in restored["approvals"][0]["invalidated_reason"]


def test_prompt_versions_can_be_deleted_except_the_approved_one(client):
    _, scene = ready_scene(client)
    first = scene["prompts"][0]
    scene = save_template_prompt(client, scene)
    second = scene["prompts"][0]
    assert second["version"] == 2

    def delete(prompt, expect):
        result = client.delete(
            f"/api/scenes/{scene['id']}/prompts/{prompt['id']}", headers=authorization(client)
        )
        assert result.status_code == expect, result.text
        return result.json()

    approved = approve(client, scene)
    assert approved["approval"]["current"]["prompt_id"] == second["id"]
    assert "Withdraw the approval" in delete(second, 409)["detail"]
    # Older versions can go without touching the approval.
    after = delete(first, 200)
    assert [p["version"] for p in after["prompts"]] == [2]
    assert after["workflow_state"] == "approved"
    assert delete(first, 404)

    withdrawn = client.post(
        f"/api/scenes/{scene['id']}/approval/withdraw",
        headers=authorization(client),
        json={"approval_id": approved["approval"]["current"]["id"]},
    ).json()
    emptied = delete(second, 200)
    assert emptied["prompts"] == [] and emptied["workflow_state"] == "analysis_ready"
    assert emptied["approvals"][0]["prompt_version"] == 2  # the snapshot keeps its copy
    # Version 2 was approved once, so its number is never reused.
    assert save_template_prompt(client, withdrawn)["prompts"][0]["version"] == 3


def test_duplicate_copies_assignments_but_not_approval(client):
    ada, scene = ready_scene(client)
    approve(client, scene)
    copy_scene = client.post(
        f"/api/scenes/{scene['id']}/duplicate", headers=authorization(client)
    ).json()
    subjects = {s["label"]: s for s in copy_scene["subjects"]}
    assert subjects["Subject 1"]["character_id"] == ada["id"] and subjects["Subject 1"]["confirmed"]
    assert copy_scene["approvals"] == [] and copy_scene["workflow_state"] == "prompt_saved"
    deleted = client.delete(
        f"/api/scenes/{scene['id']}?revision={scene['revision']}", headers=authorization(client)
    )
    assert deleted.status_code == 200, deleted.text
    assert client.get(f"/api/characters/{ada['id']}").json()["assigned_scene_count"] == 1


def start_polish(client, scene):
    result = client.post(
        f"/api/scenes/{scene['id']}/polish",
        headers=authorization(client),
        json={"prompt_id": scene["review"]["prompt_id"]},
    )
    assert result.status_code == 202, result.text
    job = result.json()["active_job"]
    assert job["kind"] == "polish" and result.json()["workflow_state"] == "polishing"
    finished = wait_for_job(client, job["id"])
    assert finished["status"] == "completed", finished
    return client.get(f"/api/scenes/{scene['id']}").json()


def test_polish_prompt_keeps_both_versions(engine_client, fake):
    client = engine_client
    _, scene = ready_scene(client)
    approved = approve(client, scene)
    original = approved["prompts"][0]
    polished_scene = start_polish(client, approved)
    pending = polished_scene["pending_polish"]
    assert pending["missing"] == [] and pending["prompt_id"] == original["id"]
    assert "Produce one new image" in pending["polished_text"]
    # Nothing changes until the user chooses: the approval still holds.
    assert polished_scene["workflow_state"] == "approved"

    run = [json.loads(line) for line in fake.read_text(encoding="utf-8").splitlines()][-1]
    args = run["args"]
    assert args[args.index("--tools") + 1] == "" and "--restricted" in args
    assert "Read" not in args and run["stdin_closed"] and not run["leaked"]
    assert Path(run["cwd"]).name == "polish-1"

    used = client.post(
        f"/api/scenes/{scene['id']}/prompts/polished",
        headers=authorization(client),
        json={"job_id": pending["job_id"], "prompt_text": pending["polished_text"]},
    )
    assert used.status_code == 201, used.text
    detail = used.json()
    newest, older = detail["prompts"][0], detail["prompts"][1]
    assert (newest["is_polished"], newest["source"], newest["polished_from_version_id"]) == (
        True,
        "polished",
        original["id"],
    )
    assert newest["engine_version"] == "2.1.296 (Claude Code)"
    assert older["prompt_text"] == original["prompt_text"] and not older["is_polished"]
    assert detail["pending_polish"] is None
    # Polishing after approval cancels it, like any other edit.
    assert detail["approval"]["state"] == "none" and detail["workflow_state"] == "prompt_saved"
    again = client.post(
        f"/api/scenes/{scene['id']}/prompts/polished",
        headers=authorization(client),
        json={"job_id": pending["job_id"], "prompt_text": pending["polished_text"]},
    )
    assert again.status_code == 409


def test_polish_missing_elements_need_explicit_acceptance(engine_client, monkeypatch):
    client = engine_client
    _, scene = ready_scene(client)
    monkeypatch.setenv("FAKE_CLI_MODE", "drop")
    polished = start_polish(client, scene)
    pending = polished["pending_polish"]
    assert any("Subject 1" in m for m in pending["missing"])
    body = {"job_id": pending["job_id"], "prompt_text": pending["polished_text"]}
    refused = client.post(
        f"/api/scenes/{scene['id']}/prompts/polished", headers=authorization(client), json=body
    )
    assert refused.status_code == 409 and "missing required elements" in refused.json()["detail"]
    assert len(client.get(f"/api/scenes/{scene['id']}").json()["prompts"]) == 1
    accepted = client.post(
        f"/api/scenes/{scene['id']}/prompts/polished",
        headers=authorization(client),
        json={**body, "accept_warnings": True},
    )
    assert accepted.status_code == 201
    assert any("Subject 1 is not linked" in w for w in accepted.json()["review"]["warnings"])

    monkeypatch.setenv("FAKE_CLI_MODE", "ok")
    kept_scene = start_polish(client, accepted.json())
    job_id = kept_scene["pending_polish"]["job_id"]
    kept = client.post(
        f"/api/scenes/{scene['id']}/prompts/polished/{job_id}/keep-original",
        headers=authorization(client),
    ).json()
    assert kept["pending_polish"] is None and len(kept["prompts"]) == 2


def test_polish_failures_leave_the_prompt_unchanged(engine_client, monkeypatch):
    client = engine_client
    _, scene = ready_scene(client)
    unsaved = client.post(
        f"/api/scenes/{scene['id']}/polish", headers=authorization(client), json={"prompt_id": "x"}
    )
    assert unsaved.status_code == 409
    monkeypatch.setenv("FAKE_CLI_MODE", "limit")
    job = client.post(
        f"/api/scenes/{scene['id']}/polish",
        headers=authorization(client),
        json={"prompt_id": scene["review"]["prompt_id"]},
    ).json()["active_job"]
    finished = wait_for_job(client, job["id"])
    assert (finished["status"], finished["error_kind"]) == ("failed", "usage_limit")
    time.sleep(0.3)
    detail = client.get(f"/api/scenes/{scene['id']}").json()
    assert detail["pending_polish"] is None and len(detail["prompts"]) == 1
    assert detail["workflow_state"] == "prompt_saved"


def test_upgrade_backfills_reference_photo_hashes(settings):
    with TestClient(create_app(settings), base_url="http://127.0.0.1:8765") as client:
        ada = character_with_photos(client, "Ada")
    with sqlite3.connect(settings.data_dir / "studio.db") as db:
        db.execute("UPDATE reference_photos SET content_hash = NULL")
    with TestClient(create_app(settings), base_url="http://127.0.0.1:8765"):
        pass
    with sqlite3.connect(settings.data_dir / "studio.db") as db:
        (value,) = db.execute(
            "SELECT content_hash FROM reference_photos WHERE id = ?", (ada["photos"][0]["id"],)
        ).fetchone()
    assert value and len(value) == 64
