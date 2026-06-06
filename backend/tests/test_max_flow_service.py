"""Tests for the Max-Flow planning / recommendation helpers (pure, no actuation)."""

from __future__ import annotations

import math
from typing import Any

import pytest

from app.services import max_flow_service as mfs
from app.services import reference_data
from app.services.max_flow_service import RampParams


def test_filament_area_and_feedrate() -> None:
    area = mfs.filament_area(1.75)
    assert area == pytest.approx(math.pi * 0.875 * 0.875, rel=1e-9)
    # 10 mm³/s through 1.75 mm filament → ~249.5 mm/min
    assert mfs.flow_to_feedrate(10.0, 1.75) == pytest.approx(10.0 / area * 60.0, rel=1e-9)
    # Thicker filament needs a slower feedrate for the same flow.
    assert mfs.flow_to_feedrate(10.0, 2.85) < mfs.flow_to_feedrate(10.0, 1.75)


def test_plan_ramp_steps_and_ascending_feedrate() -> None:
    steps = mfs.plan_ramp(RampParams(temperature=240, start_flow=5, end_flow=10, step_flow=1))
    assert [s.flow_mm3s for s in steps] == [5, 6, 7, 8, 9, 10]  # end inclusive
    feeds = [s.feedrate_mm_min for s in steps]
    assert feeds == sorted(feeds)  # feedrate rises with flow
    assert all(s.extrude_mm == 5.0 for s in steps)


def test_plan_ramp_fractional_step_inclusive() -> None:
    steps = mfs.plan_ramp(RampParams(temperature=240, start_flow=5, end_flow=6, step_flow=0.5))
    assert [s.flow_mm3s for s in steps] == [5.0, 5.5, 6.0]


@pytest.mark.parametrize(
    "kw",
    [
        {"temperature": 100},  # too cold
        {"temperature": 400},  # too hot
        {"temperature": 240, "start_flow": 10, "end_flow": 5},  # end <= start
        {"temperature": 240, "step_flow": 0},  # non-positive step
        {"temperature": 240, "filament_diameter": 0.5},  # too thin
        {"temperature": 240, "extrude_per_step": 0.1},  # too small
        {"temperature": 240, "samples_per_step": 1},  # too few
        {"temperature": 240, "start_flow": 1, "end_flow": 300, "step_flow": 1},  # too many steps
    ],
)
def test_validate_rejects_bad_params(kw: dict[str, Any]) -> None:
    with pytest.raises(ValueError):
        mfs.validate(RampParams(**kw))


def test_recommend() -> None:
    rec = mfs.recommend(20.0)
    assert rec == {"max": 20.0, "conservative": 16.0, "balanced": 18.0}
    assert mfs.recommend(None) == {"max": None, "conservative": None, "balanced": None}
    assert mfs.recommend(0) == {"max": None, "conservative": None, "balanced": None}


def test_hotend_hint() -> None:
    rows = reference_data.hotends()
    assert rows, "reference hotend table should be non-empty"
    name = str(rows[0]["name"])
    hit = mfs.hotend_hint(name)
    assert hit is not None and hit["name"] == name
    assert mfs.hotend_hint(None) is None
    assert mfs.hotend_hint("nonexistent-hotend-xyz") is None


def test_plan_shape() -> None:
    out = mfs.plan(
        RampParams(temperature=240, start_flow=5, end_flow=9, step_flow=1, driver="TMC2209")
    )
    assert out["driver"] == "tmc2209"
    assert out["stallguard_field"] == reference_data.stallguard_field("tmc2209")
    assert out["step_count"] == 5
    assert out["total_extrude_mm"] == pytest.approx(25.0)
    assert len(out["steps"]) == 5
    assert out["steps"][0]["flow_mm3s"] == 5


# ── route-level ──────────────────────────────────────────────────────────────
def test_route_plan_ok() -> None:
    from fastapi.testclient import TestClient

    from app.main import create_app

    resp = TestClient(create_app()).post(
        "/api/maxflow/plan",
        json={"temperature": 240, "start_flow": 5, "end_flow": 12, "step_flow": 1},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["step_count"] == 8
    assert body["steps"][0]["feedrate_mm_min"] > 0


def test_route_plan_bad_temp_400() -> None:
    from fastapi.testclient import TestClient

    from app.main import create_app

    resp = TestClient(create_app()).post("/api/maxflow/plan", json={"temperature": 50})
    assert resp.status_code == 400
