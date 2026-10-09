"""Guard the recovery records and exclusions a fresh checkout depends on."""

import subprocess

from backend.configuration import PROJECT_ROOT


def test_recovery_entrypoints_and_dependency_locks_exist():
    for name in (
        "PLAN.md",
        "AGENTS.md",
        "PROJECT_STATUS.md",
        "SESSION_HANDOFF.md",
        "CHANGELOG.md",
        "DECISIONS.md",
        "README.md",
        "docs/CONTINUITY.md",
        "docs/RECOVERY.md",
        "uv.lock",
        "frontend/package-lock.json",
        "Start-Studio.cmd",
        "Stop-Studio.cmd",
    ):
        assert (PROJECT_ROOT / name).is_file(), f"Missing recovery dependency: {name}"
        assert (PROJECT_ROOT / name).stat().st_size > 0
    instructions = (PROJECT_ROOT / "AGENTS.md").read_text(encoding="utf-8")
    for name in ("PLAN.md", "PROJECT_STATUS.md", "SESSION_HANDOFF.md", "DECISIONS.md"):
        assert name in instructions, f"Fresh sessions are not directed to {name}"
    assert "Phase 2" in instructions


def test_git_excludes_private_material_but_retains_source_and_locks():
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
    result = subprocess.run(
        ["git", "check-ignore", "--no-index", "--stdin", "-z"],
        cwd=PROJECT_ROOT,
        input="\0".join(private + ["PLAN.md", "uv.lock", "frontend/package-lock.json"]) + "\0",
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert set(result.stdout.rstrip("\0").split("\0")) == set(private)
