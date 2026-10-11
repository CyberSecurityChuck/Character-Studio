"""Optional API engines: the providers' official HTTPS APIs with the user's own keys.

Phase 6 (DECISIONS.md D022). Off until the user saves a key and selects the engine;
every run is started by the user after confirming that it may be charged, runs once
and is never retried. Only the official endpoints below are used, with Python's
standard HTTP client. Keys come from `backend.keystore` and are sent only to their own
provider, in a header; they are never written to job folders, logs or messages.
"""

import base64
import json
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

from backend.analysis_schema import (
    JSON_SCHEMA,
    MANUAL_INSTRUCTION,
    AnalysisFormatError,
    SceneAnalysisData,
    parse_analysis_text,
    validate_analysis,
)
from backend.configuration import Settings
from backend.engines import ENGINE_NAMES, EngineError
from backend.keystore import KeyStoreError, load_key

# Long edge of the copy sent for analysis. Subject boxes are relative (0–1), so the
# analysis is unchanged by scaling, and every provider accepts this size without resizing.
ANALYSIS_EDGE = 1568
ANTHROPIC_VERSION = "2023-06-01"
MAX_MODEL_NAME = 80
_MODEL_SHAPE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,79}$")


@dataclass(frozen=True)
class ApiEngine:
    id: str
    name: str
    company: str
    base_url: str
    key_help: str
    pricing_url: str
    # A suggestion only, verified on the provider's pricing page on 2026-10-11. The user
    # chooses the model; "Test key" lists what the key can use.
    suggested_model: str | None
    charge_note: str


API_ENGINES = {
    "gemini_api": ApiEngine(
        id="gemini_api",
        name="Gemini API",
        company="Google",
        base_url="https://generativelanguage.googleapis.com",
        key_help="Create a key in Google AI Studio (aistudio.google.com → Get API key).",
        pricing_url="https://ai.google.dev/gemini-api/docs/pricing",
        suggested_model="gemini-2.5-flash",
        charge_note="Free-tier keys are not charged for analysis with free models (Google "
        "may use free-tier content to improve its products). Keys on a billed project are "
        "charged per use.",
    ),
    "anthropic_api": ApiEngine(
        id="anthropic_api",
        name="Anthropic API",
        company="Anthropic",
        base_url="https://api.anthropic.com",
        key_help="Create a key in the Claude Console (console.anthropic.com → API keys). "
        "API use is billed separately from a Claude Pro plan.",
        pricing_url="https://docs.anthropic.com/en/docs/about-claude/pricing",
        suggested_model=None,
        charge_note="Every run is charged per use to your Anthropic API account.",
    ),
    "openai_api": ApiEngine(
        id="openai_api",
        name="OpenAI API",
        company="OpenAI",
        base_url="https://api.openai.com",
        key_help="Create a key at platform.openai.com → API keys. API use is billed "
        "separately from ChatGPT plans.",
        pricing_url="https://developers.openai.com/api/docs/pricing",
        suggested_model=None,
        charge_note="Every run is charged per use to your OpenAI API account.",
    ),
}


def is_api_engine(engine: str) -> bool:
    return engine in API_ENGINES


def engine_label(engine: str) -> str:
    if engine in API_ENGINES:
        return API_ENGINES[engine].name
    return ENGINE_NAMES.get(engine, "Manual")


def engine_timeout(row, engine: str) -> int:
    """The time limit for a run with this engine, from the saved engine settings."""
    if engine in API_ENGINES:
        return row.api_timeout
    return row.claude_timeout if engine == "claude_cli" else row.codex_timeout


def models_of(row) -> dict:
    try:
        value = json.loads(row.api_models_json or "{}")
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def chosen_model(row, engine: str, purpose: str = "analysis") -> str | None:
    model = (models_of(row).get(engine) or {}).get(purpose)
    return model if isinstance(model, str) and model else None


def charge_confirmation(engine: str) -> str:
    """Refusal text when an API run arrives without the user's cost confirmation."""
    return (
        f"Runs with the {API_ENGINES[engine].name} may be charged to your "
        f"{API_ENGINES[engine].company} account. Confirm the charge in the studio first."
    )


def check_model_name(model: str) -> str:
    model = model.strip()
    if not _MODEL_SHAPE.match(model):
        raise ValueError("Enter a model name such as the ones Test key lists.")
    return model


class ApiCancelled(Exception):
    """The user cancelled while the request was in flight."""


@dataclass
class ApiReply:
    status: int
    body: dict
    seconds: float


def _base(settings: Settings, engine: str) -> str:
    # Tests point engines at a local fake server; never read from the environment.
    return settings.api_base_urls.get(engine, API_ENGINES[engine].base_url).rstrip("/")


def _headers(engine: str, key: str) -> dict[str, str]:
    if engine == "gemini_api":
        return {"x-goog-api-key": key}
    if engine == "anthropic_api":
        return {"x-api-key": key, "anthropic-version": ANTHROPIC_VERSION}
    return {"Authorization": f"Bearer {key}"}


def _send(url: str, headers: dict, body: dict | None, timeout: float) -> ApiReply:
    started = time.monotonic()
    data = None if body is None else json.dumps(body).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        method="GET" if body is None else "POST",
        headers={**headers, "Content-Type": "application/json", "User-Agent": "CharacterStudio"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            status, raw = response.status, response.read()
    except urllib.error.HTTPError as error:
        status, raw = error.code, error.read()
    try:
        parsed = json.loads(raw.decode("utf-8", errors="replace") or "{}")
    except json.JSONDecodeError:
        parsed = {"_text": raw.decode("utf-8", errors="replace")[:500]}
    return ApiReply(status, parsed if isinstance(parsed, dict) else {}, time.monotonic() - started)


def _call(
    url: str,
    headers: dict,
    body: dict | None,
    timeout: float,
    company: str,
    should_stop: Callable[[], bool] = lambda: False,
) -> ApiReply:
    """Send once in a helper thread so Cancel and the time limit respond within a moment.

    A request already sent cannot be withdrawn: the provider may still finish and charge
    for it. Nothing is ever sent again automatically.
    """
    box: dict = {}

    def work():
        try:
            box["reply"] = _send(url, headers, body, timeout)
        except Exception as error:  # reported below without internals
            box["error"] = error

    thread = threading.Thread(target=work, name="api-request", daemon=True)
    started = time.monotonic()
    thread.start()
    while thread.is_alive():
        thread.join(timeout=0.25)
        if not thread.is_alive():
            break
        if should_stop():
            raise ApiCancelled()
        if time.monotonic() - started > timeout + 5:
            raise EngineError(
                "timeout",
                f"{company} did not answer in time, so the studio stopped waiting. The request "
                "may still finish on their side and be charged. Raise the time limit in Studio "
                "settings or try again later.",
            )
    if "error" in box:
        error = box["error"]
        if isinstance(error, TimeoutError) or "timed out" in str(error):
            raise EngineError(
                "timeout",
                f"{company} did not answer in time. The request may still finish on their "
                "side and be charged.",
            )
        raise EngineError(
            "network",
            f"The studio could not reach {company}. Check the internet connection and try "
            "again.",
        )
    return box["reply"]


def _message(body: dict) -> str:
    error = body.get("error")
    if isinstance(error, dict):
        return str(error.get("message") or error.get("status") or error.get("type") or "")
    if isinstance(error, str):
        return error
    return str(body.get("_text") or body.get("message") or "")


def _redact(text: str, key: str | None) -> str:
    if key:
        text = text.replace(key, "[key]")
    return text.strip()[:400] or "No details were given."


def classify(engine: str, reply: ApiReply, key: str | None) -> EngineError:
    """Turn an HTTP error into a message the user can act on. Never includes the key."""
    company = API_ENGINES[engine].company
    said = _redact(_message(reply.body), key)
    lowered = said.lower()
    status = reply.status
    if status in (401, 403) or "api key" in lowered or "api_key_invalid" in lowered:
        return EngineError(
            "key_problem",
            f"{company} did not accept the API key. Check or replace it in Studio settings. "
            f"{company} said: {said}",
        )
    if status == 429 or "quota" in lowered or "credit balance" in lowered or "billing" in lowered:
        return EngineError(
            "usage_limit",
            f"{company} reports a rate, quota or spending limit. Wait, check your "
            f"{company} account, or choose another engine. {company} said: {said}",
        )
    missing = "not found" in lowered or "does not exist" in lowered
    if status == 404 or ("model" in lowered and missing):
        return EngineError(
            "model_problem",
            f"{company} does not offer the selected model to this key. Use Test key in Studio "
            f"settings to choose another. {company} said: {said}",
        )
    if status >= 500:
        return EngineError(
            "engine_error",
            f"{company} had a temporary problem ({status}). Try again later. {company} said: "
            f"{said}",
        )
    return EngineError("engine_error", f"{company} reported an error ({status}): {said}")


def require_key(settings: Settings, engine: str) -> str:
    try:
        key = load_key(settings, engine)
    except KeyStoreError as error:
        raise EngineError("key_problem", str(error)) from error
    if not key:
        raise EngineError(
            "key_problem",
            f"No {API_ENGINES[engine].name} key is saved. Add one in Studio settings, or "
            "choose another engine.",
        )
    return key


# ---------------------------------------------------------------- models list


def _model_page(settings: Settings, engine: str, key: str, page: str | None) -> tuple[list, str]:
    base = _base(settings, engine)
    if engine == "gemini_api":
        query = {"pageSize": "1000", **({"pageToken": page} if page else {})}
        url = f"{base}/v1beta/models?{urllib.parse.urlencode(query)}"
    elif engine == "anthropic_api":
        query = {"limit": "1000", **({"after_id": page} if page else {})}
        url = f"{base}/v1/models?{urllib.parse.urlencode(query)}"
    else:
        url = f"{base}/v1/models"
    reply = _call(url, _headers(engine, key), None, 30, API_ENGINES[engine].company)
    if reply.status != 200:
        raise classify(engine, reply, key)
    if engine == "gemini_api":
        items = [
            str(m.get("name", "")).removeprefix("models/")
            for m in reply.body.get("models", [])
            if "generateContent" in (m.get("supportedGenerationMethods") or [])
        ]
        return items, str(reply.body.get("nextPageToken") or "")
    items = [str(m.get("id", "")) for m in reply.body.get("data", [])]
    more = engine == "anthropic_api" and reply.body.get("has_more")
    return items, str(reply.body.get("last_id") or "") if more else ""


_NOT_FOR_ANALYSIS = re.compile(
    r"embed|whisper|tts|dall-e|moderation|audio|realtime|transcribe|image|search|speech|"
    r"imagen|veo|lyria|aqa|robotics|computer-use|codex",
    re.IGNORECASE,
)


def list_models(settings: Settings, engine: str) -> list[str]:
    """Check the key with the provider's free model-list call and return usable models."""
    key = require_key(settings, engine)
    found, page = [], None
    for _ in range(5):
        items, page = _model_page(settings, engine, key, page)
        found.extend(items)
        if not page:
            break
    usable = {
        m for m in found if m and len(m) <= MAX_MODEL_NAME and not _NOT_FOR_ANALYSIS.search(m)
    }
    return sorted(usable)


# ---------------------------------------------------------------- analysis


def analysis_image(job_dir: Path) -> bytes:
    """A smaller copy of the job's metadata-free base.jpg, kept in the job folder."""
    target = job_dir / "api-image.jpg"
    with Image.open(job_dir / "base.jpg") as source:
        image = source.convert("RGB")
        image.thumbnail((ANALYSIS_EDGE, ANALYSIS_EDGE))
        image.save(target, "JPEG", quality=90)
    return target.read_bytes()


def analysis_request(settings: Settings, engine: str, model: str, image: bytes):
    """Return (url, body) for one analysis request. The instruction includes the schema."""
    data = base64.b64encode(image).decode("ascii")
    base = _base(settings, engine)
    if engine == "gemini_api":
        url = f"{base}/v1beta/models/{urllib.parse.quote(model, safe='-._')}:generateContent"
        return url, {
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {"text": MANUAL_INSTRUCTION},
                        {"inline_data": {"mime_type": "image/jpeg", "data": data}},
                    ],
                }
            ],
            "generationConfig": {"responseMimeType": "application/json"},
        }
    if engine == "anthropic_api":
        # A forced tool call returns the analysis as a JSON object, checked against the schema.
        return f"{base}/v1/messages", {
            "model": model,
            "max_tokens": 8192,
            "tools": [
                {
                    "name": "save_scene_analysis",
                    "description": "Save the scene analysis in the studio format.",
                    "input_schema": JSON_SCHEMA,
                }
            ],
            "tool_choice": {"type": "tool", "name": "save_scene_analysis"},
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {"type": "base64", "media_type": "image/jpeg", "data": data},
                        },
                        {"type": "text", "text": MANUAL_INSTRUCTION},
                    ],
                }
            ],
        }
    return f"{base}/v1/chat/completions", {
        "model": model,
        "response_format": {"type": "json_object"},
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": MANUAL_INSTRUCTION},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{data}"}},
                ],
            }
        ],
    }


def _blocked(company: str, reason: str) -> EngineError:
    return EngineError(
        "blocked", f"{company} declined to analyse this image ({reason}). Nothing was saved."
    )


def _cut_off(company: str) -> EngineError:
    return EngineError(
        "invalid_output", f"{company}'s reply was cut off before the analysis was complete."
    )


def read_analysis_reply(engine: str, body: dict) -> tuple[object, dict]:
    """Return (analysis JSON object or text, token usage) from a successful reply."""
    company = API_ENGINES[engine].company
    if engine == "gemini_api":
        feedback = body.get("promptFeedback") or {}
        if feedback.get("blockReason"):
            raise _blocked(company, str(feedback["blockReason"]))
        candidates = body.get("candidates") or []
        if not candidates:
            raise EngineError("invalid_output", f"{company} replied without an analysis.")
        candidate = candidates[0]
        finish = str(candidate.get("finishReason") or "")
        if finish in ("SAFETY", "PROHIBITED_CONTENT", "BLOCKLIST", "IMAGE_SAFETY"):
            raise _blocked(company, finish.lower().replace("_", " "))
        if finish == "MAX_TOKENS":
            raise _cut_off(company)
        parts = (candidate.get("content") or {}).get("parts") or []
        text = "".join(str(p.get("text", "")) for p in parts if not p.get("thought"))
        meta = body.get("usageMetadata") or {}
        usage = {
            "input_tokens": meta.get("promptTokenCount"),
            "output_tokens": (meta.get("candidatesTokenCount") or 0)
            + (meta.get("thoughtsTokenCount") or 0),
        }
        return text, usage
    if engine == "anthropic_api":
        if body.get("stop_reason") == "refusal":
            raise _blocked(company, "refusal")
        if body.get("stop_reason") == "max_tokens":
            raise _cut_off(company)
        meta = body.get("usage") or {}
        usage = {
            "input_tokens": meta.get("input_tokens"),
            "output_tokens": meta.get("output_tokens"),
        }
        for block in body.get("content") or []:
            if block.get("type") == "tool_use" and isinstance(block.get("input"), dict):
                return block["input"], usage
        text = "".join(str(b.get("text", "")) for b in body.get("content") or [])
        return text, usage
    choices = body.get("choices") or []
    if not choices:
        raise EngineError("invalid_output", f"{company} replied without an analysis.")
    message = choices[0].get("message") or {}
    if message.get("refusal"):
        raise _blocked(company, "refusal")
    if choices[0].get("finish_reason") == "length":
        raise _cut_off(company)
    meta = body.get("usage") or {}
    usage = {
        "input_tokens": meta.get("prompt_tokens"),
        "output_tokens": meta.get("completion_tokens"),
    }
    return str(message.get("content") or ""), usage


def _summary(url: str, model: str, engine: str, image_bytes: int) -> dict:
    """What was sent, for the job folder: no key, no image data."""
    return {
        "engine": engine,
        "company": API_ENGINES[engine].company,
        "url": url,
        "model": model,
        "image": f"api-image.jpg ({image_bytes} bytes, location data removed)",
        "instruction": "instruction.txt",
    }


def run_analysis(
    settings: Settings,
    engine: str,
    model: str,
    job_dir: Path,
    timeout: float,
    should_stop: Callable[[], bool],
) -> tuple[SceneAnalysisData, dict]:
    """One analysis request; returns the validated analysis and the reported usage."""
    company = API_ENGINES[engine].company
    key = require_key(settings, engine)
    image = analysis_image(job_dir)
    url, body = analysis_request(settings, engine, model, image)
    (job_dir / "request.json").write_text(
        json.dumps(_summary(url, model, engine, len(image)), indent=2), encoding="utf-8"
    )
    if should_stop():
        raise ApiCancelled()
    reply = _call(url, _headers(engine, key), body, timeout, company, should_stop)
    (job_dir / "response.json").write_text(
        json.dumps(reply.body, indent=2).replace(key, "[key]"), encoding="utf-8"
    )
    if reply.status != 200:
        raise classify(engine, reply, key)
    value, usage = read_analysis_reply(engine, reply.body)
    usage = {"model": model, **usage, "seconds": round(reply.seconds, 1)}
    try:
        data = validate_analysis(value) if isinstance(value, dict) else parse_analysis_text(value)
    except AnalysisFormatError as error:
        detail = str(error)
        raise EngineError(
            "invalid_output", f"{company} replied, but {detail[:1].lower()}{detail[1:]}"
        ) from error
    return data, usage
