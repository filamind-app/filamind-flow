"""Tests for the pure max-flow analysis core (StallGuard slip detection)."""

from __future__ import annotations

import math

from app.services import max_flow
from app.services.max_flow import StepMeasurement


def _clean(flow: float, center: float = 400.0) -> StepMeasurement:
    """A low-variance step centred on ``center`` (tight grip, no slip)."""
    samples = [center + d for d in (-2.0, -1.0, 0.0, 1.0, 2.0)]
    return StepMeasurement(flow_mm3s=flow, sg_samples=samples)


def _erratic(flow: float, center: float = 400.0) -> StepMeasurement:
    """A high-variance / wide-IQR step (slipping grip)."""
    samples = [center + d for d in (-180.0, -90.0, 0.0, 110.0, 200.0)]
    return StepMeasurement(flow_mm3s=flow, sg_samples=samples)


# ── statistics helpers ──────────────────────────────────────────────────────────
def test_step_stats_clean_step() -> None:
    stats = max_flow.step_stats(_clean(10.0, center=400.0))
    assert stats.flow == 10.0
    assert stats.n == 5
    assert stats.median == 400.0
    assert stats.iqr == 2.0  # p75 - p25 = 402 - 400 ... 401-399 = 2
    # Tight cluster -> coefficient of variation is small.
    assert stats.cv_pct < 1.0


def test_step_stats_empty_samples_is_safe() -> None:
    stats = max_flow.step_stats(StepMeasurement(flow_mm3s=5.0, sg_samples=[]))
    assert stats.n == 0
    assert stats.cv_pct == 0.0
    assert stats.iqr == 0.0


def test_percentile_and_median_helpers() -> None:
    values = [1.0, 2.0, 3.0, 4.0]
    assert max_flow._median(values) == 2.5
    assert max_flow._median([5.0]) == 5.0
    assert max_flow._percentile(values, 0.0) == 1.0
    assert max_flow._percentile(values, 100.0) == 4.0
    assert max_flow._percentile(values, 50.0) == 2.5
    assert math.isclose(max_flow._pstdev([2.0, 4.0, 4.0, 4.0, 5.0, 5.0, 7.0, 9.0]), 2.0)


# ── analyze: slip detected (SG2 wide-range driver) ──────────────────────────────
def test_iqr_spike_detects_slip_sg2() -> None:
    # Several clean steps then a wide-IQR erratic step -> slip at the erratic flow.
    steps = [
        _clean(5.0),
        _clean(7.0),
        _clean(9.0),
        _clean(11.0),
        _erratic(13.0),
    ]
    result = max_flow.analyze(steps, "tmc5160")
    assert result.slip_flow == 13.0
    assert result.max_flow_mm3s == 11.0  # last clean step before slip
    assert "slip detected at 13" in result.reason


def test_cv_spike_detects_slip_sg4_cv_centric() -> None:
    # TMC2209 (SG4) leans on the CV detector; a high-variance step trips it even
    # though its IQR absolute trigger is raised. Build a step whose CV is high
    # but whose absolute IQR stays under the SG4 absolute trigger (50).
    def cv_only_erratic(flow: float) -> StepMeasurement:
        # mean 100, large relative spread -> high CV, IQR ~30 (< 50 trigger).
        return StepMeasurement(flow, [70.0, 85.0, 100.0, 115.0, 145.0])

    steps = [
        _clean(2.0, center=100.0),
        _clean(4.0, center=100.0),
        _clean(6.0, center=100.0),
        cv_only_erratic(8.0),
    ]
    result = max_flow.analyze(steps, "tmc2209")
    assert result.slip_flow == 8.0
    assert result.max_flow_mm3s == 6.0
    assert "cv-spike" in result.reason


def test_run_outlier_detects_median_jump() -> None:
    # Steps stay tight but the load median jumps far out of the established run.
    steps = [
        _clean(5.0, center=400.0),
        _clean(7.0, center=402.0),
        _clean(9.0, center=399.0),
        _clean(11.0, center=120.0),  # median collapses -> outlier
    ]
    result = max_flow.analyze(steps, "tmc5160")
    assert result.slip_flow == 11.0
    assert result.max_flow_mm3s == 9.0
    assert "run-outlier" in result.reason


# ── analyze: never slips ────────────────────────────────────────────────────────
def test_never_slip_returns_highest_flow() -> None:
    steps = [_clean(f) for f in (5.0, 7.0, 9.0, 11.0, 13.0)]
    result = max_flow.analyze(steps, "tmc5160")
    assert result.slip_flow is None
    assert result.max_flow_mm3s == 13.0  # highest tested flow
    assert "no slip detected" in result.reason


def test_slip_on_first_step_yields_no_max() -> None:
    # The very first step is already erratic -> no clean step ever established.
    steps = [_erratic(5.0), _clean(7.0)]
    result = max_flow.analyze(steps, "tmc5160")
    assert result.slip_flow == 5.0
    assert result.max_flow_mm3s is None
    assert "no clean step" in result.reason


def test_opening_transient_excused_by_warmup_for_noisy_5160() -> None:
    """Regression (Voron TMC5160): the unsettled opening step's load-CV transient — which spikes as
    the ramp starts on a noisy SG2 driver — must not register as slip. With warmup=2 the opening
    forms the baseline and the genuine grind later is what trips. (The service passes warmup=2 for
    the StallGuard path; the 5160 also carries a higher CV/IQR ceiling override.)"""
    opening = StepMeasurement(5.0, [400.0 + d for d in (-90.0, -45.0, 0.0, 45.0, 90.0)])
    steps = [opening, _clean(7.5), _clean(10.0), _clean(12.5), _clean(15.0), _erratic(17.5)]
    # warmup=1 false-trips on the opening transient — the failure this fix addresses.
    assert max_flow.analyze(steps, "tmc5160", warmup=1).max_flow_mm3s is None
    # warmup=2 excuses the opening; the real grind at 17.5 is the slip.
    fixed = max_flow.analyze(steps, "tmc5160", warmup=2)
    assert fixed.slip_flow == 17.5
    assert fixed.max_flow_mm3s == 15.0


def test_empty_input() -> None:
    result = max_flow.analyze([], "tmc5160")
    assert result.max_flow_mm3s is None
    assert result.slip_flow is None
    assert result.steps == []
    assert "no steps" in result.reason


def test_steps_sorted_into_ascending_flow_order() -> None:
    # Supplied out of order; analysis must order by flow and report stats sorted.
    steps = [_clean(11.0), _clean(5.0), _erratic(13.0), _clean(7.0), _clean(9.0)]
    result = max_flow.analyze(steps, "tmc5160")
    flows = [s.flow for s in result.steps]
    assert flows == sorted(flows)
    assert result.slip_flow == 13.0
    assert result.max_flow_mm3s == 11.0


def test_uses_driver_specific_constants() -> None:
    # SG4 (tmc2209) raises the IQR absolute trigger to 50 and the ratio to 5.0;
    # SG2 (tmc5160) keeps the base 25 / 3.0. Build clean steps with a moderate
    # baseline IQR (~10) and a final step with IQR ~30, between the two triggers.
    def base_step(flow: float) -> StepMeasurement:
        # p25=395, p75=405 -> baseline IQR ~10, tight CV.
        return StepMeasurement(flow, [390.0, 395.0, 400.0, 405.0, 410.0])

    def mid_iqr(flow: float) -> StepMeasurement:
        # p25=385, p75=415 -> IQR ~30; ratio vs baseline 10 is 3.0.
        return StepMeasurement(flow, [380.0, 385.0, 400.0, 415.0, 420.0])

    base = [base_step(5.0), base_step(7.0), base_step(9.0)]
    sg2 = max_flow.analyze([*base, mid_iqr(11.0)], "tmc5160")
    sg4 = max_flow.analyze([*base, mid_iqr(11.0)], "tmc2209")
    # SG2: IQR 30 >= absolute 25 -> trips. SG4: 30 < 50 absolute and ratio
    # 30/10 = 3.0 < 5.0 -> stays clean. Same data, different driver verdict.
    assert sg2.slip_flow == 11.0
    assert sg4.slip_flow is None
