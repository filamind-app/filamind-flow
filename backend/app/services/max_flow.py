"""Pure max-flow analysis core — StallGuard-based extrusion slip detection.

The max-flow test ramps the requested volumetric flow rate step by step. At each
step a short burst of StallGuard load samples is captured. As long as the
extruder grips the filament cleanly the StallGuard readings stay tight (low
spread); once the hobbed gear starts to slip the readings become erratic — the
per-step variance and inter-quartile spread jump. This module turns those raw
per-step sample arrays into a verdict: the highest flow rate the extruder
sustained before slip, and the flow at which slip first appeared.

Everything here is pure: it takes the captured samples plus the per-driver
detection constants and returns a result. No motion, no hardware, no host
dependency — the constants come from :mod:`app.services.reference_data`, which
provides ``resolved_profile(driver)`` (base thresholds merged with per-driver
overrides). Different driver families expose StallGuard differently (some report
a wide 0-1023 range, others a narrow 0-255), so the trip thresholds are
parameterised by driver rather than hard-coded.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from app.services import reference_data

# ── Fallback constants ─────────────────────────────────────────────────────────
# Used when a driver profile omits a key. Kept conservative so an unknown driver
# still trips on genuinely erratic data without firing on ordinary noise.
_DEFAULTS: dict[str, float] = {
    "CV_HIGH_VARIANCE": 10.0,
    "CV_JUMP_RATIO_COARSE": 2.5,
    "CV_JUMP_MIN_COARSE": 5.0,
    "IQR_ABSOLUTE_TRIGGER": 25.0,
    "IQR_RATIO_COARSE": 3.0,
    "IQR_RATIO_MIN_ABS": 12.0,
    "OUTLIER_MAD_RATIO": 4.0,
    "OUTLIER_MIN_REL": 0.08,
}

#: Steps inspected when forming a rolling baseline for the ratio detectors.
_BASELINE_WINDOW = 3


# ── Data shapes ────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class StepMeasurement:
    """Raw StallGuard load samples captured at one requested flow rate."""

    flow_mm3s: float
    sg_samples: list[float]


@dataclass(frozen=True)
class StepStats:
    """Summary statistics for a single flow step."""

    flow: float
    median: float
    p25: float
    p75: float
    iqr: float
    cv_pct: float
    n: int


@dataclass
class FlowResult:
    """Outcome of a max-flow analysis run."""

    max_flow_mm3s: float | None
    slip_flow: float | None
    steps: list[StepStats] = field(default_factory=list)
    reason: str = ""


# ── Pure statistics helpers ────────────────────────────────────────────────────
def _median(values: list[float]) -> float:
    """Median of a non-empty list (mean of the two middle values when even)."""
    ordered = sorted(values)
    count = len(ordered)
    mid = count // 2
    if count % 2:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2.0


def _percentile(values: list[float], pct: float) -> float:
    """Linear-interpolation percentile (``pct`` in ``0..100``) of a non-empty list."""
    ordered = sorted(values)
    count = len(ordered)
    if count == 1:
        return ordered[0]
    rank = (pct / 100.0) * (count - 1)
    low = math.floor(rank)
    high = math.ceil(rank)
    if low == high:
        return ordered[low]
    frac = rank - low
    return ordered[low] + (ordered[high] - ordered[low]) * frac


def _pstdev(values: list[float]) -> float:
    """Population standard deviation of a non-empty list."""
    count = len(values)
    if count < 2:
        return 0.0
    mean = sum(values) / count
    variance = sum((v - mean) ** 2 for v in values) / count
    return math.sqrt(variance)


def step_stats(measurement: StepMeasurement) -> StepStats:
    """Reduce one step's raw samples to its summary statistics.

    ``cv_pct`` is the coefficient of variation (stdev / mean * 100) using the
    absolute mean, so it is well defined for the signed StallGuard ranges. An
    empty sample set yields an all-zero record so downstream code never divides
    by an empty list.
    """
    samples = list(measurement.sg_samples)
    if not samples:
        return StepStats(measurement.flow_mm3s, 0.0, 0.0, 0.0, 0.0, 0.0, 0)
    median = _median(samples)
    p25 = _percentile(samples, 25.0)
    p75 = _percentile(samples, 75.0)
    iqr = p75 - p25
    mean = sum(samples) / len(samples)
    stdev = _pstdev(samples)
    cv_pct = (stdev / abs(mean) * 100.0) if mean != 0 else 0.0
    return StepStats(
        flow=measurement.flow_mm3s,
        median=median,
        p25=p25,
        p75=p75,
        iqr=iqr,
        cv_pct=cv_pct,
        n=len(samples),
    )


# ── Internal helpers ───────────────────────────────────────────────────────────
def _constants(driver: str) -> dict[str, Any]:
    """Resolved detection constants for ``driver`` with safe fallbacks."""
    merged = dict(_DEFAULTS)
    profile = reference_data.resolved_profile(driver)
    constants = profile.get("constants")
    if isinstance(constants, dict):
        for key, value in constants.items():
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                merged[key] = float(value)
    return merged


def _baseline(values: list[float]) -> float | None:
    """Median of the trailing ``_BASELINE_WINDOW`` prior values (None if none)."""
    window = values[-_BASELINE_WINDOW:]
    if not window:
        return None
    return _median(window)


# ── Slip detectors ─────────────────────────────────────────────────────────────
def cv_spike(history: list[StepStats], constants: dict[str, Any]) -> tuple[bool, str]:
    """Trip when the latest step's coefficient of variation spikes.

    Fires if the CV crosses the absolute high-variance ceiling, or if it rises
    sharply versus the recent clean baseline (ratio jump) once it is also above a
    minimum absolute floor — so a ratio jump against a near-zero clean baseline
    (ordinary measurement jitter) does not register as slip.
    """
    if not history:
        return False, ""
    last = history[-1]
    high = constants.get("CV_HIGH_VARIANCE", _DEFAULTS["CV_HIGH_VARIANCE"])
    if last.cv_pct >= high:
        return True, f"CV {last.cv_pct:.1f}% >= ceiling {high:.1f}%"
    ratio = constants.get("CV_JUMP_RATIO_COARSE", _DEFAULTS["CV_JUMP_RATIO_COARSE"])
    min_abs = constants.get("CV_JUMP_MIN_COARSE", _DEFAULTS["CV_JUMP_MIN_COARSE"])
    base = _baseline([s.cv_pct for s in history[:-1]])
    if base is not None and base > 0 and last.cv_pct >= min_abs and last.cv_pct >= ratio * base:
        return True, f"CV {last.cv_pct:.1f}% >= {ratio:.1f}x baseline {base:.1f}%"
    return False, ""


def iqr_spread(history: list[StepStats], constants: dict[str, Any]) -> tuple[bool, str]:
    """Trip when the latest step's inter-quartile spread widens.

    Fires on the absolute IQR trigger, or on a ratio jump versus the recent
    baseline once the spread is also above a minimum absolute floor (so tiny
    baselines do not produce spurious ratio trips).
    """
    if not history:
        return False, ""
    last = history[-1]
    absolute = constants.get("IQR_ABSOLUTE_TRIGGER", _DEFAULTS["IQR_ABSOLUTE_TRIGGER"])
    if last.iqr >= absolute:
        return True, f"IQR {last.iqr:.1f} >= absolute trigger {absolute:.1f}"
    ratio = constants.get("IQR_RATIO_COARSE", _DEFAULTS["IQR_RATIO_COARSE"])
    min_abs = constants.get("IQR_RATIO_MIN_ABS", _DEFAULTS["IQR_RATIO_MIN_ABS"])
    base = _baseline([s.iqr for s in history[:-1]])
    if base is not None and base > 0 and last.iqr >= min_abs and last.iqr >= ratio * base:
        return True, f"IQR {last.iqr:.1f} >= {ratio:.1f}x baseline {base:.1f}"
    return False, ""


def run_outlier(history: list[StepStats], constants: dict[str, Any]) -> tuple[bool, str]:
    """Trip when the latest step's median departs from the established run.

    Uses a median-absolute-deviation band over the prior clean steps: a slip
    typically shifts the load level as well as widening the spread, so a median
    that jumps far outside the MAD band of the run is a slip signal.
    """
    if len(history) < _BASELINE_WINDOW:
        return False, ""
    last = history[-1]
    priors = [s.median for s in history[:-1]]
    center = _median(priors)
    mad = _median([abs(m - center) for m in priors])
    mad_ratio = constants.get("OUTLIER_MAD_RATIO", _DEFAULTS["OUTLIER_MAD_RATIO"])
    min_rel = constants.get("OUTLIER_MIN_REL", _DEFAULTS["OUTLIER_MIN_REL"])
    deviation = abs(last.median - center)
    rel_floor = abs(center) * min_rel
    band = max(mad_ratio * mad, rel_floor)
    if band > 0 and deviation >= band:
        return True, f"median {last.median:.0f} deviates {deviation:.0f} (band {band:.0f})"
    return False, ""


_DETECTORS = (
    ("cv-spike", cv_spike),
    ("iqr-spread", iqr_spread),
    ("run-outlier", run_outlier),
)


# ── Top-level analysis ─────────────────────────────────────────────────────────
def analyze(
    steps: list[StepMeasurement], driver: str, constants: dict[str, Any] | None = None
) -> FlowResult:
    """Find the sustainable max flow from a ramp of per-step load captures.

    Steps are evaluated in ascending flow order. For each step the slip detectors
    run against the running history; the first step that trips any detector sets
    ``slip_flow`` and ``max_flow_mm3s`` becomes the last clean step before it. If
    no step trips, the run is treated as never-slipping and ``max_flow_mm3s`` is
    the last (highest) tested flow.

    ``constants`` overrides the per-driver detection thresholds — the accelerometer
    (vibration) fallback passes its own ratio-based set rather than the StallGuard ones.
    """
    if not steps:
        return FlowResult(None, None, [], "no steps supplied")

    ordered = sorted(steps, key=lambda s: s.flow_mm3s)
    if constants is None:
        constants = _constants(driver)
    else:
        merged = dict(_DEFAULTS)
        merged.update({k: float(v) for k, v in constants.items() if isinstance(v, (int, float))})
        constants = merged
    history: list[StepStats] = []
    last_clean: StepStats | None = None

    for measurement in ordered:
        stats = step_stats(measurement)
        history.append(stats)
        for name, detector in _DETECTORS:
            tripped, why = detector(history, constants)
            if tripped:
                if last_clean is None:
                    return FlowResult(
                        max_flow_mm3s=None,
                        slip_flow=stats.flow,
                        steps=history,
                        reason=(
                            f"slip at the first step {stats.flow:g} mm3/s "
                            f"via {name} ({why}); no clean step established"
                        ),
                    )
                return FlowResult(
                    max_flow_mm3s=last_clean.flow,
                    slip_flow=stats.flow,
                    steps=history,
                    reason=(
                        f"slip detected at {stats.flow:g} mm3/s via {name} ({why}); "
                        f"max sustained flow {last_clean.flow:g} mm3/s"
                    ),
                )
        last_clean = stats

    highest = history[-1].flow
    return FlowResult(
        max_flow_mm3s=highest,
        slip_flow=None,
        steps=history,
        reason=(
            f"no slip detected across {len(history)} steps; "
            f"reached the highest tested flow {highest:g} mm3/s"
        ),
    )
