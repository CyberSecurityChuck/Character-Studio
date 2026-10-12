"""Phase 6 review fixes: model choice for the subscription CLIs and built-in presets."""

import json

from tests.conftest import authorization, wait_for_job
from tests.test_generation import approved_scene
from tests.test_scenes import create_scene, set_engine


def runs(log):
    calls = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
    return [c["args"] for c in calls if "--version" not in c["args"] and "status" not in c["args"]]


def test_subscription_engines_use_the_chosen_model_or_their_default(engine_client, fake):
    client = engine_client
    # No model chosen: the CLI's own default (no model flag).
    scene = create_scene(client)
    job = wait_for_job(client, client.post(
        f"/api/scenes/{scene['id']}/analyse", headers=authorization(client)
    ).json()["active_job"]["id"])
    assert job["status"] == "completed" and job["model"] is None
    assert "--model" not in runs(fake)[-1]

    saved = set_engine(client, "claude_cli", models={"claude_cli": {"analysis": "opus"}})
    assert saved["models"] == {"claude_cli": {"analysis": "opus"}}
    second = create_scene(client, title="Second")
    job = wait_for_job(client, client.post(
        f"/api/scenes/{second['id']}/analyse", headers=authorization(client)
    ).json()["active_job"]["id"])
    args = runs(fake)[-1]
    assert job["model"] == "opus" and args[args.index("--model") + 1] == "opus"

    set_engine(client, "codex_cli", models={"codex_cli": {"analysis": "gpt-test"}})
    third = create_scene(client, title="Third")
    wait_for_job(client, client.post(
        f"/api/scenes/{third['id']}/analyse", headers=authorization(client)
    ).json()["active_job"]["id"])
    args = runs(fake)[-1]
    assert args[0] == "exec" and args[args.index("-m") + 1] == "gpt-test"
    assert args.index("-m") < args.index("--")

    bad = client.put("/api/engines/settings", headers=authorization(client), json={
        **client.get("/api/engines/settings").json(), "models": {"other_cli": {"analysis": "x"}}
    })
    assert bad.status_code == 422


def test_builtin_presets_are_listed_read_only_and_usable(engine_client, fake):
    client = engine_client
    headers = authorization(client)
    presets = client.get("/api/presets").json()
    builtins = [p for p in presets if p["builtin"]]
    assert len(builtins) == 10
    assert {p["category"] for p in builtins} == {"individual", "couple", "family", "friends"}
    first = builtins[0]
    body = {k: first[k] for k in ("name", "scene_changes", "negative_additions", "images")}
    assert client.put(f"/api/presets/{first['id']}", headers=headers,
                      json={**body, "revision": 1}).status_code == 409
    assert client.delete(f"/api/presets/{first['id']}", headers=headers).status_code == 409
    # Same name as a built-in is refused; a changed copy is saved as a new custom preset.
    assert client.post("/api/presets", headers=headers, json=body).status_code == 409
    copy = client.post("/api/presets", headers=headers, json={
        **body, "name": f"{first['name']} (mine)", "category": "couple"
    })
    assert copy.status_code == 201 and copy.json()["category"] == "couple"
    assert copy.json()["builtin"] is False

    _ada, scene = approved_scene(client)
    reply = client.post(f"/api/scenes/{scene['id']}/generate", headers=headers, json={
        "approval_id": scene["approval"]["current"]["id"], "preset_id": first["id"]
    })
    assert reply.status_code == 202, reply.text
    wait_for_job(client, reply.json()["active_job"]["id"])
    result = client.get(f"/api/scenes/{scene['id']}").json()["results"][0]
    assert result["preset"] == first["name"]
