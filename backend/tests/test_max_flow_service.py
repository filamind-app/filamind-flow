"""Tests for the Max-Flow planning / recommendation helpers (pure, no actuation)."""

from __future__ import annotations

import math
from typing import Any

import httpx
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


# ── live measurement loop (mocked client; no real motion) ─────────────────────
class _RunClient:
    """Stub MoonrakerClient for the run loop: scripted StallGuard samples + recorded g-code."""

    def __init__(
        self,
        sg_values: list[float],
        state: str = "standby",
        fail_on: str | None = None,
        config: dict[str, Any] | None = None,
    ) -> None:
        self._sg = iter(sg_values)
        self._state = state
        self._fail_on = fail_on
        # Default: a StallGuard-readable SG4 extruder (StealthChop on) so the C1 preflight passes.
        self._config = (
            config
            if config is not None
            else {"tmc2209 extruder": {"stealthchop_threshold": 999999}}
        )
        self.gcodes: list[str] = []

    async def query_objects(self, objects: list[str]) -> dict[str, Any]:
        if "print_stats" in objects:
            return {"print_stats": {"state": self._state}}
        if "configfile" in objects:
            return {"configfile": {"settings": self._config}}
        section = objects[0]
        try:
            value = next(self._sg)
        except StopIteration:
            value = 0.0
        return {section: {"sg_result": value}}

    async def run_gcode(self, script: str) -> None:
        self.gcodes.append(script)
        if self._fail_on and self._fail_on in script:
            raise httpx.HTTPError("simulated command failure")


_RUN_PARAMS: dict[str, Any] = {
    "temperature": 240,
    "start_flow": 5,
    "end_flow": 7,
    "step_flow": 1,
    "samples_per_step": 4,
    "extrude_per_step": 4,
}


async def test_run_clean_no_slip() -> None:
    client = _RunClient([100.0] * 12)  # 3 steps x 4 samples, perfectly steady
    out = await mfs.run_max_flow(client, RampParams(**_RUN_PARAMS))  # type: ignore[arg-type]
    assert out["slip_flow"] is None
    assert out["max_flow_mm3s"] == 7  # reached the highest tested flow
    assert out["sg_samples_seen"] is True
    assert "M109 S240" in client.gcodes  # waited for temperature
    assert "M83" in client.gcodes  # relative extrusion
    assert "M104 S0" in client.gcodes  # heater off at the end


async def test_run_detects_slip_and_stops() -> None:
    # Steps at flow 5 and 6 are steady; flow 7 is wildly erratic → slip there.
    # (All values stay above the SG4 bias floor of 50 so none are dropped by C2.)
    sg = [100.0] * 8 + [200.0, 1000.0, 200.0, 1000.0]
    client = _RunClient(sg)
    out = await mfs.run_max_flow(client, RampParams(**_RUN_PARAMS))  # type: ignore[arg-type]
    assert out["slip_flow"] == 7
    assert out["max_flow_mm3s"] == 6  # last clean step before slip
    assert "M104 S0" in client.gcodes


async def test_run_refused_when_busy() -> None:
    client = _RunClient([100.0] * 12, state="printing")
    with pytest.raises(mfs.MaxFlowBusyError):
        await mfs.run_max_flow(client, RampParams(temperature=240))  # type: ignore[arg-type]
    assert client.gcodes == []  # nothing was sent to the printer


async def test_run_turns_heater_off_on_error() -> None:
    client = _RunClient([100.0] * 12, fail_on="G1 E")  # first extrude move fails
    with pytest.raises(httpx.HTTPError):
        await mfs.run_max_flow(client, RampParams(**_RUN_PARAMS))  # type: ignore[arg-type]
    assert "M104 S0" in client.gcodes  # heater cut despite the failure


# ── H1: safe-extrusion temperature floor (180 °C) ─────────────────────────────
def test_temp_floor_is_180() -> None:
    with pytest.raises(ValueError):
        mfs.validate(RampParams(temperature=170))  # below the 180 floor
    mfs.validate(RampParams(temperature=180))  # exactly the floor is allowed


# ── C2: SG4 bias-region floor ─────────────────────────────────────────────────
def test_sg_floor_per_driver() -> None:
    assert mfs._sg_floor("tmc2209") == 50.0
    assert mfs._sg_floor("tmc2240") == 50.0
    assert mfs._sg_floor("tmc2130") == 0.0  # SG2 has no bias floor


async def test_run_drops_bias_region_samples() -> None:
    # Each step interleaves real load (100) with bias-region noise (40 < 50 floor → dropped),
    # so every step reduces to steady [100, 100] → no spurious slip.
    sg = [100.0, 40.0] * 6  # 3 steps x 4 samples
    client = _RunClient(sg)
    out = await mfs.run_max_flow(client, RampParams(**_RUN_PARAMS))  # type: ignore[arg-type]
    assert out["slip_flow"] is None
    assert out["max_flow_mm3s"] == 7
    assert out["sg_samples_seen"] is True


# ── C1: chopper-mode / StallGuard preflight ───────────────────────────────────
async def test_preflight_rejects_non_stallguard_driver() -> None:
    client = _RunClient([100.0] * 12)
    with pytest.raises(mfs.MaxFlowPreflightError):
        await mfs.run_max_flow(client, RampParams(temperature=240, driver="tmc2208"))  # type: ignore[arg-type]
    assert client.gcodes == []  # refused before heating


async def test_preflight_rejects_missing_extruder_section() -> None:
    client = _RunClient([100.0] * 12, config={})  # no [tmc2209 extruder] section
    with pytest.raises(mfs.MaxFlowPreflightError):
        await mfs.run_max_flow(client, RampParams(**_RUN_PARAMS))  # type: ignore[arg-type]


async def test_preflight_rejects_sg4_without_stealthchop() -> None:
    # SG4 (2209) with no stealthchop_threshold → StallGuard can't read → refuse.
    client = _RunClient([100.0] * 12, config={"tmc2209 extruder": {"run_current": "0.8"}})
    with pytest.raises(mfs.MaxFlowPreflightError):
        await mfs.run_max_flow(client, RampParams(**_RUN_PARAMS))  # type: ignore[arg-type]
    assert client.gcodes == []


async def test_preflight_rejects_sg2_in_stealthchop() -> None:
    # SG2 (2130) needs SpreadCycle; stealthchop on → refuse.
    client = _RunClient([100.0] * 12, config={"tmc2130 extruder": {"stealthchop_threshold": "500"}})
    with pytest.raises(mfs.MaxFlowPreflightError):
        await mfs.run_max_flow(client, RampParams(temperature=240, driver="tmc2130"))  # type: ignore[arg-type]


def test_tmc2240_sg_field_consistent_across_sources() -> None:
    """C3 lock: the tmc2240 StallGuard field agrees across the 3 sources (all sg4_thrs)."""
    import json
    from pathlib import Path

    from app.services import reference_data

    assert reference_data.stallguard_field("tmc2240") == "sg4_thrs"
    cat = json.loads(
        (Path(reference_data.__file__).parent.parent / "data" / "driver_catalog.json").read_text(
            encoding="utf-8"
        )
    )
    by_model = {
        d["model"]: d.get("stallguard_field") for d in cat.get("drivers", []) if isinstance(d, dict)
    }
    assert by_model.get("tmc2240") == "sg4_thrs"
