"""Phase 8B: several API keys per provider, chosen per engine panel, named in every charge
confirmation, recorded on every paid run, and Continue with another key."""

import json
import time

from backend.api_engines import require_key
from backend.engines import EngineError
from backend.keystore import _dpapi, load_key
from tests.conftest import authorization, wait_for_job
from tests.test_api_engines import (  # noqa: F401
    CHARGE,
    KEY,
    analyse,
    api_client,
    api_settings,
    key_path,
    providers,
    save_key,
    select_api,
)
from tests.test_generate_all import approved_in
from tests.test_image_engines import gemini_image_reply, select_generation
from tests.test_mapping import character_with_photos
from tests.test_pipeline import latest_run, wait_for_run
from tests.test_preparation import make_set
from tests.test_scenes import create_scene

SECOND = "second-key-0123456789-zyxwvuts"
THIRD = "third-key-0123456789-qponmlkj"


def engine_of(client, engine):
    return {e["id"]: e for e in client.get("/api/api-engines").json()}[engine]


def settings_with(client, **changes):
    current = client.get("/api/engines/settings").json()
    return client.put(
        "/api/engines/settings", headers=authorization(client), json={**current, **changes}
    )


def wait_for_batch(client, batch_id, state, timeout=20):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        batch = client.get(f"/api/batches/{batch_id}").json()
        if batch["state"] == state:
            return batch
        time.sleep(0.1)
    raise AssertionError(batch)


def test_the_single_key_of_earlier_versions_becomes_default(api_settings):  # noqa: F811
    folder = api_settings.data_dir / "keys"
    folder.mkdir(parents=True)
    (folder / "openai_api.key").write_bytes(_dpapi(KEY.encode(), protect=True))
    assert load_key(api_settings, "openai_api") == KEY
    assert not (folder / "openai_api.key").exists()
    assert (folder / "openai_api" / "default.key").is_file()
    listed = json.loads((folder / "keys.json").read_text(encoding="utf-8"))["keys"]
    assert [(k["id"], k["label"]) for k in listed] == [("default", "Default")]
    assert KEY not in (folder / "keys.json").read_text(encoding="utf-8")


def test_several_named_keys_chosen_per_panel(api_client, providers):  # noqa: F811
    client = api_client
    save_key(client, "openai_api")
    added = save_key(client, "openai_api", SECOND, label="Work")
    work = added["key_id"]
    assert [k["label"] for k in added["keys"]] == ["Default", "Work"]
    assert KEY not in json.dumps(added) and SECOND not in json.dumps(added)
    # Names are unique per provider, and a key is never shown again.
    same = client.post(
        "/api/api-engines/openai_api/keys",
        headers=authorization(client),
        json={"label": "work", "key": THIRD},
    )
    assert same.status_code == 422 and "name" in same.json()["detail"]
    renamed = client.put(
        key_path("openai_api", work), headers=authorization(client), json={"label": "Client A"}
    )
    assert [k["label"] for k in renamed.json()["keys"]] == ["Default", "Client A"]
    # The first key serves both panels until a panel chooses another one.
    assert engine_of(client, "openai_api")["active"] == {
        "analysis": "default",
        "generation": "default",
    }
    chosen = settings_with(
        client,
        analysis_engine="openai_api",
        models={"openai_api": {"analysis": "gpt-test-vision"}},
        keys={"openai_api:generation": work},
    )
    assert chosen.status_code == 200, chosen.text
    assert chosen.json()["keys"]["openai_api:generation"] == work
    assert chosen.json()["keys"]["openai_api:analysis"] == "default"
    assert engine_of(client, "openai_api")["active"] == {"analysis": "default", "generation": work}
    unknown = settings_with(client, keys={"openai_api:analysis": "f" * 32})
    assert unknown.status_code == 409
    assert settings_with(client, keys={"claude_cli:analysis": "default"}).status_code == 422
    # Test key checks one key at a time with the free model list.
    tested = client.post(f"{key_path('openai_api', work)}/test", headers=authorization(client))
    assert tested.status_code == 200 and tested.json()["models_listed_by"] == "Client A"
    assert providers.requests[-1]["headers"]["authorization"] == f"Bearer {SECOND}"
    # The analysis panel's key cannot be removed; the other one can (it is not selected
    # for generation, since Codex is still the generation engine).
    refused = client.delete(key_path("openai_api"), headers=authorization(client))
    assert refused.status_code == 409 and "Analysis engine panel" in refused.json()["detail"]
    removed = client.delete(key_path("openai_api", work), headers=authorization(client))
    assert removed.status_code == 200 and [k["id"] for k in removed.json()["keys"]] == ["default"]
    assert engine_of(client, "openai_api")["active"]["generation"] == "default"
    assert providers.posts() == []


def test_a_confirmation_covers_only_the_key_it_names(api_client, providers):  # noqa: F811
    client = api_client
    save_key(client, "gemini_api")
    second = save_key(client, "gemini_api", SECOND, label="Personal")["key_id"]
    assert select_api(client, "gemini_api", keys={"gemini_api:analysis": second}).status_code == 200
    scene = create_scene(client)
    # Confirming charges to another key (the Default) does not cover "Personal".
    refused = analyse(client, scene)
    assert refused.status_code == 409 and "“Personal”" in refused.json()["detail"]
    assert providers.posts() == []
    queued = client.post(
        f"/api/scenes/{scene['id']}/analyse",
        headers=authorization(client),
        json={"confirm_charges": True, "charge_keys": [second]},
    )
    assert queued.status_code == 202, queued.text
    job = wait_for_job(client, queued.json()["active_job"]["id"])
    assert job["status"] == "completed", job
    assert job["key"] == {"id": second, "label": "Personal"}
    [sent] = providers.posts()
    assert sent["headers"]["x-goog-api-key"] == SECOND
    detail = client.get(f"/api/scenes/{scene['id']}").text
    assert KEY not in detail and SECOND not in detail


def test_continue_a_paused_batch_with_another_key(api_client, providers):  # noqa: F811
    client = api_client
    headers = authorization(client)
    save_key(client, "anthropic_api")
    other = save_key(client, "anthropic_api", SECOND, label="Backup")["key_id"]
    assert select_api(client, "anthropic_api").status_code == 200
    ids = [create_scene(client, title=f"Scene {n}")["id"] for n in range(3)]
    providers.next["anthropic_api"] = (
        401,
        {"type": "error", "error": {"type": "authentication_error", "message": "bad x-api-key"}},
    )
    started = client.post(
        "/api/batches/analysis", headers=headers, json={"scene_ids": ids, **CHARGE}
    ).json()["batch"]
    assert started["key"] == {"id": "default", "label": "Default"}
    batch = wait_for_batch(client, started["id"], "paused")
    assert batch["pause_kind"] == "key_problem" and batch["counts"]["not_started"] == 2
    del providers.next["anthropic_api"]
    url = f"/api/batches/{started['id']}/continue"
    # Continuing on "Backup" needs a confirmation that names "Backup".
    moving = {"account_id": other, "make_active": True}
    refused = client.post(url, headers=headers, json={**CHARGE, **moving})
    assert refused.status_code == 409 and "“Backup”" in refused.json()["detail"]
    continued = client.post(
        url, headers=headers, json={"confirm_charges": True, "charge_keys": [other], **moving}
    )
    assert continued.status_code == 200, continued.text
    assert continued.json()["key"] == {"id": other, "label": "Backup"}
    batch = wait_for_batch(client, started["id"], "finished")
    # The failed item is not retried; the two waiting items ran on the other key.
    assert batch["counts"]["completed"] == 2 and batch["counts"]["failed"] == 1
    sent = [r["headers"]["x-api-key"] for r in providers.posts()]
    assert sent == [KEY, SECOND, SECOND]
    jobs = [j for s in ids for j in client.get(f"/api/scenes/{s}").json()["jobs"]]
    assert sorted(j["key"]["label"] for j in jobs) == ["Backup", "Backup", "Default"]
    # "Also use for future runs" made it the analysis panel's key.
    assert engine_of(client, "anthropic_api")["active"]["analysis"] == other
    assert client.get("/api/engines/settings").json()["keys"]["anthropic_api:analysis"] == other


def test_a_removed_key_stops_queued_runs_before_sending(api_client, api_settings, providers):  # noqa: F811
    client = api_client
    save_key(client, "gemini_api")
    spare = save_key(client, "gemini_api", SECOND, label="Spare")["key_id"]
    assert select_api(client, "gemini_api", keys={"gemini_api:analysis": spare}).status_code == 200
    scene = create_scene(client)
    providers.delay = 1.5
    queued = client.post(
        f"/api/scenes/{scene['id']}/analyse",
        headers=authorization(client),
        json={"confirm_charges": True, "charge_keys": [spare]},
    ).json()
    # A key with runs waiting or in progress cannot be removed.
    busy = client.delete(key_path("gemini_api", spare), headers=authorization(client))
    assert busy.status_code == 409 and "waiting or in progress" in busy.json()["detail"]
    job = wait_for_job(client, queued["active_job"]["id"])
    assert job["status"] == "completed" and job["key"]["label"] == "Spare"
    providers.delay = 0
    # A run recorded with a key that is gone fails before anything is sent.
    settings_with(client, keys={"gemini_api:analysis": "default"})
    gone = client.delete(key_path("gemini_api", spare), headers=authorization(client))
    assert gone.status_code == 200
    try:
        require_key(api_settings, "gemini_api", {"key": spare, "key_label": "Spare"})
    except EngineError as error:
        assert error.kind == "key_problem" and "“Spare” was removed" in error.message
    else:
        raise AssertionError("a removed key was used")


def test_generate_all_continues_with_another_key(api_client, providers):  # noqa: F811
    client = api_client
    headers = authorization(client)
    holiday = make_set(client)
    ada = character_with_photos(client, "Ada")
    scenes = [approved_in(client, holiday, ada, f"Scene {n}") for n in range(2)]
    save_key(client, "gemini_api")
    spare = save_key(client, "gemini_api", SECOND, label="Spare")["key_id"]
    select_generation(client, "gemini_api")
    providers.next["gemini_api"] = (403, {"error": {"message": "API key not valid."}})
    url = f"/api/scene-sets/{holiday['id']}/generate-all"
    body = {"scene_ids": [s["id"] for s in scenes]}
    # The confirmation must name the key the Generation panel uses.
    named_other = client.post(url, headers=headers, json={**body, "confirm_charges": True,
                                                         "charge_keys": [spare]})
    assert named_other.status_code == 409 and "“Default”" in named_other.json()["detail"]
    started = client.post(url, headers=headers, json={**body, **CHARGE})
    assert started.status_code == 202, started.text
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        run = latest_run(client, holiday)
        if run["batches"] and run["batches"][0]["state"] == "paused":
            break
        time.sleep(0.1)
    assert run["batches"][0]["pause_kind"] == "key_problem", run
    assert run["batches"][0]["key"] == {"id": "default", "label": "Default"}
    providers.next["gemini_api"] = (200, gemini_image_reply())
    go_on = f"/api/pipelines/{run['id']}/continue"
    moving = {"account_id": spare, "account_engine": "gemini_api"}
    refused = client.post(go_on, headers=headers, json={**CHARGE, **moving})
    assert refused.status_code == 409 and "“Spare”" in refused.json()["detail"]
    continued = client.post(
        go_on, headers=headers, json={"confirm_charges": True, "charge_keys": [spare], **moving}
    )
    assert continued.status_code == 200, continued.text
    run = wait_for_run(client, holiday, ("finished",))
    assert run["summary"]["done"] == 1 and run["summary"]["failed"] == 1
    sent = [r["headers"]["x-goog-api-key"] for r in providers.posts()]
    assert sent == [KEY, SECOND]
    # Try failed again is charged to the key the batch now uses, and must name it.
    retry = f"/api/pipelines/{run['id']}/retry"
    assert client.post(retry, headers=headers, json=CHARGE).status_code == 409
    again = client.post(
        retry, headers=headers, json={"confirm_charges": True, "charge_keys": [spare]}
    )
    assert again.status_code == 202, again.text
    run = wait_for_run(client, holiday, ("finished",))
    assert run["summary"]["done"] == 2
    assert [r["headers"]["x-goog-api-key"] for r in providers.posts()][-1] == SECOND
    # Without "Also use for future runs" the Generation panel keeps the Default key.
    assert engine_of(client, "gemini_api")["active"]["generation"] == "default"
