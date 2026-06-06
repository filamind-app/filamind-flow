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


# ── shipped dataset sanity + data-quality gates ───────────────────────────────
def test_dataset_loaded_and_clean() -> None:
    items = reference_data.hardware_items()
    assert len(items) > 3000  # the curated component DB
    cats = reference_data.hardware_categories()
    assert len(cats) >= 10
    mans = reference_data.hardware_manufacturers()
    assert len(mans) > 100
    # No external-project provenance leaked into the published dataset.
    import json

    blob = json.dumps({"i": items, "m": mans, "c": cats}, ensure_ascii=False).lower()
    for banned in (
        "ratos",
        "klipper_tmc_autotune",
        "shake&tune",
        "shaketune",
        "fragmon",
        "klippain",
        "gpl-3",
    ):
        assert banned not in blob, f"leaked: {banned}"
    # Every item has the core shape (now including a non-empty name).
    for it in items:
        assert "category" in it and "manufacturer" in it and "specs" in it and "name" in it


def test_data_quality_gates() -> None:
    """Lock the identity-hygiene fixes so the defects can't regress (audit §4c.5)."""
    import json

    items = reference_data.hardware_items()
    empty_name = [i for i in items if not str(i.get("name", "")).strip()]
    assert empty_name == [], f"{len(empty_name)} items have an empty name"
    # No exact-duplicate full records.
    seen = [
        (i["category"], i["manufacturer"], i["name"], json.dumps(i["specs"], sort_keys=True))
        for i in items
    ]
    assert len(seen) == len(set(seen)), "exact-duplicate item records present"
    # Manufacturer-directory rows must not pollute the product list.
    leaked_dir = [i for i in items if {"Country", "Website", "Specialty"} <= set(i["specs"])]
    assert leaked_dir == [], f"{len(leaked_dir)} manufacturer-directory rows leaked into items"


def test_no_category_was_gutted() -> None:
    """Regression: the v0.108.0 over-clean dropped 605 stepper products; they were
    restored in v0.109.0. Lock per-category floors so a regen can never silently
    gut a whole category again (audit follow-up — restore-not-delete)."""
    from collections import Counter

    items = reference_data.hardware_items()
    by_cat = Counter(i["category"] for i in items)
    floors = {
        "Stepper Motors": 600,  # 641 after restore (was wrongly 64)
        "Electronics & Wiring": 190,  # 195 after restore
        "MCU & Boards": 1000,
        "Sensors & Probes": 200,
    }
    for cat, floor in floors.items():
        assert by_cat[cat] >= floor, (
            f"{cat} has {by_cat[cat]} rows, below floor {floor} — data loss?"
        )


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
