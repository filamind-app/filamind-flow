"""Max-flow measurement planning + slicer recommendations (Track B foundation).

Pure, hardware-free helpers for the Max-Flow widget:

* convert a volumetric flow (mm³/s) to an extruder feedrate (mm/min) for a filament,
* plan the ramp of flow steps a run would execute — a preview shown *before* any actuation,
* turn a measured max flow into conservative slicer values,
* match a hotend to the reference melt-zone / expected-flow table.

Everything here is pure and testable without a printer. The actuating measurement loop
(heat → extrude → sample StallGuard) and the live run land in a later slice; the slip
analysis itself lives in :mod:`app.services.max_flow`.
"""

from __future__ import annotations

import contextlib
import math
from dataclasses import dataclass
from typing import Any

from app.services import max_flow, reference_data
from app.services.max_flow import StepMeasurement
from app.services.moonraker_client import MoonrakerClient

# Safety bounds for a run request — rejected outside these.
# Safe-extrusion floor: a max-flow test below this risks reading cold-extrusion grind as slip.
_TEMP_MIN, _TEMP_MAX = 180.0, 350.0
_DIAM_MIN, _DIAM_MAX = 1.0, 3.5
_EXTRUDE_MIN, _EXTRUDE_MAX = 1.0, 50.0
_SAMPLES_MIN, _SAMPLES_MAX = 3, 200
_MAX_STEPS = 60

#: Fractions of the measured max flow suggested as slicer "max volumetric speed" values.
_CONSERVATIVE = 0.80
_BALANCED = 0.90

#: The printer-object name for the extruder, and how its TMC driver section is named.
_EXTRUDER = "extruder"


class MaxFlowBusyError(RuntimeError):
    """Raised when a run is refused because the printer is busy."""


class MaxFlowPreflightError(RuntimeError):
    """Raised when the extruder driver is not configured to read StallGuard for this test."""


#: StallGuard families. SG4 (2209 / 2240) reads only in StealthChop; SG2 reads in SpreadCycle.
_SG4_DRIVERS = frozenset({"tmc2209", "tmc2240"})
_SG2_DRIVERS = frozenset({"tmc2130", "tmc5160", "tmc2660"})


@dataclass(frozen=True)
class RampParams:
    """Inputs for a max-flow run (and its dry-run plan). ``temperature`` is required."""

    temperature: float
    start_flow: float = 5.0
    end_flow: float = 25.0
    step_flow: float = 1.0
    filament_diameter: float = 1.75
    extrude_per_step: float = 5.0
    samples_per_step: int = 20
    driver: str = "tmc2209"


@dataclass(frozen=True)
class RampStep:
    """One planned step: the requested flow, the feedrate that yields it, and how much to push."""

    flow_mm3s: float
    feedrate_mm_min: float
    extrude_mm: float


def filament_area(diameter_mm: float) -> float:
    """Cross-sectional area (mm²) of round filament."""
    radius = diameter_mm / 2.0
    return math.pi * radius * radius


def flow_to_feedrate(flow_mm3s: float, diameter_mm: float) -> float:
    """Extruder feedrate (mm/min) that delivers ``flow_mm3s`` for this filament.

    ``flow = area * linear_speed``, so ``feedrate = flow / area * 60``.
    """
    area = filament_area(diameter_mm)
    if area <= 0:
        raise ValueError("filament diameter must be positive")
    return (flow_mm3s / area) * 60.0


def validate(params: RampParams) -> None:
    """Raise :class:`ValueError` if a run request is unsafe or malformed."""
    if not (_TEMP_MIN <= params.temperature <= _TEMP_MAX):
        raise ValueError(f"temperature must be {_TEMP_MIN:.0f}-{_TEMP_MAX:.0f} °C")
    if not (_DIAM_MIN <= params.filament_diameter <= _DIAM_MAX):
        raise ValueError(f"filament diameter must be {_DIAM_MIN}-{_DIAM_MAX} mm")
    if params.start_flow <= 0 or params.end_flow <= 0 or params.step_flow <= 0:
        raise ValueError("flows and step must be positive")
    if params.end_flow <= params.start_flow:
        raise ValueError("end_flow must exceed start_flow")
    if not (_EXTRUDE_MIN <= params.extrude_per_step <= _EXTRUDE_MAX):
        raise ValueError(f"extrude_per_step must be {_EXTRUDE_MIN}-{_EXTRUDE_MAX} mm")
    if not (_SAMPLES_MIN <= params.samples_per_step <= _SAMPLES_MAX):
        raise ValueError(f"samples_per_step must be {_SAMPLES_MIN}-{_SAMPLES_MAX}")
    count = math.floor((params.end_flow - params.start_flow) / params.step_flow) + 1
    if count > _MAX_STEPS:
        raise ValueError(f"too many steps ({count} > {_MAX_STEPS}); increase step_flow")


def plan_ramp(params: RampParams) -> list[RampStep]:
    """The ascending flow steps a run would execute (validated first)."""
    validate(params)
    steps: list[RampStep] = []
    eps = params.step_flow * 1e-6
    flow = params.start_flow
    while flow <= params.end_flow + eps:
        steps.append(
            RampStep(
                flow_mm3s=round(flow, 3),
                feedrate_mm_min=round(flow_to_feedrate(flow, params.filament_diameter), 1),
                extrude_mm=params.extrude_per_step,
            )
        )
        flow += params.step_flow
    return steps


def recommend(max_flow_mm3s: float | None) -> dict[str, Any]:
    """Conservative slicer "max volumetric speed" values from a measured max flow."""
    if max_flow_mm3s is None or max_flow_mm3s <= 0:
        return {"max": None, "conservative": None, "balanced": None}
    return {
        "max": round(max_flow_mm3s, 1),
        "conservative": round(max_flow_mm3s * _CONSERVATIVE, 1),  # 80% — safe everyday
        "balanced": round(max_flow_mm3s * _BALANCED, 1),  # 90% — pushing it
    }


def hotend_hint(name: str | None) -> dict[str, Any] | None:
    """The reference hotend row matching ``name`` (case-insensitive substring), if any."""
    if not name:
        return None
    needle = name.strip().lower()
    if not needle:
        return None
    for row in reference_data.hotends():
        label = str(row.get("name", "")).lower()
        if needle in label or (label and label in needle):
            return row
    return None


def plan(params: RampParams) -> dict[str, Any]:
    """Full dry-run preview: the ramp + the driver's StallGuard field + totals.

    Pure — no actuation. The UI shows this so the operator sees exactly what *would* run
    (every flow step, feedrate, total filament pushed) before committing to a live test.
    """
    steps = plan_ramp(params)
    return {
        "driver": params.driver.lower(),
        "stallguard_field": reference_data.stallguard_field(params.driver),
        "temperature": params.temperature,
        "filament_diameter": params.filament_diameter,
        "samples_per_step": params.samples_per_step,
        "step_count": len(steps),
        "total_extrude_mm": round(len(steps) * params.extrude_per_step, 1),
        "steps": [
            {
                "flow_mm3s": s.flow_mm3s,
                "feedrate_mm_min": s.feedrate_mm_min,
                "extrude_mm": s.extrude_mm,
            }
            for s in steps
        ],
    }


# ── Live measurement loop (actuating — heat + extrude + sample StallGuard) ──────
async def _is_busy(client: MoonrakerClient) -> bool:
    """True while the printer is printing, paused, or in error — block a run then."""
    status = await client.query_objects(["print_stats"])
    stats = status.get("print_stats")
    if not isinstance(stats, dict):
        return False
    return str(stats.get("state", "")).lower() in ("printing", "paused", "error")


def _extract_sg(obj: dict[str, Any]) -> float | None:
    """Best-effort live StallGuard load from an extruder-TMC object's status.

    The exact field carrying the *live* StallGuard load during extrusion varies by driver
    family / Klipper version (the 2209 SG4 path especially), so several candidates are tried
    in order. A live run validates which one is populated; ``sg_samples_seen`` in the result
    flags when none was found so the operator knows to adjust.
    """
    for key in ("sg_result", "SG_RESULT", "sg"):
        value = obj.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return float(value)
    drv = obj.get("drv_status")
    if isinstance(drv, dict):
        for key in ("sg_result", "SG_RESULT", "sg", "SGRESULT"):
            value = drv.get(key)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                return float(value)
    return None


def _as_float(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _sg_floor(driver: str) -> float:
    """Below this StallGuard reading is bias-region noise (SG4 sticks low under the min velocity),
    not real load — drop such samples. 0 for SG2 (no floor)."""
    consts = reference_data.resolved_profile(driver).get("constants", {})
    value = consts.get("SG_MIN_INFORMATIVE") if isinstance(consts, dict) else None
    return _as_float(value) or 0.0


async def _extruder_section(client: MoonrakerClient, driver: str) -> dict[str, Any] | None:
    """The live ``[<driver> extruder]`` config section, or None if absent."""
    configfile = await client.query_objects(["configfile"])
    obj = configfile.get("configfile")
    if not isinstance(obj, dict):
        return None
    for key in ("settings", "config"):
        sections = obj.get(key)
        if isinstance(sections, dict):
            section = sections.get(f"{driver} extruder")
            if isinstance(section, dict):
                return section
    return None


async def _preflight(client: MoonrakerClient, driver: str) -> None:
    """Verify the extruder driver can actually read StallGuard for this test (C1).

    Refuses a driver with no StallGuard, a missing ``[<driver> extruder]`` section, or a chopper
    mode that makes StallGuard meaningless (SG4 needs StealthChop; SG2 needs SpreadCycle) — so the
    run can't silently measure garbage.

    Raises:
        MaxFlowPreflightError: if the driver/config can't yield a valid StallGuard signal.
    """
    d = driver.lower()
    field = reference_data.stallguard_field(d)
    if not field:
        raise MaxFlowPreflightError(
            f"Driver '{driver}' has no StallGuard — max-flow needs a StallGuard-capable "
            "extruder driver."
        )
    section = await _extruder_section(client, d)
    if section is None:
        raise MaxFlowPreflightError(
            f"No [{d} extruder] section found — the extruder's TMC driver must be configured first."
        )
    stealth = _as_float(section.get("stealthchop_threshold"))
    stealth_on = stealth is not None and stealth > 0
    if d in _SG4_DRIVERS and not stealth_on:
        raise MaxFlowPreflightError(
            f"StallGuard4 ({field}) only reads in StealthChop — set a non-zero "
            f"stealthchop_threshold on [{d} extruder] before running max-flow."
        )
    if d in _SG2_DRIVERS and stealth_on:
        raise MaxFlowPreflightError(
            f"StallGuard2 ({field}) only reads in SpreadCycle — remove/zero the "
            f"stealthchop_threshold on [{d} extruder] before running max-flow."
        )


async def run_max_flow(client: MoonrakerClient, params: RampParams) -> dict[str, Any]:
    """Run the live max-flow test: heat, then ramp the flow while sampling StallGuard.

    Safe by construction: refused while the printer is busy; the heater is **always turned
    off** in a ``finally`` (even on error); and the ramp **stops as soon as slip is detected**
    so no filament is ground past the first slip. The client should be created with a long
    timeout (heating + extrusion blocks for minutes).

    Raises:
        ValueError: on invalid params.
        MaxFlowBusyError: if the printer is busy.
        MaxFlowPreflightError: if the extruder driver can't read StallGuard for this test.
        httpx.HTTPError: if Moonraker is unreachable or a command fails.
    """
    validate(params)
    if await _is_busy(client):
        raise MaxFlowBusyError("Refusing to run a max-flow test while the printer is busy.")
    await _preflight(client, params.driver)  # C1: refuse a config that can't read StallGuard

    plan_steps = plan_ramp(params)
    driver_section = f"{params.driver.lower()} {_EXTRUDER}"
    sub_mm = params.extrude_per_step / params.samples_per_step
    sg_floor = _sg_floor(params.driver)  # C2: drop SG4 bias-region noise (below the min velocity)
    measurements: list[StepMeasurement] = []
    try:
        await client.run_gcode(f"M104 S{params.temperature:.0f}")  # start heating
        await client.run_gcode("M83")  # relative extrusion
        await client.run_gcode(f"M109 S{params.temperature:.0f}")  # wait for temp
        for step in plan_steps:
            samples: list[float] = []
            for _ in range(params.samples_per_step):
                await client.run_gcode(f"G1 E{sub_mm:.4f} F{step.feedrate_mm_min:.0f}")
                await client.run_gcode("M400")  # finish the move before sampling
                status = await client.query_objects([driver_section])
                obj = status.get(driver_section)
                sg = _extract_sg(obj if isinstance(obj, dict) else {})
                if sg is not None and sg >= sg_floor:
                    samples.append(sg)
            measurements.append(StepMeasurement(flow_mm3s=step.flow_mm3s, sg_samples=samples))
            # Stop the moment slip is detected — don't grind filament past the first slip.
            if max_flow.analyze(measurements, params.driver).slip_flow is not None:
                break
    finally:
        # Always cut the heater, even if a command raised mid-run (best-effort).
        with contextlib.suppress(Exception):
            await client.run_gcode("M104 S0")

    result = max_flow.analyze(measurements, params.driver)
    return {
        "ok": True,
        "max_flow_mm3s": result.max_flow_mm3s,
        "slip_flow": result.slip_flow,
        "reason": result.reason,
        "steps": [
            {"flow": s.flow, "median": s.median, "iqr": s.iqr, "cv_pct": s.cv_pct, "n": s.n}
            for s in result.steps
        ],
        "recommend": recommend(result.max_flow_mm3s),
        "driver": params.driver.lower(),
        "stallguard_field": reference_data.stallguard_field(params.driver),
        "sg_samples_seen": any(m.sg_samples for m in measurements),
    }
