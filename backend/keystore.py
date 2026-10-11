"""API keys for the optional API engines (Phase 6, DECISIONS.md D022).

One file per provider in `<data dir>/keys/`, encrypted with Windows DPAPI for the
signed-in Windows user, so a copied file is useless on another account or PC. The
folder is outside the repository and outside backups. Keys are never logged, never
returned to the browser and only ever sent to their own provider.
"""

import ctypes
import os
import re
from datetime import UTC, datetime
from pathlib import Path

from backend.configuration import Settings

KEY_DIRECTORY = "keys"
# Printable characters without spaces; real keys are 20–200 characters.
_KEY_SHAPE = re.compile(r"^[\x21-\x7e]{16,300}$")
_ENTROPY = b"Character Studio API key v1"
_UI_FORBIDDEN = 0x1


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


def _key_file(settings: Settings, provider: str) -> Path:
    if not re.fullmatch(r"[a-z_]{2,30}", provider):
        raise KeyStoreError("Unknown provider.")
    return key_folder(settings) / f"{provider}.key"


def check_key_shape(key: str) -> str:
    key = key.strip()
    if not _KEY_SHAPE.match(key):
        raise KeyStoreError(
            "This does not look like an API key. Paste the whole key without spaces."
        )
    return key


def save_key(settings: Settings, provider: str, key: str) -> None:
    key = check_key_shape(key)
    target = _key_file(settings, provider)
    target.parent.mkdir(exist_ok=True)
    temporary = target.with_suffix(".tmp")
    temporary.write_bytes(_dpapi(key.encode("utf-8"), protect=True))
    os.replace(temporary, target)


def load_key(settings: Settings, provider: str) -> str | None:
    path = _key_file(settings, provider)
    if not path.is_file():
        return None
    return _dpapi(path.read_bytes(), protect=False).decode("utf-8")


def delete_key(settings: Settings, provider: str) -> None:
    _key_file(settings, provider).unlink(missing_ok=True)


def key_info(settings: Settings, provider: str) -> dict:
    """Whether a key is saved and when. The key itself never leaves this module."""
    path = _key_file(settings, provider)
    if not path.is_file():
        return {"saved": False, "saved_at": None}
    saved = datetime.fromtimestamp(path.stat().st_mtime, UTC).isoformat()
    return {"saved": True, "saved_at": saved}
