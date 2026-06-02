"""Input-shaper resonance analysis.

Runs Klipper's own shaper-calibration math on a resonance CSV and returns a
structured result: the recommended input shaper, every tested shaper's metrics,
and the frequency-response series for plotting in the browser.

The heavy lifting is Klipper's vendored ``shaper_calibrate`` (see
``app.vendor.klipper_shaper``). ``ShaperCalibrate(printer=None)`` runs serially
with only numpy — no Klipper host, no multiprocessing — so this works on any
machine with no printer attached.
"""

from __future__ import annotations

import io
from typing import Any

from app.vendor.klipper_shaper import shaper_calibrate as _sc

#: The shaper families Klipper's auto-tuner tests by default.
DEFAULT_SHAPERS: list[str] = list(_sc.AUTOTUNE_SHAPERS)

#: Header that marks a Klipper power-spectral-density CSV (vs raw accelerometer).
_PSD_HEADER = "freq,psd_x,psd_y,psd_z,psd_xyz"


class ShaperAnalysisError(ValueError):
    """Raised when a resonance CSV cannot be parsed or analysed."""


def _first_data_header(text: str) -> str:
    """Returns the first non-comment line — a PSD header or the first data row."""
    for line in text.splitlines():
        if line and not line.startswith("#"):
            return line
    return ""


def _parse_csv(raw: bytes, helper: Any) -> Any:
    """Parses a resonance CSV (PSD or raw-accelerometer) into Klipper CalibrationData."""
    np = helper.numpy
    text = raw.decode("utf-8", "replace")
    header = _first_data_header(text)
    buf = io.StringIO(text)
    if header.startswith(_PSD_HEADER):
        data = np.loadtxt(buf, skiprows=1, comments="#", delimiter=",")
        if data.ndim != 2 or data.shape[1] < 5:
            raise ShaperAnalysisError("Malformed PSD CSV (need freq,psd_x,psd_y,psd_z,psd_xyz)")
        cd = _sc.CalibrationData(
            freq_bins=data[:, 0],
            psd_sum=data[:, 4],
            psd_x=data[:, 1],
            psd_y=data[:, 2],
            psd_z=data[:, 3],
        )
        cd.set_numpy(np)
        # A file that already carries shaper columns is pre-normalized.
        if "mzv" not in header:
            cd.normalize_to_frequencies()
        return cd
    # Raw accelerometer samples: time, accel_x, accel_y, accel_z. Tolerant of a
    # ragged row (e.g. a truncated final line) — fall back to skipping bad rows.
    try:
        data = np.loadtxt(buf, comments="#", delimiter=",")
    except ValueError:
        data = np.genfromtxt(
            io.StringIO(text),
            comments="#",
            delimiter=",",
            usecols=(0, 1, 2, 3),
            invalid_raise=False,
        )
        data = data[~np.isnan(data).any(axis=1)]
    if data.ndim != 2 or data.shape[1] < 4:
        raise ShaperAnalysisError("Malformed accelerometer CSV (need time,accel_x,accel_y,accel_z)")
    cd = helper.process_accelerometer_data(data)
    cd.normalize_to_frequencies()
    return cd


def analyze(
    raw_csv: bytes,
    *,
    scv: float = 5.0,
    max_freq: float = 200.0,
    max_smoothing: float | None = None,
    damping_ratio: float | None = None,
    shapers: list[str] | None = None,
    axis: str | None = None,
) -> dict[str, Any]:
    """Analyses a resonance CSV → recommended shaper + per-shaper metrics + plot series."""
    if not raw_csv.strip():
        raise ShaperAnalysisError("Empty CSV")
    try:
        # ShaperCalibrate imports numpy lazily here, so a missing dependency
        # surfaces as a clean 400 rather than an unhandled 500.
        helper = _sc.ShaperCalibrate(printer=None)
        cal = _parse_csv(raw_csv, helper)
    except ShaperAnalysisError:
        raise
    except Exception as exc:  # e.g. numpy not installed, or malformed data
        raise ShaperAnalysisError(f"Could not analyse resonance data: {exc}") from exc

    log: list[str] = []
    best, all_shapers = helper.find_best_shaper(
        cal,
        shapers=shapers or None,
        damping_ratio=damping_ratio,
        scv=scv,
        shaper_freqs=[],
        max_smoothing=max_smoothing,
        test_damping_ratios=None,
        max_freq=max_freq,
        logger=log.append,
    )

    # Every shaper's response curve covers the same leading frequency bins (those
    # at or below the calibrator's max_freq); slice the PSD series to match.
    n = len(all_shapers[0].vals) if all_shapers else int((cal.freq_bins <= max_freq).sum())
    result_shapers = [
        {
            "name": s.name,
            "freq": round(float(s.freq), 1),
            "vibrations_pct": round(float(s.vibrs) * 100.0, 1),
            "smoothing": round(float(s.smoothing), 3),
            "max_accel": float(round(s.max_accel / 100.0) * 100.0),
            "recommended": bool(best is not None and s.name == best.name),
        }
        for s in all_shapers
    ]
    return {
        "recommended_shaper": best.name if best else None,
        "recommended_freq": round(float(best.freq), 1) if best else None,
        "axis": axis,
        "max_freq": float(max_freq),
        "shapers": result_shapers,
        "freqs": [float(f) for f in cal.freq_bins[:n]],
        "psd_x": [float(v) for v in cal.psd_x[:n]],
        "psd_y": [float(v) for v in cal.psd_y[:n]],
        "psd_z": [float(v) for v in cal.psd_z[:n]],
        "psd_sum": [float(v) for v in cal.psd_sum[:n]],
        "shaper_curves": [
            {"name": s.name, "vals": [float(v) for v in s.vals]} for s in all_shapers
        ],
        "log": log,
    }
