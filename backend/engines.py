"""Official `claude` and `codex` CLIs as analysis and polish engines (DECISIONS.md D009).

Only flags confirmed in Phase 2.5 (docs/PROVIDER_FINDINGS.md) are used. The studio
launches the programs and reads their output files; it never reads, stores or
forwards their logins. Status checks keep only "found / version / signed in".
"""

import json
import os
import re
import shutil
import signal
import subprocess
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from backend.analysis_schema import (
    ENGINE_INSTRUCTION,
    AnalysisFormatError,
    SceneAnalysisData,
    parse_analysis_text,
    validate_analysis,
)

ENGINE_NAMES = {"claude_cli": "Claude", "codex_cli": "Codex"}
PROGRAMS = {"claude_cli": "claude", "codex_cli": "codex"}
# npm installs a .cmd shim on Windows. Running it would pass the prompt through cmd.exe,
# so run the package's own launcher with node instead (arguments stay exact).
NPM_LAUNCHERS = {
    "claude_cli": ("@anthropic-ai", "claude-code", "cli.js"),
    "codex_cli": ("@openai", "codex", "bin", "codex.js"),
}
SIGN_IN_HELP = {
    "claude_cli": "Open a terminal, run claude and sign in with your Claude account",
    "codex_cli": "Open a terminal, run codex login and sign in with your ChatGPT account",
}
# Variables that could redirect a run to a host app's session, an API key (per-use
# billing) or another endpoint. The CLIs then use only their own subscription login.
_DROP_PREFIXES = ("CLAUDE", "ANTHROPIC")
_DROP_NAMES = {"OPENAI_API_KEY", "OPENAI_BASE_URL", "CODEX_API_KEY"}
_LIMIT = re.compile(
    r"(usage|rate|plan)[ -]?limit|limit (has been |was )?reached|quota|too many requests"
    r"|\b429\b|hit your limit",
    re.IGNORECASE,
)
_SIGNED_OUT = re.compile(r"not logged in|/login|401|unauthori[sz]ed|sign in again", re.IGNORECASE)


class EngineError(Exception):
    """A run that failed for a reason the user can act on; the message is safe to show."""

    def __init__(self, kind: str, message: str):
        super().__init__(message)
        self.kind = kind
        self.message = message


def clean_environment() -> dict[str, str]:
    return {
        key: value
        for key, value in os.environ.items()
        if not key.upper().startswith(_DROP_PREFIXES) and key.upper() not in _DROP_NAMES
    }


def resolve_command(engine: str, overrides: dict | None = None) -> list[str] | None:
    if overrides and engine in overrides:
        return list(overrides[engine])
    found = shutil.which(PROGRAMS[engine])
    if not found:
        return None
    path = Path(found)
    if os.name == "nt" and path.suffix.lower() in {".cmd", ".bat"}:
        launcher = path.parent.joinpath("node_modules", *NPM_LAUNCHERS[engine])
        node = path.parent / "node.exe"
        node_path = str(node) if node.is_file() else shutil.which("node")
        if launcher.is_file() and node_path:
            return [node_path, str(launcher)]
        return None
    return [str(path)]


def _creation_options() -> dict:
    if os.name == "nt":
        flags = subprocess.CREATE_NEW_PROCESS_GROUP | getattr(subprocess, "CREATE_NO_WINDOW", 0)
        return {"creationflags": flags}
    return {"start_new_session": True}


def kill_tree(process: subprocess.Popen) -> None:
    """Stop the CLI and anything it started (npm launchers start a child process)."""
    if process.poll() is not None:
        return
    try:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                capture_output=True,
                timeout=15,
                check=False,
                **_creation_options(),
            )
        else:
            os.killpg(process.pid, signal.SIGKILL)
    except (OSError, subprocess.SubprocessError):
        pass
    try:
        process.kill()
        process.wait(timeout=10)
    except (OSError, subprocess.SubprocessError):
        pass


def _quick(argv: list[str], timeout: float = 20) -> subprocess.CompletedProcess:
    return subprocess.run(
        argv,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        env=clean_environment(),
        check=False,
        **_creation_options(),
    )


def engine_status(engine: str, overrides: dict | None = None) -> dict:
    """Found / version / signed in. Raw status output is never returned or stored."""
    name = ENGINE_NAMES[engine]
    status = {
        "engine": engine,
        "name": name,
        "installed": False,
        "version": None,
        "signed_in": False,
        "plan": None,
        "message": "",
    }
    command = resolve_command(engine, overrides)
    if command is None:
        status["message"] = f"{PROGRAMS[engine]} was not found on this PC."
        return status
    try:
        version = _quick([*command, "--version"])
        status["installed"] = version.returncode == 0
        status["version"] = (version.stdout.strip().splitlines() or [""])[0][:80] or None
        if not status["installed"]:
            status["message"] = f"{PROGRAMS[engine]} was found but did not start."
            return status
        if engine == "claude_cli":
            result = _quick([*command, "auth", "status"])
            try:
                details = json.loads(result.stdout)
            except json.JSONDecodeError:
                details = {}
            status["signed_in"] = details.get("loggedIn") is True
            plan = details.get("subscriptionType")
            status["plan"] = str(plan).capitalize()[:20] if status["signed_in"] and plan else None
        else:
            result = _quick([*command, "login", "status"])
            text = (result.stdout + result.stderr).lower()
            status["signed_in"] = "logged in" in text and "not logged in" not in text
            status["plan"] = "ChatGPT" if status["signed_in"] and "chatgpt" in text else None
    except (OSError, subprocess.SubprocessError):
        status["message"] = f"{PROGRAMS[engine]} could not be checked. Try again."
        return status
    if not status["signed_in"]:
        status["message"] = f"Signed out. {SIGN_IN_HELP[engine]}."
    return status


def require_ready(engine: str, overrides: dict | None = None) -> str | None:
    """Fail fast with a clear message before launching; returns the CLI version."""
    status = engine_status(engine, overrides)
    name = ENGINE_NAMES[engine]
    if not status["installed"]:
        raise EngineError(
            "not_installed",
            f"{name} ({PROGRAMS[engine]}) is not installed or could not start on this PC. "
            "Install it, sign in, then use Check again in Studio settings.",
        )
    if not status["signed_in"]:
        raise EngineError(
            "signed_out", f"{name} is signed out. {SIGN_IN_HELP[engine]}, then try again."
        )
    return status["version"]


@dataclass
class ProcessOutcome:
    exit_code: int | None
    timed_out: bool = False
    cancelled: bool = False
    seconds: float = 0


def run_process(
    argv: list[str],
    cwd: Path,
    stdout_path: Path,
    timeout: float,
    should_stop: Callable[[], bool] = lambda: False,
    on_start: Callable[[subprocess.Popen], None] = lambda _process: None,
) -> ProcessOutcome:
    """Run with stdin closed, output to files, an external timeout and a stop check."""
    started = time.monotonic()
    with stdout_path.open("wb") as stdout, (cwd / "stderr.txt").open("wb") as stderr:
        process = subprocess.Popen(
            argv,
            cwd=cwd,
            env=clean_environment(),
            stdin=subprocess.DEVNULL,
            stdout=stdout,
            stderr=stderr,
            **_creation_options(),
        )
        on_start(process)
        outcome = ProcessOutcome(exit_code=None)
        while True:
            try:
                outcome.exit_code = process.wait(timeout=0.25)
                break
            except subprocess.TimeoutExpired:
                pass
            if should_stop():
                outcome.cancelled = True
            elif time.monotonic() - started > timeout:
                outcome.timed_out = True
            else:
                continue
            kill_tree(process)
            outcome.exit_code = process.poll()
            break
    outcome.seconds = time.monotonic() - started
    return outcome


def analysis_command(engine: str, command: list[str], job_dir: Path, schema_json: str):
    """Return (argv, stdout file name). Flags exactly as confirmed in Phase 2.5."""
    if engine == "claude_cli":
        # --restricted confines file tools to the job folder and removes command/web tools.
        return [
            *command,
            "-p",
            ENGINE_INSTRUCTION,
            "--tools",
            "Read",
            "--restricted",
            "--strict-mcp-config",
            "--output-format",
            "json",
            "--json-schema",
            schema_json,
            "--no-session-persistence",
            "--permission-prompts",
            "none",
        ], "output.json"
    # Read-only sandbox with image generation off: Codex sees only the attached image.
    return [
        *command,
        "exec",
        "--skip-git-repo-check",
        "--ephemeral",
        "--ignore-user-config",
        "-s",
        "read-only",
        "--disable",
        "image_generation",
        "-C",
        str(job_dir),
        "-i",
        str(job_dir / "base.jpg"),
        "--output-schema",
        str(job_dir / "schema.json"),
        "-o",
        str(job_dir / "last-message.json"),
        "--json",
        "--",
        ENGINE_INSTRUCTION,
    ], "events.jsonl"


def polish_command(command: list[str], instruction: str, schema_json: str) -> list[str]:
    """Claude, text only: no tools at all (`--tools ""`), confined and without settings."""
    return [
        *command,
        "-p",
        instruction,
        "--tools",
        "",
        "--restricted",
        "--strict-mcp-config",
        "--output-format",
        "json",
        "--json-schema",
        schema_json,
        "--no-session-persistence",
        "--permission-prompts",
        "none",
    ]


def _tail(path: Path, limit: int = 400) -> str:
    try:
        text = path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return ""
    return text[-limit:]


def _classify(engine: str, text: str) -> EngineError:
    name = ENGINE_NAMES[engine]
    shown = text.strip()[:500] or "No details were given."
    if _SIGNED_OUT.search(text):
        return EngineError(
            "signed_out", f"{name} is signed out. {SIGN_IN_HELP[engine]}, then try again."
        )
    if _LIMIT.search(text):
        return EngineError(
            "usage_limit",
            f"{name}'s plan usage limit appears to be reached. Wait for it to reset, choose "
            f"another engine in Studio settings, or do it manually. {name} said: {shown}",
        )
    return EngineError("engine_error", f"{name} reported an error: {shown}")


def _check_timeout(engine: str, outcome: ProcessOutcome, fallback: str) -> None:
    if outcome.timed_out:
        raise EngineError(
            "timeout",
            f"{ENGINE_NAMES[engine]} did not finish in time, so the run was stopped. Try again, "
            f"raise the time limit in Studio settings, or {fallback}.",
        )


def _claude_envelope(job_dir: Path) -> dict:
    """Read `--output-format json`; raise EngineError for errors or unexpected output."""
    engine, name = "claude_cli", ENGINE_NAMES["claude_cli"]
    raw = (job_dir / "output.json").read_text(encoding="utf-8", errors="replace")
    if not raw.strip():
        raise _classify(engine, _tail(job_dir / "stderr.txt") or "No output.")
    try:
        envelope = json.loads(raw)
    except json.JSONDecodeError as error:
        raise EngineError("invalid_output", f"{name} replied in an unexpected format.") from error
    if not isinstance(envelope, dict):
        raise EngineError("invalid_output", f"{name} replied in an unexpected format.")
    if envelope.get("is_error"):
        raise _classify(engine, str(envelope.get("result") or envelope.get("subtype")))
    return envelope


def interpret_polish(job_dir: Path, outcome: ProcessOutcome, max_length: int) -> str:
    """Return the polished prompt text, or raise EngineError. The original is never touched."""
    _check_timeout("claude_cli", outcome, "edit the prompt by hand")
    try:
        envelope = _claude_envelope(job_dir)
    except OSError as error:
        raise EngineError("engine_error", "Claude's output could not be read.") from error
    structured = envelope.get("structured_output")
    if isinstance(structured, dict) and isinstance(structured.get("prompt"), str):
        text = structured["prompt"]
    else:
        text = str(envelope.get("result") or "")
    text = text.strip()
    if not text:
        raise EngineError("invalid_output", "Claude replied without a polished prompt.")
    if len(text) > max_length:
        raise EngineError("invalid_output", "Claude's polished prompt is too long to use.")
    return text


def interpret_analysis(engine: str, job_dir: Path, outcome: ProcessOutcome) -> SceneAnalysisData:
    """Turn a finished run into a validated analysis, or raise EngineError."""
    name = ENGINE_NAMES[engine]
    _check_timeout(engine, outcome, "do it manually")
    try:
        if engine == "claude_cli":
            envelope = _claude_envelope(job_dir)
            structured = envelope.get("structured_output")
            if structured is not None:
                return validate_analysis(structured)
            return parse_analysis_text(str(envelope.get("result") or ""))
        last = job_dir / "last-message.json"
        if last.is_file() and last.read_text(encoding="utf-8", errors="replace").strip():
            return parse_analysis_text(last.read_text(encoding="utf-8", errors="replace"))
        errors = []
        events = job_dir / "events.jsonl"
        if events.is_file():
            for line in events.read_text(encoding="utf-8", errors="replace").splitlines():
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if event.get("type") == "error":
                    errors.append(str(event.get("message", "")))
                elif event.get("type") == "turn.failed":
                    errors.append(str((event.get("error") or {}).get("message", "")))
        raise _classify(engine, (errors[-1] if errors else "") or _tail(job_dir / "stderr.txt"))
    except AnalysisFormatError as error:
        detail = str(error)
        raise EngineError(
            "invalid_output", f"{name} replied, but {detail[:1].lower()}{detail[1:]}"
        ) from error
    except OSError as error:
        raise EngineError("engine_error", f"{name}'s output could not be read.") from error
