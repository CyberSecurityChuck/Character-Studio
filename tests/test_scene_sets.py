"""Phase 7A: Scenes page stages, scene sets and the free duplicate checks."""

import io
import random
import sqlite3

from fastapi.testclient import TestClient
from PIL import Image, ImageDraw

from backend.duplicates import NEAR_COPY_BITS, distance, fingerprint
from backend.main import create_app
from tests.conftest import authorization
from tests.test_generation import approved_scene
from tests.test_scenes import create_scene, import_manual


def drawing(seed: int, size=(900, 600), format="JPEG", quality=90) -> bytes:
    """A synthetic picture with structure, so its fingerprint is not trivially flat."""
    shapes = random.Random(seed)
    image = Image.new("RGB", (900, 600), tuple(shapes.randrange(256) for _ in range(3)))
    draw = ImageDraw.Draw(image)
    for _ in range(12):
        x, y = shapes.randrange(800), shapes.randrange(500)
        colour = tuple(shapes.randrange(256) for _ in range(3))
        draw.ellipse((x, y, x + shapes.randrange(80, 300), y + shapes.randrange(60, 250)), colour)
    image = image.resize(size)
    stream = io.BytesIO()
    image.save(stream, format, **({"quality": quality} if format == "JPEG" else {}))
    return stream.getvalue()


def check(client, content):
    return client.post(
        "/api/scene-imports/check",
        headers={**authorization(client), "Content-Type": "application/octet-stream"},
        content=content,
    )


def test_fingerprints_match_resaved_copies_and_not_other_pictures():
    original = fingerprint(drawing(1))
    for copy in (
        drawing(1, format="PNG"),
        drawing(1, format="WEBP"),
        drawing(1, size=(450, 300)),
        drawing(1, quality=40),
    ):
        assert distance(original, fingerprint(copy)) <= NEAR_COPY_BITS
    for other in (2, 3, 4, 5):
        assert distance(original, fingerprint(drawing(other))) > NEAR_COPY_BITS


def test_exact_copies_are_refused_unless_imported_anyway(client):
    first = create_scene(client, "Original", drawing(1), allow_duplicate=False)
    assert first["stage"] == "not_analysed" and first["problem"] is None

    checked = check(client, drawing(1)).json()
    assert [s["id"] for s in checked["exact"]] == [first["id"]]
    assert checked["near"] == []  # an exact copy is reported once, as exact
    near = check(client, drawing(1, format="PNG")).json()
    assert near["exact"] == [] and [s["id"] for s in near["near"]] == [first["id"]]
    assert near["near"][0]["distance"] <= NEAR_COPY_BITS
    unrelated = check(client, drawing(3)).json()
    assert (unrelated["exact"], unrelated["near"]) == ([], [])
    assert check(client, b"not an image").status_code == 422
    # The check stores nothing.
    assert len(client.get("/api/scenes").json()) == 1

    refused = client.post(
        "/api/scenes?title=Again",
        headers={**authorization(client), "Content-Type": "application/octet-stream"},
        content=drawing(1),
    )
    assert refused.status_code == 409 and "“Original” already uses this exact image" in refused.text
    assert len(client.get("/api/scenes").json()) == 1
    create_scene(client, "Again", drawing(1), allow_duplicate=True)
    # Near copies are only shown before import; the server accepts them.
    create_scene(client, "Re-saved", drawing(1, format="PNG"), allow_duplicate=False)
    assert len(client.get("/api/scenes").json()) == 3


def test_scene_sets_group_scenes_and_deleting_a_set_keeps_them(client):
    headers = authorization(client)
    beach = client.post("/api/scene-sets", headers=headers, json={"name": "Beach"})
    assert beach.status_code == 201
    beach = beach.json()
    for name, status in (("beach", 409), ("  ", 422)):
        assert (
            client.post("/api/scene-sets", headers=headers, json={"name": name}).status_code
            == status
        )

    inside = client.post(
        f"/api/scenes?title=Shore&scene_set_id={beach['id']}",
        headers={**headers, "Content-Type": "application/octet-stream"},
        content=drawing(2),
    ).json()
    assert inside["scene_set_id"] == beach["id"]
    gone = client.post(
        "/api/scenes?title=Lost&scene_set_id=" + "0" * 32,
        headers={**headers, "Content-Type": "application/octet-stream"},
        content=drawing(4),
    )
    assert gone.status_code == 422 and "no longer exists" in gone.text

    outside = create_scene(client, "Street", drawing(3))
    moved = client.put(
        "/api/scene-set-members",
        headers=headers,
        json={"scene_ids": [outside["id"]], "scene_set_id": beach["id"]},
    )
    assert moved.json() == {"moved": 1}
    # Organising is not an edit: the scene's revision stays, so open windows keep working.
    assert client.get(f"/api/scenes/{outside['id']}").json()["revision"] == outside["revision"]
    assert client.get("/api/scene-sets").json()[0]["scene_count"] == 2

    renamed = client.put(
        f"/api/scene-sets/{beach['id']}", headers=headers, json={"name": "Coast", "revision": 1}
    )
    assert renamed.json()["name"] == "Coast" and renamed.json()["revision"] == 2
    stale = client.put(
        f"/api/scene-sets/{beach['id']}", headers=headers, json={"name": "Sea", "revision": 1}
    )
    assert stale.status_code == 409

    out = client.put(
        "/api/scene-set-members",
        headers=headers,
        json={"scene_ids": [inside["id"]], "scene_set_id": None},
    )
    assert out.json() == {"moved": 1}
    assert client.get(f"/api/scenes/{inside['id']}").json()["scene_set_id"] is None
    # A duplicated scene stays in its source's set.
    copy = client.post(f"/api/scenes/{outside['id']}/duplicate", headers=headers).json()
    assert copy["scene_set_id"] == beach["id"]

    deleted = client.delete(f"/api/scene-sets/{beach['id']}?revision=2", headers=headers)
    assert deleted.json() == {"deleted": True, "scenes_kept": 2}
    assert client.get("/api/scene-sets").json() == []
    scenes = client.get("/api/scenes").json()
    assert len(scenes) == 3 and {s["scene_set_id"] for s in scenes} == {None}


def test_stages_and_problems_for_the_filters(client, settings):
    scene = create_scene(client, "Bike", drawing(5))
    import_manual(client, scene)
    # The sample analysis has an uncertainty to confirm, so the user's check is needed.
    assert client.get(f"/api/scenes/{scene['id']}").json()["stage"] == "needs_check"

    with sqlite3.connect(settings.data_dir / "studio.db") as db:
        db.execute(
            "INSERT INTO engine_jobs (id, kind, scene_id, engine, status, timeout_seconds, "
            "created_at, finished_at) VALUES ('j-old', 'analysis', ?, 'claude_cli', 'completed', "
            "300, '2026-11-01T00:00:00', '2026-11-01T00:01:00'), ('j-new', 'analysis', ?, "
            "'claude_cli', 'failed', 300, '2026-11-02T00:00:00', '2026-11-02T00:01:00')",
            (scene["id"], scene["id"]),
        )
    listed = next(s for s in client.get("/api/scenes").json() if s["id"] == scene["id"])
    assert listed["problem"] == {
        "kind": "analysis",
        "status": "failed",
        "at": "2026-11-02T00:01:00",
    }


def test_find_duplicates_skips_duplicate_scene_copies_and_fills_old_fingerprints(client, settings):
    headers = authorization(client)
    first = create_scene(client, "First", drawing(1), allow_duplicate=False)
    create_scene(client, "Exact", drawing(1), allow_duplicate=True)
    create_scene(client, "Near", drawing(1, size=(450, 300)), allow_duplicate=False)
    other = create_scene(client, "Other", drawing(2), allow_duplicate=False)
    client.post(f"/api/scenes/{other['id']}/duplicate", headers=headers)
    # Scenes from before Phase 7 have no fingerprint yet.
    with sqlite3.connect(settings.data_dir / "studio.db") as db:
        db.execute("UPDATE scenes SET perceptual_hash = NULL")

    found = client.get("/api/scene-duplicates").json()
    assert found["checked"] == 5
    assert [[s["title"] for s in group] for group in found["exact"]] == [["First", "Exact"]]
    assert [sorted(s["title"] for s in group) for group in found["near"]] == [
        ["Exact", "First", "Near"]
    ]
    with sqlite3.connect(settings.data_dir / "studio.db") as db:
        missing = db.execute("SELECT count(*) FROM scenes WHERE perceptual_hash IS NULL")
        assert missing.fetchone() == (0,)
    assert first["id"] in {s["id"] for s in found["exact"][0]}


def test_upgrade_from_region_edit_schema_records_earlier_approvals_as_single(settings):
    with TestClient(create_app(settings), base_url="http://127.0.0.1:8765") as client:
        _ada, scene = approved_scene(client)
    with sqlite3.connect(settings.data_dir / "studio.db") as db:
        db.execute("DROP TABLE scene_sets")
        db.execute("DROP INDEX ix_scenes_scene_set_id")
        db.execute("ALTER TABLE scenes DROP COLUMN scene_set_id")
        db.execute("ALTER TABLE scenes DROP COLUMN perceptual_hash")
        db.execute("ALTER TABLE approvals DROP COLUMN approval_mode")
        db.execute("UPDATE alembic_version SET version_num = '0012_region_edits'")
    with TestClient(create_app(settings), base_url="http://127.0.0.1:8765") as client:
        assert client.get("/api/health").json()["schema_revision"] == "0013_scene_sets"
        detail = client.get(f"/api/scenes/{scene['id']}").json()
        assert detail["approval"]["current"]["approval_mode"] == "single"
        assert (detail["stage"], detail["scene_set_id"]) == ("approved", None)
