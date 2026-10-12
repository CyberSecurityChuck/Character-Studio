"""Phase 6C-2: region edits and selective replacement (fake Codex, fake provider APIs)."""

import base64
import io
import json
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageChops, ImageDraw

from backend.editing import composite, flux3_prompt, mask_box, read_mask
from backend.main import create_app
from tests.conftest import authorization, wait_for_job
from tests.test_api_engines import KEY, api_settings, providers, save_key  # noqa: F401
from tests.test_generation import approved_scene, generation_calls, import_result
from tests.test_image_engines import openai_image_reply, png

SIZE = (800, 600)
AREA = (500, 150, 700, 450)  # left, top, right, bottom of the marked rectangle


def textured(size=SIZE) -> bytes:
    """A result with detail everywhere, so any change outside the area would show."""
    image = Image.effect_noise(size, 60).convert("RGB")
    draw = ImageDraw.Draw(image)
    for x in range(0, size[0], 40):
        draw.line([(x, 0), (x, size[1])], fill=(200, 40, 40), width=3)
    buffer = io.BytesIO()
    image.save(buffer, "PNG")
    return buffer.getvalue()


def mask_png(size=SIZE, area=AREA) -> str:
    mask = Image.new("L", size, 0)
    ImageDraw.Draw(mask).rectangle(area, fill=255)
    buffer = io.BytesIO()
    mask.save(buffer, "PNG")
    return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode()


def edit(client, result_id, expect=202, **body):
    payload = {"kind": "fix", "option": "codex_cli", "instruction": "Make the bench green.",
               "mask": mask_png(), **body}
    reply = client.post(f"/api/results/{result_id}/edit", headers=authorization(client),
                        json=payload)
    assert reply.status_code == expect, reply.text
    return reply.json()


def image_of(client, result) -> Image.Image:
    data = client.get(result["image_url"]).content
    return Image.open(io.BytesIO(data)).convert("RGB")


def assert_only_area_changed(before: Image.Image, after: Image.Image):
    assert before.size == after.size
    outside = Image.new("L", before.size, 255)
    ImageDraw.Draw(outside).rectangle(AREA, fill=0)
    diff = ImageChops.difference(before, after).convert("L")
    # Not a single pixel outside the marked area differs.
    assert ImageChops.multiply(diff, outside).getbbox() is None
    assert diff.getbbox() is not None


def ready_result(client):
    _ada, scene = approved_scene(client)
    detail = import_result(client, scene, content=textured())
    return scene, detail["results"][0]


def test_paste_back_keeps_every_pixel_outside_the_area():
    original = Image.open(io.BytesIO(textured())).convert("RGB")
    edited = Image.new("RGB", (400, 300), (10, 200, 10))  # a different size from the engine
    mask = read_mask(mask_png(), SIZE)
    merged, shape_changed = composite(original, edited, mask)
    assert_only_area_changed(original, merged)
    assert shape_changed is False
    # Well inside the area the edit shows fully; the soft edge stays inside the area.
    assert merged.getpixel((600, 300)) == (10, 200, 10)
    assert mask_box(mask) == [0.625, 0.25, 0.8762, 0.7517]
    for bad, message in ((mask_png((400, 300), (10, 10, 50, 50)), "size"),
                         (mask_png(area=(0, 0, 0, 0)), "Mark the area"),
                         (mask_png(area=(0, 0, 800, 600)), "almost everything"),
                         ("data:image/png;base64,bm90IGFuIGltYWdl", "could not be read")):
        with pytest.raises(ValueError, match=message):
            read_mask(bad, SIZE)
    prompt = flux3_prompt("replace", [0.5, 0.25, 0.8, 0.75], "", 2)
    assert "<ref_image_0>" in prompt and "<ref_image_2>" in prompt
    row = json.loads(prompt.splitlines()[-1])[0]
    assert row["tgt_bbox"] == [250, 500, 750, 800]  # [y0, x0, y1, x1] on 0-1000


def test_codex_fix_and_replace_paste_back_and_keep_provenance(engine_client, fake):
    client = engine_client
    scene, parent = ready_result(client)
    queued = edit(client, parent["id"])
    assert queued["workflow_state"] == "editing"
    assert queued["active_job"]["kind"] == "edit"
    assert queued["active_job"]["engine_name"] == "Codex"
    job = wait_for_job(client, queued["active_job"]["id"])
    assert job["status"] == "completed", job
    detail = client.get(f"/api/scenes/{scene['id']}").json()
    edited = next(r for r in detail["results"] if r["mode"] == "edit")
    assert edited["parent_result_id"] == parent["id"]
    assert edited["approval_id"] == parent["approval_id"]
    assert edited["edit"]["kind"] == "fix" and edited["edit"]["parent_version"] == 1
    assert edited["edit"]["instruction"] == "Make the bench green."
    assert (edited["width"], edited["height"]) == SIZE
    assert_only_area_changed(image_of(client, parent), image_of(client, edited))
    mask = client.get(edited["mask_url"])
    assert mask.status_code == 200 and mask.headers["content-type"] == "image/png"
    [call] = generation_calls(fake)
    instruction = call["args"][-1]
    assert "Change only the marked area" in instruction and "Ada" not in instruction
    assert call["args"].count("-i") == 1  # a fix sends only the result

    # Replacing a person sends that subject's approved reference photos, nothing else.
    job = wait_for_job(client, edit(client, parent["id"], kind="replace", subject="Subject 1",
                                    instruction="")["active_job"]["id"])
    assert job["status"] == "completed", job
    call = generation_calls(fake)[-1]
    references = len(next(m for m in parent["mappings"] if m["subject"] == "Subject 1")["images"])
    assert call["args"].count("-i") == 1 + references
    assert "Subject 1" in call["args"][-1] and "Ada" not in call["args"][-1]
    # Subject 2 was kept, so it has no approved photos to replace with.
    refused = edit(client, parent["id"], expect=422, kind="replace", subject="Subject 2")
    assert "approved reference photos" in refused["detail"]
    assert edit(client, parent["id"], expect=422, instruction="  ")["detail"].startswith(
        "Describe"
    )
    assert edit(client, "missing", expect=404)


def test_edits_respect_withdrawn_approvals_and_block_deletion(engine_client, fake, settings):
    client = engine_client
    scene, parent = ready_result(client)
    with sqlite3.connect(settings.data_dir / "studio.db") as db:
        db.execute(
            "INSERT INTO engine_jobs (id, kind, scene_id, engine, status, timeout_seconds, "
            "input_id, created_at) VALUES ('e-wait', 'edit', ?, 'codex_cli', 'not_started', "
            "300, ?, 'z')",
            (scene["id"], parent["id"]),
        )
    refused = client.delete(f"/api/results/{parent['id']}", headers=authorization(client))
    assert refused.status_code == 409 and "edit" in refused.json()["detail"]
    client.post("/api/jobs/e-wait/cancel", headers=authorization(client))
    current = client.get(f"/api/scenes/{scene['id']}").json()
    withdrawn = client.post(
        f"/api/scenes/{scene['id']}/approval/withdraw",
        headers=authorization(client),
        json={"approval_id": current["approval"]["current"]["id"]},
    )
    assert withdrawn.status_code == 200, withdrawn.text
    assert client.get(f"/api/scenes/{scene['id']}").json()["results"][0]["editable"] is False
    blocked = edit(client, parent["id"], expect=409)
    assert "withdrew" in blocked["detail"]


def flux_client(api_settings, providers):  # noqa: F811
    return TestClient(create_app(api_settings), base_url="http://127.0.0.1:8765")


def test_flux_fill_fixes_with_a_true_mask_and_never_replaces(api_settings, providers):  # noqa: F811
    providers.bfl_sample = png(800, 600, (20, 160, 20))
    with flux_client(api_settings, providers) as client:
        scene, parent = ready_result(client)
        options = {o["id"]: o for o in client.get("/api/edit-options").json()}
        assert options["flux_fill"]["available"] is False
        assert "key" in options["flux_fill"]["reason"]
        save_key(client, "bfl_api")
        options = {o["id"]: o for o in client.get("/api/edit-options").json()}
        assert options["flux_fill"]["kinds"] == ["fix"] and options["flux_fill"]["area"] == "mask"
        assert edit(client, parent["id"], expect=422, option="flux_fill", kind="replace",
                    subject="Subject 1")["detail"].startswith("FLUX.1 Fill cannot replace")
        assert "charged" in edit(client, parent["id"], expect=409, option="flux_fill")["detail"]
        job = wait_for_job(client, edit(client, parent["id"], option="flux_fill",
                                        confirm_charges=True)["active_job"]["id"])
        assert job["status"] == "completed", job
        assert job["engine_name"] == "FLUX.1 Fill" and job["usage"]["cost_credits"] == 5
        [submit] = providers.posts()
        assert submit["path"].endswith("/v1/flux-pro-1.0-fill")
        assert submit["headers"]["x-key"] == KEY
        sent_mask = Image.open(io.BytesIO(base64.b64decode(submit["body"]["mask"])))
        assert sent_mask.getpixel((600, 300)) == 255 and sent_mask.getpixel((10, 10)) == 0
        assert submit["body"]["prompt"] == "Make the bench green."
        sample = next(r for r in providers.requests if r["path"].endswith("/sample.png"))
        assert "x-key" not in sample["headers"]  # the key never goes to the result link
        edited = next(r for r in client.get(f"/api/scenes/{scene['id']}").json()["results"]
                      if r["mode"] == "edit")
        assert edited["source"] == "bfl_api"
        assert_only_area_changed(image_of(client, parent), image_of(client, edited))

        providers.bfl_statuses = ["Content Moderated"]
        job = wait_for_job(client, edit(client, parent["id"], option="flux_fill",
                                        confirm_charges=True)["active_job"]["id"])
        assert job["status"] == "failed" and job["error_kind"] == "blocked"


def test_flux_3_replaces_with_approved_photos_and_can_be_recovered(api_settings, providers):  # noqa: F811
    providers.bfl_sample = png(800, 600, (200, 20, 200))
    with flux_client(api_settings, providers) as client:
        scene, parent = ready_result(client)
        save_key(client, "bfl_api")
        providers.bfl_statuses = ["Error"]
        job = wait_for_job(client, edit(client, parent["id"], option="flux_3", kind="replace",
                                        subject="Subject 1", instruction="",
                                        confirm_charges=True)["active_job"]["id"])
        assert job["status"] == "failed" and job["recoverable"], job
        [submit] = providers.posts()
        assert submit["path"].endswith("/v1/flux-3-image")
        body = submit["body"]
        mapping = next(m for m in parent["mappings"] if m["subject"] == "Subject 1")
        references = len(mapping["images"])
        assert len(body["images"]) == 1 + references and body["aspect_ratio"] == "auto"
        assert "<ref_image_0>" in body["prompt"] and "tgt_bbox" in body["prompt"]
        assert "Ada" not in json.dumps(body)
        assert (Path(job["job_folder"]) / "submitted.json").is_file()
        # The task finished after all: one free status check keeps it, nothing is resent.
        providers.bfl_statuses = ["Ready"]
        found = client.post(f"/api/jobs/{job['id']}/recover", headers=authorization(client))
        assert found.status_code == 200 and found.json()["found"] == 1, found.text
        assert len(providers.posts()) == 1
        edited = next(r for r in found.json()["scene"]["results"] if r["mode"] == "edit")
        assert edited["recovered"] and edited["edit"]["subject"] == "Subject 1"
        assert_only_area_changed(image_of(client, parent), image_of(client, edited))
        again = client.post(f"/api/jobs/{job['id']}/recover", headers=authorization(client))
        assert again.json()["found"] == 0

        # A result link outside Black Forest Labs is never followed.
        providers.bfl_statuses = ["Ready"]
        providers.bfl_sample_url = "https://example.com/sample.png"
        job = wait_for_job(client, edit(client, parent["id"], option="flux_3",
                                        confirm_charges=True)["active_job"]["id"])
        assert job["status"] == "failed" and "image link" in job["error_details"]


def test_openai_edit_sends_the_mask_and_needs_an_image_model(api_settings, providers):  # noqa: F811
    with flux_client(api_settings, providers) as client:
        scene, parent = ready_result(client)
        save_key(client, "openai_api")
        options = {o["id"]: o for o in client.get("/api/edit-options").json()}
        assert options["openai_api"]["available"] is False
        assert "image model" in options["openai_api"]["reason"]
        current = client.get("/api/engines/settings").json()
        reply = client.put("/api/engines/settings", headers=authorization(client), json={
            **current, "models": {"openai_api": {"generation": "img-model"}}})
        assert reply.status_code == 200, reply.text
        providers.next["openai_api"] = (200, openai_image_reply())
        job = wait_for_job(client, edit(client, parent["id"], option="openai_api",
                                        confirm_charges=True)["active_job"]["id"])
        assert job["status"] == "completed", job
        [sent] = providers.posts()
        form = sent["body"]
        assert sent["path"].endswith("/v1/images/edits") and form["fields"]["model"] == "img-model"
        names = [f["name"] for f in form["files"]]
        assert names == ["image[]", "mask"]
        guide = Image.open(io.BytesIO(form["files"][1]["bytes"]))
        width, height = map(int, form["fields"]["size"].split("x"))
        assert guide.mode == "RGBA" and guide.size == (width, height)
        # Transparent where OpenAI may change the image, opaque elsewhere.
        assert guide.getpixel((int(width * 0.75), height // 2))[3] == 0
        assert guide.getpixel((5, 5))[3] == 255
        edited = next(r for r in client.get(f"/api/scenes/{scene['id']}").json()["results"]
                      if r["mode"] == "edit")
        assert edited["source"] == "openai_api"
