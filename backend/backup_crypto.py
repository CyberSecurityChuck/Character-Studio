"""Password-protected backups (Phase 6D, DECISIONS.md D028).

An encrypted backup is the normal backup zip, encrypted as a whole into one
`.csbackup` file:

    magic "CSBACKUP" | 4-byte header length | header JSON | chunk, chunk, ...

The header holds only the format, the scrypt settings, a random salt and a random
nonce prefix; nothing about the studio's contents. The key comes from the password
with scrypt (n = 2**17, r = 8, p = 1, about 128 MB of memory, so guessing is slow).
The zip is cut into 1 MiB chunks, each sealed with AES-256-GCM under its own nonce
(prefix + chunk number); the header and a "last chunk" flag are authenticated with
every chunk, so a changed, reordered or shortened file is refused.

The password is never stored, logged or written anywhere: a forgotten password means
the backup cannot be opened by anyone.
"""

import json
import os
import struct
from pathlib import Path

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

MAGIC = b"CSBACKUP"
FORMAT = 1
CHUNK = 1 << 20
TAG = 16
SCRYPT = {"n": 2**17, "r": 8, "p": 1}
MIN_PASSWORD = 10
MAX_PASSWORD = 1024
MAX_HEADER = 4096


class WrongPassword(Exception):
    """The password does not open this backup, or the file was changed or damaged."""


class NotEncrypted(Exception):
    """The file is not a password-protected Character Studio backup."""


def check_password(password: str) -> str:
    """Raise ValueError with a message the user can act on."""
    if len(password) < MIN_PASSWORD:
        raise ValueError(
            f"Use a password of at least {MIN_PASSWORD} characters (a few words work well)."
        )
    if len(password) > MAX_PASSWORD:
        raise ValueError("That password is too long.")
    if password.strip() != password:
        raise ValueError("The password starts or ends with a space. Remove it to avoid mistakes.")
    return password


def _key(password: str, salt: bytes, params: dict) -> bytes:
    kdf = Scrypt(salt=salt, length=32, n=params["n"], r=params["r"], p=params["p"])
    return kdf.derive(password.encode("utf-8"))


def _nonce(prefix: bytes, number: int) -> bytes:
    return prefix + struct.pack(">I", number)


def _aad(header: bytes, last: bool) -> bytes:
    return header + (b"\x01" if last else b"\x00")


def is_encrypted(path: Path) -> bool:
    try:
        with path.open("rb") as file:
            return file.read(len(MAGIC)) == MAGIC
    except OSError:
        return False


def encrypt_file(source: Path, target: Path, password: str) -> None:
    """Encrypt `source` (a backup zip) into `target`."""
    salt, prefix = os.urandom(16), os.urandom(8)
    header = json.dumps(
        {
            "format": FORMAT,
            "application": "character-studio",
            "kdf": {"name": "scrypt", **SCRYPT, "salt": salt.hex()},
            "cipher": "AES-256-GCM",
            "chunk": CHUNK,
            "nonce_prefix": prefix.hex(),
        },
        sort_keys=True,
    ).encode()
    cipher = AESGCM(_key(password, salt, SCRYPT))
    size = source.stat().st_size
    chunks = max(1, -(-size // CHUNK))
    if chunks >= 2**32:
        raise ValueError("This backup is too large to encrypt.")
    with source.open("rb") as plain, target.open("xb") as out:
        out.write(MAGIC + struct.pack(">I", len(header)) + header)
        for number in range(chunks):
            block = plain.read(CHUNK)
            last = number == chunks - 1
            out.write(cipher.encrypt(_nonce(prefix, number), block, _aad(header, last)))
        out.flush()
        os.fsync(out.fileno())


def read_header(path: Path) -> tuple[dict, bytes, int]:
    """(header, raw header bytes, offset of the first chunk)."""
    with path.open("rb") as file:
        if file.read(len(MAGIC)) != MAGIC:
            raise NotEncrypted("This is not a password-protected Character Studio backup.")
        length = struct.unpack(">I", file.read(4) or b"\0\0\0\0")[0]
        if not 0 < length <= MAX_HEADER:
            raise NotEncrypted("This password-protected backup is damaged.")
        raw = file.read(length)
    try:
        header = json.loads(raw)
    except json.JSONDecodeError as error:
        raise NotEncrypted("This password-protected backup is damaged.") from error
    if header.get("application") != "character-studio" or header.get("format") != FORMAT:
        raise NotEncrypted("This password-protected backup needs a newer Character Studio.")
    return header, raw, len(MAGIC) + 4 + length


def decrypt_file(source: Path, target: Path, password: str) -> None:
    """Decrypt `source` into `target` (a new file). Raises WrongPassword on any mismatch."""
    header, raw, offset = read_header(source)
    kdf = header["kdf"]
    params = {k: int(kdf[k]) for k in ("n", "r", "p")}
    # Refuse settings that would make this PC run out of memory (a damaged header).
    if params["n"] > 2**20 or params["r"] > 16 or params["p"] > 4:
        raise NotEncrypted("This password-protected backup is damaged.")
    cipher = AESGCM(_key(password, bytes.fromhex(kdf["salt"]), params))
    prefix, chunk = bytes.fromhex(header["nonce_prefix"]), int(header["chunk"])
    sealed = chunk + TAG
    total = source.stat().st_size - offset
    chunks = max(1, -(-total // sealed))
    try:
        with source.open("rb") as file, target.open("xb") as out:
            file.seek(offset)
            for number in range(chunks):
                block = file.read(sealed)
                last = number == chunks - 1
                out.write(cipher.decrypt(_nonce(prefix, number), block, _aad(raw, last)))
    except InvalidTag as error:
        target.unlink(missing_ok=True)
        raise WrongPassword(
            "The password is wrong, or this backup file was changed or damaged."
        ) from error
    except BaseException:
        target.unlink(missing_ok=True)
        raise
