"""API keys for the optional API engines (Phase 6, DECISIONS.md D022; Phase 8B, D041).

Each key is one file, `<data dir>/keys/<provider>/<id>.key`, encrypted with Windows DPAPI
for the signed-in Windows user, so a copied file is useless on another account or PC.
The folder is outside the repository and outside backups. Keys are never logged, never
returned to the browser and only ever sent to their own provider.

Several keys per provider (8B): `keys.json` next to the files lists each key's id and
name and which key each engine panel's new runs use, per provider and purpose (like the
CLI accounts after the 8A review, D044): analysis also covers quality checks;
generation also covers region edits. The single key of earlier versions
(`keys/<provider>.key`) becomes that provider's "Default" key on first use.

Every paid job records the id and name of the key it was queued with (`key` and
`key_label` in its settings, never the key): what was queued runs on that key and is
charged to whoever owns it, whatever is chosen later.
"""

import ctypes
import json
import os
import re
import threading
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from backend import fallback
from backend.configuration import Settings

KEY_DIRECTORY = "keys"
# Printable characters without spaces; real keys are 20–200 characters.
_KEY_SHAPE = re.compile(r"^[\x21-\x7e]{16,300}$")
_ENTROPY = b"Character Studio API key v1"
_UI_FORBIDDEN = 0x1
REGISTRY = "keys.json"
DEFAULT = "default"
DEFAULT_LABEL = "Default"
# Which engine panels choose a key of each provider: Gemini and OpenAI keys serve the
# Analysis and the Generation panel, FLUX keys only region edits (the generation purpose).
PURPOSES = {
    "gemini_api": ("analysis", "generation"),
    "anthropic_api": ("analysis",),
    "openai_api": ("analysis", "generation"),
    "bfl_api": ("generation",),
}
CHOICES = tuple(f"{p}:{purpose}" for p, purposes in PURPOSES.items() for purpose in purposes)
PURPOSE_OF_KIND = {
    "analysis": "analysis",
    "check": "analysis",
    "generation": "generation",
    "edit": "generation",
}
MAX_KEYS = 10
MAX_LABEL = 40
_ID = re.compile(r"^(default|[0-9a-f]{32})$")
_LOCK = threading.RLock()


class KeyStoreError(Exception):
    """A problem the user can act on; the message never contains the key."""


class _Blob(ctypes.Structure):
    _fields_ = [("cbData", ctypes.c_uint32), ("pbData", ctypes.POINTER(ctypes.c_char))]


def _blob(data: bytes) -> tuple[_Blob, ctypes.Array]:
    buffer = ctypes.create_string_buffer(data, len(data))
    return _Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char))), buffer


def _dpapi(data: bytes, protect: bool) -> bytes:
    if os.name != "nt":
        raise KeyStoreError("Saving API keys needs Windows' built-in protection.")
    crypt32, kernel32 = ctypes.windll.crypt32, ctypes.windll.kernel32
    source, _keep = _blob(data)
    entropy, _keep_entropy = _blob(_ENTROPY)
    output = _Blob()
    call = crypt32.CryptProtectData if protect else crypt32.CryptUnprotectData
    ok = call(
        ctypes.byref(source),
        None,
        ctypes.byref(entropy),
        None,
        None,
        _UI_FORBIDDEN,
        ctypes.byref(output),
    )
    if not ok:
        raise KeyStoreError(
            "The saved key could not be read by this Windows account. Enter it again."
            if not protect
            else "Windows could not protect the key. Try again."
        )
    try:
        return ctypes.string_at(output.pbData, output.cbData)
    finally:
        kernel32.LocalFree(output.pbData)


def key_folder(settings: Settings) -> Path:
    return settings.data_dir / KEY_DIRECTORY


def _provider(provider: str) -> str:
    if provider not in PURPOSES:
        raise KeyStoreError("Unknown provider.")
    return provider


def _key_file(settings: Settings, provider: str, key_id: str) -> Path:
    if not _ID.match(key_id or ""):
        raise KeyStoreError("That key does not exist.")
    return key_folder(settings) / _provider(provider) / f"{key_id}.key"


def check_key_shape(key: str) -> str:
    key = key.strip()
    if not _KEY_SHAPE.match(key):
        raise KeyStoreError(
            "This does not look like an API key. Paste the whole key without spaces."
        )
    return key


# The list of keys ------------------------------------------------------------------------


def _write(settings: Settings, data: dict) -> None:
    path = key_folder(settings) / REGISTRY
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(data, indent=2), encoding="utf-8")
    os.replace(temporary, path)


def _migrate(settings: Settings, data: dict) -> bool:
    """The one key per provider of earlier versions becomes its "Default" key (8B)."""
    changed = False
    for provider in PURPOSES:
        old = key_folder(settings) / f"{provider}.key"
        if not old.is_file():
            continue
        target = _key_file(settings, provider, DEFAULT)
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            saved = datetime.fromtimestamp(old.stat().st_mtime, UTC).isoformat()
            os.replace(old, target)
            if not any(k["provider"] == provider and k["id"] == DEFAULT for k in data["keys"]):
                data["keys"].insert(
                    0,
                    {
                        "id": DEFAULT,
                        "provider": provider,
                        "label": DEFAULT_LABEL,
                        "created_at": saved,
                    },
                )
        else:
            old.unlink()
        changed = True
    return changed


def _read(settings: Settings) -> dict:
    with _LOCK:
        try:
            raw = json.loads((key_folder(settings) / REGISTRY).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            raw = {}
        data = {
            "keys": [
                k
                for k in raw.get("keys", [])
                if isinstance(k, dict)
                and k.get("provider") in PURPOSES
                and isinstance(k.get("id"), str)
                and _ID.match(k["id"])
                and isinstance(k.get("label"), str)
            ],
            "active": raw.get("active") if isinstance(raw.get("active"), dict) else {},
            # Phase 8C: each panel's fallback list (off unless the user turned it on).
            "fallback": fallback.clean(raw.get("fallback")),
        }
        if _migrate(settings, data):
            _write(settings, data)
        return data


def _public(settings: Settings, item: dict) -> dict:
    path = _key_file(settings, item["provider"], item["id"])
    saved = (
        datetime.fromtimestamp(path.stat().st_mtime, UTC).isoformat() if path.is_file() else None
    )
    return {
        "id": item["id"],
        "provider": item["provider"],
        "label": item["label"],
        "created_at": item.get("created_at"),
        "saved_at": saved,
    }


def keys(settings: Settings, provider: str) -> list[dict]:
    """The provider's keys in the order they were added (a file that went missing is left out)."""
    _provider(provider)
    found = [_public(settings, k) for k in _read(settings)["keys"] if k["provider"] == provider]
    return [k for k in found if k["saved_at"]]


def find(settings: Settings, provider: str, key_id: str | None) -> dict | None:
    return next((k for k in keys(settings, provider) if k["id"] == key_id), None)


def purpose_of(provider: str, kind: str | None) -> str:
    """The choice a run of this kind uses (FLUX keys only serve edits)."""
    purpose = PURPOSE_OF_KIND.get(kind or "", "analysis")
    allowed = PURPOSES.get(provider, ("analysis",))
    return purpose if purpose in allowed else allowed[0]


def active(settings: Settings, provider: str, purpose: str = "analysis") -> dict | None:
    """The key new runs of this purpose use: the chosen one, else the first key; None when
    the provider has no key. The charge confirmation always names it."""
    listed = keys(settings, provider)
    chosen = _read(settings)["active"].get(f"{provider}:{purpose}")
    return next((k for k in listed if k["id"] == chosen), None) or (listed[0] if listed else None)


def choices(settings: Settings) -> dict[str, str | None]:
    """Every provider-and-purpose choice, as saved with the engine panels."""
    result = {}
    for choice in CHOICES:
        key = active(settings, *choice.split(":"))
        result[choice] = key["id"] if key else None
    return result


def key_info(settings: Settings, provider: str, purpose: str | None = None) -> dict:
    """Whether a key is saved (for a purpose: the one its runs use). Never the key itself."""
    if purpose is None:
        listed = keys(settings, provider)
        key = listed[0] if listed else None
    else:
        key = active(settings, provider, purpose)
    if key is None:
        return {"saved": False, "saved_at": None, "id": None, "label": None}
    return {"saved": True, "saved_at": key["saved_at"], "id": key["id"], "label": key["label"]}


def _clean_label(label: str) -> str:
    text = " ".join(label.split())
    if not text:
        raise KeyStoreError("Give the key a name, for example “Work” or “Personal”.")
    if len(text) > MAX_LABEL:
        raise KeyStoreError(f"Keep the name to {MAX_LABEL} characters or fewer.")
    return text


def _unique(data: dict, provider: str, text: str, own: str | None = None) -> None:
    taken = {
        k["label"].casefold() for k in data["keys"] if k["provider"] == provider and k["id"] != own
    }
    if text.casefold() in taken:
        raise KeyStoreError("Another key already has that name. Choose a different one.")


def _store(settings: Settings, provider: str, key_id: str, key: str) -> None:
    target = _key_file(settings, provider, key_id)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(".tmp")
    temporary.write_bytes(_dpapi(key.encode("utf-8"), protect=True))
    os.replace(temporary, target)


def add_key(settings: Settings, provider: str, label: str, key: str) -> dict:
    """Save a new key under a name. A provider's first key is used by its panels."""
    _provider(provider)
    text, key = _clean_label(label), check_key_shape(key)
    with _LOCK:
        data = _read(settings)
        mine = [k for k in data["keys"] if k["provider"] == provider]
        if len(mine) >= MAX_KEYS:
            raise KeyStoreError(f"Up to {MAX_KEYS} keys can be saved per provider.")
        _unique(data, provider, text)
        key_id = DEFAULT if not mine else uuid4().hex
        _store(settings, provider, key_id, key)
        item = {
            "id": key_id,
            "provider": provider,
            "label": text,
            "created_at": datetime.now(UTC).isoformat(),
        }
        data["keys"].append(item)
        _write(settings, data)
    return _public(settings, item)


def replace_key(settings: Settings, provider: str, key_id: str, key: str) -> dict:
    """Put a new key in place of a saved one; it keeps its name and its place in choices."""
    key = check_key_shape(key)
    with _LOCK:
        if find(settings, provider, key_id) is None:
            raise KeyStoreError("That key no longer exists. Reload the page.")
        _store(settings, provider, key_id, key)
    return find(settings, provider, key_id)


def rename_key(settings: Settings, provider: str, key_id: str, label: str) -> dict:
    text = _clean_label(label)
    with _LOCK:
        data = _read(settings)
        item = next(
            (k for k in data["keys"] if k["provider"] == provider and k["id"] == key_id), None
        )
        if item is None:
            raise KeyStoreError("That key no longer exists. Reload the page.")
        _unique(data, provider, text, key_id)
        item["label"] = text
        _write(settings, data)
    return _public(settings, item)


def choose_key(settings: Settings, provider: str, key_id: str, purpose: str | None = None) -> dict:
    """Use this key for new runs of one purpose (None: every purpose of the provider).
    Runs already queued keep their own key."""
    purposes = (purpose,) if purpose else PURPOSES[_provider(provider)]
    with _LOCK:
        if find(settings, provider, key_id) is None:
            raise KeyStoreError("That key no longer exists. Reload the page.")
        data = _read(settings)
        for each in purposes:
            if each not in PURPOSES[provider]:
                raise KeyStoreError("That provider has no such choice.")
            data["active"][f"{provider}:{each}"] = key_id
        _write(settings, data)
    return active(settings, provider, purposes[0])


def fallback_of(settings: Settings, provider: str, purpose: str) -> dict:
    """The panel's fallback list (Phase 8C): {"on": bool, "order": [key ids]}."""
    existing = [k["id"] for k in keys(settings, provider)]
    return fallback.read(_read(settings), f"{provider}:{purpose}", existing)


def fallbacks(settings: Settings) -> dict[str, dict]:
    return {choice: fallback_of(settings, *choice.split(":")) for choice in CHOICES}


def set_fallback(settings: Settings, provider: str, purpose: str, on: bool, order: list[str]):
    """Save a panel's fallback list (with the panel's Save)."""
    with _LOCK:
        known = {k["id"] for k in keys(settings, provider)}
        if any(i not in known for i in order):
            raise KeyStoreError("That key no longer exists. Reload the page.")
        data = _read(settings)
        fallback.write(data, f"{provider}:{purpose}", on, order)
        _write(settings, data)


def promote(settings: Settings, provider: str, purpose: str, old: str, new: str) -> None:
    """After an automatic switch: the key that worked becomes the panel's choice (D046)."""
    with _LOCK:
        if find(settings, provider, new) is None:
            return
        data = _read(settings)
        fallback.promote(data, f"{provider}:{purpose}", old, new)
        _write(settings, data)


def delete_key(settings: Settings, provider: str, key_id: str) -> None:
    """Remove the key from this PC. It stays valid at the provider until revoked there."""
    with _LOCK:
        data = _read(settings)
        before = len(data["keys"])
        data["keys"] = [
            k for k in data["keys"] if not (k["provider"] == provider and k["id"] == key_id)
        ]
        if len(data["keys"]) == before:
            raise KeyStoreError("That key no longer exists. Reload the page.")
        prefix = f"{provider}:"
        chosen = [c for c, v in data["active"].items() if c.startswith(prefix) and v == key_id]
        for choice in chosen:
            data["active"].pop(choice)
        fallback.forget(data, prefix, key_id)
        _key_file(settings, provider, key_id).unlink(missing_ok=True)
        _write(settings, data)


def load_key(settings: Settings, provider: str, key_id: str | None = DEFAULT) -> str | None:
    """The key itself, for the one request it is sent with. Runs queued before 8B recorded
    no key and use the Default key. None when the key was removed."""
    key_id = key_id or DEFAULT
    path = _key_file(settings, provider, key_id)
    if find(settings, provider, key_id) is None or not path.is_file():
        return None
    return _dpapi(path.read_bytes(), protect=False).decode("utf-8")


# Recording the key on what is queued -----------------------------------------------------


def stamp(key: dict) -> dict:
    """The job settings that name a key (never the key itself)."""
    return {"key": key["id"], "key_label": key["label"]}


def recorded(settings_json: str | None) -> tuple[str, str]:
    """(key id, name) a job or batch was queued with; older runs used the Default key."""
    values = json.loads(settings_json or "{}")
    return values.get("key") or DEFAULT, values.get("key_label") or DEFAULT_LABEL


def move(item, key: dict) -> None:
    """Point a not-started job or a batch at another key (the user's Continue)."""
    values = json.loads(item.settings_json or "{}")
    values["key"], values["key_label"] = key["id"], key["label"]
    item.settings_json = json.dumps(values)
