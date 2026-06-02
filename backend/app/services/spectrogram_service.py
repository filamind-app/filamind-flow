"""Time-frequency spectrogram of a raw accelerometer capture — backs the "sustain
frequency" hands-on diagnostic (hold a frequency, touch parts to find what rattles).

Pure numpy STFT. The vendored ``shaper_calibrate`` collapses time (Welch mean), so it
cannot produce a time-resolved spectrogram; this is a small, self-contained port of the
idea from Shake&Tune's ``spectrogram.py``. No Klipper host, no matplotlib.
"""

from __future__ import annotations

import io
from typing import Any

import numpy as np

from app.services.shaper_service import ShaperAnalysisError

#: Caps so the grid sent to the browser stays light.
_MAX_TIME_BINS = 120
_MAX_FREQ_BINS = 160
#: Half-width (Hz) of the "did the requested frequency dominate?" band.
_BAND_HALF = 2.0


def _parse_raw_accel(raw: bytes) -> np.ndarray:
    """Parses a Klipper raw-accel CSV (``#time,accel_x,accel_y,accel_z``) to Nx4."""
    text = raw.decode("utf-8", errors="replace")
    try:
        data = np.loadtxt(io.StringIO(text), comments="#", delimiter=",")
    except ValueError:
        data = np.genfromtxt(
            io.StringIO(text),
            comments="#",
            delimiter=",",
            usecols=(0, 1, 2, 3),
            invalid_raise=False,
        )
        data = data[~np.isnan(data).any(axis=1)] if data.ndim == 2 else np.empty((0, 4))
    data = np.atleast_2d(data)
    if data.shape[1] < 4 or data.shape[0] < 256:
        raise ShaperAnalysisError("Capture is too short for a spectrogram")
    return np.asarray(data[:, :4], dtype=float)


def _next_pow2(n: float) -> int:
    return 1 << max(0, int(n) - 1).bit_length()


def _downsample_rows(
    values: np.ndarray, axis_vals: np.ndarray, cap: int
) -> tuple[np.ndarray, np.ndarray]:
    step = max(1, -(-len(axis_vals) // cap))  # ceil division
    return values[::step], axis_vals[::step]


def compute_spectrogram(
    raw: bytes, *, freq: float, duration: float, axis: str, max_freq: float = 200.0
) -> dict[str, Any]:
    """STFT of the capture → a downsampled heatmap grid + an energy-vs-time timeline
    + a verdict on whether the requested frequency dominated and whether a touch
    visibly reduced the vibration."""
    data = _parse_raw_accel(raw)
    times_all = data[:, 0]
    n = len(times_all)
    span = float(times_all[-1] - times_all[0])
    fs = n / span if span > 0 else 3200.0

    nperseg = min(_next_pow2(0.5 * fs), n)
    nperseg = max(64, nperseg)
    noverlap = nperseg // 2
    step = nperseg - noverlap
    window = np.kaiser(nperseg, 6.0)
    win_scale = 1.0 / (fs * np.sum(window**2))

    all_freqs = np.fft.rfftfreq(nperseg, d=1.0 / fs)
    fmask = all_freqs <= max_freq
    freqs = all_freqs[fmask]

    seg_times: list[float] = []
    cols: list[np.ndarray] = []
    for start in range(0, n - nperseg + 1, step):
        seg_center = (times_all[start] + times_all[start + nperseg - 1]) / 2 - times_all[0]
        power = np.zeros(int(fmask.sum()))
        for col in (1, 2, 3):
            seg = data[start : start + nperseg, col]
            seg = seg - seg.mean()
            spec = np.abs(np.fft.rfft(seg * window)) ** 2 * win_scale
            spec[1:-1] *= 2.0  # one-sided
            power += spec[fmask]
        seg_times.append(float(seg_center))
        cols.append(power)

    if len(cols) < 2:
        raise ShaperAnalysisError("Capture is too short for a spectrogram")

    pdata = np.array(cols).T  # [n_freq, n_time]
    times = np.array(seg_times)

    dfreq = float(freqs[1] - freqs[0]) if len(freqs) > 1 else 1.0
    energy = pdata.sum(axis=0) * dfreq  # energy(t)

    # Did the requested frequency dominate?
    band = (freqs >= freq - _BAND_HALF) & (freqs <= freq + _BAND_HALF)
    total_power = float(pdata.sum()) or 1.0
    excited_band_pct = (
        round(100.0 * float(pdata[band].sum()) / total_power, 1) if band.any() else 0.0
    )
    dominant_freq = float(freqs[int(pdata.sum(axis=1).argmax())])
    dominant_ok = abs(dominant_freq - freq) <= max(3.0, _BAND_HALF)

    # Did a touch visibly drop the vibration during the hold?
    energy_drop_pct = (
        round(100.0 * float(energy.max() - energy.min()) / float(energy.max()), 0)
        if energy.max() > 0
        else 0.0
    )

    if not dominant_ok:
        verdict = (
            f"The toolhead isn't vibrating mainly at {freq:.0f} Hz "
            f"(peak is {dominant_freq:.0f} Hz) — the source may not reach the toolhead sensor."
        )
    elif energy_drop_pct >= 30:
        verdict = (
            f"Holding {freq:.0f} Hz — vibration dropped ~{energy_drop_pct:.0f}% at some point; "
            "whatever you touched then is a strong contributor."
        )
    else:
        verdict = (
            f"Holding {freq:.0f} Hz — touch belts, the toolhead, gantry joints and idlers one "
            "at a time; the part that silences the buzz is your resonance source."
        )

    # Normalise + downsample the grid for the browser (log scale → 0..1).
    grid = np.log1p(pdata)
    grid = grid / (grid.max() or 1.0)
    grid, freqs_ds = _downsample_rows(grid, freqs, _MAX_FREQ_BINS)
    grid_t, times_ds = _downsample_rows(grid.T, times, _MAX_TIME_BINS)
    grid = grid_t.T
    energy_norm = energy / (energy.max() or 1.0)
    energy_ds, _ = _downsample_rows(energy_norm, times, _MAX_TIME_BINS)

    return {
        "axis": axis,
        "freq": freq,
        "duration": duration,
        "max_freq": max_freq,
        "freqs": [round(f, 1) for f in freqs_ds.tolist()],
        "times": [round(t, 3) for t in times_ds.tolist()],
        "spectrogram": [[round(v, 4) for v in row] for row in grid.tolist()],
        "energy": [round(v, 4) for v in energy_ds.tolist()],
        "excited_band_pct": excited_band_pct,
        "energy_drop_pct": float(energy_drop_pct),
        "dominant_freq": round(dominant_freq, 1),
        "dominant_ok": bool(dominant_ok),
        "verdict": verdict,
    }
