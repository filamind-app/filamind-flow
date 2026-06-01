from __future__ import annotations

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

    def __init__(self, *, printing: bool, has_tester: bool, write_dir: Path) -> None:
        self.printing = printing
        self.has_tester = has_tester
        self.write_dir = write_dir

    async def query_objects(self, objects: list[str]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        if "print_stats" in objects:
            out["print_stats"] = {"state": "printing" if self.printing else "ready"}
        if "configfile" in objects:
            out["configfile"] = {"config": {"resonance_tester": {}} if self.has_tester else {}}
        return out

    async def run_gcode(self, _script: str) -> None:
        _write(self.write_dir, "resonances_x_filamind_x.csv")


def _patch_client(monkeypatch: pytest.MonkeyPatch, fake: _FakeClient) -> None:
    monkeypatch.setattr(resonance_service, "MoonrakerClient", lambda *a, **k: fake)


async def test_live_test_runs_and_analyses(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_client(monkeypatch, _FakeClient(printing=False, has_tester=True, write_dir=tmp_path))
    result = await resonance_service.run_live_test("http://x", str(tmp_path), axis="x")
    assert result["recommended_shaper"] in _SHAPERS
    assert result["source_file"] == "resonances_x_filamind_x.csv"


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
