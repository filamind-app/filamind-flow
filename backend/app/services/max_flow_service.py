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

import math
from dataclasses import dataclass
from typing import Any

from app.services import reference_data

# Safety bounds for a run request — rejected outside these.
_TEMP_MIN, _TEMP_MAX = 150.0, 350.0
_DIAM_MIN, _DIAM_MAX = 1.0, 3.5
_EXTRUDE_MIN, _EXTRUDE_MAX = 1.0, 50.0
_SAMPLES_MIN, _SAMPLES_MAX = 3, 200
_MAX_STEPS = 60

#: Fractions of the measured max flow suggested as slicer "max volumetric speed" values.
_CONSERVATIVE = 0.80
_BALANCED = 0.90


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
