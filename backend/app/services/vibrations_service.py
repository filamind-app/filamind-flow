"""Machine vibrations profile — find the speeds and directions that vibrate least.

Pure numpy analysis (no Klipper host, no matplotlib), ported from Shake&Tune's
``vibrations_computation.py`` (GPL-3.0, (C) 2024 Felix Boisselier). Given many short
constant-speed back-and-forth captures taken at the kinematic motor angles (0/90 for
Cartesian/CoreXZ, 45/135 for CoreXY) across a range of speeds, it builds a directional
speed-vs-vibration map and reports:

* the **speeds to avoid** (resonance peaks) and the **smoothest speed ranges**,
* a **polar energy** curve over travel direction + the smoothest angle ranges,
* a **symmetry** score (how alike the two motors behave),
* the **motors' main resonant frequency** and damping ratio.

The per-segment power spectral density reuses the vendored Klipper ``ShaperCalibrate``
(the same engine ``shaper_service`` uses). This is the pure math; the printer-side sweep
that produces the captures lives in ``resonance_service.run_vibrations_profile``.

Differences from upstream Shake&Tune (documented so the omission is honest):

* No motor TMC-config comparison (driver registers are not reachable over Moonraker
  REST, and that section is advisory). The mechanical motor resonance / damping that
  Shake&Tune derives from the global motor profile is kept.
* The directional projection loop is vectorized with ``np.interp`` over speed; upstream
  hand-rolls the same linear interpolation point by point.
* Upstream ``_compute_symmetry_analysis`` calls ``np.clip(0, 100, value)`` with its
  arguments transposed (a latent bug that clamps oddly); here the symmetry score is
  clamped to ``[0, 100]`` as intended.
"""

from __future__ import annotations

import io
import math
from typing import Any

import numpy as np

from app.services.shaper_service import ShaperAnalysisError
from app.vendor.klipper_shaper import shaper_calibrate as _sc

# Peak / valley detection tuning (verbatim from Shake&Tune).
PEAKS_DETECTION_THRESHOLD = 0.05
PEAKS_RELATIVE_HEIGHT_THRESHOLD = 0.04
SPEEDS_VALLEY_DETECTION_THRESHOLD = 0.7  # lower is more sensitive
SPEEDS_AROUND_PEAK_DELETION = 3  # delete +-3 mm/s around a detected peak
ANGLES_VALLEY_DETECTION_THRESHOLD = 1.1

#: Caps so the grids sent to the browser stay light.
_MAX_ANGLE_BINS = 120
_MAX_SPEED_BINS = 120


def kinematics_main_angles(kinematics: str) -> list[float]:
    """The two motor angles a sweep must cover for this kinematics."""
    kin = kinematics.lower()
    if kin in {"cartesian", "limited_cartesian", "corexz", "limited_corexz"}:
        return [0.0, 90.0]
    if kin in {"corexy", "limited_corexy"}:
        return [45.0, 135.0]
    raise ShaperAnalysisError(
        "Only Cartesian, CoreXY and CoreXZ kinematics are supported by the vibrations tool"
    )


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
    if data.shape[1] < 4 or data.shape[0] < 10:
        raise ShaperAnalysisError("A vibrations segment has too few or malformed samples")
    return np.asarray(data[:, :4], dtype=float)


# ---------------------------------------------------------------------------
# Pure helpers ported from Shake&Tune's common_func.py
# ---------------------------------------------------------------------------


def _compute_mechanical_parameters(
    psd: np.ndarray, freqs: np.ndarray, min_freq: float = 0.0
) -> tuple[float | None, float | None, bool]:
    """Natural frequency + damping ratio via the half-power bandwidth method."""
    max_under_min_freq = False
    if min_freq > 0.0:
        min_freq_index = int(np.searchsorted(freqs, min_freq, side="left"))
        if min_freq_index >= len(freqs):
            return None, None, max_under_min_freq
        if int(np.argmax(psd)) < min_freq_index:
            max_under_min_freq = True
    else:
        min_freq_index = 0

    psd_above = psd[min_freq_index:]
    if len(psd_above) == 0:
        return None, None, max_under_min_freq

    max_power_index = int(np.argmax(psd_above)) + min_freq_index
    fr = float(freqs[max_power_index])
    max_power = float(psd[max_power_index])

    half_power = max_power / math.sqrt(2)
    indices_below = np.where(psd[:max_power_index] <= half_power)[0]
    indices_above = np.where(psd[max_power_index:] <= half_power)[0]
    if len(indices_below) == 0 or len(indices_above) == 0:
        return fr, None, max_under_min_freq

    idx_below = int(indices_below[-1])
    idx_above = int(indices_above[0]) + max_power_index
    freq_below = freqs[idx_below] + (half_power - psd[idx_below]) * (
        freqs[idx_below + 1] - freqs[idx_below]
    ) / (psd[idx_below + 1] - psd[idx_below])
    freq_above = freqs[idx_above - 1] + (half_power - psd[idx_above - 1]) * (
        freqs[idx_above] - freqs[idx_above - 1]
    ) / (psd[idx_above] - psd[idx_above - 1])

    bandwidth = float(freq_above - freq_below)
    bw1 = math.pow(bandwidth / fr, 2)
    bw2 = math.pow(bandwidth / fr, 4)
    try:
        zeta = math.sqrt(0.5 - math.sqrt(1 / (4 + 4 * bw1 - bw2)))
    except ValueError:
        return fr, None, max_under_min_freq
    return fr, zeta, max_under_min_freq


def _detect_peaks(
    data: np.ndarray,
    indices: np.ndarray,
    detection_threshold: float,
    relative_height_threshold: float,
    window_size: int,
    vicinity: int,
) -> tuple[int, np.ndarray]:
    """Peaks where the smoothed derivative flips sign and the height clears a threshold."""
    kernel = np.ones(window_size) / window_size
    smoothed = np.convolve(data, kernel, mode="valid")
    mean_pad = [float(np.mean(data[:window_size]))] * (window_size // 2)
    smoothed = np.concatenate((mean_pad, smoothed))

    candidates = np.where((smoothed[:-2] < smoothed[1:-1]) & (smoothed[1:-1] > smoothed[2:]))[0] + 1
    candidates = candidates[smoothed[candidates] > detection_threshold]

    valid_peaks: list[int] = []
    for peak in candidates:
        peak_height = smoothed[peak] - np.min(
            smoothed[max(0, peak - vicinity) : min(len(smoothed), peak + vicinity + 1)]
        )
        if peak_height > relative_height_threshold * smoothed[peak]:
            valid_peaks.append(int(peak))

    refined: list[int] = []
    for peak in valid_peaks:
        local = (
            peak
            + int(np.argmax(data[max(0, peak - vicinity) : min(len(data), peak + vicinity + 1)]))
            - vicinity
        )
        refined.append(local)
    refined_arr = np.array(refined, dtype=int)
    return len(refined), indices[refined_arr] if len(refined) else np.array([])


def _identify_low_energy_zones(
    power_total: np.ndarray, detection_threshold: float
) -> list[tuple[int, int, float]]:
    """Flat low-energy valleys (good zones) in a 1-D signal, sorted best-first."""
    mean_energy = (
        float(np.mean(power_total)) + (float(np.max(power_total)) - float(np.min(power_total))) / 4
    )
    std_energy = float(np.std(power_total))
    threshold_value = mean_energy - detection_threshold * std_energy

    valleys: list[tuple[int, int]] = []
    in_valley = False
    start_idx = 0
    for i, value in enumerate(power_total):
        if not in_valley and value < threshold_value:
            in_valley = True
            start_idx = i
        elif in_valley and value >= threshold_value:
            in_valley = False
            valleys.append((start_idx, i))
    if in_valley:
        valleys.append((start_idx, len(power_total) - 1))

    max_signal = float(np.max(power_total)) or 1.0
    pct: list[tuple[int, int, float]] = []
    for start, end in valleys:
        segment_mean = np.mean(power_total[start:end])
        if not np.isnan(segment_mean):
            pct.append((start, end, float(segment_mean) / max_signal * 100.0))
    return sorted(pct, key=lambda v: v[2])


def _filter_and_split_ranges(
    all_speeds: np.ndarray,
    good_speeds: list[tuple[int, int, float]],
    peak_speed_indices: dict[float, int],
    deletion_range: int,
) -> list[tuple[int, int, float]]:
    """Carve detected resonance peaks out of the good-speed ranges, then merge overlaps."""
    filtered: list[tuple[int, int, float]] = []
    for start, end, energy in good_speeds:
        start_speed, end_speed = float(all_speeds[start]), float(all_speeds[end])
        intersecting = sorted(
            idx for speed, idx in peak_speed_indices.items() if start_speed <= speed <= end_speed
        )
        if not intersecting:
            filtered.append((start, end, energy))
            continue
        current_start = start
        for peak_index in intersecting:
            before_peak_end = max(current_start, peak_index - deletion_range)
            if current_start < before_peak_end:
                filtered.append((current_start, before_peak_end, energy))
            current_start = peak_index + deletion_range + 1
        if current_start < end:
            filtered.append((current_start, end, energy))

    if not filtered:
        return []
    sorted_ranges = sorted(filtered, key=lambda x: x[0])
    merged: list[tuple[int, int, float]] = [sorted_ranges[0]]
    for current in sorted_ranges[1:]:
        last_start, last_end, last_energy = merged[-1]
        if current[0] <= last_end:
            merged[-1] = (last_start, max(last_end, current[1]), min(last_energy, current[2]))
        else:
            merged.append(current)
    return merged


# ---------------------------------------------------------------------------
# Stage computations (ported from VibrationsComputation)
# ---------------------------------------------------------------------------


def _dir_speed_spectrogram(
    measured_speeds: list[float],
    psds_sum: dict[float, dict[float, float]],
    kinematics: str,
    main_angles: list[float],
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Project the two motor responses onto every travel direction over [0, 360)."""
    spectrum_angles = np.linspace(0, 360, 720)
    spectrum_speeds = np.linspace(
        min(measured_speeds), max(measured_speeds), max(2, len(measured_speeds) * 6)
    )
    speeds_arr = np.asarray(measured_speeds, dtype=float)
    vib0 = np.array([psds_sum[main_angles[0]][s] for s in measured_speeds], dtype=float)
    vib1 = np.array([psds_sum[main_angles[1]][s] for s in measured_speeds], dtype=float)

    radians = np.deg2rad(spectrum_angles)
    cos_vals = np.cos(radians)
    sin_vals = np.sin(radians)
    sqrt_2_inv = 1.0 / math.sqrt(2.0)
    is_corexy = kinematics.lower() in {"corexy", "limited_corexy"}

    out = np.zeros((len(spectrum_angles), len(spectrum_speeds)))
    for i in range(len(spectrum_angles)):
        if is_corexy:
            speed_1 = np.abs(spectrum_speeds * (cos_vals[i] + sin_vals[i]) * sqrt_2_inv)
            speed_2 = np.abs(spectrum_speeds * (cos_vals[i] - sin_vals[i]) * sqrt_2_inv)
        else:
            speed_1 = np.abs(spectrum_speeds * cos_vals[i])
            speed_2 = np.abs(spectrum_speeds * sin_vals[i])
        out[i, :] = np.interp(speed_1, speeds_arr, vib0) + np.interp(speed_2, speeds_arr, vib1)
    return spectrum_angles, spectrum_speeds, out


def _angle_powers(spectrogram: np.ndarray) -> np.ndarray:
    """Total vibration energy per travel direction (integrated over speed, smoothed)."""
    powers = np.trapezoid(spectrogram, axis=1)
    extended = np.concatenate([powers[-9:], powers, powers[:9]])
    convolved = np.convolve(extended, np.ones(15) / 15, mode="same")
    return convolved[9:-9]


def _pad_and_smooth(data: np.ndarray, window: int, conv_filter: np.ndarray) -> np.ndarray:
    padded = np.pad(data, (window,), mode="edge")
    return np.convolve(padded, conv_filter, mode="valid")


def _speed_powers(spectrogram: np.ndarray, smoothing_window: int = 15) -> np.ndarray:
    """min / max / variance / vibration-metric curves over speed (smoothed)."""
    min_values = np.amin(spectrogram, axis=0)
    max_values = np.amax(spectrogram, axis=0)
    var_values = np.var(spectrogram, axis=0)
    var_max = float(var_values.max()) or 1.0
    var_values = var_values / var_max * float(max_values.max())
    vibration_metric = max_values * var_values

    conv_filter = np.ones(smoothing_window) / smoothing_window
    window = smoothing_window // 2
    stacked = np.stack([min_values, max_values, var_values, vibration_metric])
    return np.array([_pad_and_smooth(row, window, conv_filter) for row in stacked])


def _motor_profiles(
    freqs: np.ndarray,
    psds: dict[float, dict[float, np.ndarray]],
    all_angles_energy: np.ndarray,
    main_angles: list[float],
    energy_amplification_factor: int = 2,
) -> np.ndarray:
    """Weighted-average motor PSD profile across the measured angles."""
    weighted_sum = np.zeros_like(freqs)
    total_weight = 0.0
    conv_filter = np.ones(20) / 20
    for angle in main_angles:
        speeds = psds[angle]
        sum_curve = np.sum(np.array([speeds[s] for s in speeds]), axis=0)
        profile = np.convolve(sum_curve / len(speeds), conv_filter, mode="same")
        # Upstream weights by all_angles_energy[int(angle)] (an index into the 720-point
        # energy array, not the energy at `angle` degrees); kept for parity.
        angle_energy = float(all_angles_energy[int(angle)]) ** energy_amplification_factor
        curve_area = float(np.trapezoid(profile, freqs)) ** energy_amplification_factor
        weight = angle_energy * curve_area
        weighted_sum += profile * weight
        total_weight += weight
    return weighted_sum / total_weight if total_weight != 0 else weighted_sum


def _symmetry_analysis(
    all_angles: np.ndarray, spectrogram: np.ndarray, main_angles: list[float]
) -> float:
    """How alike the two halves of the directional spectrogram are (0-100%)."""
    total = len(all_angles)
    half = total // 2
    extended = np.concatenate((spectrogram[-half:], spectrogram), axis=0)
    midpoint_angle = float(np.mean(main_angles))
    split = int(midpoint_angle * (total / 360) + half)
    seg_len = half // 2
    seg1 = extended[split - seg_len : split].flatten()
    seg2 = extended[split : split + seg_len].flatten()
    if len(seg1) != len(seg2) or len(seg1) < 2:
        return 0.0
    correlation = float(np.corrcoef(seg1, seg2)[0, 1])
    if math.isnan(correlation):
        return 0.0
    biased = 100.0 * math.pow(max(correlation, 0.0), 0.75) + 10.0
    return float(np.clip(biased, 0.0, 100.0))


def _downsample_axis(values: np.ndarray, cap: int) -> tuple[np.ndarray, int]:
    step = max(1, -(-len(values) // cap))  # ceil division
    return values[::step], step


def analyze_vibrations(
    segments: list[dict[str, Any]],
    *,
    kinematics: str,
    accel: float,
    max_freq: float = 200.0,
) -> dict[str, Any]:
    """Analyses many constant-speed captures into a directional vibration profile.

    ``segments`` is a list of ``{"angle": float, "speed": float, "raw": bytes}`` where
    ``raw`` is a Klipper raw-accel CSV. ``angle`` must include both motor angles for the
    given kinematics. Returns a JSON-friendly dict (see ``VibrationsProfile``).
    """
    main_angles = kinematics_main_angles(kinematics)
    helper = _sc.ShaperCalibrate(printer=None)

    psds: dict[float, dict[float, np.ndarray]] = {}
    psds_sum: dict[float, dict[float, float]] = {}
    target_freqs: np.ndarray | None = None
    used = 0
    for seg in segments:
        try:
            data = _parse_raw_accel(seg["raw"])
            freq_response = helper.process_accelerometer_data(data)
        except Exception:  # a short or malformed segment is skipped, not fatal
            continue
        first_freqs = np.asarray(freq_response.freq_bins, dtype=float)
        psd_sum = np.asarray(freq_response.psd_sum, dtype=float)
        if target_freqs is None:
            target_freqs = first_freqs[first_freqs <= max_freq]
        mask = first_freqs <= max_freq
        psd_sum_m = psd_sum[mask]
        first_freqs_m = first_freqs[mask]

        angle = float(seg["angle"])
        speed = float(seg["speed"])
        psds.setdefault(angle, {})
        psds_sum.setdefault(angle, {})
        psds[angle][speed] = np.interp(target_freqs, first_freqs_m, psd_sum_m)
        psds_sum[angle][speed] = float(np.trapezoid(psd_sum_m, first_freqs_m))
        used += 1

    if target_freqs is None:
        raise ShaperAnalysisError("No usable vibrations segments were captured")

    measured_angles = sorted(psds_sum.keys())
    for main_angle in main_angles:
        if main_angle not in measured_angles:
            raise ShaperAnalysisError(
                f"Sweep is missing the {main_angle:.0f} angle required for {kinematics} kinematics"
            )
    measured_speeds = sorted({s for a in psds_sum.values() for s in a})
    if len(measured_speeds) < 2:
        raise ShaperAnalysisError("A vibrations sweep needs at least two speeds")

    all_angles, all_speeds, spectrogram = _dir_speed_spectrogram(
        measured_speeds, psds_sum, kinematics, main_angles
    )
    all_angles_energy = _angle_powers(spectrogram)
    speed_powers = _speed_powers(spectrogram)
    _sp_min, sp_max, _sp_var, vibration_metric = speed_powers
    global_motor_profile = _motor_profiles(target_freqs, psds, all_angles_energy, main_angles)

    symmetry = _symmetry_analysis(all_angles, spectrogram, main_angles)

    metric_max = float(vibration_metric.max()) or 1.0
    _num_peaks, peaks_speeds = _detect_peaks(
        vibration_metric,
        all_speeds,
        PEAKS_DETECTION_THRESHOLD * metric_max,
        PEAKS_RELATIVE_HEIGHT_THRESHOLD,
        10,
        10,
    )

    good_speeds = _identify_low_energy_zones(vibration_metric, SPEEDS_VALLEY_DETECTION_THRESHOLD)
    if good_speeds and len(all_speeds) > 1:
        deletion_range = int(SPEEDS_AROUND_PEAK_DELETION / (all_speeds[1] - all_speeds[0]))
        peak_idx = {float(ps): int(np.argmin(np.abs(all_speeds - ps))) for ps in set(peaks_speeds)}
        good_speeds = _filter_and_split_ranges(all_speeds, good_speeds, peak_idx, deletion_range)

    good_angles = _identify_low_energy_zones(all_angles_energy, ANGLES_VALLEY_DETECTION_THRESHOLD)
    motor_fr, motor_zeta, lowfreq_max = _compute_mechanical_parameters(
        global_motor_profile, target_freqs, 30.0
    )

    # ---- Shape the JSON payload (downsample the heavy grids for the browser) ----
    angles_ds, a_step = _downsample_axis(all_angles, _MAX_ANGLE_BINS)
    speeds_ds, s_step = _downsample_axis(all_speeds, _MAX_SPEED_BINS)
    metric_norm = vibration_metric / metric_max
    max_norm = sp_max / (float(sp_max.max()) or 1.0)
    angle_energy_norm = all_angles_energy / (float(all_angles_energy.max()) or 1.0)

    grid = np.log1p(spectrogram)
    grid = grid / (float(grid.max()) or 1.0)
    grid_ds = grid[::a_step, ::s_step]

    peak_speed_vals = sorted(round(float(p), 1) for p in peaks_speeds)
    good_speed_ranges = [
        {
            "start": round(float(all_speeds[start]), 1),
            "end": round(float(all_speeds[end]), 1),
            "energy_pct": round(energy, 1),
        }
        for start, end, energy in good_speeds
    ]
    good_angle_ranges = [
        {
            "start": round(float(all_angles[start]), 1),
            "end": round(float(all_angles[end]), 1),
            "energy_pct": round(energy, 1),
        }
        for start, end, energy in good_angles
    ]

    if good_speed_ranges:
        best = good_speed_ranges[0]
        recommended_speed: float | None = round((best["start"] + best["end"]) / 2.0, 1)
    else:
        recommended_speed = round(float(all_speeds[int(np.argmin(vibration_metric))]), 1)

    return {
        "kinematics": kinematics,
        "accel": float(accel),
        "max_freq": float(max_freq),
        "main_angles": main_angles,
        "segments_used": used,
        "speeds": [round(float(s), 1) for s in speeds_ds.tolist()],
        "energy_profile": [round(float(v), 4) for v in metric_norm[::s_step].tolist()],
        "max_profile": [round(float(v), 4) for v in max_norm[::s_step].tolist()],
        "peak_speeds": peak_speed_vals,
        "good_speed_ranges": good_speed_ranges,
        "angles": [round(float(a), 1) for a in angles_ds.tolist()],
        "angle_energy": [round(float(v), 4) for v in angle_energy_norm[::a_step].tolist()],
        "good_angle_ranges": good_angle_ranges,
        "symmetry_pct": round(symmetry, 1),
        "motor_freq": round(motor_fr, 1) if motor_fr is not None else None,
        "motor_damping": round(motor_zeta, 3) if motor_zeta is not None else None,
        "low_freq_warning": bool(lowfreq_max),
        "spectrogram": [[round(float(v), 4) for v in row] for row in grid_ds.tolist()],
        "recommended_speed": recommended_speed,
        "verdict": _verdict(recommended_speed, peak_speed_vals, symmetry, motor_fr, lowfreq_max),
    }


def _verdict(
    recommended_speed: float | None,
    peak_speeds: list[float],
    symmetry: float,
    motor_freq: float | None,
    low_freq_warning: bool,
) -> str:
    """A one-line, plain-language summary of the profile."""
    if low_freq_warning:
        return (
            "Too much low-frequency motion was recorded -- lower the ACCEL (or raise SIZE) "
            "and re-run so only constant speeds are measured."
        )
    parts: list[str] = []
    if recommended_speed is not None:
        parts.append(f"Smoothest around {recommended_speed:.0f} mm/s")
    if peak_speeds:
        shown = ", ".join(f"{p:.0f}" for p in peak_speeds[:4])
        parts.append(f"avoid speeds near {shown} mm/s")
    if symmetry >= 70:
        parts.append(f"motors are well matched ({symmetry:.0f}% symmetry)")
    elif symmetry > 0:
        parts.append(f"motor symmetry is low ({symmetry:.0f}%) -- check belt tension")
    if motor_freq is not None:
        parts.append(f"motor resonance ~{motor_freq:.0f} Hz")
    return "; ".join(parts) + "." if parts else "Vibrations profile complete."
