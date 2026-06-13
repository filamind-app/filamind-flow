"""Tests for the accelerometer (vibration) max-flow fallback — pure parsing + slip detection."""

from __future__ import annotations

import pathlib

import pytest

from app.services import max_flow_accel as mfa
from app.services import resonance_service
from app.services.max_flow import StepMeasurement


def _csv(amp: float, n: int = 160) -> str:
    """A synthetic raw-accel CSV oscillating ±amp around 1g on Z (std ≈ amp)."""
    lines = ["#time,accel_x,accel_y,accel_z"]
    for i in range(n):
        az = 9800.0 + (amp if i % 2 == 0 else -amp)
        lines.append(f"{i * 0.001:.3f},0.0,0.0,{az:.3f}")
    return "\n".join(lines)


def test_step_energy_samples_tracks_vibration() -> None:
    quiet = mfa.step_energy_samples(_csv(2.0))
    loud = mfa.step_energy_samples(_csv(60.0))
    assert quiet and loud
    assert all(v >= 0 for v in quiet)
    # a much noisier capture yields a much higher per-window RMS
    assert max(loud) > 5 * max(quiet)


def test_step_energy_samples_handles_garbage() -> None:
    assert mfa.step_energy_samples("") == []
    assert mfa.step_energy_samples("#time,x,y,z\n") == []


def _meas(flow: float, level: float, spread: float = 0.05) -> StepMeasurement:
    return StepMeasurement(flow, [level - spread, level, level + spread, level])


def test_analyze_detects_vibration_jump() -> None:
    # vibration rises gently through the warm-up, then a level outlier (jump) past it
    steps = [
        _meas(5, 2.0),
        _meas(7.5, 2.1),
        _meas(10, 2.2),
        _meas(12.5, 2.3),
        _meas(15, 2.4),
        _meas(17.5, 2.5),
        _meas(20, 12.0),
    ]
    res = mfa.analyze(steps)
    assert res.slip_flow == 20
    assert res.max_flow_mm3s == 17.5  # last clean step before the jump


def test_analyze_no_slip_on_gentle_rise() -> None:
    steps = [_meas(5, 2.0), _meas(6, 2.1), _meas(7, 2.2), _meas(8, 2.3)]
    res = mfa.analyze(steps)
    assert res.slip_flow is None
    assert res.max_flow_mm3s == 8  # reached the highest tested flow


def test_analyze_detects_cv_explosion() -> None:
    # The real SV08 grind signature: the within-step CV% explodes (settled ~0-12%, grind 26-71%)
    # while the level stays flat. A late high-CV step must be flagged as the slip.
    clean = [600.0, 605.0, 598.0, 602.0]  # CV ~0.4%
    grind = [600.0, 900.0, 300.0, 900.0]  # CV ~37%
    steps = [
        StepMeasurement(5, clean),
        StepMeasurement(7.5, clean),
        StepMeasurement(10, clean),
        StepMeasurement(12.5, clean),
        StepMeasurement(15, clean),
        StepMeasurement(17.5, grind),
    ]
    res = mfa.analyze(steps)
    assert res.slip_flow == 17.5
    assert res.max_flow_mm3s == 15  # last clean step before the CV explosion


def test_analyze_warmup_ignores_early_jump() -> None:
    # Regression: a big vibration jump within the warm-up window must NOT trip (the SV08
    # false-positive was a 9→35 IQR jump at the 2nd step reported as "slip at 7.5").
    steps = [_meas(5, 2.0), _meas(6, 25.0)]  # huge jump at the 2nd step
    res = mfa.analyze(steps)
    assert res.slip_flow is None
    assert res.max_flow_mm3s == 6  # reached the highest tested flow, no false slip


def test_analyze_empty() -> None:
    assert mfa.analyze([]).max_flow_mm3s is None


class _AccelClient:
    """Fake MoonrakerClient whose ACCELEROMETER_MEASURE writes a Klipper-shaped capture CSV,
    exactly as the real Input Shaping test fakes do (``<chip>-<name>.csv``)."""

    def __init__(self, write_dir: str, rows: int = 200, amp: float = 4.0) -> None:
        self._dir = write_dir
        self._rows = rows
        self._amp = amp
        self.gcodes: list[str] = []

    async def run_gcode(self, script: str) -> None:
        self.gcodes.append(script)
        if "ACCELEROMETER_MEASURE" in script and "NAME=" in script:
            name = script.split("NAME=", 1)[1].split()[0]
            lines = ["#time,accel_x,accel_y,accel_z"]
            for i in range(self._rows):
                az = 9800.0 + (self._amp if i % 2 == 0 else -self._amp)
                lines.append(f"{i * 0.001:.3f},0.0,0.0,{az:.3f}")
            (pathlib.Path(self._dir) / f"adxl345-{name}.csv").write_text(
                "\n".join(lines), encoding="utf-8"
            )


async def test_ramp_finds_reads_and_cleans_up_captures(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Regression guard: the capture filename (adxl345-maxflow_N.csv) MUST match a list_files glob,
    # or _await_new_file never sees it and the ramp times out on every step.
    monkeypatch.setattr(resonance_service, "_FILE_SETTLE", 0.05)
    monkeypatch.setattr(resonance_service, "_POLL_INTERVAL", 0.02)
    monkeypatch.setattr(
        resonance_service, "_FILE_WAIT_TIMEOUT", 4.0
    )  # fail fast if the glob breaks
    client = _AccelClient(str(tmp_path))
    steps = [(5.0, 124.7, 2.0), (7.0, 187.1, 2.0)]
    out = await mfa.ramp(client, "adxl345", str(tmp_path), steps, samples_per_step=4, total=2)  # type: ignore[arg-type]
    assert len(out) == 2
    assert all(m.sg_samples for m in out)  # the capture was found + reduced to vibration samples
    assert list(tmp_path.glob("*-maxflow_*.csv")) == []  # transient captures cleaned up
