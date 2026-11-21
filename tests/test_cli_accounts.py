"""Several Claude Code and Codex accounts (Phase 8A, DECISIONS.md D041, D042).

The fake CLIs keep a "login" in the profile folder the studio points them at, so these
tests check which folder each run used without any real sign-in.
"""

import json
import time

from backend import cli_accounts
from tests.conftest import authorization, wait_for_job
from tests.test_batches import analysis_calls, post, wait_for_batch
from tests.test_generation import approved_scene, generate, generation_calls
from tests.test_scenes import create_scene, set_engine


def accounts_of(client, engine):
    listed = {e["engine"]: e for e in client.get("/api/cli-accounts").json()}
    return listed[engine]


def add_account(client, engine, label, expect=201):
    result = client.post(
        f"/api/cli-accounts/{engine}", headers=authorization(client), json={"label": label}
    )
    assert result.status_code == expect, result.text
    return result.json()


def sign_in(client, engine, account_id, monkeypatch):
    """The real sign-in path, but in this process's console instead of a new window."""
    monkeypatch.setattr(cli_accounts, "_console_options", lambda: {})
    post(client, f"/api/cli-accounts/{engine}/{account_id}/sign-in")
    cli_accounts._open[engine].wait(timeout=30)


def choose(client, engine, account_id):
    result = client.put(
        f"/api/cli-accounts/{engine}/active",
        headers=authorization(client),
        json={"account_id": account_id},
    )
    assert result.status_code == 200, result.text
    return result.json()


def profile_folder(settings, engine, account_id):
    return settings.data_dir / "cli-accounts" / engine / account_id


def signed_in_account(client, engine, label, monkeypatch):
    account = add_account(client, engine, label)["account"]
    sign_in(client, engine, account["id"], monkeypatch)
    return account


def test_default_only_changes_nothing_and_accounts_are_isolated(
    engine_client, engine_settings, fake, monkeypatch
):
    client = engine_client
    claude = accounts_of(client, "claude_cli")
    assert claude["active"] == "default"
    assert [(a["id"], a["label"], a["default"]) for a in claude["accounts"]] == [
        ("default", "Default", True)
    ]
    assert claude["accounts"][0]["status"]["signed_in"] is True
    # Nothing is written until an account is added.
    assert not (engine_settings.data_dir / "cli-accounts").exists()

    # A run on the Default account sets no profile folder, as before Phase 8.
    scene = create_scene(client)
    job = post(client, f"/api/scenes/{scene['id']}/analyse")["active_job"]
    done = wait_for_job(client, job["id"])
    assert done["status"] == "completed"
    assert done["account"] == {"id": "default", "label": "Default"}
    assert analysis_calls(fake)[-1]["profile"] is None

    # A new account starts signed out in its own empty folder.
    added = add_account(client, "claude_cli", "  Claude –   work ")
    account = added["account"]
    assert account["label"] == "Claude – work"
    folder = profile_folder(engine_settings, "claude_cli", account["id"])
    assert folder.is_dir() and not any(folder.iterdir())
    listed = accounts_of(client, "claude_cli")
    assert listed["active"] == "default"  # adding does not switch
    assert listed["accounts"][1]["status"]["signed_in"] is False
    assert "Sign in" in listed["accounts"][1]["status"]["message"]
    for label in ("Default", "claude – WORK", ""):
        assert add_account(client, "claude_cli", label, expect=409 if label else 422)

    # The CLI's own sign-in, with only that folder set.
    sign_in(client, "claude_cli", account["id"], monkeypatch)
    listed = accounts_of(client, "claude_cli")
    assert [a["status"]["signed_in"] for a in listed["accounts"]] == [True, True]
    assert listed["accounts"][1]["status"]["plan"] == "Pro"
    assert "private@example.com" not in json.dumps(listed)

    # Choosing it changes only new runs, and the engine status names it.
    choose(client, "claude_cli", account["id"])
    status = {s["engine"]: s for s in client.get("/api/engines/status").json()}
    assert status["claude_cli"]["account_label"] == "Claude – work"
    assert status["codex_cli"]["account_label"] == "Default"
    job = post(client, f"/api/scenes/{scene['id']}/analyse")["active_job"]
    done = wait_for_job(client, job["id"])
    assert done["status"] == "completed"
    assert done["account"] == {"id": account["id"], "label": "Claude – work"}
    last = analysis_calls(fake)[-1]
    assert last["profile"] == str(folder) and last["leaked"] == []


def test_a_queued_run_keeps_its_account_and_codex_images_come_from_its_folder(
    engine_client, engine_settings, fake, monkeypatch
):
    client = engine_client
    account = signed_in_account(client, "codex_cli", "Codex – personal", monkeypatch)
    choose(client, "codex_cli", account["id"])
    _ada, scene = approved_scene(client)
    job = generate(client, scene)["active_job"]
    # Switching back now does not move the queued run.
    choose(client, "codex_cli", "default")
    done = wait_for_job(client, job["id"])
    assert done["status"] == "completed", done
    assert done["account"]["label"] == "Codex – personal"
    folder = profile_folder(engine_settings, "codex_cli", account["id"])
    assert generation_calls(fake)[-1]["profile"] == str(folder)
    # The image was saved, and found, in that account's own generated_images folder.
    assert list((folder / "generated_images").rglob("*.png"))
    assert not (fake.parent / "codex-home" / "generated_images").exists()


def test_continue_with_another_account_moves_only_not_started_items(
    engine_client, engine_settings, fake, monkeypatch
):
    client = engine_client
    work = signed_in_account(client, "claude_cli", "Work", monkeypatch)
    home = signed_in_account(client, "claude_cli", "Home", monkeypatch)
    out = add_account(client, "claude_cli", "Signed out")["account"]
    choose(client, "claude_cli", work["id"])
    (profile_folder(engine_settings, "claude_cli", work["id"]) / "fake-mode").write_text("limit")
    scenes = [create_scene(client, f"Scene {n}") for n in range(3)]
    batch = post(client, "/api/batches/analysis", {"scene_ids": [s["id"] for s in scenes]})[
        "batch"
    ]
    assert batch["account"] == {"id": work["id"], "label": "Work"}
    paused = wait_for_batch(client, batch["id"])
    assert (paused["state"], paused["pause_kind"]) == ("paused", "usage_limit")
    assert [i["status"] for i in paused["items"]] == ["failed", "not_started", "not_started"]
    calls = len(analysis_calls(fake))

    # A signed-out account is refused before anything changes.
    refused = post(
        client, f"/api/batches/{batch['id']}/continue", {"account_id": out["id"]}, expect=409
    )
    assert "“Signed out” is signed out" in refused["detail"]
    assert client.get(f"/api/batches/{batch['id']}").json()["account"]["id"] == work["id"]

    # Continue on Home, for this run only.
    post(client, f"/api/batches/{batch['id']}/continue", {"account_id": home["id"]}, expect=200)
    done = wait_for_batch(client, batch["id"])
    assert [i["status"] for i in done["items"]] == ["failed", "completed", "completed"]
    assert done["account"]["label"] == "Home"
    home_folder = str(profile_folder(engine_settings, "claude_cli", home["id"]))
    assert [c["profile"] for c in analysis_calls(fake)[calls:]] == [home_folder, home_folder]
    failed = client.get(f"/api/jobs/{done['items'][0]['job_id']}").json()
    assert failed["account"]["label"] == "Work"  # what ran keeps its account
    assert accounts_of(client, "claude_cli")["active"] == work["id"]

    # Try failed again offers the account choice too; "Also use for future runs" switches.
    retried = post(
        client,
        f"/api/batches/{batch['id']}/retry",
        {"account_id": "default", "make_active": True},
    )["batch"]
    assert retried["items"][3]["retry_of"] == done["items"][0]["job_id"]
    finished = wait_for_batch(client, batch["id"])
    assert finished["items"][3]["status"] == "completed"
    assert analysis_calls(fake)[-1]["profile"] is None
    assert accounts_of(client, "claude_cli")["active"] == "default"


def test_a_limit_on_one_account_does_not_pause_another_accounts_batch(
    engine_client, engine_settings, fake, monkeypatch, tmp_path
):
    client = engine_client
    gate = tmp_path / "gate"
    monkeypatch.setenv("FAKE_CLI_GATE", str(gate))
    work = signed_in_account(client, "claude_cli", "Work", monkeypatch)
    first = post(client, "/api/batches/analysis", {"scene_ids": [create_scene(client)["id"]]})
    choose(client, "claude_cli", work["id"])
    (profile_folder(engine_settings, "claude_cli", work["id"]) / "fake-mode").write_text("limit")
    scenes = [create_scene(client, f"Work {n}") for n in range(2)]
    second = post(client, "/api/batches/analysis", {"scene_ids": [s["id"] for s in scenes]})
    gate.write_text("go")
    assert wait_for_batch(client, first["batch"]["id"])["state"] == "finished"
    paused = wait_for_batch(client, second["batch"]["id"])
    assert paused["pause_kind"] == "usage_limit"


def test_removing_an_account_signs_it_out_and_deletes_its_folder(
    engine_client, engine_settings, fake, monkeypatch
):
    client = engine_client
    headers = authorization(client)
    account = signed_in_account(client, "codex_cli", "Spare", monkeypatch)
    folder = profile_folder(engine_settings, "codex_cli", account["id"])
    choose(client, "codex_cli", account["id"])
    assert client.delete("/api/cli-accounts/codex_cli/default", headers=headers).status_code == 409

    # Not while a run waits on it: a paused batch keeps its items.
    set_engine(client, "codex_cli")
    (folder / "fake-mode").write_text("limit")
    scenes = [create_scene(client, f"Scene {n}") for n in range(2)]
    batch = post(client, "/api/batches/analysis", {"scene_ids": [s["id"] for s in scenes]})[
        "batch"
    ]
    assert wait_for_batch(client, batch["id"])["state"] == "paused"
    busy = client.delete(f"/api/cli-accounts/codex_cli/{account['id']}", headers=headers)
    assert busy.status_code == 409 and "1 run is waiting" in busy.json()["detail"]
    post(client, f"/api/batches/{batch['id']}/cancel", expect=200)

    removed = client.delete(f"/api/cli-accounts/codex_cli/{account['id']}", headers=headers)
    assert removed.status_code == 200, removed.text
    assert removed.json()["signed_out"] is True
    assert not folder.exists()
    listed = accounts_of(client, "codex_cli")
    assert listed["active"] == "default" and len(listed["accounts"]) == 1
    calls = [json.loads(line) for line in fake.read_text(encoding="utf-8").splitlines()]
    assert ["logout"] in [c["args"] for c in calls if c["profile"] == str(folder)]
    # Past runs keep the account's name.
    item = client.get(f"/api/batches/{batch['id']}").json()["items"][0]
    assert client.get(f"/api/jobs/{item['job_id']}").json()["account"]["label"] == "Spare"


def test_a_removed_account_is_never_used_and_continue_needs_another(
    engine_client, engine_settings, fake, monkeypatch
):
    client = engine_client
    spare = signed_in_account(client, "claude_cli", "Spare", monkeypatch)
    choose(client, "claude_cli", spare["id"])
    (profile_folder(engine_settings, "claude_cli", spare["id"]) / "fake-mode").write_text("limit")
    scenes = [create_scene(client, f"Scene {n}") for n in range(2)]
    batch = post(client, "/api/batches/analysis", {"scene_ids": [s["id"] for s in scenes]})[
        "batch"
    ]
    assert wait_for_batch(client, batch["id"])["state"] == "paused"
    # Removed outside the studio's checks (for example by an older restore).
    cli_accounts.forget(engine_settings, "claude_cli", spare["id"])
    refused = post(client, f"/api/batches/{batch['id']}/continue", {}, expect=409)
    assert "was removed" in refused["detail"]
    calls = len(analysis_calls(fake))
    post(client, f"/api/batches/{batch['id']}/continue", {"account_id": "default"}, expect=200)
    assert wait_for_batch(client, batch["id"])["items"][1]["status"] == "completed"
    assert len(analysis_calls(fake)) == calls + 1


def test_one_sign_in_window_per_engine(engine_client, monkeypatch):
    client = engine_client

    class StillOpen:
        def poll(self):
            return None

    monkeypatch.setitem(cli_accounts._open, "codex_cli", StillOpen())
    result = client.post(
        "/api/cli-accounts/codex_cli/default/sign-in", headers=authorization(client)
    )
    assert result.status_code == 409 and "still open" in result.json()["detail"]
    missing = client.post(
        f"/api/cli-accounts/codex_cli/{'0' * 32}/sign-in", headers=authorization(client)
    )
    assert missing.status_code == 404


def test_generate_all_continues_on_another_account_for_the_whole_run(
    engine_client, engine_settings, fake, monkeypatch
):
    from tests.test_generate_all import approved_in, generate
    from tests.test_mapping import character_with_photos
    from tests.test_pipeline import latest_run, wait_for_run
    from tests.test_preparation import make_set

    client = engine_client
    monkeypatch.setattr("backend.pipeline.MAX_GENERATION_RUNS", 1)
    first = signed_in_account(client, "codex_cli", "First", monkeypatch)
    second = signed_in_account(client, "codex_cli", "Second", monkeypatch)
    choose(client, "codex_cli", first["id"])
    (profile_folder(engine_settings, "codex_cli", first["id"]) / "fake-mode").write_text("limit")
    holiday = make_set(client)
    ada = character_with_photos(client, "Ada")
    scenes = [approved_in(client, holiday, ada, f"Scene {n}") for n in range(3)]
    run = generate(client, holiday, scenes)
    assert len(run["batches"]) == 3
    deadline = time.monotonic() + 30
    while latest_run(client, holiday)["summary"]["paused"] is None:
        assert time.monotonic() < deadline
        time.sleep(0.1)
    time.sleep(0.3)

    post(
        client,
        f"/api/pipelines/{run['id']}/continue",
        {"account_id": second["id"], "account_engine": "codex_cli"},
        expect=200,
    )
    done = wait_for_run(client, holiday, ("finished",))
    assert (done["summary"]["done"], done["summary"]["retryable"]) == (2, 1)
    folder = str(profile_folder(engine_settings, "codex_cli", second["id"]))
    assert [c["profile"] for c in generation_calls(fake)[1:]] == [folder, folder]
    assert accounts_of(client, "codex_cli")["active"] == first["id"]


def test_profile_folders_are_never_backed_up_and_survive_a_restore(
    engine_settings, fake, monkeypatch
):
    import zipfile

    from fastapi.testclient import TestClient

    from backend.backup import restore_backup
    from backend.main import create_app
    from tests.test_backup import make_backup

    with TestClient(create_app(engine_settings), base_url="http://127.0.0.1:8765") as client:
        account = signed_in_account(client, "codex_cli", "Kept", monkeypatch)
        state = make_backup(client)
    archive = engine_settings.data_dir / "backups" / state["items"][0]["name"]
    with zipfile.ZipFile(archive) as zipped:
        assert not any(name.startswith("cli-accounts/") for name in zipped.namelist())
    restored, _previous = restore_backup(archive, engine_settings.data_dir)
    folder = profile_folder(engine_settings, "codex_cli", account["id"])
    assert folder.is_dir() and (restored / "cli-accounts" / "accounts.json").is_file()
    assert cli_accounts.find(engine_settings, "codex_cli", account["id"])["label"] == "Kept"
