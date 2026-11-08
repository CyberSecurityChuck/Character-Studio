"""Guard the recovery records and exclusions a fresh checkout depends on."""

import subprocess

import pytest

from backend.configuration import PROJECT_ROOT

# AI work-session notes: on the developer's computer only, never in Git (D040).
LOCAL_NOTES = (
    "AGENTS.md",
    "PLAN.md",
    "DECISIONS.md",
    "PROJECT_STATUS.md",
    "SESSION_HANDOFF.md",
    "docs/CONTINUITY.md",
)


def test_recovery_entrypoints_and_dependency_locks_exist():
    for name in (
        "CHANGELOG.md",
        "README.md",
        "docs/USER_GUIDE.md",
        "docs/RECOVERY.md",
        "uv.lock",
        "frontend/package-lock.json",
        "Start-Studio.cmd",
        "Stop-Studio.cmd",
    ):
        assert (PROJECT_ROOT / name).is_file(), f"Missing recovery dependency: {name}"
        assert (PROJECT_ROOT / name).stat().st_size > 0


def test_local_development_notes_direct_fresh_sessions():
    if not (PROJECT_ROOT / "AGENTS.md").is_file():
        pytest.skip("Local development notes are not in this checkout (they are never in Git)")
    for name in LOCAL_NOTES:
        assert (PROJECT_ROOT / name).is_file(), f"Missing development note: {name}"
        assert (PROJECT_ROOT / name).stat().st_size > 0
    instructions = (PROJECT_ROOT / "AGENTS.md").read_text(encoding="utf-8")
    for name in ("PLAN.md", "PROJECT_STATUS.md", "SESSION_HANDOFF.md", "DECISIONS.md"):
        assert name in instructions, f"Fresh sessions are not directed to {name}"
    assert "Phase 2" in instructions


def test_git_excludes_private_material_and_notes_but_retains_source_and_locks():
    private = [
        ".env",
        "family.jpg",
        "references/person.png",
        "studio.db",
        "studio.db-wal",
        "exports/package.zip",
        "backups/private.db",
        "server.stderr.log",
    ]
    kept = [
        "README.md",
        "CHANGELOG.md",
        "docs/USER_GUIDE.md",
        "uv.lock",
        "frontend/package-lock.json",
    ]
    result = subprocess.run(
        ["git", "check-ignore", "--no-index", "--stdin", "-z"],
        cwd=PROJECT_ROOT,
        input="\0".join(private + list(LOCAL_NOTES) + kept) + "\0",
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert set(result.stdout.rstrip("\0").split("\0")) == set(private) | set(LOCAL_NOTES)
    tracked = subprocess.run(
        ["git", "ls-files", "--", *LOCAL_NOTES],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=True,
    )
    assert tracked.stdout == "", f"Development notes are tracked: {tracked.stdout}"
