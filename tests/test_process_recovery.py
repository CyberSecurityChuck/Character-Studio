"""Exercise persistence across a real killed server process, not just an ORM session."""

import json
import os
import socket
import subprocess
import sys
import time
from urllib.error import URLError
from urllib.request import Request, urlopen

from backend.configuration import PROJECT_ROOT
from tests.test_library import picture


def test_committed_preference_survives_process_termination(tmp_path):
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    env = {**os.environ, "STUDIO_DATA_DIR": str(tmp_path / "private"), "STUDIO_PORT": str(port)}
    base = f"http://127.0.0.1:{port}"

    def fetch(path, data=None, token=None, method=None):
        request = Request(
            base + path,
            data=data if isinstance(data, bytes) else json.dumps(data).encode() if data else None,
            method=method or ("PUT" if data else "GET"),
            headers={
                "Content-Type": "application/json",
                "X-Studio-Token": token or "",
            },
        )
        with urlopen(request, timeout=2) as response:
            return json.load(response)

    for iteration in range(2):
        process = subprocess.Popen(
            [sys.executable, "-B", "-m", "backend"],
            cwd=PROJECT_ROOT,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            for _ in range(100):
                assert process.poll() is None, "Server exited before becoming ready"
                try:
                    fetch("/api/health")
                    break
                except (URLError, TimeoutError):
                    time.sleep(0.1)
            else:
                raise AssertionError("Server failed to become ready")
            current = fetch("/api/bootstrap")
            if iteration == 0:
                assert (
                    fetch(
                        "/api/preferences",
                        {
                            "studio_name": "Restart verified",
                            "revision": 1,
                        },
                        current["session_token"],
                    )["revision"]
                    == 2
                )
                character = fetch(
                    "/api/characters",
                    {"name": "Restart character", "age_category": "Adult"},
                    current["session_token"],
                    "POST",
                )
                character = fetch(
                    f"/api/characters/{character['id']}/photos?revision=1",
                    picture(),
                    current["session_token"],
                    "POST",
                )
                group = fetch(
                    "/api/groups",
                    {"name": "Restart group", "member_ids": [character["id"]]},
                    current["session_token"],
                    "POST",
                )
            else:
                assert current["preferences"] == {
                    "studio_name": "Restart verified",
                    "revision": 2,
                }
                restored = fetch(f"/api/characters/{character['id']}")
                assert restored["photos"] == character["photos"]
                assert restored["group_ids"] == [group["id"]]
                with urlopen(base + restored["photos"][0]["original_url"], timeout=2) as response:
                    assert response.read() == picture()
        finally:
            process.kill()
            process.wait(timeout=5)
