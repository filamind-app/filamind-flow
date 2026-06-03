from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from app.services import resonance_service, shaper_service, vibrations_service

_FS = 3200.0
_N = 2600  # > the 2048-sample window the PSD needs


def _seg_raw(
    speed: float, *, peak_speed: float = 80.0, res_hz: float = 55.0, seed: int = 0
) -> bytes:
    """A synthetic constant-speed capture whose vibration amplitude bumps near peak_speed."""
    amp = 200.0 + 1500.0 * np.exp(-(((speed - peak_speed) / 25.0) ** 2))
    t = np.arange(_N) / _FS
    data = np.zeros((_N, 4))
    data[:, 0] = t
    data[:, 1] = amp * np.sin(2 * np.pi * res_hz * t)
    data[:, 2] = amp * 0.6 * np.sin(2 * np.pi * res_hz * t + 0.5)
    data[:, 3] = 9810.0
    data[:, 1:] += np.random.default_rng(seed).normal(0, 15.0, size=(_N, 3))
    lines = ["#time,accel_x,accel_y,accel_z"]
    lines += [f"{r[0]:.6f},{r[1]:.2f},{r[2]:.2f},{r[3]:.2f}" for r in data]
    return ("\n".join(lines) + "\n").encode()


def _corexy_segments(peak_speed: float = 80.0) -> list[dict[str, Any]]:
    speeds = list(range(20, 130, 10))
    segs: list[dict[str, Any]] = []
    for i, angle in enumerate((45.0, 135.0)):
        for j, speed in enumerate(speeds):
            segs.append(
                {
                    "angle": angle,
                    "speed": float(speed),
                    "raw": _seg_raw(speed, peak_speed=peak_speed, seed=i * 100 + j),
                }
            )
    return segs


def test_kinematics_main_angles() -> None:
    assert vibrations_service.kinematics_main_angles("corexy") == [45.0, 135.0]
    assert vibrations_service.kinematics_main_angles("cartesian") == [0.0, 90.0]
    assert vibrations_service.kinematics_main_angles("corexz") == [0.0, 90.0]
    with pytest.raises(shaper_service.ShaperAnalysisError):
        vibrations_service.kinematics_main_angles("delta")


def test_analyze_vibrations_profiles_a_corexy_sweep() -> None:
    result = vibrations_service.analyze_vibrations(
        _corexy_segments(peak_speed=80.0), kinematics="corexy", accel=3000.0
    )
    # Structure is internally consistent (heatmap rows = angles, cols = speeds).
    assert result["segments_used"] == 22
    assert len(result["speeds"]) == len(result["energy_profile"]) == len(result["max_profile"])
    assert len(result["angles"]) == len(result["angle_energy"])
    assert len(result["spectrogram"]) == len(result["angles"])
    assert all(len(row) == len(result["speeds"]) for row in result["spectrogram"])
    # The profile has real dynamic range (a resonance bump was injected).
    assert max(result["energy_profile"]) > min(result["energy_profile"]) + 0.1
    # Identical responses on both belts => a near-symmetric machine.
    assert result["symmetry_pct"] > 40.0
    assert result["main_angles"] == [45.0, 135.0]
    # A smooth speed is recommended within the swept range.
    assert isinstance(result["recommended_speed"], float)
    assert 20.0 <= result["recommended_speed"] <= 120.0
    assert result["verdict"]


def test_analyze_vibrations_finds_motor_resonance() -> None:
    result = vibrations_service.analyze_vibrations(
        _corexy_segments(), kinematics="corexy", accel=3000.0
    )
    # The injected structural resonance is at 55 Hz; the motor profile should land near it.
    assert result["motor_freq"] is not None
    assert abs(result["motor_freq"] - 55.0) <= 15.0


def test_analyze_vibrations_requires_both_motor_angles() -> None:
    only_one = [s for s in _corexy_segments() if s["angle"] == 45.0]
    with pytest.raises(shaper_service.ShaperAnalysisError, match="135"):
        vibrations_service.analyze_vibrations(only_one, kinematics="corexy", accel=3000.0)


def test_analyze_vibrations_rejects_empty() -> None:
    with pytest.raises(shaper_service.ShaperAnalysisError, match="usable"):
        vibrations_service.analyze_vibrations([], kinematics="corexy", accel=3000.0)


class _FakeVibClient:
    """Stand-in for MoonrakerClient: ACCELEROMETER_MEASURE stop 'writes' the vib CSV."""

    def __init__(
        self,
        *,
        printing: bool = False,
        has_tester: bool = True,
        kinematics: str = "corexy",
        write_dir: Path,
    ) -> None:
        self.printing = printing
        self.has_tester = has_tester
        self.kinematics = kinematics
        self.write_dir = write_dir
        self.gcodes: list[str] = []
        self._active: set[str] = set()

    async def query_objects(self, objects: list[str]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        if "print_stats" in objects:
            out["print_stats"] = {"state": "printing" if self.printing else "ready"}
        if "configfile" in objects:
            config: dict[str, Any] = {"printer": {"kinematics": self.kinematics}}
            if self.has_tester:
                config["resonance_tester"] = {"accel_chip": "adxl345"}
                config["adxl345"] = {"axes_map": "x,y,z"}
            out["configfile"] = {"config": config}
        if "toolhead" in objects:
            out["toolhead"] = {
                "homed_axes": "xyz",
                "axis_minimum": [0.0, 0.0, 0.0, 0.0],
                "axis_maximum": [350.0, 350.0, 340.0, 0.0],
                "max_accel": 5000.0,
                "square_corner_velocity": 5.0,
            }
        return out

    def _write_vib(self, name: str) -> None:
        match = re.search(r"sp(\d+)_", name)
        speed = float(match.group(1)) if match else 50.0
        (self.write_dir / f"adxl345-{name}.csv").write_bytes(_seg_raw(speed))

    async def run_gcode(self, script: str) -> None:
        self.gcodes.append(script)
        if script.startswith("ACCELEROMETER_MEASURE"):
            match = re.search(r"NAME=(\S+)", script)
            name = match.group(1) if match else "meas"
            if name in self._active:  # paired stop -> flush CSV
                self._active.discard(name)
                self._write_vib(name)
            else:
                self._active.add(name)


def _patch(monkeypatch: pytest.MonkeyPatch, fake: _FakeVibClient) -> None:
    monkeypatch.setattr(resonance_service, "MoonrakerClient", lambda *a, **k: fake)
    monkeypatch.setattr(resonance_service, "_FILE_SETTLE", 0.0)
    monkeypatch.setattr(resonance_service, "_POLL_INTERVAL", 0.0)


async def test_run_vibrations_profile_sweeps_and_analyses(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = _FakeVibClient(write_dir=tmp_path)
    _patch(monkeypatch, fake)
    result = await resonance_service.run_vibrations_profile(
        "http://x", str(tmp_path), max_speed=45.0, min_speed=25.0, speed_increment=10.0
    )
    # 3 speeds x 2 corexy angles.
    assert result["segments_captured"] == 6
    assert result["segments_used"] == 6
    assert result["kinematics"] == "corexy"
    # Both belt diagonals were swept and each segment bracketed by ACCELEROMETER_MEASURE.
    assert sum(g.startswith("ACCELEROMETER_MEASURE") for g in fake.gcodes) == 12
    # Velocity limit was set and then restored to the original max_accel.
    assert any("SET_VELOCITY_LIMIT ACCEL=3000" in g for g in fake.gcodes)
    assert any("SET_VELOCITY_LIMIT ACCEL=5000" in g for g in fake.gcodes)
    # Transient captures are cleaned up.
    assert not list(tmp_path.glob("*-vib_*.csv"))


async def test_run_vibrations_profile_refuses_while_printing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch(monkeypatch, _FakeVibClient(printing=True, write_dir=tmp_path))
    with pytest.raises(shaper_service.ShaperAnalysisError, match="printing"):
        await resonance_service.run_vibrations_profile("http://x", str(tmp_path))


async def test_run_vibrations_profile_refuses_without_resonance_tester(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch(monkeypatch, _FakeVibClient(has_tester=False, write_dir=tmp_path))
    with pytest.raises(shaper_service.ShaperAnalysisError, match="resonance_tester"):
        await resonance_service.run_vibrations_profile("http://x", str(tmp_path))


async def test_run_vibrations_profile_rejects_unsupported_kinematics(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch(monkeypatch, _FakeVibClient(kinematics="delta", write_dir=tmp_path))
    with pytest.raises(shaper_service.ShaperAnalysisError, match="kinematics"):
        await resonance_service.run_vibrations_profile(
            "http://x", str(tmp_path), max_speed=45.0, min_speed=25.0, speed_increment=10.0
        )
