"""Phase 6A: API analysis engines against a local fake of the three providers' APIs."""

import base64
import json
import threading
import time
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.backup import restore_backup
from backend.configuration import Settings
from backend.keystore import load_key
from backend.main import create_app
from tests.conftest import ANALYSIS, authorization, wait_for_job
from tests.test_backup import make_backup
from tests.test_scenes import create_scene

KEY = "test-key-0123456789-abcdefgh"
ENGINES = ("gemini_api", "anthropic_api", "openai_api")


def reply_for(engine: str, analysis: dict) -> dict:
    text = json.dumps(analysis)
    if engine == "gemini_api":
        return {
            "candidates": [{"content": {"parts": [{"text": text}]}, "finishReason": "STOP"}],
            "usageMetadata": {"promptTokenCount": 1290, "candidatesTokenCount": 850},
        }
    if engine == "anthropic_api":
        return {
            "content": [{"type": "tool_use", "name": "save_scene_analysis", "input": analysis}],
            "stop_reason": "tool_use",
            "usage": {"input_tokens": 1600, "output_tokens": 900},
        }
    return {
        "choices": [{"message": {"content": text}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 1100, "completion_tokens": 800},
    }


MODEL_LISTS = {
    "gemini": {
        "models": [
            {"name": "models/gemini-2.5-flash", "supportedGenerationMethods": ["generateContent"]},
            {
                "name": "models/gemini-nano-banana-2.1",
                "supportedGenerationMethods": ["generateContent"],
            },
            {"name": "models/text-embedding-004", "supportedGenerationMethods": ["embedContent"]},
        ]
    },
    "anthropic": {"data": [{"id": "claude-test-1"}], "has_more": False},
    "openai": {
        "data": [
            {"id": "gpt-test-vision"},
            {"id": "whisper-1"},
            {"id": "tts-1"},
            {"id": "gpt-image-2.5-sunburst"},
        ]
    },
}


def multipart(raw: bytes, content_type: str) -> dict:
    """Fields and files of a multipart form, as the fake OpenAI image endpoint sees them."""
    boundary = content_type.split("boundary=")[1].encode()
    fields, files = {}, []
    for part in raw.split(b"--" + boundary)[1:-1]:
        # Each part sits between CRLF pairs; its headers end at the first blank line.
        head, _, data = part[2:-2].partition(b"\r\n\r\n")
        disposition = head.decode().split("\r\n")[0]
        name = disposition.split('name="')[1].split('"')[0]
        if "filename=" in disposition:
            files.append({"name": name, "bytes": data})
        else:
            fields[name] = data.decode("utf-8")
    return {"multipart": True, "fields": fields, "files": files}


class FakeProviders:
    """One local server; /gemini, /anthropic and /openai stand in for the three APIs."""

    def __init__(self):
        self.requests: list[dict] = []
        self.next: dict[str, tuple[int, dict]] = {}
        self.delay = 0.0
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def _answer(self, body: dict | None):
                prefix = self.path.split("/")[1]
                engine = {"gemini": "gemini_api", "anthropic": "anthropic_api"}.get(
                    prefix, "openai_api"
                )
                fake.requests.append(
                    {
                        "engine": engine,
                        "path": self.path,
                        "headers": {k.lower(): v for k, v in self.headers.items()},
                        "body": body,
                    }
                )
                if body is None:
                    status, payload = 200, MODEL_LISTS[prefix]
                else:
                    time.sleep(fake.delay)
                    status, payload = fake.next.get(engine, (200, reply_for(engine, ANALYSIS)))
                data = json.dumps(payload).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self):
                self._answer(None)

            def do_POST(self):
                length = int(self.headers.get("Content-Length", 0))
                raw = self.rfile.read(length)
                kind = self.headers.get("Content-Type", "")
                form = kind.startswith("multipart/")
                self._answer(multipart(raw, kind) if form else json.loads(raw))

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        port = self.server.server_address[1]
        self.urls = {
            "gemini_api": f"http://127.0.0.1:{port}/gemini",
            "anthropic_api": f"http://127.0.0.1:{port}/anthropic",
            "openai_api": f"http://127.0.0.1:{port}/openai",
        }

    def posts(self):
        return [r for r in self.requests if r["body"] is not None]

    def close(self):
        self.server.shutdown()


@pytest.fixture
def providers():
    fake = FakeProviders()
    yield fake
    fake.close()


@pytest.fixture
def api_settings(tmp_path, providers):
    return Settings(
        data_dir=tmp_path / "private-data",
        frontend_dir=tmp_path / "no-build",
        api_base_urls=providers.urls,
    )


@pytest.fixture
def api_client(api_settings):
    with TestClient(create_app(api_settings), base_url="http://127.0.0.1:8765") as client:
        yield client


def save_key(client, engine, key=KEY):
    result = client.put(
        f"/api/api-engines/{engine}/key", headers=authorization(client), json={"key": key}
    )
    assert result.status_code == 200, result.text
    return result.json()


def select_api(client, engine, model="test-model", **changes):
    current = client.get("/api/engines/settings").json()
    body = {
        **current,
        "analysis_engine": engine,
        "models": {engine: {"analysis": model}},
        **changes,
    }
    return client.put("/api/engines/settings", headers=authorization(client), json=body)


def analyse(client, scene, confirm=True):
    return client.post(
        f"/api/scenes/{scene['id']}/analyse",
        headers=authorization(client),
        json={"confirm_charges": confirm},
    )


def test_keys_are_protected_write_only_and_kept_out_of_backups(api_settings):
    with TestClient(create_app(api_settings), base_url="http://127.0.0.1:8765") as client:
        archive = _save_and_back_up(client, api_settings)
    # Saved keys stay with this PC's data folder when a backup is restored.
    restored, _previous = restore_backup(archive, api_settings.data_dir)
    assert load_key(api_settings, "gemini_api") == KEY and (restored / "keys").is_dir()


def _save_and_back_up(client, api_settings):
    listed = {e["id"]: e for e in client.get("/api/api-engines").json()}
    assert set(listed) == set(ENGINES)
    assert listed["gemini_api"]["suggested_model"] == "gemini-2.5-flash"
    assert listed["gemini_api"]["key"] == {"saved": False, "saved_at": None}
    assert client.get("/api/bootstrap").json()["paid_operations_enabled"] is False

    bad = client.put(
        "/api/api-engines/gemini_api/key", headers=authorization(client), json={"key": "a b"}
    )
    assert bad.status_code == 422
    saved = save_key(client, "gemini_api")
    assert saved["key"]["saved"] is True and KEY not in json.dumps(saved)
    assert client.get("/api/bootstrap").json()["paid_operations_enabled"] is True

    stored = api_settings.data_dir / "keys" / "gemini_api.key"
    assert stored.is_file() and KEY.encode() not in stored.read_bytes()
    assert load_key(api_settings, "gemini_api") == KEY
    for path in ("/api/api-engines", "/api/engines/settings", "/api/bootstrap"):
        assert KEY not in client.get(path).text
    assert client.put(
        "/api/api-engines/unknown/key", headers=authorization(client), json={"key": KEY}
    ).status_code == 404

    state = make_backup(client)
    archive = api_settings.data_dir / "backups" / state["items"][0]["name"]
    with zipfile.ZipFile(archive) as zipped:
        assert not any(name.startswith("keys/") for name in zipped.namelist())
    return archive


def test_test_key_lists_usable_models_without_generating(api_client, providers):
    client = api_client
    missing = client.post("/api/api-engines/openai_api/models", headers=authorization(client))
    assert missing.status_code == 409 and "No OpenAI API key" in missing.json()["detail"]
    for engine, expected in (
        ("gemini_api", ["gemini-2.5-flash"]),
        ("anthropic_api", ["claude-test-1"]),
        ("openai_api", ["gpt-test-vision"]),
    ):
        # Saving a key fetches its model list once, and the list stays saved.
        saved = save_key(client, engine)
        assert saved["models"] == expected and saved["models_error"] is None
        listed = {e["id"]: e for e in client.get("/api/api-engines").json()}
        assert listed[engine]["models"] == expected and listed[engine]["models_checked_at"]
        result = client.post(f"/api/api-engines/{engine}/models", headers=authorization(client))
        assert result.json()["models"] == expected
    assert providers.posts() == []
    removed = client.delete("/api/api-engines/openai_api/key", headers=authorization(client))
    assert removed.json()["models"] == []
    headers = {r["engine"]: r["headers"] for r in providers.requests}
    assert headers["gemini_api"]["x-goog-api-key"] == KEY
    assert headers["anthropic_api"]["x-api-key"] == KEY
    assert headers["openai_api"]["authorization"] == f"Bearer {KEY}"


def test_selecting_an_api_engine_needs_a_model_and_a_key(api_client):
    client = api_client
    assert select_api(client, "gemini_api").status_code == 422  # no key yet
    save_key(client, "gemini_api")
    assert select_api(client, "gemini_api", model="").status_code == 422
    assert select_api(client, "gemini_api", model="bad model!").status_code == 422
    result = select_api(client, "gemini_api", model="gemini-2.5-flash", api_timeout=240)
    assert result.status_code == 200, result.text
    assert result.json()["models"] == {"gemini_api": {"analysis": "gemini-2.5-flash"}}
    assert result.json()["api_timeout"] == 240
    # The selected engine's key cannot be removed until another engine is chosen.
    assert client.delete(
        "/api/api-engines/gemini_api/key", headers=authorization(client)
    ).status_code == 409


@pytest.mark.parametrize("engine", ENGINES)
def test_api_analysis_needs_confirmation_and_records_provenance(
    api_client, api_settings, providers, engine
):
    client = api_client
    save_key(client, engine)
    assert select_api(client, engine).status_code == 200
    scene = create_scene(client)
    refused = analyse(client, scene, confirm=False)
    assert refused.status_code == 409 and "charged" in refused.json()["detail"]
    assert client.post(
        f"/api/scenes/{scene['id']}/analyse", headers=authorization(client)
    ).status_code == 409
    assert providers.posts() == []

    detail = analyse(client, scene).json()
    job = wait_for_job(client, detail["active_job"]["id"])
    assert job["status"] == "completed", job
    assert job["engine_version"] == "test-model" and job["model"] == "test-model"
    assert job["usage"]["input_tokens"] > 0 and job["usage"]["output_tokens"] > 0
    analysis = client.get(f"/api/scenes/{scene['id']}").json()["analyses"][0]
    assert analysis["source"] == engine
    assert analysis["analysis"]["subjects"][0]["label"] == "Subject 1"
    listed = {e["id"]: e for e in client.get("/api/api-engines").json()}
    assert listed[engine]["typical_usage"]["runs"] == 1

    [sent] = providers.posts()
    body = json.dumps(sent["body"])
    assert "Subject 1" in body  # the instruction with the studio's schema
    assert "Ada" not in body
    image = (
        sent["body"]["contents"][0]["parts"][2]["inline_data"]["data"]
        if engine == "gemini_api"
        else sent["body"]["messages"][0]["content"][1]["source"]["data"]
        if engine == "anthropic_api"
        else sent["body"]["messages"][0]["content"][2]["image_url"]["url"].split(",")[1]
    )
    assert base64.b64decode(image)[:2] == b"\xff\xd8"  # a JPEG copy
    folder = Path(job["job_folder"])
    assert folder.is_relative_to(api_settings.data_dir)
    for name in ("request.json", "response.json", "api-base.jpg", "base.jpg"):
        assert (folder / name).is_file()
    for name in ("request.json", "response.json"):
        assert KEY not in (folder / name).read_text(encoding="utf-8")


@pytest.mark.parametrize(
    ("status", "payload", "kind"),
    [
        (401, {"error": {"message": "invalid x-api-key"}}, "key_problem"),
        (400, {"error": {"message": "API key not valid.", "status": "X"}}, "key_problem"),
        (429, {"error": {"message": "Resource has been exhausted."}}, "usage_limit"),
        (404, {"error": {"message": "models/test-model is not found"}}, "model_problem"),
        (503, {"error": {"message": "The model is overloaded."}}, "engine_error"),
        (200, {"promptFeedback": {"blockReason": "SAFETY"}}, "blocked"),
        (200, {"candidates": [{"content": {"parts": [{"text": "{}"}]}}]}, "invalid_output"),
    ],
)
def test_api_failures_are_explained_once_and_never_retried(
    api_client, providers, status, payload, kind
):
    client = api_client
    save_key(client, "gemini_api")
    select_api(client, "gemini_api")
    providers.next["gemini_api"] = (status, {**payload, "echo": KEY})
    scene = create_scene(client)
    job = wait_for_job(client, analyse(client, scene).json()["active_job"]["id"])
    assert (job["status"], job["error_kind"]) == ("failed", kind), job
    assert KEY not in job["error_details"]
    time.sleep(0.3)
    assert len(providers.posts()) == 1


def test_cancel_stops_waiting_and_says_a_charge_is_possible(api_client, providers):
    client = api_client
    save_key(client, "openai_api")
    select_api(client, "openai_api")
    providers.delay = 3
    scene = create_scene(client)
    job_id = analyse(client, scene).json()["active_job"]["id"]
    deadline = time.monotonic() + 10
    while not providers.posts() and time.monotonic() < deadline:
        time.sleep(0.05)
    client.post(f"/api/jobs/{job_id}/cancel", headers=authorization(client))
    job = wait_for_job(client, job_id, timeout=5)
    assert job["status"] == "cancelled" and "may still finish there" in job["error_details"]
    assert client.get(f"/api/scenes/{scene['id']}").json()["analyses"] == []


def test_api_batches_confirm_charges_and_pause_on_spending_limits(api_client, providers):
    client = api_client
    save_key(client, "anthropic_api")
    select_api(client, "anthropic_api")
    scenes = [create_scene(client, title=f"Scene {n}") for n in range(3)]
    ids = [s["id"] for s in scenes]
    headers = authorization(client)
    refused = client.post("/api/batches/analysis", headers=headers, json={"scene_ids": ids})
    assert refused.status_code == 409
    providers.next["anthropic_api"] = (
        400,
        {"type": "error", "error": {"type": "invalid_request_error", "message": "Your credit "
         "balance is too low to access the Anthropic API."}},
    )
    started = client.post(
        "/api/batches/analysis", headers=headers, json={"scene_ids": ids, "confirm_charges": True}
    ).json()["batch"]
    assert started["engine_name"] == "Anthropic API"
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        batch = client.get(f"/api/batches/{started['id']}").json()
        if batch["state"] == "paused":
            break
        time.sleep(0.1)
    assert batch["pause_kind"] == "usage_limit" and batch["counts"]["not_started"] == 2
    assert len(providers.posts()) == 1
    del providers.next["anthropic_api"]
    url = f"/api/batches/{started['id']}/continue"
    assert client.post(url, headers=headers).status_code == 409
    assert client.post(url, headers=headers, json={"confirm_charges": True}).status_code == 200
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        batch = client.get(f"/api/batches/{started['id']}").json()
        if batch["state"] == "finished":
            break
        time.sleep(0.1)
    assert batch["counts"]["completed"] == 2 and batch["counts"]["failed"] == 1
    retry = f"/api/batches/{started['id']}/retry"
    assert client.post(retry, headers=headers).status_code == 409
    assert client.post(retry, headers=headers, json={"confirm_charges": True}).status_code == 202
    jobs = [j for s in ids for j in client.get(f"/api/scenes/{s}").json()["jobs"]]
    assert {j["model"] for j in jobs} == {"test-model"}
