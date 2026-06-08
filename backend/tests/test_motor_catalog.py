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


def test_motors_carry_autotune_params() -> None:
    """Motors in the autotune database carry the full datasheet params (resistance / inductance /
    holding torque / current / steps) the Motor Drivers autotune + recommender need."""
    with_at = [m for m in reference_data.motors() if m.get("autotune")]
    assert len(with_at) >= 150, f"only {len(with_at)} motors have autotune params"
    for m in with_at:
        at = m["autotune"]
        assert at["resistance_ohm"] > 0 and at["inductance_H"] > 0, m["motor_id"]
        assert at["holding_torque_Nm"] > 0 and at["max_current_A"] > 0
        assert at["steps_per_rev"] >= 200


def test_motor_nema_and_step_angle_normalised() -> None:
    """Data-audit lock (Wave 4): stepAngle uses one encoding (degree sign, not '1.8 deg'/'1.8'),
    and NEMA was backfilled from part numbers so few motors are left sizeless."""
    import re

    motors = reference_data.motors()
    for m in motors:
        sa = str(m.get("stepAngle", "")).strip()
        assert not re.fullmatch(r"\d+(\.\d+)?(\s*deg)?", sa), (
            f"{m['motor_id']} stepAngle not normalised: {sa!r}"
        )
    by_id = {m["motor_id"]: m for m in motors}
    assert by_id["bigtre-17h4401s"]["nema"] == "17"  # backfilled from the part number
    sizeless = sum(1 for m in motors if not str(m.get("nema", "")).strip())
    assert sizeless <= 30, f"{sizeless} motors still have no NEMA size (backfill regressed)"


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
