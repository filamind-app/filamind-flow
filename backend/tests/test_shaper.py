from __future__ import annotations

import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.services import shaper_service

_SHAPER_NAMES = {"zv", "mzv", "ei", "2hump_ei", "3hump_ei"}


def _psd_csv(peak_hz: float = 50.0) -> bytes:
    """A synthetic Klipper PSD CSV with a single resonance peak."""
    freqs = np.arange(5.0, 205.0, 1.0)
    peak = 1.0 / (1.0 + ((freqs - peak_hz) / 3.0) ** 2)
    psd_x = peak * 1000.0 + 5.0
    psd_y = peak * 200.0 + 5.0
    psd_z = peak * 50.0 + 5.0
    psd_sum = psd_x + psd_y + psd_z
    lines = ["freq,psd_x,psd_y,psd_z,psd_xyz"]
    lines += [
        f"{f:.1f},{x:.4e},{y:.4e},{z:.4e},{s:.4e}"
        for f, x, y, z, s in zip(freqs, psd_x, psd_y, psd_z, psd_sum, strict=True)
    ]
    return ("\n".join(lines) + "\n").encode()


def _raw_accel_csv() -> bytes:
    """A synthetic accelerometer time-series ringing at ~45 Hz on the X axis."""
    fs, n = 3000.0, 4096
    t = np.arange(n) / fs
    rng = np.random.default_rng(0)
    ax = np.sin(2 * np.pi * 45.0 * t) + 0.05 * rng.standard_normal(n)
    ay = 0.1 * rng.standard_normal(n)
    az = 0.1 * rng.standard_normal(n)
    lines = ["#time,accel_x,accel_y,accel_z"]
    lines += [f"{t[i]:.6f},{ax[i]:.5f},{ay[i]:.5f},{az[i]:.5f}" for i in range(n)]
    return ("\n".join(lines) + "\n").encode()


def test_analyze_psd_recommends_a_shaper() -> None:
    result = shaper_service.analyze(_psd_csv(50.0))

    assert result["recommended_shaper"] in _SHAPER_NAMES
    assert result["recommended_freq"] is not None
    assert {s["name"] for s in result["shapers"]} == _SHAPER_NAMES

    # The plot series are all aligned to the same frequency bins.
    n = len(result["freqs"])
    assert n > 10
    assert len(result["psd_sum"]) == n
    assert all(len(c["vals"]) == n for c in result["shaper_curves"])

    # Exactly one shaper is flagged as recommended, and it carries metrics.
    recommended = [s for s in result["shapers"] if s["recommended"]]
    assert len(recommended) == 1
    assert recommended[0]["max_accel"] > 0


def test_analyze_raw_accelerometer_csv() -> None:
    # Restrict to one shaper family to keep this FFT-path test fast.
    result = shaper_service.analyze(_raw_accel_csv(), shapers=["mzv"])
    assert result["recommended_shaper"] == "mzv"
    assert len(result["freqs"]) > 10


def test_analyze_tolerates_a_truncated_final_row() -> None:
    # A capture read mid-write can end in a truncated (2-column) line — the parser
    # must skip it rather than erroring on "the number of columns changed".
    raw = _raw_accel_csv().rstrip(b"\n") + b"\n8183.379,1924.5\n"
    result = shaper_service.analyze(raw, shapers=["mzv"])
    assert result["recommended_shaper"] == "mzv"


def test_analyze_rejects_empty_and_garbage() -> None:
    with pytest.raises(shaper_service.ShaperAnalysisError):
        shaper_service.analyze(b"")
    with pytest.raises(shaper_service.ShaperAnalysisError):
        shaper_service.analyze(b"not,a,valid\nresonance,csv,here\n")


def test_analyze_route() -> None:
    client = TestClient(create_app())

    ok = client.post("/api/shaper/analyze?axis=x", content=_psd_csv(60.0))
    assert ok.status_code == 200
    body = ok.json()
    assert body["recommended_shaper"] in _SHAPER_NAMES
    assert body["axis"] == "x"
    assert len(body["shaper_curves"]) == len(_SHAPER_NAMES)

    assert client.post("/api/shaper/analyze", content=b"").status_code == 400


def test_analyze_surfaces_a_failed_init_as_a_clean_error(monkeypatch: pytest.MonkeyPatch) -> None:
    # A missing dependency (e.g. numpy not installed) must not 500 — it should be
    # caught and reported, since ShaperCalibrate imports numpy on construction.
    def boom(*_a: object, **_k: object) -> object:
        raise Exception("Failed to import `numpy` module")

    monkeypatch.setattr(shaper_service._sc, "ShaperCalibrate", boom)
    with pytest.raises(shaper_service.ShaperAnalysisError, match="Could not analyse"):
        shaper_service.analyze(_psd_csv())
