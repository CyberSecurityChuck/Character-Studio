"""Phase 5: Generate via the Codex CLI, the manual bridge, results and recovery."""

import io
import json
import sqlite3
import time
import zipfile
from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image

from backend.generation import VARIATION_LINE
from backend.main import create_app
from tests.conftest import authorization, wait_for_job
from tests.test_library import picture
from tests.test_mapping import approve, ready_scene


def approved_scene(client):
    ada, scene = ready_scene(client)
    return ada, approve(client, scene)


def generate(client, scene, mode="generate", expect=202):
    result = client.post(
        f"/api/scenes/{scene['id']}/generate",
        headers=authorization(client),
        json={"approval_id": scene["approval"]["current"]["id"], "mode": mode},
    )
    assert result.status_code == expect, result.text
    return result.json()


def generation_calls(log: Path):
    if not log.is_file():
        return []
    calls = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
    return [c for c in calls if c["args"][:1] == ["exec"] and "--output-schema" not in c["args"]]


def run_generation(client, scene, mode="generate"):
    queued = generate(client, scene, mode)
    assert queued["workflow_state"] == "generating"
    job = wait_for_job(client, queued["active_job"]["id"])
    return job, client.get(f"/api/scenes/{scene['id']}").json()


def has_exif(path: Path) -> bool:
    with Image.open(path) as image:
        return bool(image.getexif()) or "exif" in image.info


def test_generate_sends_only_the_approved_package_and_keeps_every_result(
    engine_client, fake, settings
):
    client = engine_client
    ada, scene = ready_scene(client)
    # No approval yet: nothing can be generated.
    refused = client.post(
        f"/api/scenes/{scene['id']}/generate",
        headers=authorization(client),
        json={"approval_id": "none"},
    )
    assert refused.status_code == 409 and "Approve this scene" in refused.json()["detail"]
    scene = approve(client, scene)
    wrong = client.post(
        f"/api/scenes/{scene['id']}/generate",
        headers=authorization(client),
        json={"approval_id": "0" * 32},
    )
    assert wrong.status_code == 409

    job, detail = run_generation(client, scene)
    assert job["status"] == "completed", job
    assert job["engine_version"] == "codex-cli 0.162.1"
    assert detail["workflow_state"] == "generated"
    [result] = detail["results"]
    approval_id = scene["approval"]["current"]["id"]
    assert (result["version"], result["source"], result["mode"]) == (1, "codex_cli", "generate")
    assert isinstance(result["seconds"], int) and result["seconds"] >= 0
    assert detail["generation_timing"]["runs"] == 1
    assert job["seconds"] == result["seconds"]
    assert result["approval_id"] == approval_id and result["approval_current"]
    assert result["job_id"] == job["id"] and result["prompt_version"] == 1
    assert result["mappings"][0]["character_name"] == "Ada"
    image = client.get(result["image_url"])
    assert image.status_code == 200 and image.content.startswith(b"\x89PNG")

    # The package: numbered metadata-free images, text files, no character names.
    folder = Path(job["job_folder"])
    total = scene["total_images"]
    assert total == 4
    for number in range(1, total + 1):
        assert not has_exif(folder / f"image-{number}.jpg")
    assert not (folder / f"image-{total + 1}.jpg").exists()
    mapping = (folder / "mapping.txt").read_text(encoding="utf-8")
    assert "Subject 1: identity only from Image 2, Image 3 and Image 4." in mapping
    assert "Ada" not in mapping
    instruction = (folder / "instruction.txt").read_text(encoding="utf-8")
    prompt = scene["prompts"][0]
    assert prompt["prompt_text"].strip() in instruction
    assert "Ada" not in instruction and VARIATION_LINE not in instruction

    # Exactly the Phase 2.5 command, confined and with a clean environment.
    [call] = generation_calls(fake)
    args = call["args"]
    assert args[:6] == ["exec", "--skip-git-repo-check", "--ephemeral", "--ignore-user-config",
                        "-s", "read-only"]
    assert "--disable" not in args and "--output-schema" not in args
    assert [args[i + 1] for i, a in enumerate(args) if a == "-i"] == [
        str(folder / f"image-{n}.jpg") for n in range(1, total + 1)
    ]
    assert args[args.index("--") + 1] == instruction
    assert call["leaked"] == [] and call["stdin_closed"]
    assert Path(call["cwd"]).resolve() == folder.resolve()

    # A variation is a new result; the first one is untouched.
    first_bytes = image.content
    job, detail = run_generation(client, scene, "variation")
    assert job["status"] == "completed" and job["mode"] == "variation"
    assert [r["version"] for r in detail["results"]] == [2, 1]
    assert detail["results"][0]["mode"] == "variation"
    assert VARIATION_LINE in (Path(job["job_folder"]) / "instruction.txt").read_text("utf-8")
    assert client.get(detail["results"][1]["image_url"]).content == first_bytes
    assert len(generation_calls(fake)) == 2


def test_generation_failures_are_reported_and_never_retried(engine_client, fake, monkeypatch):
    client = engine_client
    _ada, scene = approved_scene(client)
    expected = {
        "no_image": "no_image",
        "outside": "no_image",
        "silent": "no_image",
        "limit": "usage_limit",
    }
    for count, (mode, kind) in enumerate(expected.items(), start=1):
        monkeypatch.setenv("FAKE_CLI_MODE", mode)
        job, detail = run_generation(client, scene)
        assert (job["status"], job["error_kind"]) == ("failed", kind), (mode, job)
        assert job["recoverable"] is True
        assert detail["results"] == [] and detail["workflow_state"] == "approved"
        # One launch per click; nothing is retried.
        assert len(generation_calls(fake)) == count
    # Signed out is caught before anything is sent.
    monkeypatch.setenv("FAKE_CLI_MODE", "signed_out")
    job, _detail = run_generation(client, scene)
    assert job["error_kind"] == "signed_out" and job["job_folder"] is None
    assert len(generation_calls(fake)) == len(expected)


def test_saved_image_can_be_recovered_after_cancel_or_failure(engine_client, fake, monkeypatch):
    client = engine_client
    _ada, scene = approved_scene(client)
    monkeypatch.setenv("FAKE_CLI_MODE", "save_then_hang")
    queued = generate(client, scene)
    job_id = queued["active_job"]["id"]
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        job = client.get(f"/api/jobs/{job_id}").json()
        folder = Path(job["job_folder"]) if job["job_folder"] else None
        if folder and (folder / "events.jsonl").is_file() and (
            folder / "events.jsonl"
        ).read_text(encoding="utf-8"):
            break
        time.sleep(0.1)
    time.sleep(1)
    client.post(f"/api/jobs/{job_id}/cancel", headers=authorization(client))
    job = wait_for_job(client, job_id)
    assert job["status"] == "cancelled" and job["recoverable"]
    found = client.post(f"/api/jobs/{job_id}/recover", headers=authorization(client)).json()
    assert found["found"] == 1
    [result] = found["scene"]["results"]
    assert result["recovered"] and result["job_id"] == job_id
    # Checking again never duplicates a result.
    again = client.post(f"/api/jobs/{job_id}/recover", headers=authorization(client)).json()
    assert again["found"] == 0 and len(again["scene"]["results"]) == 1
    # Completed runs cannot be "recovered".
    monkeypatch.setenv("FAKE_CLI_MODE", "ok")
    done, _detail = run_generation(client, scene)
    refused = client.post(f"/api/jobs/{done['id']}/recover", headers=authorization(client))
    assert refused.status_code == 409


def test_queued_run_with_an_ended_approval_sends_nothing(engine_client, fake):
    client = engine_client
    _ada, scene = approved_scene(client)
    old = scene["approval"]["current"]["id"]
    client.post(
        f"/api/scenes/{scene['id']}/approval/withdraw",
        headers=authorization(client),
        json={"approval_id": old},
    )
    with sqlite3.connect(client.app.state.settings.data_dir / "studio.db") as db:
        db.execute(
            "INSERT INTO engine_jobs (id, kind, scene_id, engine, status, timeout_seconds, "
            "input_id, settings_json, created_at) VALUES ('g-old', 'generation', ?, "
            "'codex_cli', 'not_started', 300, ?, '{\"mode\": \"generate\"}', 't')",
            (scene["id"], old),
        )
    client.app.state.runner.notify()
    job = wait_for_job(client, "g-old")
    assert (job["status"], job["error_kind"]) == ("failed", "approval_ended")
    assert "nothing was sent" in job["error_details"]
    assert generation_calls(fake) == []


def test_generate_guards_engine_setting_and_running_jobs(engine_client, fake, monkeypatch):
    client = engine_client
    _ada, scene = approved_scene(client)
    current = client.get("/api/engines/settings").json()
    client.put(
        "/api/engines/settings",
        headers=authorization(client),
        json={**current, "generation_engine": "manual"},
    )
    manual = generate(client, scene, expect=409)
    assert "Export for manual use" in manual["detail"]
    current = client.get("/api/engines/settings").json()
    client.put(
        "/api/engines/settings",
        headers=authorization(client),
        json={**current, "generation_engine": "codex_cli"},
    )
    monkeypatch.setenv("FAKE_CLI_MODE", "slow")
    queued = generate(client, scene)
    # A second click while one run is active is refused, so no duplicate request.
    assert "Wait for the running engine job" in generate(client, scene, expect=409)["detail"]
    client.post(f"/api/jobs/{queued['active_job']['id']}/cancel", headers=authorization(client))
    assert wait_for_job(client, queued["active_job"]["id"])["status"] == "cancelled"


def export(client, scene, expect=201):
    result = client.post(
        f"/api/scenes/{scene['id']}/exports",
        headers=authorization(client),
        json={"approval_id": scene["approval"]["current"]["id"] if scene["approval"]["current"]
              else "none"},
    )
    assert result.status_code == expect, result.text
    return result.json()


def import_result(client, scene, content=None, expect=201, **params):
    query = "&".join(f"{k}={v}" for k, v in params.items())
    result = client.post(
        f"/api/scenes/{scene['id']}/results?{query}",
        headers={**authorization(client), "Content-Type": "application/octet-stream"},
        content=content if content is not None else picture("JPEG"),
    )
    assert result.status_code == expect, result.text
    return result.json()


def test_manual_export_and_import_stay_linked_to_the_approval(client):
    _ada, scene = ready_scene(client)
    assert "Approve this scene" in export(client, scene, expect=409)["detail"]
    scene = approve(client, scene)
    created = export(client, scene)
    [package] = created["scene"]["exports"]
    assert package["id"] == created["export_id"] and package["approval_current"]
    assert package["result_count"] == 0
    download = client.get(package["download_url"])
    assert download.status_code == 200
    assert "package%201.zip" in download.headers["content-disposition"]
    with zipfile.ZipFile(io.BytesIO(download.content)) as archive:
        names = set(archive.namelist())
        assert names == {
            "image-1.jpg", "image-2.jpg", "image-3.jpg", "image-4.jpg",
            "prompt.txt", "negative_prompt.txt", "mapping.txt", "README.txt",
        }
        # The user handles this package themselves, so it may say who is who.
        assert "Subject 1 (Ada)" in archive.read("mapping.txt").decode()
        with Image.open(io.BytesIO(archive.read("image-2.jpg"))) as image:
            assert not image.getexif()
        assert archive.read("prompt.txt").decode().strip() == (
            scene["prompts"][0]["prompt_text"].strip()
        )

    detail = import_result(client, scene, export_id=package["id"], note="ChatGPT Images")
    [result] = detail["results"]
    assert (result["source"], result["mode"], result["note"]) == (
        "manual_import", "import", "ChatGPT Images"
    )
    assert result["job_id"] == package["id"]
    assert result["approval_id"] == scene["approval"]["current"]["id"]
    assert detail["exports"][0]["result_count"] == 1
    assert detail["workflow_state"] == "generated"

    # After withdrawing, the package still links its import to the inputs it carried.
    withdrawn = client.post(
        f"/api/scenes/{scene['id']}/approval/withdraw",
        headers=authorization(client),
        json={"approval_id": scene["approval"]["current"]["id"]},
    ).json()
    later = import_result(client, withdrawn, export_id=package["id"])
    assert len(later["results"]) == 2 and not later["results"][0]["approval_current"]
    unlinked = import_result(client, withdrawn, expect=409)
    assert "linked to approved inputs" in unlinked["detail"]
    damaged = import_result(
        client, scene, content=b"not an image", expect=422, export_id=package["id"]
    )
    assert "damaged or unsupported" in damaged["detail"]


def test_results_gallery_preferred_and_deletion(client, settings):
    _ada, scene = approved_scene(client)
    first = import_result(client, scene)
    second = import_result(client, scene)
    newest, oldest = second["results"]
    gallery = client.get("/api/results").json()
    assert [r["id"] for r in gallery] == [newest["id"], oldest["id"]]
    assert gallery[0]["scene_title"] == "Two people"
    assert first["results"][0]["id"] == oldest["id"]

    def prefer(result, value=True):
        return client.put(
            f"/api/results/{result['id']}/preferred",
            headers=authorization(client),
            json={"preferred": value},
        ).json()

    prefer(oldest)
    detail = prefer(newest)
    # Several results of one scene may be preferred (user's choice in the Phase 5 review).
    assert [r["is_preferred"] for r in detail["results"]] == [True, True]
    detail = prefer(oldest, False)
    assert [r["is_preferred"] for r in detail["results"]] == [True, False]

    # Several results download as one zip, named after their scene and version.
    zipped = client.get(f"/api/results/download?id={newest['id']}&id={oldest['id']}")
    assert zipped.status_code == 200
    names = zipfile.ZipFile(io.BytesIO(zipped.content)).namelist()
    assert names == ["Two people - result 2.jpg", "Two people - result 1.jpg"]
    assert not any((settings.data_dir / "exports").glob("results-*.zip"))  # Temporary file gone.
    imported = client.get(f"/api/scenes/{scene['id']}").json()
    assert all(r["seconds"] is None for r in imported["results"])  # The studio did not time them.

    files = [
        settings.data_dir / row
        for row in sqlite3.connect(settings.data_dir / "studio.db").execute(
            "SELECT original_path FROM generation_results WHERE id = ?", (newest["id"],)
        ).fetchone()
    ]
    deleted = client.delete(f"/api/results/{newest['id']}", headers=authorization(client)).json()
    assert deleted["cleanup_pending"] is False
    assert [r["id"] for r in deleted["scene"]["results"]] == [oldest["id"]]
    assert not files[0].exists()

    # Deleting the scene removes its results and their files.
    remaining = settings.data_dir / sqlite3.connect(settings.data_dir / "studio.db").execute(
        "SELECT original_path FROM generation_results"
    ).fetchone()[0]
    scene = client.get(f"/api/scenes/{scene['id']}").json()
    assert scene["result_count"] == 1
    client.delete(f"/api/scenes/{scene['id']}?revision={scene['revision']}",
                  headers=authorization(client))
    assert client.get("/api/results").json() == [] and not remaining.exists()


def test_results_survive_restart_and_interrupted_generation_is_not_resubmitted(settings):
    with TestClient(create_app(settings), base_url="http://127.0.0.1:8765") as client:
        _ada, scene = approved_scene(client)
        import_result(client, scene)
        approval_id = scene["approval"]["current"]["id"]
    with sqlite3.connect(settings.data_dir / "studio.db") as db:
        db.execute(
            "INSERT INTO engine_jobs (id, kind, scene_id, engine, status, timeout_seconds, "
            "input_id, job_folder, created_at) VALUES ('g-run', 'generation', ?, 'codex_cli', "
            "'running', 300, ?, 'jobs/x/generation-1', 't')",
            (scene["id"], approval_id),
        )
    with TestClient(create_app(settings), base_url="http://127.0.0.1:8765") as client:
        job = client.get("/api/jobs/g-run").json()
        assert (job["status"], job["recoverable"]) == ("interrupted", True)
        detail = client.get(f"/api/scenes/{scene['id']}").json()
        assert detail["workflow_state"] == "generated" and len(detail["results"]) == 1
        assert detail["active_job"] is None


def test_upgrade_from_mapping_schema_keeps_approvals(settings):
    with TestClient(create_app(settings), base_url="http://127.0.0.1:8765") as client:
        _ada, scene = approved_scene(client)
    with sqlite3.connect(settings.data_dir / "studio.db") as db:
        db.execute("DROP TABLE generation_results")
        db.execute("ALTER TABLE engine_jobs DROP COLUMN settings_json")
        db.execute("ALTER TABLE engine_jobs DROP COLUMN provider_request_id")
        db.execute("UPDATE alembic_version SET version_num = '0005_mapping'")
    with TestClient(create_app(settings), base_url="http://127.0.0.1:8765") as client:
        assert client.get("/api/health").json()["schema_revision"] == "0006_generation"
        detail = client.get(f"/api/scenes/{scene['id']}").json()
        assert detail["approval"]["state"] == "approved"
        assert detail["results"] == [] and detail["exports"] == []


def test_deleting_can_remove_package_copies_only_when_asked(engine_client, fake):
    client = engine_client
    ada, scene = approved_scene(client)
    job, _detail = run_generation(client, scene)
    export(client, scene)
    photo_ids = scene["subjects"][0]["reference_ids"]

    def copies(**query):
        params = "&".join(f"{k}={v}" for k, v in query.items())
        return client.get(f"/api/package-copies?{params}").json()

    # Three references, each in the generation folder and the export package.
    assert copies(character=ada["id"]) == {"count": 6, "packages": 2, "scenes": ["Two people"]}
    assert copies(photo=photo_ids[0])["count"] == 2

    def revision():
        return client.get(f"/api/characters/{ada['id']}").json()["revision"]

    # Keeping copies (the default) leaves the package untouched.
    kept = client.delete(
        f"/api/photos/{photo_ids[0]}?revision={revision()}", headers=authorization(client)
    ).json()
    assert kept["copies_removed"] == 0 and copies(photo=photo_ids[0])["count"] == 2
    # Removing copies of one photo deletes just its files and notes it in the package.
    removed = client.delete(
        f"/api/photos/{photo_ids[1]}?revision={revision()}&remove_copies=true",
        headers=authorization(client),
    ).json()
    assert removed["copies_removed"] == 2 and copies(photo=photo_ids[1])["count"] == 0
    detail = client.get(f"/api/scenes/{scene['id']}").json()
    [package] = detail["exports"]
    assert package["photos_removed"] == 1
    zipped = zipfile.ZipFile(io.BytesIO(client.get(package["download_url"]).content))
    assert "image-3.jpg" not in zipped.namelist() and "image-2.jpg" in zipped.namelist()
    assert "were removed from this package" in zipped.read("README.txt").decode()

    # Deleting the character with its copies: every copy goes, results and Image 1 stay.
    gone = client.delete(
        f"/api/characters/{ada['id']}?revision={revision()}&remove_copies=true",
        headers=authorization(client),
    ).json()
    assert gone["copies_removed"] == 4 and copies(character=ada["id"])["count"] == 0
    detail = client.get(f"/api/scenes/{scene['id']}").json()
    assert len(detail["results"]) == 1 and detail["exports"][0]["photos_removed"] == 3
    zipped = zipfile.ZipFile(io.BytesIO(client.get(package["download_url"]).content))
    assert [n for n in zipped.namelist() if n.startswith("image-")] == ["image-1.jpg"]
    mapping = zipped.read("mapping.txt").decode()
    assert "Ada" not in mapping and "Subject 1 (Deleted character)" in mapping
    assert sorted(p.name for p in Path(job["job_folder"]).glob("image-*.jpg")) == ["image-1.jpg"]


def test_manual_package_can_be_deleted_and_imports_are_kept(client, settings):
    _ada, scene = approved_scene(client)
    created = export(client, scene)
    export_id = created["export_id"]
    folder = Path(created["scene"]["exports"][0]["job_folder"])
    imported = import_result(client, scene, export_id=export_id)["results"][0]
    assert folder.is_dir() and imported["job_id"] == export_id
    gone = client.delete(f"/api/exports/{export_id}", headers=authorization(client)).json()
    assert gone["cleanup_pending"] is False and gone["scene"]["exports"] == []
    assert not folder.exists()
    [kept] = gone["scene"]["results"]
    assert kept["id"] == imported["id"] and kept["job_id"] is None
    assert kept["approval_id"] == scene["approval"]["current"]["id"]
    assert client.get(f"/api/exports/{export_id}/package").status_code == 404
    again = client.delete(f"/api/exports/{export_id}", headers=authorization(client))
    assert again.status_code == 404
