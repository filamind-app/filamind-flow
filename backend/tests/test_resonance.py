from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from app.services import resonance_service, shaper_service

_SHAPERS = {"zv", "mzv", "ei", "2hump_ei", "3hump_ei"}


def _psd_csv(peak_hz: float = 50.0) -> bytes:
    freqs = np.arange(5.0, 205.0, 1.0)
    peak = 1.0 / (1.0 + ((freqs - peak_hz) / 3.0) ** 2)
    x, y, z = peak * 1000 + 5, peak * 200 + 5, peak * 50 + 5
    lines = ["freq,psd_x,psd_y,psd_z,psd_xyz"]
    lines += [
        f"{f:.1f},{a:.4e},{b:.4e},{c:.4e},{a + b + c:.4e}"
        for f, a, b, c in zip(freqs, x, y, z, strict=True)
    ]
    return ("\n".join(lines) + "\n").encode()


def _write(directory: Path, name: str) -> Path:
    path = directory / name
    path.write_bytes(_psd_csv())
    return path


def test_list_files_finds_resonance_csvs_with_axis(tmp_path: Path) -> None:
    _write(tmp_path, "resonances_x_test.csv")
    _write(tmp_path, "calibration_data_y_20260102.csv")
    (tmp_path / "unrelated.txt").write_text("nope")

    files = resonance_service.list_files(str(tmp_path))
    names = {f["name"]: f["axis"] for f in files}
    assert names == {"resonances_x_test.csv": "x", "calibration_data_y_20260102.csv": "y"}


def test_analyze_file_reads_and_analyses_a_host_file(tmp_path: Path) -> None:
    path = _write(tmp_path, "resonances_x_test.csv")
    result = resonance_service.analyze_file(str(tmp_path), str(path), axis="x")
    assert result["recommended_shaper"] in _SHAPERS
    assert result["source_file"] == "resonances_x_test.csv"


def test_analyze_file_rejects_paths_outside_allowed_dirs(tmp_path: Path) -> None:
    outside = tmp_path.parent / "evil.csv"
    outside.write_bytes(_psd_csv())
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    with pytest.raises(shaper_service.ShaperAnalysisError, match="outside"):
        resonance_service.analyze_file(str(allowed), str(outside))


class _FakeClient:
    """Stand-in for MoonrakerClient: run_gcode 'writes' the CSV Klipper would."""

    def __init__(
        self,
        *,
        printing: bool,
        has_tester: bool,
        write_dir: Path,
        homed: str = "xyz",
        noise: tuple[float, float, float] = (12.0, 15.0, 9.0),
    ) -> None:
        self.printing = printing
        self.has_tester = has_tester
        self.write_dir = write_dir
        self.homed = homed
        self.noise = noise
        self.gcodes: list[str] = []
        self._store: list[dict[str, Any]] = []
        self._t = 0.0

    async def query_objects(self, objects: list[str]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        if "print_stats" in objects:
            out["print_stats"] = {"state": "printing" if self.printing else "ready"}
        if "configfile" in objects:
            out["configfile"] = {"config": {"resonance_tester": {}} if self.has_tester else {}}
        if "toolhead" in objects:
            out["toolhead"] = {"homed_axes": self.homed}
        return out

    async def run_gcode(self, script: str) -> None:
        self.gcodes.append(script)
        if script.startswith("TEST_RESONANCES"):
            # Mirror Klipper's raw_data_<axislabel>_<name>.csv naming.
            name = re.search(r"NAME=(\S+)", script)
            axis = re.search(r"AXIS=(\S+)", script)
            nm = name.group(1) if name else "test"
            ax = (axis.group(1) if axis else "x").lower().replace(",", "").replace("-", "")
            _write(self.write_dir, f"raw_data_{ax}_{nm}.csv")
        elif script == "MEASURE_AXES_NOISE":
            x, y, z = self.noise
            self._t += 1.0
            self._store.append(
                {
                    "time": self._t,
                    "type": "response",
                    "message": (
                        f"Axes noise for xy-axis accelerometer: "
                        f"{x:.6f} (x), {y:.6f} (y), {z:.6f} (z)"
                    ),
                }
            )

    async def gcode_store(self, count: int = 20) -> list[dict[str, Any]]:
        return self._store[-count:]


def _patch_client(monkeypatch: pytest.MonkeyPatch, fake: _FakeClient) -> None:
    monkeypatch.setattr(resonance_service, "MoonrakerClient", lambda *a, **k: fake)
    # Don't actually wait for the (synchronously written) fake CSV to "settle".
    monkeypatch.setattr(resonance_service, "_FILE_SETTLE", 0.0)
    monkeypatch.setattr(resonance_service, "_POLL_INTERVAL", 0.0)


async def test_live_test_runs_and_analyses(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeClient(printing=False, has_tester=True, write_dir=tmp_path)  # already homed
    _patch_client(monkeypatch, fake)
    result = await resonance_service.run_live_test("http://x", str(tmp_path), axis="x")
    assert result["recommended_shaper"] in _SHAPERS
    assert result["source_file"] == "raw_data_x_filamind_x.csv"
    assert "G28" not in fake.gcodes  # already homed → no re-home


async def test_live_test_homes_first_when_not_homed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = _FakeClient(printing=False, has_tester=True, write_dir=tmp_path, homed="")
    _patch_client(monkeypatch, fake)
    await resonance_service.run_live_test("http://x", str(tmp_path), axis="x")
    assert "G28" in fake.gcodes
    assert any(g.startswith("TEST_RESONANCES") for g in fake.gcodes)


async def test_live_test_refuses_while_printing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_client(monkeypatch, _FakeClient(printing=True, has_tester=True, write_dir=tmp_path))
    with pytest.raises(shaper_service.ShaperAnalysisError, match="printing"):
        await resonance_service.run_live_test("http://x", str(tmp_path), axis="x")


async def test_live_test_refuses_without_resonance_tester(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_client(monkeypatch, _FakeClient(printing=False, has_tester=False, write_dir=tmp_path))
    with pytest.raises(shaper_service.ShaperAnalysisError, match="resonance_tester"):
        await resonance_service.run_live_test("http://x", str(tmp_path), axis="x")


async def test_measure_noise_parses_and_grades_good(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = _FakeClient(printing=False, has_tester=True, write_dir=tmp_path, noise=(12.0, 15.0, 9.0))
    _patch_client(monkeypatch, fake)
    result = await resonance_service.measure_noise("http://x")
    assert "MEASURE_AXES_NOISE" in fake.gcodes
    assert result["grade"] == "good"
    assert result["ok"] is True
    assert result["max_noise"] == pytest.approx(15.0)
    assert result["chips"][0] == {"label": "xy", "x": 12.0, "y": 15.0, "z": 9.0}


async def test_measure_noise_flags_high_noise(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = _FakeClient(
        printing=False, has_tester=True, write_dir=tmp_path, noise=(1500.0, 1200.0, 50.0)
    )
    _patch_client(monkeypatch, fake)
    result = await resonance_service.measure_noise("http://x")
    assert result["grade"] == "high"
    assert result["ok"] is False


async def test_measure_noise_refuses_without_resonance_tester(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_client(monkeypatch, _FakeClient(printing=False, has_tester=False, write_dir=tmp_path))
    with pytest.raises(shaper_service.ShaperAnalysisError, match="resonance_tester"):
        await resonance_service.measure_noise("http://x")


async def test_compare_belts_runs_both_diagonals(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = _FakeClient(printing=False, has_tester=True, write_dir=tmp_path)
    _patch_client(monkeypatch, fake)
    result = await resonance_service.compare_belts("http://x", str(tmp_path))
    assert result["belt_a"]["recommended_shaper"] in _SHAPERS
    assert result["belt_b"]["recommended_shaper"] in _SHAPERS
    # Both belt diagonals were excited, and each produced its own capture.
    tr = [g for g in fake.gcodes if g.startswith("TEST_RESONANCES")]
    assert any("AXIS=1,1 " in g for g in tr)
    assert any("AXIS=1,-1 " in g for g in tr)
    assert result["belt_a"]["source_file"] != result["belt_b"]["source_file"]


async def test_compare_belts_refuses_while_printing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_client(monkeypatch, _FakeClient(printing=True, has_tester=True, write_dir=tmp_path))
    with pytest.raises(shaper_service.ShaperAnalysisError, match="printing"):
        await resonance_service.compare_belts("http://x", str(tmp_path))
