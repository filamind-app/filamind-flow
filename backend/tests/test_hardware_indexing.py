"""Locks for the DB-1 performance foundation: canonical tile counts, ETag/304 caching,
precomputed-haystack search correctness, O(1) id lookups, and no internal-field leakage."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import create_app
from app.services import hardware_search, reference_data

client = TestClient(create_app())


def test_categories_counts_are_canonical() -> None:
    body = client.get("/api/hardware/categories").json()
    counts = body["counts"]
    # the four typed categories match their canonical entity sets, not the raw item rows
    by_name = {c.lower(): c for c in body["categories"]}
    boards_cat = next(c for lc, c in by_name.items() if "mcu" in lc and "board" in lc)
    assert counts[boards_cat] == len(reference_data.boards())
    motors_cat = next(c for lc, c in by_name.items() if "stepper" in lc and "motor" in lc)
    assert counts[motors_cat] == len(reference_data.motors())
    # canonical board count is far below the raw row count it used to show
    assert body["rawCounts"][boards_cat] > counts[boards_cat]
    # a generic catalog category matches its canonical list
    for cat, ents in reference_data.catalog().items():
        if cat in counts:
            assert counts[cat] == len(ents)


def test_etag_and_conditional_304() -> None:
    r = client.get("/api/hardware/boards", params={"limit": 1})
    assert r.status_code == 200
    etag = r.headers.get("ETag")
    assert etag and r.headers.get("Cache-Control")
    # a matching If-None-Match yields 304 with no body
    r2 = client.get("/api/hardware/boards", params={"limit": 1}, headers={"If-None-Match": etag})
    assert r2.status_code == 304
    assert not r2.content
    # a stale ETag re-fetches
    assert (
        client.get("/api/hardware/boards", headers={"If-None-Match": '"stale"'}).status_code == 200
    )


def test_precomputed_haystacks_match_onthefly_search() -> None:
    items = reference_data.hardware_items()
    hays = reference_data.item_haystacks()
    assert len(hays) == len(items)
    for q in ("tmc2209", "noctua", "e3d", "nema"):
        with_hay = hardware_search.search(items, q=q, limit=200, haystacks=hays)
        without = hardware_search.search(items, q=q, limit=200)
        assert with_hay["total"] == without["total"]


def test_no_internal_haystack_leak_in_responses() -> None:
    # flat search items and a board detail must not expose the internal "_hay" field
    flat = client.get("/api/hardware", params={"q": "board", "limit": 5}).json()
    assert all("_hay" not in it for it in flat["items"])
    bid = client.get("/api/hardware/boards", params={"limit": 1}).json()["boards"][0]["board_id"]
    assert "_hay" not in client.get(f"/api/hardware/boards/{bid}").json()


def test_id_lookups_resolve() -> None:
    assert reference_data.board_by_id("__nope__") is None
    one = reference_data.boards()[0]["board_id"]
    assert reference_data.board_by_id(one)["board_id"] == one
    assert reference_data.dataset_etag().startswith('W/"hw-')
