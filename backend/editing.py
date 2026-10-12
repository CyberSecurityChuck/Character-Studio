"""Region edits and selective replacement of a result (Phase 6C-2, DECISIONS.md D025/D027).

The user marks an area of a result and either describes a fix or asks to replace one
person with that subject's approved reference photos (never other photos). One engine
run makes a new image; the studio then pastes back only the marked area, with a soft
edge inside it, so every pixel outside the area is exactly the original. Each edit is a
new result version that records its parent result, mask, instruction, engine and model.

Engines: Codex (instruction and references, no mask), OpenAI Images (mask as guidance),
Gemini image (instruction only), FLUX.1 Fill (true mask, no references, fixes only) and
FLUX 3 (references and a box region). Results are made from the parent's own approval
snapshot; an approval the user withdrew cannot be used.
"""

import base64
import hashlib
import io
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageChops, ImageFilter, ImageOps

from backend.api_engines import (
    API_ENGINES,
    ApiCancelled,
    _base,
    _call,
    _headers,
    _message,
    _redact,
    classify,
    require_key,
)
from backend.configuration import Settings, asset_path
from backend.engines import EngineError
from backend.generation import (
    MAX_RESULT_BYTES,
    PackageError,
    _clean_copy,
    new_job_folder,
    snapshot_of,
)
from backend.image_api import (
    DEFAULT_OPTIONS,
    SEND_EDGE,
    _multipart,
    _without_image_data,
    gemini_ratio,
    openai_error,
    openai_size,
    read_image_reply,
)
from backend.library import file_hash
from backend.models import Approval, GenerationResult, ReferencePhoto

WITHDRAWN = "You withdrew this approval."
MAX_INSTRUCTION = 1000
MAX_MASK_SHARE = 0.95
MIN_MASK_SHARE = 0.0005
POLL_SECONDS = 1.0
_FLUX_RESOLUTION = {"1K": "1k", "2K": "2k", "4K": "4k"}
_BFL_WAITING = ("Pending", "Queued", "Reasoning", "Generating", "Processing")
_BFL_MODERATED = ("Request Moderated", "Content Moderated")


@dataclass(frozen=True)
class EditOption:
    id: str
    engine: str
    name: str
    kinds: tuple[str, ...]
    # How the marked area reaches the engine: "mask" (exact), "guided" (a mask the model may
    # not follow exactly), "box" (a box region) or "words" (described in the instruction).
    area: str
    model: str | None = None

    @property
    def charged(self) -> bool:
        return self.engine in API_ENGINES


EDIT_OPTIONS = {
    "codex_cli": EditOption("codex_cli", "codex_cli", "Codex", ("fix", "replace"), "words"),
    "openai_api": EditOption(
        "openai_api", "openai_api", "OpenAI Images", ("fix", "replace"), "guided"
    ),
    "gemini_api": EditOption(
        "gemini_api", "gemini_api", "Gemini image", ("fix", "replace"), "words"
    ),
    "flux_fill": EditOption(
        "flux_fill", "bfl_api", "FLUX.1 Fill", ("fix",), "mask", "flux-pro-1.0-fill"
    ),
    "flux_3": EditOption("flux_3", "bfl_api", "FLUX 3", ("fix", "replace"), "box", "flux-3-image"),
}


def edit_label(settings_json: str | None) -> str:
    option = EDIT_OPTIONS.get(json.loads(settings_json or "{}").get("option", ""))
    return option.name if option else "Edit"


# ---------------------------------------------------------------- the marked area


def read_mask(data: str, size: tuple[int, int]) -> Image.Image:
    """A black-and-white mask (white = change) the size of the result, or ValueError."""
    try:
        raw = base64.b64decode(data.split(",", 1)[-1], validate=True)
        with Image.open(io.BytesIO(raw)) as source:
            source.load()
            mask = source.convert("L")
    except (ValueError, OSError) as error:
        raise ValueError("The marked area could not be read. Mark it again.") from error
    if mask.size != size:
        raise ValueError("The marked area does not match the result's size. Mark it again.")
    mask = mask.point(lambda v: 255 if v >= 128 else 0)
    share = mask.histogram()[255] / (size[0] * size[1])
    if share < MIN_MASK_SHARE:
        raise ValueError("Mark the area to change first.")
    if share > MAX_MASK_SHARE:
        raise ValueError("The marked area covers almost everything. Generate a new image instead.")
    return mask


def mask_box(mask: Image.Image) -> list[float]:
    """The marked area's bounding box as fractions: [left, top, right, bottom]."""
    left, top, right, bottom = mask.getbbox()
    w, h = mask.size
    return [round(left / w, 4), round(top / h, 4), round(right / w, 4), round(bottom / h, 4)]


def feather_width(size: tuple[int, int]) -> int:
    return max(2, round(min(size) * 0.006))


def composite(
    original: Image.Image, edited: Image.Image, mask: Image.Image
) -> tuple[Image.Image, bool]:
    """Paste the edited image back inside the mask only. Returns (image, shape changed).

    The soft edge is kept inside the mask (blurred mask multiplied by the mask), so every
    pixel outside it keeps the original value exactly.
    """
    edited = edited.convert("RGB")
    shape_changed = abs(edited.width / edited.height - original.width / original.height) > 0.02
    if edited.size != original.size:
        edited = edited.resize(original.size, Image.Resampling.LANCZOS)
    soft = mask.filter(ImageFilter.GaussianBlur(feather_width(original.size)))
    alpha = ImageChops.multiply(soft, mask)
    return Image.composite(edited, original, alpha), shape_changed


def upright(path: Path) -> Image.Image:
    with Image.open(path) as source:
        image = ImageOps.exif_transpose(source).convert("RGB")
    clean = Image.new("RGB", image.size)
    clean.paste(image)
    return clean


def png_bytes(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, "PNG")
    return buffer.getvalue()


# ---------------------------------------------------------------- inputs


def usable_approval(session, result: GenerationResult) -> Approval:
    """The result's own approval, unless the user withdrew it (D027)."""
    approval = session.get(Approval, result.approval_id)
    if approval is None:
        raise ValueError("This result's approval no longer exists, so it cannot be edited.")
    if approval.invalidated_reason == WITHDRAWN:
        raise ValueError(
            "You withdrew the approval this result was made from, so it cannot be edited."
        )
    return approval


def replaceable(inputs: dict) -> dict[str, list[dict]]:
    """Subjects that were replaced with approved reference photos: {label: references}."""
    return {
        m["subject"]: m["references"]
        for m in inputs["mappings"]
        if m["action"] == "replace" and m["references"]
    }


def prepare_edit_folder(
    settings: Settings, session, result: GenerationResult, subject: str | None
) -> tuple[str, Path, list[Path]]:
    """Job folder: `image-1.png` (the result, metadata-free) and, to replace a person, that
    subject's approved reference photos as `image-2.jpg`, ... (hash-checked)."""
    approval = usable_approval(session, result)
    inputs = snapshot_of(approval)["inputs"]
    source = asset_path(settings, result.original_path)
    if not source.is_file():
        raise PackageError("The result's image file is missing. Restore it from a backup.")
    key, folder, _number = new_job_folder(settings, result.scene_id, "edit")
    files = [folder / "image-1.png"]
    upright(source).save(files[0], "PNG")
    if subject:
        references = replaceable(inputs).get(subject)
        if not references:
            raise PackageError(f"{subject} has no approved reference photos.")
        for number, reference in enumerate(references, 2):
            photo = session.get(ReferencePhoto, reference["photo_id"])
            path = asset_path(settings, photo.original_path) if photo else None
            actual = file_hash(path) if path else None
            expected = reference["content_hash"]
            if actual is None or (expected and actual != expected):
                raise PackageError(
                    f"A reference photo for {subject} is missing or changed since it was approved."
                )
            target = folder / f"image-{number}.jpg"
            _clean_copy(path, target)
            files.append(target)
    return key, folder, files


def _area_words(box: list[float]) -> str:
    left, top, right, bottom = (round(v * 100) for v in box)
    return (
        f"the marked area, from {left}% to {right}% of the width (from the left) and from "
        f"{top}% to {bottom}% of the height (from the top)"
    )


def edit_instruction(
    kind: str, box: list[float], instruction: str, subject: str | None, references: int,
    codex: bool = False,
) -> str:
    """The fixed edit wording around the user's instruction. Never contains names."""
    area = _area_words(box)
    if codex:
        lines = [
            "You are the image-editing step of Character Studio, a local app. Use your built-in "
            "image generation to create exactly one edited copy of Image 1. Do not run shell "
            "commands, do not read, create or change any files yourself, and do not ask "
            "questions.",
        ]
    else:
        lines = ["You are the image-editing step of Character Studio, a local app. Create "
                 "exactly one edited copy of Image 1."]
    lines += ["", "Image 1 is a finished photograph."]
    if kind == "replace":
        refs = "Image 2" if references == 1 else f"Images 2 to {references + 1}"
        lines += [
            f"{refs}: identity reference photos of one person.",
            "",
            f"In {area} there is {subject}. Make that person the person shown in {refs}: the "
            "same face, facial features, hair, skin tone and apparent age. Keep their pose, "
            "head angle, gaze, expression, outfit, size, position and the lighting on them "
            "exactly as in Image 1.",
        ]
        if instruction:
            lines += ["", f"Also: {instruction}"]
    else:
        lines += ["", f"Change only {area}: {instruction}"]
    lines += [
        "",
        "Keep everything outside that area exactly as it is: the same framing, size, people, "
        "poses, background, lighting and colours. Return the whole image at the same framing "
        "and shape as Image 1.",
    ]
    if codex:
        lines += ["", "When the image has been generated, reply with only the full path of the "
                  "saved image file."]
    return "\n".join(lines)


def flux3_prompt(kind: str, box: list[float], instruction: str, references: int) -> str:
    """FLUX 3 prose with an inline tag and its box row ([y0, x0, y1, x1] on 0–1000)."""
    left, top, right, bottom = box
    target = [round(top * 1000), round(left * 1000), round(bottom * 1000), round(right * 1000)]
    if kind == "replace":
        refs = ", ".join(f"<ref_image_{n}>" for n in range(1, references + 1))
        prose = (
            f"In <ref_image_0>, replace the person <person_1> with the same person as in {refs}: "
            "same face, hair, skin tone and apparent age, keeping the pose, head angle, "
            "expression, outfit and lighting of <person_1>."
            + (f" Also: {instruction}" if instruction else "")
            + " Keep everything else exactly unchanged."
        )
        row = {"id": "person_1", "from": None, "src_bbox": None, "tgt_bbox": target,
               "desc": "the person from the identity references, in the original pose",
               "kind": "new"}
    else:
        prose = (f"In <ref_image_0>, change only the area <area_1>: {instruction} "
                 "Keep everything else exactly unchanged.")
        row = {"id": "area_1", "from": None, "src_bbox": None, "tgt_bbox": target,
               "desc": instruction[:200], "kind": "new"}
    return f"{prose}\n{json.dumps([row])}"


# ---------------------------------------------------------------- provider requests


def _jpeg_copy(path: Path, edge: int = SEND_EDGE) -> bytes:
    with Image.open(path) as source:
        image = source.convert("RGB")
    image.thumbnail((edge, edge))
    buffer = io.BytesIO()
    image.save(buffer, "JPEG", quality=92)
    return buffer.getvalue()


def openai_edit_request(settings, model, files, mask, instruction, options):
    """`/v1/images/edits` with the result and its mask at an OpenAI size, then references."""
    with Image.open(files[0]) as source:
        image = source.convert("RGB")
    width, height = map(int, openai_size(*image.size, options.get("size", "1K")).split("x"))
    sent = image.resize((width, height), Image.Resampling.LANCZOS)
    # OpenAI edits where the mask is transparent; the mask must match the first image.
    alpha = ImageOps.invert(mask.resize((width, height), Image.Resampling.NEAREST))
    guide = Image.new("RGBA", (width, height), (0, 0, 0, 255))
    guide.putalpha(alpha)
    fields = [
        ("model", model),
        ("prompt", instruction),
        ("n", "1"),
        ("size", f"{width}x{height}"),
        ("quality", options.get("quality") or DEFAULT_OPTIONS["quality"]),
        ("output_format", "png"),
    ]
    parts = [("image[]", "image-1.png", png_bytes(sent), "image/png")]
    parts += [("image[]", p.name, _jpeg_copy(p)) for p in files[1:]]
    parts.append(("mask", "mask.png", png_bytes(guide), "image/png"))
    url = f"{_base(settings, 'openai_api')}/v1/images/edits"
    return url, _multipart(fields, parts), {"size": f"{width}x{height}", "quality": fields[4][1]}


def gemini_edit_request(settings, model, files, instruction, options):
    with Image.open(files[0]) as source:
        size = source.size
    ratio = gemini_ratio(*size)
    parts = [{"text": instruction}]
    for number, path in enumerate(files, 1):
        data = base64.b64encode(_jpeg_copy(path)).decode("ascii")
        parts += [{"text": f"Image {number}:"},
                  {"inline_data": {"mime_type": "image/jpeg", "data": data}}]
    body = {
        "contents": [{"role": "user", "parts": parts}],
        "generationConfig": {
            "responseModalities": ["TEXT", "IMAGE"],
            "imageConfig": {"aspectRatio": ratio, "imageSize": options.get("size", "1K")},
        },
    }
    quoted = urllib.parse.quote(model, safe="-._")
    url = f"{_base(settings, 'gemini_api')}/v1beta/models/{quoted}:generateContent"
    return url, body, {"aspect_ratio": ratio, "image_size": options.get("size", "1K")}


def flux_request(settings, option: EditOption, files, mask, prompt, options):
    base = _base(settings, "bfl_api")
    first = base64.b64encode(_jpeg_copy(files[0])).decode("ascii")
    if option.id == "flux_fill":
        with Image.open(files[0]) as source:
            image = source.convert("RGB")
        image.thumbnail((SEND_EDGE, SEND_EDGE))
        sized = mask.resize(image.size, Image.Resampling.NEAREST)
        body = {
            "prompt": prompt,
            "image": base64.b64encode(png_bytes(image)).decode("ascii"),
            "mask": base64.b64encode(png_bytes(sized)).decode("ascii"),
            "output_format": "png",
        }
        return f"{base}/v1/flux-pro-1.0-fill", body, {"size": f"{image.width}x{image.height}"}
    images = [first] + [base64.b64encode(_jpeg_copy(p)).decode("ascii") for p in files[1:]]
    resolution = _FLUX_RESOLUTION.get(options.get("size", "1K"), "1k")
    body = {"prompt": prompt, "images": images, "aspect_ratio": "auto", "resolution": resolution}
    return f"{base}/v1/flux-3-image", body, {"resolution": resolution}


def _trusted(settings: Settings, url: str) -> bool:
    """FLUX polling and result links: the API's own host or Black Forest Labs' HTTPS hosts."""
    parsed, base = urllib.parse.urlparse(url), urllib.parse.urlparse(_base(settings, "bfl_api"))
    if (parsed.scheme, parsed.netloc) == (base.scheme, base.netloc):
        return True
    host = (parsed.hostname or "").lower()
    return parsed.scheme == "https" and (
        host == "bfl.ai" or host.endswith(".bfl.ai") or host.endswith(".bfl.ml")
    )


def _download(url: str, timeout: float) -> bytes:
    """Fetch FLUX's signed result link (no key is sent)."""
    request = urllib.request.Request(url, headers={"User-Agent": "CharacterStudio"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            data = response.read(MAX_RESULT_BYTES + 1)
    except (urllib.error.URLError, TimeoutError) as error:
        raise EngineError(
            "network", "The finished FLUX image could not be downloaded. Look for a saved "
            "image soon: the link expires after a few minutes."
        ) from error
    if len(data) > MAX_RESULT_BYTES:
        raise EngineError("invalid_output", "FLUX sent an image that is too large.")
    return data


def flux_poll_once(settings: Settings, key: str, polling_url: str) -> tuple[str, bytes | None]:
    """One status check (free). Returns (status, image bytes when Ready)."""
    if not _trusted(settings, polling_url):
        raise EngineError("engine_error", "FLUX returned an unexpected address, so the studio "
                          "did not follow it.")
    reply = _call(polling_url, _headers("bfl_api", key), None, 30, "Black Forest Labs")
    if reply.status != 200:
        raise classify("bfl_api", reply, key)
    status = str(reply.body.get("status") or "")
    if status == "Ready":
        sample = (reply.body.get("result") or {}).get("sample")
        if not isinstance(sample, str) or not _trusted(settings, sample):
            raise EngineError("invalid_output", "FLUX finished without a usable image link.")
        return status, _download(sample, 60)
    if status in _BFL_MODERATED:
        raise EngineError("blocked", f"Black Forest Labs declined this edit ({status.lower()}). "
                          "Nothing was saved.")
    if status in _BFL_WAITING:
        return status, None
    said = _redact(_message(reply.body) or status, key)
    raise EngineError("engine_error", f"FLUX could not finish this edit: {said}")


def run_flux(settings, option, files, mask, prompt, options, job_dir, timeout, should_stop):
    """Submit once, then check the status until the image is ready (checks are free)."""
    key = require_key(settings, "bfl_api")
    url, body, asked = flux_request(settings, option, files, mask, prompt, options)
    _write_request(job_dir, "bfl_api", url, option.model, asked, files)
    if should_stop():
        raise ApiCancelled()
    started = time.monotonic()
    reply = _call(url, _headers("bfl_api", key), body, timeout, "Black Forest Labs", should_stop)
    (job_dir / "response.json").write_text(json.dumps(reply.body, indent=2).replace(key, "[key]"),
                                           encoding="utf-8")
    if reply.status != 200:
        raise classify("bfl_api", reply, key)
    polling_url = reply.body.get("polling_url")
    if not isinstance(polling_url, str):
        raise EngineError("invalid_output", "FLUX accepted the edit but sent no way to fetch it.")
    # Kept so "Look for a saved image" can check this one task again; it is never resubmitted.
    (job_dir / "submitted.json").write_text(
        json.dumps({"id": reply.body.get("id"), "polling_url": polling_url}), encoding="utf-8"
    )
    while True:
        status, payload = flux_poll_once(settings, key, polling_url)
        if payload is not None:
            usage = {"cost_credits": reply.body.get("cost"), **asked}
            return payload, usage
        if time.monotonic() - started > timeout:
            raise EngineError(
                "timeout",
                "FLUX did not finish in time, so the studio stopped waiting. It may still finish "
                "and be charged; Look for a saved image checks it again without resending.",
            )
        deadline = time.monotonic() + POLL_SECONDS
        while time.monotonic() < deadline:
            if should_stop():
                raise ApiCancelled()
            time.sleep(0.1)


def _write_request(job_dir, engine, url, model, asked, files) -> None:
    summary = {
        "engine": engine,
        "company": API_ENGINES[engine].company,
        "url": url,
        "model": model,
        "asked_for": asked,
        "images": [f"Image {n}: {p.name} (location data removed)" for n, p in enumerate(files, 1)],
        "mask": "mask.png",
        "instruction": "instruction.txt",
    }
    (job_dir / "request.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")


def run_api_edit(settings, option, model, files, mask, instruction, options, job_dir, timeout,
                 should_stop: Callable[[], bool]) -> tuple[bytes, dict]:
    """One OpenAI or Gemini edit request; returns (image bytes, usage)."""
    engine = option.engine
    key = require_key(settings, engine)
    if engine == "openai_api":
        url, body, asked = openai_edit_request(settings, model, files, mask, instruction, options)
    else:
        url, body, asked = gemini_edit_request(settings, model, files, instruction, options)
    _write_request(job_dir, engine, url, model, asked, files)
    if should_stop():
        raise ApiCancelled()
    company = API_ENGINES[engine].company
    reply = _call(url, _headers(engine, key), body, timeout, company, should_stop)
    (job_dir / "response.json").write_text(
        json.dumps(_without_image_data(engine, reply.body), indent=2).replace(key, "[key]"),
        encoding="utf-8",
    )
    if reply.status != 200:
        raise openai_error(reply, key) if engine == "openai_api" else classify(engine, reply, key)
    payload, _media, usage, text = read_image_reply(engine, reply.body)
    report = {"model": model, **asked, **usage, "seconds": round(reply.seconds, 1)}
    if text:
        report["note"] = text[:400]
    return payload, report


# ---------------------------------------------------------------- the new result


def finish_edit(settings: Settings, job_dir: Path, parent_path: Path, mask_path: Path,
                payload: bytes) -> tuple[bytes, dict]:
    """Save the engine's image as `output.*`, paste the marked area back onto the original
    and return (PNG bytes of the new result, facts about the paste)."""
    try:
        with Image.open(io.BytesIO(payload)) as source:
            source.load()
            edited = source.convert("RGB")
    except OSError as error:
        raise EngineError(
            "invalid_output", "The engine sent a file that is not a usable image."
        ) from error
    output = job_dir / "output.png"
    if not output.exists():
        edited.save(output, "PNG")
    original = upright(parent_path)
    with Image.open(mask_path) as source:
        mask = source.convert("L")
    if mask.size != original.size:
        raise EngineError("missing_file", "The marked area no longer matches the result.")
    merged, shape_changed = composite(original, edited, mask)
    data = png_bytes(merged)
    facts = {
        "shape_changed": shape_changed,
        "engine_size": f"{edited.width}x{edited.height}",
        "feather": feather_width(original.size),
        "sha256": hashlib.sha256(data).hexdigest(),
    }
    return data, facts


def area_share(box: list[float]) -> float:
    return max(0.0, (box[2] - box[0]) * (box[3] - box[1]))


def describe(edit: dict) -> str:
    """A short line for result cards: "Fix · FLUX.1 Fill" or "Replace Subject 2 · Codex"."""
    option = EDIT_OPTIONS.get(edit.get("option", ""))
    name = option.name if option else "Edit"
    what = f"Replace {edit['subject']}" if edit.get("kind") == "replace" else "Fix"
    return f"{what} · {name}"

