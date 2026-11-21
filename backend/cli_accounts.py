"""Several sign-ins for the subscription CLIs (Phase 8A, DECISIONS.md D041, D042).

Each extra account is a private profile folder, `<data dir>/cli-accounts/<engine>/<id>/`,
that the official CLI keeps its own login in (`CLAUDE_CONFIG_DIR` for Claude Code,
`CODEX_HOME` for Codex; docs/PROVIDER_FINDINGS.md, Phase 8 start). The studio never
opens the files in these folders: the user signs in with the CLI's own sign-in, status
comes from the CLI's own status command, and removing an account runs the CLI's own
sign-out before the folder is deleted. The only exception is Codex's
`generated_images/<thread_id>/`, read for "Look for a saved image" as before.

The Default account is the CLI's usual login (no folder variable set), so nothing
changes until a second account is added. The list of accounts and the account each
engine uses for new runs live in `accounts.json` next to the folders. Like `keys/`,
the folder is outside the repository and outside backups, and a restore keeps the
one on this PC.

Every engine job and batch records the account it was queued with (`account` and
`account_label` in its settings), like the API model (D022): what was queued runs on
that account, whatever is chosen later.
"""

import json
import os
import re
import shutil
import subprocess
import threading
import weakref
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from sqlalchemy import event
from sqlalchemy.orm import Session

from backend.configuration import Settings
from backend.models import Batch, EngineJob

ACCOUNT_DIRECTORY = "cli-accounts"
DEFAULT = "default"
DEFAULT_LABEL = "Default"
# The variable that points each CLI at a profile folder (confirmed on this PC, Phase 8A).
FOLDER_VARIABLES = {"claude_cli": "CLAUDE_CONFIG_DIR", "codex_cli": "CODEX_HOME"}
ACCOUNT_ENGINES = tuple(FOLDER_VARIABLES)
MAX_ACCOUNTS = 10
MAX_LABEL = 40
_ID = re.compile(r"^[0-9a-f]{32}$")
_LOCK = threading.Lock()


class AccountError(Exception):
    """A problem the user can act on; the message is safe to show."""


def _root(settings: Settings) -> Path:
    return settings.data_dir / ACCOUNT_DIRECTORY


def _registry_path(settings: Settings) -> Path:
    return _root(settings) / "accounts.json"


def _read(settings: Settings) -> dict:
    try:
        data = json.loads(_registry_path(settings).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    accounts = [
        a
        for a in data.get("accounts", [])
        if isinstance(a, dict)
        and a.get("engine") in ACCOUNT_ENGINES
        and isinstance(a.get("id"), str)
        and _ID.match(a["id"])
        and isinstance(a.get("label"), str)
    ]
    active = data.get("active") if isinstance(data.get("active"), dict) else {}
    return {"accounts": accounts, "active": active}


def _write(settings: Settings, data: dict) -> None:
    path = _registry_path(settings)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(data, indent=2), encoding="utf-8")
    os.replace(temporary, path)


def _default(engine: str) -> dict:
    return {"id": DEFAULT, "engine": engine, "label": DEFAULT_LABEL, "default": True}


def accounts(settings: Settings, engine: str) -> list[dict]:
    """Default first, then the added accounts in the order they were added."""
    listed = [
        {**a, "default": False} for a in _read(settings)["accounts"] if a["engine"] == engine
    ]
    return [_default(engine), *listed]


def find(settings: Settings, engine: str, account_id: str | None) -> dict | None:
    account_id = account_id or DEFAULT
    return next((a for a in accounts(settings, engine) if a["id"] == account_id), None)


def active(settings: Settings, engine: str) -> dict:
    """The account new runs use; Default when none is chosen or the chosen one was removed."""
    chosen = _read(settings)["active"].get(engine)
    return find(settings, engine, chosen) or _default(engine)


def folder(settings: Settings, engine: str, account_id: str) -> Path:
    if not _ID.match(account_id):
        raise AccountError("That account does not exist.")
    return _root(settings) / engine / account_id


def account_env(settings: Settings, engine: str, account_id: str | None) -> dict[str, str]:
    """The variable to set after cleaning the environment, or nothing for Default.

    Raises AccountError when the account was removed. Codex refuses to start with a
    missing CODEX_HOME, so the folder is (re)created; an empty folder is simply signed out.
    """
    if engine not in ACCOUNT_ENGINES or (account_id or DEFAULT) == DEFAULT:
        return {}
    account = find(settings, engine, account_id)
    if account is None:
        raise AccountError("removed")
    path = folder(settings, engine, account_id)
    path.mkdir(parents=True, exist_ok=True)
    return {FOLDER_VARIABLES[engine]: str(path)}


def home_of(settings: Settings, engine: str, account_id: str | None) -> Path | None:
    """The profile folder of an account (None for Default), without creating anything."""
    if (account_id or DEFAULT) == DEFAULT:
        return None
    try:
        return folder(settings, engine, account_id)
    except AccountError:
        return None


def _clean_label(label: str) -> str:
    text = " ".join(label.split())
    if not text:
        raise AccountError("Give the account a name, for example “Claude – personal”.")
    if len(text) > MAX_LABEL:
        raise AccountError(f"Keep the name to {MAX_LABEL} characters or fewer.")
    return text


def add(settings: Settings, engine: str, label: str) -> dict:
    """Create an empty profile folder; the user then signs in to it."""
    text = _clean_label(label)
    with _LOCK:
        data = _read(settings)
        mine = [a for a in data["accounts"] if a["engine"] == engine]
        if len(mine) >= MAX_ACCOUNTS:
            raise AccountError(f"Up to {MAX_ACCOUNTS} extra accounts can be added per engine.")
        names = {DEFAULT_LABEL.casefold(), *(a["label"].casefold() for a in mine)}
        if text.casefold() in names:
            raise AccountError("Another account already has that name. Choose a different one.")
        account = {
            "id": uuid4().hex,
            "engine": engine,
            "label": text,
            "created_at": datetime.now(UTC).isoformat(),
        }
        folder(settings, engine, account["id"]).mkdir(parents=True, exist_ok=True)
        data["accounts"].append(account)
        _write(settings, data)
    return {**account, "default": False}


def rename(settings: Settings, engine: str, account_id: str, label: str) -> dict:
    text = _clean_label(label)
    with _LOCK:
        data = _read(settings)
        account = next(
            (a for a in data["accounts"] if a["engine"] == engine and a["id"] == account_id), None
        )
        if account is None:
            raise AccountError("That account no longer exists. Reload the page.")
        others = {
            a["label"].casefold()
            for a in data["accounts"]
            if a["engine"] == engine and a["id"] != account_id
        }
        if text.casefold() in {DEFAULT_LABEL.casefold(), *others}:
            raise AccountError("Another account already has that name. Choose a different one.")
        account["label"] = text
        _write(settings, data)
    return {**account, "default": False}


def choose(settings: Settings, engine: str, account_id: str) -> dict:
    """Use this account for new runs. Runs already queued keep their own account."""
    with _LOCK:
        if find(settings, engine, account_id) is None:
            raise AccountError("That account no longer exists. Reload the page.")
        data = _read(settings)
        data["active"][engine] = account_id
        _write(settings, data)
    return active(settings, engine)


def forget(settings: Settings, engine: str, account_id: str) -> None:
    """Remove the account from the list and delete its folder (sign-out comes first)."""
    if account_id == DEFAULT:
        raise AccountError("The Default account is your usual sign-in and cannot be removed.")
    path = folder(settings, engine, account_id)
    with _LOCK:
        data = _read(settings)
        before = len(data["accounts"])
        data["accounts"] = [
            a for a in data["accounts"] if not (a["engine"] == engine and a["id"] == account_id)
        ]
        if len(data["accounts"]) == before:
            raise AccountError("That account no longer exists. Reload the page.")
        if data["active"].get(engine) == account_id:
            data["active"].pop(engine)
        _write(settings, data)
    root = (_root(settings) / engine).resolve()
    target = path.resolve()
    if target.parent == root and target.is_dir():
        shutil.rmtree(target, ignore_errors=True)


# Recording the account on what is queued -------------------------------------------------

_SETTINGS: "weakref.WeakKeyDictionary" = weakref.WeakKeyDictionary()


def register(database, settings: Settings) -> None:
    """Let this database's sessions stamp new CLI jobs and batches with the active account."""
    _SETTINGS[database] = settings


def stamp(settings: Settings, engine: str, values: dict) -> dict:
    """`values` with the account an engine's new runs use, unless one is already set."""
    if engine not in ACCOUNT_ENGINES or "account" in values:
        return values
    chosen = active(settings, engine)
    return {**values, "account": chosen["id"], "account_label": chosen["label"]}


@event.listens_for(Session, "before_flush")
def _record_account(session, _context, _instances) -> None:
    settings = _SETTINGS.get(session.bind) if session.bind is not None else None
    if settings is None:
        return
    for item in list(session.new):
        if not isinstance(item, (EngineJob, Batch)) or item.engine not in ACCOUNT_ENGINES:
            continue
        values = json.loads(item.settings_json or "{}")
        if "account" not in values:
            item.settings_json = json.dumps(stamp(settings, item.engine, values))


def recorded(settings_json: str | None) -> tuple[str, str]:
    """(account id, label) a job or batch was queued with; older runs used Default."""
    values = json.loads(settings_json or "{}")
    return values.get("account") or DEFAULT, values.get("account_label") or DEFAULT_LABEL


def move(item, account: dict) -> None:
    """Point a not-started job or a batch at another account (the user's Continue)."""
    values = json.loads(item.settings_json or "{}")
    values["account"], values["account_label"] = account["id"], account["label"]
    item.settings_json = json.dumps(values)


# The CLI's own sign-in, in a console window the user completes ---------------------------

_SIGN_IN = {"claude_cli": ("auth", "login"), "codex_cli": ("login",)}
_SIGN_OUT = {"claude_cli": ("auth", "logout"), "codex_cli": ("logout",)}
_open: dict[str, subprocess.Popen] = {}


def _console_options() -> dict:
    if os.name == "nt":
        return {"creationflags": subprocess.CREATE_NEW_CONSOLE}
    return {"start_new_session": True}


def open_sign_in(command: list[str], engine: str, env: dict[str, str]) -> None:
    """Start the CLI's own sign-in in a new console window; the user completes it there.

    One sign-in window per engine at a time: Codex's sign-in listens on one local port.
    """
    with _LOCK:
        running = _open.get(engine)
        if running is not None and running.poll() is None:
            raise AccountError(
                "A sign-in window for this engine is still open. Finish or close it first."
            )
        _open[engine] = subprocess.Popen(
            [*command, *_SIGN_IN[engine]], env=env, **_console_options()
        )


def sign_out(command: list[str], engine: str, env: dict[str, str]) -> bool:
    """Run the CLI's own sign-out for one profile folder. Output is never kept."""
    try:
        result = subprocess.run(
            [*command, *_SIGN_OUT[engine]],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            timeout=30,
            env=env,
            check=False,
            **(
                {"creationflags": subprocess.CREATE_NO_WINDOW}
                if os.name == "nt"
                else {"start_new_session": True}
            ),
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0
