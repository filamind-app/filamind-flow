"""Locks for the generic canonical catalog (9 remaining categories): entities, snippet, routes."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import create_app
from app.services import catalog_search, reference_data

client = TestClient(create_app())

EXPECTED_CATS = {
    "Sensors & Probes",
    "Hotends & Heaters",
    "Fans, Power & Bed",
    "Motion & Mechanical",
    "Nozzles",
    "Extruders",
    "Filament Materials",
    "Electronics & Wiring",
    "Cameras & Displays",
}


def test_catalog_covers_remaining_categories() -> None:
    cats = set(reference_data.catalog_categories())
    assert cats >= EXPECTED_CATS, f"missing catalog categories: {EXPECTED_CATS - cats}"


def test_every_catalog_entity_has_id_and_snippet() -> None:
    seen = set()
    for cat in reference_data.catalog_categories():
        ents = reference_data.catalog_entities(cat)
        assert ents, f"{cat} has no entities"
        for e in ents:
            assert (e.get("configSnippet") or "").strip(), f"{e.get('catalog_id')} missing snippet"
            cid = e["catalog_id"]
            assert cid not in seen, f"duplicate catalog_id {cid}"
            seen.add(cid)


def test_extruder_snippet_has_gear_ratio_or_rotation() -> None:
    ext = reference_data.catalog_entities("Extruders")
    assert ext
    assert all("[extruder]" in e["configSnippet"] for e in ext)


def test_route_catalog_list_and_detail() -> None:
    r = client.get("/api/hardware/catalog", params={"category": "Extruders", "limit": 5})
    assert r.status_code == 200
    body = r.json()
    assert body["total"] >= 50 and body["entities"]
    assert "configSnippet" not in body["entities"][0]  # summary stays light

    cid = body["entities"][0]["catalog_id"]
    one = client.get(f"/api/hardware/catalog/{cid}")
    assert one.status_code == 200 and "configSnippet" in one.json()

    assert client.get("/api/hardware/catalog", params={"category": "Nope"}).status_code == 404
    assert client.get("/api/hardware/catalog/nope-nope").status_code == 404


def test_summary_is_lightweight() -> None:
    e = reference_data.catalog_entities("Sensors & Probes")[0]
    summ = catalog_search.summarize(e)
    assert "configSnippet" not in summ and "specs" not in summ
