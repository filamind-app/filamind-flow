"""Tests for the Config Templates library data + route."""

from __future__ import annotations

import json

from app.services import reference_data


def test_templates_shape() -> None:
    tpls = reference_data.templates()
    assert len(tpls) >= 10
    ids = set()
    for t in tpls:
        for key in ("id", "name", "category", "description", "body"):
            assert key in t, f"{t.get('id')} missing {key}"
        assert t["body"], f"{t['id']} has empty body"
        assert t["name"] and t["category"], f"{t['id']} missing name/category"
        ids.add(t["id"])
    assert len(ids) == len(tpls)  # unique ids
    # A few expected templates exist.
    assert {"print_start", "print_end", "input_shaper"} <= ids
    cats = {t["category"] for t in tpls}
    assert "Macros" in cats and "Config blocks" in cats


def test_templates_no_external_refs() -> None:
    blob = json.dumps(reference_data.templates(), ensure_ascii=False).lower()
    for banned in ("ratos", "klipper_tmc_autotune", "shake&tune", "shaketune", "fragmon"):
        assert banned not in blob, f"leaked: {banned}"


def test_route_templates() -> None:
    from fastapi.testclient import TestClient

    from app.main import create_app

    resp = TestClient(create_app()).get("/api/reference/templates")
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body, list) and len(body) >= 10
    assert any(t["id"] == "print_start" for t in body)
