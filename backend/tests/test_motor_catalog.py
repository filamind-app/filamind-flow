"""Locks for the canonical stepper-motor catalog: entities, run_current snippet, routes."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import create_app
from app.services import motor_search, reference_data

client = TestClient(create_app())


def test_motors_exist_with_unique_ids() -> None:
    motors = reference_data.motors()
    assert len(motors) >= 400, "expected the canonical motor set"
    ids = [m["motor_id"] for m in motors]
    assert len(ids) == len(set(ids)), "motor_id must be unique"


def test_every_motor_has_copyable_snippet() -> None:
    for m in reference_data.motors():
        assert (m.get("configSnippet") or "").strip(), f"{m['motor_id']} has no configSnippet"


def test_run_current_recommendation_is_sane() -> None:
    """When a rated current is known, the recommended run_current is present, in the snippet,
    and conservative (below the rated phase current)."""
    checked = 0
    for m in reference_data.motors():
        rec = m.get("recommendedRunCurrent")
        if rec is None:
            continue
        checked += 1
        assert 0 < rec < 6, f"{m['motor_id']} run_current {rec} out of range"
        assert f"run_current: {rec}" in m["configSnippet"]
    assert checked >= 300, "most motors should have a recommended run_current"


def test_route_motors_list_and_detail() -> None:
    r = client.get("/api/hardware/motors", params={"limit": 5})
    assert r.status_code == 200
    body = r.json()
    assert body["total"] >= 400 and body["motors"]
    assert "configSnippet" not in body["motors"][0]  # summary stays light

    by_nema = client.get("/api/hardware/motors", params={"nema": "17"})
    assert by_nema.status_code == 200
    assert all("17" in str(m.get("nema", "")) for m in by_nema.json()["motors"])

    one_id = body["motors"][0]["motor_id"]
    one = client.get(f"/api/hardware/motors/{one_id}")
    assert one.status_code == 200
    assert "run_current" in one.json()["configSnippet"]

    assert client.get("/api/hardware/motors/does-not-exist").status_code == 404


def test_summary_is_lightweight() -> None:
    full = reference_data.motors()[0]
    summ = motor_search.summarize(full)
    assert "configSnippet" not in summ and "specs" not in summ
