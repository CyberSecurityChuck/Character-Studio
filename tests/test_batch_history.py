"""7C review (D038): the Batches tab's full history with its filters and scene search."""

from tests.test_batches import post, two_approved_scenes, wait_for_batch
from tests.test_preparation import add_scene, make_set


def history(client, **params):
    return client.get("/api/batches/history", params=params).json()


def test_history_lists_every_batch_and_filters_by_kind_set_and_scene(engine_client, fake):
    client = engine_client
    harbour, market = make_set(client, "Harbour"), make_set(client, "Market")
    pier = add_scene(client, "Pier at dawn", harbour)
    stall = add_scene(client, "Fruit stall", market)
    loose = add_scene(client, "Loose scene")
    analyses = [
        post(client, "/api/batches/analysis", {"scene_ids": [s["id"]]})["batch"]
        for s in (pier, stall, loose)
    ]
    first, second = two_approved_scenes(client)
    images = post(
        client,
        "/api/batches/generation",
        {"items": [{"scene_id": s["id"]} for s in (first, second)], "count": 1},
    )["batch"]
    for batch in [*analyses, images]:
        wait_for_batch(client, batch["id"])

    everything = history(client)
    assert everything["total"] == 4
    # Newest first, both kinds, each with its rows and their statuses.
    assert [b["id"] for b in everything["batches"]] == [
        images["id"], *[b["id"] for b in reversed(analyses)]
    ]
    assert {i["status"] for b in everything["batches"] for i in b["items"]} == {"completed"}
    assert everything["batches"][0]["items"][0]["result_version"] == 1

    assert [b["kind"] for b in history(client, kind="generation")["batches"]] == ["generation"]
    assert history(client, kind="analysis")["total"] == 3
    in_harbour = history(client, scene_set_id=harbour["id"])["batches"]
    assert [b["id"] for b in in_harbour] == [analyses[0]["id"]]
    # "none": batches with a scene that is in no set (the loose scene and the two approved).
    assert history(client, scene_set_id="none")["total"] == 2
    found = history(client, scene="STALL")["batches"]
    assert [b["id"] for b in found] == [analyses[1]["id"]]
    assert history(client, scene="stall", kind="generation")["total"] == 0
    assert len(history(client, limit=2)["batches"]) == 2
