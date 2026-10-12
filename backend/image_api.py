"""API image engines: OpenAI Images and Gemini image models with the user's own keys.

Phase 6C-1 (DECISIONS.md D025). They reuse the Phase 6A key, call and error handling in
`backend.api_engines`: off until the user saves a key and selects the engine, every run
confirmed as possibly charged, sent once and never retried. A generation sends exactly
the approved package (the Base Image and the approved reference photos, metadata-free)
with the approved prompt, the same images Codex receives.

Facts re-checked on 2026-10-12 (docs/PROVIDER_FINDINGS.md): OpenAI `POST /v1/images/edits`
takes several `image[]` files as multipart form data and returns base64 images; Gemini
image models answer `generateContent` with `responseModalities` and `imageConfig` and
return the image as inline data.
"""

import base64
import json
import math
import urllib.parse
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from PIL import Image

from backend.api_engines import (
    API_ENGINES,
    ApiCancelled,
    RawBody,
    _base,
    _call,
    _headers,
    _message,
    _redact,
    classify,
    engine_label,
    require_key,
)
from backend.configuration import Settings
from backend.engines import EngineError

# Long edge of the copies sent to an image API. Large enough for likeness, small enough
# for every provider's request limit (Gemini inline requests stay well under 20 MB).
SEND_EDGE = 2048
MAX_IMAGE_BYTES = 60 * 1024 * 1024
SIZES = ("1K", "2K", "4K")
QUALITIES = ("low", "medium", "high", "xhigh", "max")
# Gemini's documented aspect ratios that every current image model accepts.
GEMINI_RATIOS = ("1:1", "2:3", "3:2", "3:4", "4:3", "4:5", "5:4", "9:16", "16:9", "21:9")
# Target pixel counts for OpenAI sizes: 1K is 1024 x 1024; 2K stays at 2560 x 1440 or
# fewer pixels, the largest size OpenAI does not call experimental.
OPENAI_PIXELS = {"1K": 1024 * 1024, "2K": 2560 * 1440}
_BLOCKED_FINISH = (
    "SAFETY",
    "IMAGE_SAFETY",
    "PROHIBITED_CONTENT",
    "IMAGE_PROHIBITED_CONTENT",
    "BLOCKLIST",
    "RECITATION",
    "IMAGE_RECITATION",
)
_EXTENSIONS = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp"}


@dataclass(frozen=True)
class ImageEngine:
    id: str
    name: str
    sizes: tuple[str, ...]
    # Quality levels the provider documents; empty when it offers none.
    qualities: tuple[str, ...]
    # A suggestion only, from the provider's documentation on 2026-10-12.
    suggested_model: str
    charge_note: str


IMAGE_ENGINES = {
    "gemini_api": ImageEngine(
        id="gemini_api",
        name="Gemini image",
        sizes=SIZES,
        qualities=(),
        suggested_model="gemini-nano-banana-2.1",
        charge_note="Image models are not on Google's free tier: generating needs a key on a "
        "billed project and is charged per image. Google adds an invisible SynthID watermark "
        "to every image.",
    ),
    "openai_api": ImageEngine(
        id="openai_api",
        name="OpenAI Images",
        sizes=("1K", "2K"),
        qualities=QUALITIES,
        suggested_model="gpt-image-2.5-sunburst",
        charge_note="Charged per use to your OpenAI API account (image tokens; higher quality "
        "and larger sizes cost more). OpenAI asks organisations to verify themselves before "
        "their image models can be used.",
    ),
}
DEFAULT_OPTIONS = {"size": "1K", "quality": "medium"}


def is_image_engine(engine: str) -> bool:
    return engine in IMAGE_ENGINES


def run_label(engine: str, kind: str) -> str:
    """The engine's name for a run: image runs use the image engine's own name."""
    if kind == "generation" and engine in IMAGE_ENGINES:
        return IMAGE_ENGINES[engine].name
    return engine_label(engine)


def image_options_of(row) -> dict:
    """Saved size and quality per image engine: {"openai_api": {"size", "quality"}}."""
    try:
        value = json.loads(row.image_options_json or "{}")
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def options_for(row, engine: str, preset: dict | None = None) -> dict:
    """The size and quality a run uses: the preset's choice, else Studio settings."""
    item = IMAGE_ENGINES[engine]
    saved = image_options_of(row).get(engine) or {}
    preset = preset or {}
    size = preset.get("image_size") or saved.get("size") or DEFAULT_OPTIONS["size"]
    if size not in item.sizes:
        size = item.sizes[-1] if size in SIZES else DEFAULT_OPTIONS["size"]
    options = {"size": size}
    if item.qualities:
        quality = preset.get("image_quality") or saved.get("quality") or DEFAULT_OPTIONS["quality"]
        options["quality"] = quality if quality in item.qualities else DEFAULT_OPTIONS["quality"]
    return options


def openai_size(width: int, height: int, size: str) -> str:
    """WIDTHxHEIGHT with the Base Image's shape within OpenAI's documented limits."""
    # Both target pixel counts keep a 3:1 image under the 3840 px edge limit.
    ratio = min(max(width / height, 1 / 3), 3)
    pixels = OPENAI_PIXELS.get(size, OPENAI_PIXELS["1K"])
    w = round(math.sqrt(pixels * ratio) / 16) * 16
    h = round(math.sqrt(pixels / ratio) / 16) * 16
    # Rounding to multiples of 16 must not push the shape past 3:1.
    while w > 3 * h:
        h += 16
    while h > 3 * w:
        w += 16
    return f"{w}x{h}"


def gemini_ratio(width: int, height: int) -> str:
    """The documented aspect ratio closest to the Base Image's shape."""
    target = math.log(width / height)

    def distance(ratio: str) -> float:
        a, b = ratio.split(":")
        return abs(math.log(int(a) / int(b)) - target)

    return min(GEMINI_RATIOS, key=distance)


def send_copies(job_dir: Path, files: list[Path]) -> list[bytes]:
    """`api-image-N.jpg` copies (long edge at most SEND_EDGE) of the package's images."""
    payloads = []
    for path in files:
        target = job_dir / f"api-{path.name}"
        with Image.open(path) as source:
            image = source.convert("RGB")
            image.thumbnail((SEND_EDGE, SEND_EDGE))
            image.save(target, "JPEG", quality=92)
        payloads.append(target.read_bytes())
    return payloads


def _multipart(fields: list[tuple[str, str]], files: list[tuple]) -> RawBody:
    """Form fields and files (name, filename, data[, content type]; JPEG by default)."""
    boundary = uuid4().hex
    chunks = []
    for name, value in fields:
        chunks.append(
            f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n'.encode()
            + value.encode("utf-8")
            + b"\r\n"
        )
    for name, filename, data, *kind in files:
        media = kind[0] if kind else "image/jpeg"
        chunks.append(
            (
                f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"; '
                f'filename="{filename}"\r\nContent-Type: {media}\r\n\r\n'
            ).encode()
            + data
            + b"\r\n"
        )
    chunks.append(f"--{boundary}--\r\n".encode())
    return RawBody(b"".join(chunks), f"multipart/form-data; boundary={boundary}")


def image_request(
    settings: Settings,
    engine: str,
    model: str,
    images: list[bytes],
    instruction: str,
    options: dict,
    base_size: tuple[int, int],
) -> tuple[str, dict | RawBody, dict]:
    """Return (url, body, what was asked for). Image 1 is always the Base Image."""
    base = _base(settings, engine)
    if engine == "gemini_api":
        ratio = gemini_ratio(*base_size)
        parts = [{"text": instruction}]
        for number, data in enumerate(images, 1):
            parts += [
                {"text": f"Image {number}:"},
                {
                    "inline_data": {
                        "mime_type": "image/jpeg",
                        "data": base64.b64encode(data).decode("ascii"),
                    }
                },
            ]
        body = {
            "contents": [{"role": "user", "parts": parts}],
            "generationConfig": {
                "responseModalities": ["TEXT", "IMAGE"],
                "imageConfig": {"aspectRatio": ratio, "imageSize": options["size"]},
            },
        }
        url = f"{base}/v1beta/models/{urllib.parse.quote(model, safe='-._')}:generateContent"
        return url, body, {"aspect_ratio": ratio, "image_size": options["size"]}
    size = openai_size(*base_size, options["size"])
    fields = [
        ("model", model),
        ("prompt", instruction),
        ("n", "1"),
        ("size", size),
        ("quality", options.get("quality", DEFAULT_OPTIONS["quality"])),
        ("output_format", "png"),
    ]
    files = [("image[]", f"image-{n}.jpg", data) for n, data in enumerate(images, 1)]
    asked = {"size": size, "quality": options.get("quality")}
    return f"{base}/v1/images/edits", _multipart(fields, files), asked


def _blocked(company: str, reason: str) -> EngineError:
    return EngineError(
        "blocked", f"{company} declined to make this image ({reason}). Nothing was saved."
    )


def openai_error(reply, key: str) -> EngineError:
    """OpenAI's image-specific refusals first, then the shared classification."""
    error = reply.body.get("error") if isinstance(reply.body.get("error"), dict) else {}
    said = _redact(_message(reply.body), key)
    if error.get("code") == "moderation_blocked":
        return _blocked("OpenAI", f"its content rules. OpenAI said: {said}")
    if "verif" in said.lower() and "organi" in said.lower():
        return EngineError(
            "key_problem",
            "OpenAI asks your organisation to be verified before its image models can be used. "
            f"Verify it at platform.openai.com, then try again. OpenAI said: {said}",
        )
    return classify("openai_api", reply, key)


def read_image_reply(engine: str, body: dict) -> tuple[bytes, str, dict, str]:
    """Return (image bytes, media type, token usage, text the model added)."""
    company = API_ENGINES[engine].company
    if engine == "gemini_api":
        feedback = body.get("promptFeedback") or {}
        if feedback.get("blockReason"):
            raise _blocked(company, str(feedback["blockReason"]).lower().replace("_", " "))
        candidates = body.get("candidates") or []
        if not candidates:
            raise EngineError("no_image", f"{company} replied without an image.")
        candidate = candidates[0]
        finish = str(candidate.get("finishReason") or "")
        if finish in _BLOCKED_FINISH:
            raise _blocked(company, finish.lower().replace("_", " "))
        parts = (candidate.get("content") or {}).get("parts") or []
        text = " ".join(
            str(p.get("text", "")).strip() for p in parts if p.get("text") and not p.get("thought")
        )
        found = [
            p.get("inlineData") or p.get("inline_data")
            for p in parts
            if not p.get("thought") and (p.get("inlineData") or p.get("inline_data"))
        ]
        meta = body.get("usageMetadata") or {}
        usage = {
            "input_tokens": meta.get("promptTokenCount"),
            "output_tokens": (meta.get("candidatesTokenCount") or 0)
            + (meta.get("thoughtsTokenCount") or 0),
        }
        if not found:
            said = f" {company} said: {text[:400]}" if text else ""
            raise EngineError(
                "no_image", f"{company} finished without producing an image.{said}"
            )
        image = found[-1]
        media = str(image.get("mimeType") or image.get("mime_type") or "image/png")
        return _decode(company, image.get("data")), media, usage, text
    items = body.get("data") or []
    if not items or not items[0].get("b64_json"):
        raise EngineError("no_image", f"{company} replied without an image.")
    meta = body.get("usage") or {}
    usage = {"input_tokens": meta.get("input_tokens"), "output_tokens": meta.get("output_tokens")}
    media = f"image/{body.get('output_format') or 'png'}".replace("jpg", "jpeg")
    return _decode(company, items[0]["b64_json"]), media, usage, ""


def _decode(company: str, data) -> bytes:
    try:
        payload = base64.b64decode(str(data or ""), validate=True)
    except ValueError as error:
        raise EngineError(
            "invalid_output", f"{company} sent an image that could not be read."
        ) from error
    if not payload:
        raise EngineError("invalid_output", f"{company} sent an empty image.")
    if len(payload) > MAX_IMAGE_BYTES:
        raise EngineError("invalid_output", f"{company} sent an image that is too large.")
    return payload


def _without_image_data(engine: str, body: dict) -> dict:
    """The reply as saved in the job folder: image data replaced by a short note."""
    copy = json.loads(json.dumps(body))
    if engine == "gemini_api":
        for candidate in copy.get("candidates") or []:
            for part in (candidate.get("content") or {}).get("parts") or []:
                for name in ("inlineData", "inline_data"):
                    if isinstance(part.get(name), dict) and "data" in part[name]:
                        part[name]["data"] = f"<{len(str(part[name]['data']))} characters>"
    else:
        for item in copy.get("data") or []:
            if "b64_json" in item:
                item["b64_json"] = f"<{len(str(item['b64_json']))} characters>"
    return copy


def run_image(
    settings: Settings,
    engine: str,
    model: str,
    job_dir: Path,
    files: list[Path],
    instruction: str,
    options: dict,
    timeout: float,
    should_stop: Callable[[], bool],
) -> tuple[Path, dict]:
    """One image request. Saves the image as `output.<ext>` in the job folder first, so it
    can still be kept if the studio stops before storing it, and returns (file, usage)."""
    key = require_key(settings, engine)
    company = API_ENGINES[engine].company
    with Image.open(files[0]) as base:
        base_size = base.size
    images = send_copies(job_dir, files)
    url, body, asked = image_request(
        settings, engine, model, images, instruction, options, base_size
    )
    summary = {
        "engine": engine,
        "company": company,
        "url": url,
        "model": model,
        "asked_for": asked,
        "images": [
            f"Image {n}: api-{path.name} ({len(data)} bytes, location data removed)"
            for n, (path, data) in enumerate(zip(files, images, strict=True), 1)
        ],
        "instruction": "instruction.txt",
    }
    (job_dir / "request.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    if should_stop():
        raise ApiCancelled()
    reply = _call(url, _headers(engine, key), body, timeout, company, should_stop)
    (job_dir / "response.json").write_text(
        json.dumps(_without_image_data(engine, reply.body), indent=2).replace(key, "[key]"),
        encoding="utf-8",
    )
    if reply.status != 200:
        raise openai_error(reply, key) if engine == "openai_api" else classify(engine, reply, key)
    payload, media, usage, text = read_image_reply(engine, reply.body)
    output = job_dir / f"output.{_EXTENSIONS.get(media, 'png')}"
    output.write_bytes(payload)
    report = {"model": model, **asked, **usage, "seconds": round(reply.seconds, 1)}
    if text:
        report["note"] = text[:400]
    return output, report


def saved_output(job_dir: Path) -> list[Path]:
    """Recovery only: the image an API run saved in its own job folder, if any."""
    return [p for p in sorted(job_dir.glob("output.*")) if p.suffix[1:] in _EXTENSIONS.values()]
