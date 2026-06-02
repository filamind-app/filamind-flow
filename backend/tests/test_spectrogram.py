from __future__ import annotations

import numpy as np
import pytest

from app.services import shaper_service, spectrogram_service

_FS = 3200.0


def _synth_sine(freq: float, dur: float = 4.0, seed: int = 0) -> bytes:
    """A synthetic capture: a sine at ``freq`` on accel_x + gravity on z + light noise."""
    n = int(dur * _FS)
    t = np.arange(n) / _FS
    data = np.zeros((n, 4))
    data[:, 0] = t
    data[:, 1] = 1000.0 * np.sin(2 * np.pi * freq * t)
    data[:, 3] = 9810.0
    data[:, 1:] += np.random.default_rng(seed).normal(0, 20.0, size=(n, 3))
    lines = ["#time,accel_x,accel_y,accel_z"]
    lines += [f"{r[0]:.6f},{r[1]:.2f},{r[2]:.2f},{r[3]:.2f}" for r in data]
    return ("\n".join(lines) + "\n").encode()


def test_spectrogram_detects_the_held_frequency() -> None:
    result = spectrogram_service.compute_spectrogram(
        _synth_sine(50.0), freq=50.0, duration=4.0, axis="x"
    )
    assert result["dominant_ok"] is True
    assert abs(result["dominant_freq"] - 50.0) <= 3.0
    assert result["excited_band_pct"] > 20.0
    # Grid shape is consistent.
    assert len(result["spectrogram"]) == len(result["freqs"])
    assert len(result["energy"]) == len(result["times"])
    assert all(len(row) == len(result["times"]) for row in result["spectrogram"])


def test_spectrogram_flags_off_target_frequency() -> None:
    # Vibration is at 80 Hz but we asked to hold 40 Hz → not dominant there.
    result = spectrogram_service.compute_spectrogram(
        _synth_sine(80.0), freq=40.0, duration=4.0, axis="x"
    )
    assert result["dominant_ok"] is False
    assert abs(result["dominant_freq"] - 80.0) <= 4.0


def test_spectrogram_rejects_a_too_short_capture() -> None:
    with pytest.raises(shaper_service.ShaperAnalysisError):
        spectrogram_service.compute_spectrogram(
            b"#time,x,y,z\n0,0,0,0\n", freq=50.0, duration=1.0, axis="x"
        )
