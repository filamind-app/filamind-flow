"""Tests for the hardware search service + routes, and the shipped dataset."""

from __future__ import annotations

from typing import Any

from app.services import hardware_search, reference_data

ITEMS: list[dict[str, Any]] = [
    {
        "category": "Hotends",
        "manufacturer": "E3D",
        "name": "Revo Six",
        "specs": {"Max temp": "300"},
    },
    {
        "category": "Hotends",
        "manufacturer": "Phaetus",
        "name": "Rapido HF",
        "specs": {"Flow": "50"},
    },
    {
        "category": "Stepper Motors",
        "manufacturer": "LDO",
        "name": "42STH48",
        "specs": {"NEMA": "17"},
    },
]


def test_search_no_filters_paginates() -> None:
    out = hardware_search.search(ITEMS, limit=2, offset=0)
    assert out["total"] == 3
    assert out["count"] == 2
    assert len(out["items"]) == 2
    page2 = hardware_search.search(ITEMS, limit=2, offset=2)
    assert page2["count"] == 1


def test_search_category_exact() -> None:
    out = hardware_search.search(ITEMS, category="hotends")
    assert out["total"] == 2
    assert all(i["category"] == "Hotends" for i in out["items"])


def test_search_manufacturer_substring() -> None:
    out = hardware_search.search(ITEMS, manufacturer="e3d")
    assert out["total"] == 1
    assert out["items"][0]["name"] == "Revo Six"


def test_search_freetext_matches_specs() -> None:
    # "50" only appears in Rapido's Flow spec.
    out = hardware_search.search(ITEMS, q="50")
    assert out["total"] == 1
    assert out["items"][0]["name"] == "Rapido HF"
    # name match
    assert hardware_search.search(ITEMS, q="revo")["total"] == 1


def test_search_limit_capped() -> None:
    out = hardware_search.search(ITEMS, limit=99999)
    assert out["limit"] <= 200


# ── shipped dataset sanity ────────────────────────────────────────────────────
def test_dataset_loaded_and_clean() -> None:
    items = reference_data.hardware_items()
    assert len(items) > 1000  # the curated DB is sizable
    cats = reference_data.hardware_categories()
    assert len(cats) >= 10
    mans = reference_data.hardware_manufacturers()
    assert len(mans) > 100
    # No external-project provenance leaked into the published dataset.
    import json

    blob = json.dumps({"i": items[:5000], "m": mans, "c": cats}, ensure_ascii=False).lower()
    for banned in ("ratos", "klipper_tmc_autotune", "shake&tune", "shaketune"):
        assert banned not in blob, f"leaked: {banned}"
    # Every item has the core shape.
    for it in items[:50]:
        assert "category" in it and "manufacturer" in it and "specs" in it


# ── routes ────────────────────────────────────────────────────────────────────
def test_route_hardware_search() -> None:
    from fastapi.testclient import TestClient

    from app.main import create_app

    client = TestClient(create_app())
    resp = client.get("/api/hardware", params={"limit": 5})
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] > 1000
    assert body["count"] == 5


def test_route_hardware_categories_and_manufacturers() -> None:
    from fastapi.testclient import TestClient

    from app.main import create_app

    client = TestClient(create_app())
    cats = client.get("/api/hardware/categories")
    assert cats.status_code == 200
    assert cats.json()["total"] > 1000
    mans = client.get("/api/hardware/manufacturers")
    assert mans.status_code == 200
    assert len(mans.json()) > 100
