"""Phase 8C: automatic switching, off by default, only for accounts or keys that cannot be
used (D009 as changed on 2026-11-22, DECISIONS.md D046). Fake CLIs and a fake provider;
no real sign-in, key or charge."""

import json

from tests.conftest import authorization, wait_for_job
from tests.test_api_engines import (  # noqa: F401
    KEY,
    api_client,
    api_settings,
    providers,
    save_key,
    select_api,
)
from tests.test_api_keys import SECOND, THIRD
from tests.test_api_keys import wait_for_batch as wait_for_key_batch
from tests.test_batches import analysis_calls, post, wait_for_batch
from tests.test_cli_accounts import (
    accounts_of,
    choose,
    profile_folder,
    signed_in_account,
)
from tests.test_scenes import create_scene

MODEL = "claude-test-1"  # in the fake provider's model list


def fallbacks(client, choice, on, order, expect=200):
    current = client.get("/api/engines/settings").json()
    result = client.put(
        "/api/engines/settings",
        headers=authorization(client),
        json={**current, "fallbacks": {choice: {"on": on, "order": order}}},
    )
    assert result.status_code == expect, result.text
    return result.json()


def sign_out(settings, engine, account):
    (profile_folder(settings, engine, account["id"]) / "fake-login").unlink()


def test_a_signed_out_account_moves_the_batch_before_anything_is_sent(
    engine_client, engine_settings, fake, monkeypatch
):
    client = engine_client
    work = signed_in_account(client, "claude_cli", "Work", monkeypatch)
    home = signed_in_account(client, "claude_cli", "Home", monkeypatch)
    choose(client, "claude_cli", work["id"])
    saved = fallbacks(client, "claude_cli:analysis", True, [home["id"], "default"])
    assert saved["fallbacks"]["claude_cli:analysis"] == {
        "on": True,
        "order": [home["id"], "default"],
    }
    sign_out(engine_settings, "claude_cli", work)
    scenes = [create_scene(client, f"Scene {n}") for n in range(2)]
    batch = post(client, "/api/batches/analysis", {"scene_ids": [s["id"] for s in scenes]})
    done = wait_for_batch(client, batch["batch"]["id"])
    # Nothing failed and nothing ran on the signed-out account.
    assert [i["status"] for i in done["items"]] == ["completed", "completed"]
    home_folder = str(profile_folder(engine_settings, "claude_cli", home["id"]))
    assert [c["profile"] for c in analysis_calls(fake)] == [home_folder, home_folder]
    assert done["account"] == {"id": home["id"], "label": "Home"}
    [switch] = done["switches"]
    assert (switch["from_label"], switch["to_label"], switch["reason"]) == (
        "Work",
        "Home",
        "signed_out",
    )
    job = client.get(f"/api/jobs/{done['items'][0]['job_id']}").json()
    assert job["account"]["label"] == "Home" and job["switched"]["from_label"] == "Work"
    # The account that worked is now the panel's choice; Work goes to the end of the list.
    settings = client.get("/api/engines/settings").json()
    assert settings["accounts"]["claude_cli:analysis"] == home["id"]
    assert settings["fallbacks"]["claude_cli:analysis"]["order"] == ["default", work["id"]]
    assert accounts_of(client, "claude_cli")["active"]["analysis"] == home["id"]
    # A page that still shows the old choice must reload before saving.
    assert settings["revision"] > saved["revision"]
    stale = client.put(
        "/api/engines/settings", headers=authorization(client), json=saved | {"fallbacks": {}}
    )
    assert stale.status_code == 409


def test_switching_is_off_by_default_and_never_for_usage_limits(
    engine_client, engine_settings, fake, monkeypatch
):
    client = engine_client
    work = signed_in_account(client, "claude_cli", "Work", monkeypatch)
    home = signed_in_account(client, "claude_cli", "Home", monkeypatch)
    choose(client, "claude_cli", work["id"])
    # Off: a signed-out account pauses the batch as before.
    sign_out(engine_settings, "claude_cli", work)
    batch = post(client, "/api/batches/analysis", {"scene_ids": [create_scene(client)["id"]]})
    paused = wait_for_batch(client, batch["batch"]["id"])
    assert (paused["state"], paused["pause_kind"], paused["switches"]) == (
        "paused",
        "signed_out",
        [],
    )
    assert analysis_calls(fake) == []
    # On, but the account hit its plan limit: that is never a reason to switch.
    (profile_folder(engine_settings, "claude_cli", work["id"]) / "fake-mode").write_text("limit")
    fallbacks(client, "claude_cli:analysis", True, [home["id"]])
    scenes = [create_scene(client, f"Limit {n}") for n in range(2)]
    batch = post(client, "/api/batches/analysis", {"scene_ids": [s["id"] for s in scenes]})
    paused = wait_for_batch(client, batch["batch"]["id"])
    assert paused["pause_kind"] == "usage_limit" and paused["switches"] == []
    assert [i["status"] for i in paused["items"]] == ["failed", "not_started"]
    assert paused["account"]["label"] == "Work"
    assert accounts_of(client, "claude_cli")["active"]["analysis"] == work["id"]


def test_a_single_run_switches_and_one_pass_through_the_list_then_pauses(
    engine_client, engine_settings, fake, monkeypatch
):
    client = engine_client
    work = signed_in_account(client, "codex_cli", "Work", monkeypatch)
    spare = signed_in_account(client, "codex_cli", "Spare", monkeypatch)
    current = client.get("/api/engines/settings").json()
    client.put(
        "/api/engines/settings",
        headers=authorization(client),
        json={
            **current,
            "analysis_engine": "codex_cli",
            "accounts": {"codex_cli:analysis": work["id"]},
            "fallbacks": {"codex_cli:analysis": {"on": True, "order": [spare["id"]]}},
        },
    ).raise_for_status()
    sign_out(engine_settings, "codex_cli", work)
    scene = create_scene(client)
    job = post(client, f"/api/scenes/{scene['id']}/analyse")["active_job"]
    done = wait_for_job(client, job["id"])
    assert done["status"] == "completed"
    assert done["account"]["label"] == "Spare" and done["switched"]["reason"] == "signed_out"
    # Every account in the list signed out: one pass, then the batch pauses as before.
    sign_out(engine_settings, "codex_cli", spare)
    batch = post(client, "/api/batches/analysis", {"scene_ids": [create_scene(client)["id"]]})
    paused = wait_for_batch(client, batch["batch"]["id"])
    assert paused["pause_kind"] == "signed_out"
    assert "no other account in the list that is signed in" in paused["pause_details"]
    assert paused["items"][0]["status"] == "not_started"


def test_a_refused_key_moves_only_the_waiting_items_to_a_confirmed_key(
    api_client, providers  # noqa: F811
):
    client = api_client
    headers = authorization(client)
    save_key(client, "anthropic_api")
    spare = save_key(client, "anthropic_api", THIRD, label="Spare")["key_id"]
    backup = save_key(client, "anthropic_api", SECOND, label="Backup")["key_id"]
    assert select_api(client, "anthropic_api", model=MODEL).status_code == 200
    fallbacks(client, "anthropic_api:analysis", True, [spare, backup])
    providers.refused = {KEY}
    ids = [create_scene(client, title=f"Scene {n}")["id"] for n in range(3)]
    # The confirmation named Default and Backup, not Spare: Spare is never charged.
    charge = {"confirm_charges": True, "charge_keys": ["default", backup]}
    before = len(providers.requests)
    started = client.post(
        "/api/batches/analysis", headers=headers, json={"scene_ids": ids, **charge}
    ).json()["batch"]
    assert started["settings"]["fallback_keys"] == [backup]
    batch = wait_for_key_batch(client, started["id"], "finished")
    # The refused run was sent, so it stays failed and is not retried.
    assert [i["status"] for i in batch["items"]] == ["failed", "completed", "completed"]
    assert batch["items"][0]["error_kind"] == "key_problem"
    sent = [r["headers"]["x-api-key"] for r in providers.posts()]
    assert sent == [KEY, SECOND, SECOND]
    assert THIRD not in json.dumps([r["headers"] for r in providers.requests[before:]])
    [switch] = batch["switches"]
    assert (switch["from_label"], switch["to_label"], switch["reason"]) == (
        "Default",
        "Backup",
        "key_refused",
    )
    assert batch["key"] == {"id": backup, "label": "Backup"}
    settings = client.get("/api/engines/settings").json()
    assert settings["keys"]["anthropic_api:analysis"] == backup


def test_a_fallback_key_that_is_refused_too_is_skipped_and_the_batch_pauses(
    api_client, providers  # noqa: F811
):
    client = api_client
    save_key(client, "anthropic_api")
    backup = save_key(client, "anthropic_api", SECOND, label="Backup")["key_id"]
    assert select_api(client, "anthropic_api", model=MODEL).status_code == 200
    fallbacks(client, "anthropic_api:analysis", True, [backup])
    providers.refused = {KEY, SECOND}
    ids = [create_scene(client, title=f"Scene {n}")["id"] for n in range(2)]
    charge = {"confirm_charges": True, "charge_keys": ["default", backup]}
    started = client.post(
        "/api/batches/analysis", headers=authorization(client), json={"scene_ids": ids, **charge}
    ).json()["batch"]
    batch = wait_for_key_batch(client, started["id"], "paused")
    assert batch["pause_kind"] == "key_problem" and batch["switches"] == []
    # Backup was only checked with the free model list; no paid request used it.
    assert [r["headers"]["x-api-key"] for r in providers.posts()] == [KEY]
    assert any(r["headers"].get("x-api-key") == SECOND for r in providers.requests)
    assert client.get("/api/engines/settings").json()["keys"]["anthropic_api:analysis"] == (
        "default"
    )


def test_fallback_lists_are_checked_when_saved(api_client, providers):  # noqa: F811
    client = api_client
    save_key(client, "openai_api")
    fallbacks(client, "openai_api:generation", True, ["0" * 32], expect=409)
    fallbacks(client, "nobody:analysis", True, [], expect=422)
    saved = fallbacks(client, "openai_api:generation", True, ["default"])
    assert saved["fallbacks"]["openai_api:generation"] == {"on": True, "order": ["default"]}
    # The other panel's list is untouched.
    assert saved["fallbacks"]["openai_api:analysis"] == {"on": False, "order": []}
