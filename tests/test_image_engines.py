"""Phase 6C-1: API image engines (Gemini image, OpenAI Images) against local fake APIs."""

import base64
import io
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from backend.image_api import gemini_ratio, openai_size
from backend.main import create_app
from tests.conftest import authorization, wait_for_job
from tests.test_api_engines import KEY, api_settings, providers, save_key  # noqa: F401
from tests.test_generation import approved_scene


def png(width=64, height=96, colour=(40, 120, 200)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), colour).save(buffer, "PNG")
    return buffer.getvalue()


def gemini_image_reply(text="Here is the image.") -> dict:
    data = base64.b64encode(png()).decode()
    return {
        "candidates": [
            {
                "content": {
                    "parts": [
                        {"text": text},
                        {"inlineData": {"mimeType": "image/png", "data": data}},
                    ]
                },
                "finishReason": "STOP",
            }
        ],
        "usageMetadata": {"promptTokenCount": 2100, "candidatesTokenCount": 1290},
    }


def openai_image_reply() -> dict:
    return {
        "created": 1,
        "data": [{"b64_json": base64.b64encode(png()).decode()}],
        "output_format": "png",
        "usage": {"input_tokens": 3200, "output_tokens": 4160},
    }


def select_generation(client, engine, model="img-model", options=None, expect=200):
    current = client.get("/api/engines/settings").json()
    models = {**current["models"], engine: {"generation": model}} if model else current["models"]
    body = {
        **current,
        "generation_engine": engine,
        "models": models,
        "image_options": options or {},
    }
    reply = client.put("/api/engines/settings", headers=authorization(client), json=body)
    assert reply.status_code == expect, reply.text
    return reply.json()


def generate(client, scene, expect=202, **extra):
    reply = client.post(
        f"/api/scenes/{scene['id']}/generate",
        headers=authorization(client),
        json={"approval_id": scene["approval"]["current"]["id"], **extra},
    )
    assert reply.status_code == expect, reply.text
    return reply.json()


@pytest.fixture
def client(api_settings):  # noqa: F811
    with TestClient(create_app(api_settings), base_url="http://127.0.0.1:8765") as client:
        yield client


def test_sizes_follow_the_base_image_shape_within_provider_limits():
    for width, height in ((383, 801), (1000, 1000), (4000, 1000), (1000, 4000), (1920, 1080)):
        for size in ("1K", "2K"):
            w, h = map(int, openai_size(width, height, size).split("x"))
            assert w % 16 == 0 and h % 16 == 0
            assert 655_360 <= w * h <= 8_294_400 and max(w, h) <= 3840
            assert max(w / h, h / w) <= 3
    assert openai_size(1920, 1080, "2K") == "2560x1440"
    assert gemini_ratio(1920, 1080) == "16:9" and gemini_ratio(383, 801) == "9:16"
    assert gemini_ratio(1000, 1000) == "1:1"


def test_image_engine_settings_need_a_key_and_an_image_model(client, providers):  # noqa: F811
    refused = select_generation(client, "gemini_api", expect=422)
    assert "key" in refused["detail"]
    saved = save_key(client, "gemini_api")
    # The key's list keeps image models apart from analysis models.
    assert saved["image_models"] == ["gemini-nano-banana-2.1"]
    assert "gemini-nano-banana-2.1" not in saved["models"]
    assert saved["makes_images"] is True and saved["suggested_image_model"]
    assert select_generation(client, "gemini_api", model=None, expect=422)["detail"].startswith(
        "Choose an image model"
    )
    # Sizes and quality are checked per engine.
    bad = select_generation(client, "gemini_api", options={"gemini_api": {"quality": "high"}},
                            expect=422)
    assert "quality" in json.dumps(bad)
    bad = select_generation(client, "openai_api", options={"openai_api": {"size": "4K"}},
                            expect=422)
    assert "sizes" in json.dumps(bad)
    chosen = select_generation(client, "gemini_api", options={"gemini_api": {"size": "2K"}})
    assert chosen["generation_engine"] == "gemini_api"
    assert chosen["models"]["gemini_api"] == {"generation": "img-model"}
    assert chosen["image_options"] == {"gemini_api": {"size": "2K"}}
    # A key in use for generation cannot be removed.
    removed = client.delete("/api/api-engines/gemini_api/key", headers=authorization(client))
    assert removed.status_code == 409 and "generation" in removed.json()["detail"]
    anthropic = client.get("/api/api-engines").json()
    assert {e["id"]: e["makes_images"] for e in anthropic}["anthropic_api"] is False


def test_gemini_generation_sends_the_approved_package_once(client, providers, api_settings):  # noqa: F811
    _ada, scene = approved_scene(client)
    save_key(client, "gemini_api")
    select_generation(client, "gemini_api", options={"gemini_api": {"size": "2K"}})
    # Without the user's charge confirmation nothing is queued.
    refused = generate(client, scene, expect=409)
    assert "charged" in refused["detail"] and not providers.posts()
    providers.next["gemini_api"] = (200, gemini_image_reply())
    queued = generate(client, scene, confirm_charges=True)
    assert queued["active_job"]["engine"] == "gemini_api"
    job = wait_for_job(client, queued["active_job"]["id"])
    assert job["status"] == "completed", job
    assert job["model"] == "img-model" and job["usage"]["input_tokens"] == 2100
    assert job["usage"]["image_size"] == "2K"

    [sent] = providers.posts()
    assert sent["path"].endswith("/v1beta/models/img-model:generateContent")
    assert sent["headers"]["x-goog-api-key"] == KEY
    body = json.dumps(sent["body"])
    assert KEY not in body and "Ada" not in body
    config = sent["body"]["generationConfig"]
    assert config["responseModalities"] == ["TEXT", "IMAGE"]
    assert config["imageConfig"]["imageSize"] == "2K" and config["imageConfig"]["aspectRatio"]
    parts = sent["body"]["contents"][0]["parts"]
    instruction = parts[0]["text"]
    assert "full path" not in instruction and "Image 1: image-1.jpg" in instruction
    assert len([p for p in parts if "inline_data" in p]) == scene["total_images"]

    detail = client.get(f"/api/scenes/{scene['id']}").json()
    [result] = detail["results"]
    assert result["source"] == "gemini_api" and result["engine_version"] == "img-model"
    assert result["usage"]["output_tokens"] == 1290
    folder = Path(job["job_folder"])
    saved = json.loads((folder / "response.json").read_text(encoding="utf-8"))
    assert "characters>" in json.dumps(saved) and len(json.dumps(saved)) < 2000
    assert KEY not in (folder / "request.json").read_text(encoding="utf-8")
    assert (folder / "output.png").is_file()
    assert not job["recoverable"]


def test_openai_generation_uses_presets_and_reports_refusals(client, providers):  # noqa: F811
    _ada, scene = approved_scene(client)
    save_key(client, "openai_api")
    select_generation(client, "openai_api", options={"openai_api": {"size": "1K",
                                                                     "quality": "low"}})
    preset = client.post(
        "/api/presets",
        headers=authorization(client),
        json={"name": "Sharp", "image_size": "2K", "image_quality": "high"},
    )
    assert preset.status_code == 201, preset.text
    assert preset.json()["image_quality"] == "high"
    providers.next["openai_api"] = (200, openai_image_reply())
    queued = generate(client, scene, confirm_charges=True, preset_id=preset.json()["id"])
    job = wait_for_job(client, queued["active_job"]["id"])
    assert job["status"] == "completed", job
    [sent] = providers.posts()
    assert sent["path"].endswith("/v1/images/edits")
    assert sent["headers"]["authorization"] == f"Bearer {KEY}"
    form = sent["body"]
    assert form["multipart"] and form["fields"]["model"] == "img-model"
    # The preset's size and quality win over Studio settings for this run.
    assert form["fields"]["quality"] == "high"
    w, h = map(int, form["fields"]["size"].split("x"))
    assert w * h > 2_000_000 and w % 16 == 0 and h % 16 == 0
    assert [f["name"] for f in form["files"]] == ["image[]"] * scene["total_images"]
    assert "Ada" not in form["fields"]["prompt"]
    result = client.get(f"/api/scenes/{scene['id']}").json()["results"][0]
    assert result["source"] == "openai_api" and result["preset"] == "Sharp"

    providers.next["openai_api"] = (
        400,
        {"error": {"code": "moderation_blocked", "message": "Rejected by the safety system."}},
    )
    job = wait_for_job(client, generate(client, scene, confirm_charges=True)["active_job"]["id"])
    assert job["status"] == "failed" and job["error_kind"] == "blocked"
    providers.next["openai_api"] = (
        403,
        {"error": {"message": "Your organization must be verified to use the model."}},
    )
    job = wait_for_job(client, generate(client, scene, confirm_charges=True)["active_job"]["id"])
    assert job["error_kind"] == "key_problem" and "verif" in job["error_details"]
    assert KEY not in job["error_details"]
    # Nothing was retried: one request per click.
    assert len(providers.posts()) == 3


def test_a_reply_without_an_image_fails_and_a_saved_output_can_be_kept(client, providers):  # noqa: F811
    _ada, scene = approved_scene(client)
    save_key(client, "gemini_api")
    select_generation(client, "gemini_api")
    providers.next["gemini_api"] = (
        200,
        {
            "candidates": [
                {"content": {"parts": [{"text": "I can't make that."}]}, "finishReason": "STOP"}
            ]
        },
    )
    job = wait_for_job(client, generate(client, scene, confirm_charges=True)["active_job"]["id"])
    assert job["status"] == "failed" and job["error_kind"] == "no_image"
    assert "I can't make that." in job["error_details"] and not job["recoverable"]
    # An image the run saved in its own folder (for example before a crash) can be kept.
    (Path(job["job_folder"]) / "output.png").write_bytes(png())
    assert client.get(f"/api/jobs/{job['id']}").json()["recoverable"]
    found = client.post(f"/api/jobs/{job['id']}/recover", headers=authorization(client))
    assert found.status_code == 200 and found.json()["found"] == 1
    [result] = found.json()["scene"]["results"]
    assert result["recovered"] and result["source"] == "gemini_api"
    again = client.post(f"/api/jobs/{job['id']}/recover", headers=authorization(client))
    assert again.json()["found"] == 0
    providers.next["gemini_api"] = (
        200,
        {"candidates": [{"content": {"parts": []}, "finishReason": "IMAGE_SAFETY"}]},
    )
    job = wait_for_job(client, generate(client, scene, confirm_charges=True)["active_job"]["id"])
    assert job["error_kind"] == "blocked"


def test_api_generation_batches_need_confirmation_and_keep_their_engine(client, providers):  # noqa: F811
    _ada, scene = approved_scene(client)
    save_key(client, "gemini_api")
    select_generation(client, "gemini_api")
    items = {"items": [{"scene_id": scene["id"]}], "count": 2}
    refused = client.post("/api/batches/generation", headers=authorization(client), json=items)
    assert refused.status_code == 409 and "charged" in refused.json()["detail"]
    providers.next["gemini_api"] = (200, gemini_image_reply())
    started = client.post(
        "/api/batches/generation",
        headers=authorization(client),
        json={**items, "confirm_charges": True},
    )
    assert started.status_code == 202, started.text
    batch = started.json()["batch"]
    assert batch["engine"] == "gemini_api" and batch["settings"]["model"] == "img-model"
    for item in batch["items"]:
        job = wait_for_job(client, item["job_id"])
        assert job["status"] == "completed" and job["model"] == "img-model"
    assert len(client.get(f"/api/scenes/{scene['id']}").json()["results"]) == 2

    # A paused batch continues only with the engine (and charges) it was started with.
    providers.next["gemini_api"] = (429, {"error": {"message": "Quota exceeded."}})
    paused = client.post(
        "/api/batches/generation",
        headers=authorization(client),
        json={**items, "confirm_charges": True},
    ).json()["batch"]
    wait_for_job(client, paused["items"][0]["job_id"])
    state = client.get(f"/api/batches/{paused['id']}").json()
    assert state["status"] == "paused" and state["pause_kind"] == "usage_limit"
    select_generation(client, "manual", model=None)
    blocked = client.post(
        f"/api/batches/{paused['id']}/continue",
        headers=authorization(client),
        json={"confirm_charges": True},
    )
    assert blocked.status_code == 409 and "Gemini" in blocked.json()["detail"]
    path = f"/api/batches/{paused['id']}/continue"
    unconfirmed = client.post(path, headers=authorization(client))
    assert unconfirmed.status_code == 409 and "charged" in unconfirmed.json()["detail"]
