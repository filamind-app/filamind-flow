"""Axes-map calibration — detect the accelerometer's mounting orientation.

Pure numpy analysis (no Klipper host), ported from Shake&Tune's
``axes_map_computation.py`` (GPL-3.0, (C) 2024 Félix Boisselier). Given three raw
accelerometer captures — one per machine axis X/Y/Z, each a short constant-velocity
stroke — it recovers the accelerometer's orientation by low-pass filtering, velocity
integration and peak detection, and returns the Klipper ``axes_map`` string to use.

Analog of ``shaper_service`` (which vendors Klipper's ``shaper_calibrate``): the
printer-side capture lives in ``resonance_service``; this module is the pure math.
"""

from __future__ import annotations

import io
from typing import Any

import numpy as np

from app.services.shaper_service import ShaperAnalysisError

MACHINE_AXES = ("x", "y", "z")
ACCEL_AXES = ("x", "y", "z")

# Below this confidence + low velocity = a noise-only axis (2-axis / bed-slinger).
NOISE_CONFIDENCE_THRESHOLD = 0.3
MIN_CONFIDENCE = 0.5
MAX_ANGLE_ERROR = 15.0  # degrees
EXPECTED_GRAVITY = 9810.0  # mm/s^2
GRAVITY_TOLERANCE = 0.20
FILTER_CUTOFF = 25.0  # Hz — removes structural ringing while preserving motion
# Velocity series sent to the browser is downsampled to roughly this many points.
_SERIES_POINTS = 200


def _parse_raw_accel(raw: bytes) -> np.ndarray:
    """Parses a Klipper raw-accel CSV (``#time,accel_x,accel_y,accel_z``) to Nx4."""
    text = raw.decode("utf-8", errors="replace")
    try:
        data = np.loadtxt(io.StringIO(text), comments="#", delimiter=",")
    except ValueError:
        # A live capture can have a ragged final row (read mid-flush); skip bad rows.
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
        raise ShaperAnalysisError("Capture has too few or malformed accelerometer samples")
    return np.asarray(data[:, :4], dtype=float)


def _parse_axes_map_to_inverse_matrix(axes_map_str: str | None) -> np.ndarray | None:
    """Inverse of a configured ``axes_map`` so we can recover raw sensor readings."""
    if axes_map_str is None:
        return None
    normalized = axes_map_str.strip().lower().replace(" ", "")
    if normalized == "x,y,z":
        return None
    parts = normalized.split(",")
    if len(parts) != 3:
        return None
    axis_map = {"x": 0, "y": 1, "z": 2}
    forward = np.zeros((3, 3))
    for i, part in enumerate(parts):
        sign = -1.0 if part.startswith("-") else 1.0
        axis_char = part.lstrip("-")
        if axis_char not in axis_map:
            return None
        forward[i, axis_map[axis_char]] = sign
    # For a sign-permutation matrix, the inverse is the transpose.
    return forward.T


def _orthonormalize_rotation_matrix(matrix: np.ndarray) -> np.ndarray:
    """Closest proper rotation (det=+1) to ``matrix`` via SVD."""
    u, _, vt = np.linalg.svd(matrix)
    ortho = u @ vt
    if np.linalg.det(ortho) < 0:
        u[:, -1] *= -1
        ortho = u @ vt
    return ortho


def _extract_euler_xyz(matrix: np.ndarray) -> tuple[float, float, float]:
    """Intrinsic-XYZ Euler angles (roll, pitch, yaw) in degrees."""
    sy = np.sqrt(matrix[2, 1] ** 2 + matrix[2, 2] ** 2)
    if sy > 1e-6:
        roll = np.arctan2(matrix[2, 1], matrix[2, 2])
        pitch = np.arctan2(-matrix[2, 0], sy)
        yaw = np.arctan2(matrix[1, 0], matrix[0, 0])
    else:
        roll = np.arctan2(-matrix[1, 2], matrix[1, 1])
        pitch = np.arctan2(-matrix[2, 0], sy)
        yaw = 0.0
    return (float(np.degrees(roll)), float(np.degrees(pitch)), float(np.degrees(yaw)))


def _lowpass_filter(data: np.ndarray, sample_rate: float) -> np.ndarray:
    """Cascaded moving average (~2nd-order) low-pass at FILTER_CUTOFF."""
    window = int(sample_rate / FILTER_CUTOFF / 2)
    window = max(3, window | 1)
    kernel = np.ones(window) / window
    filtered = np.convolve(data, kernel, mode="same")
    return np.convolve(filtered, kernel, mode="same")


def _integrate_to_velocity(accel: np.ndarray, time: np.ndarray) -> np.ndarray:
    dt = np.diff(time)
    velocity = np.zeros(len(accel))
    velocity[1:] = np.cumsum((accel[:-1] + accel[1:]) / 2 * dt)
    return velocity


def _correct_velocity_drift(velocity: np.ndarray) -> np.ndarray:
    n = len(velocity)
    if n < 2:
        return velocity
    slope = (velocity[-1] - velocity[0]) / (n - 1)
    x = np.arange(n)
    return velocity - (velocity[0] + slope * x)


def _estimate_noise_level(accel_axis: np.ndarray, sample_rate: float) -> float:
    if len(accel_axis) < 10:
        return 0.0
    window = max(5, int(sample_rate * 0.01))
    if window % 2 == 0:
        window += 1
    kernel = np.ones(window) / window
    smoothed = np.convolve(accel_axis, kernel, mode="same")
    noise = accel_axis - smoothed
    return float(1.4826 * np.median(np.abs(noise - np.median(noise))))


def _remove_gravity(
    ax: np.ndarray, ay: np.ndarray, az: np.ndarray
) -> tuple[np.ndarray, np.ndarray, np.ndarray, float]:
    gx, gy, gz = np.median(ax), np.median(ay), np.median(az)
    magnitude = float(np.sqrt(gx**2 + gy**2 + gz**2))
    return ax - gx, ay - gy, az - gz, magnitude


def _detect_direction(
    velocities: dict[str, np.ndarray],
) -> tuple[np.ndarray, np.ndarray, float, float, dict[str, float]]:
    peaks: dict[str, float] = {}
    for axis, vel in velocities.items():
        hi, lo = float(np.max(vel)), float(np.min(vel))
        peaks[axis] = hi if abs(hi) >= abs(lo) else lo
    raw = np.array([peaks["x"], peaks["y"], peaks["z"]])
    norm = float(np.linalg.norm(raw))
    actual = raw / norm if norm > 0 else raw
    abs_peaks = {axis: abs(v) for axis, v in peaks.items()}
    primary = max(abs_peaks, key=lambda k: abs_peaks[k])
    primary_sign = 1.0 if peaks[primary] > 0 else -1.0
    direction = np.zeros(3)
    direction[{"x": 0, "y": 1, "z": 2}[primary]] = primary_sign
    angle_error = float(np.degrees(np.arccos(np.clip(np.dot(actual, direction), -1.0, 1.0))))
    sorted_peaks = sorted(abs_peaks.values(), reverse=True)
    dominance = sorted_peaks[0] / sorted_peaks[1] if sorted_peaks[1] > 0 else float("inf")
    confidence = min(1.0, max(0.0, (dominance - 1) / 4))
    return direction, actual, confidence, angle_error, peaks


def _format_direction_vector(vectors: list[np.ndarray]) -> str:
    formatted = []
    counts = {"x": 0, "y": 0, "z": 0}
    for vector in vectors:
        idx = int(np.argmax(np.abs(vector)))
        name = ACCEL_AXES[idx]
        sign = "" if vector[idx] > 0 else "-"
        formatted.append(f"{sign}{name}")
        counts[name] += 1
    if any(c != 1 for c in counts.values()):
        return "unable to determine correctly!"
    return ", ".join(formatted)


def _detect_noise_only_axis(confidences: list[float], peak_mags: list[float]) -> int | None:
    threshold = max(peak_mags) / 4.0
    noise_axes = [
        i
        for i in range(3)
        if confidences[i] < NOISE_CONFIDENCE_THRESHOLD and peak_mags[i] < threshold
    ]
    if not noise_axes:
        return None
    if len(noise_axes) == 1:
        return noise_axes[0]
    raise ShaperAnalysisError(
        "Multiple axes have no accelerometer signal — check that the sensor is mounted "
        "on the toolhead and moves with it."
    )


def _extrapolate_missing_axis(
    direction_vectors: list[np.ndarray], actual_directions: list[np.ndarray], noise_idx: int
) -> tuple[list[np.ndarray], list[np.ndarray]]:
    i, j = (k for k in range(3) if k != noise_idx)
    cross = np.cross(direction_vectors[i], direction_vectors[j])
    if (i, j) == (0, 2):  # X x Z should give -Y
        cross = -cross
    cross = cross / np.linalg.norm(cross)
    dvs, ads = list(direction_vectors), list(actual_directions)
    dvs[noise_idx] = cross
    ads[noise_idx] = cross
    return dvs, ads


def _downsample(time: np.ndarray, series: np.ndarray) -> tuple[list[float], list[float]]:
    step = max(1, len(time) // _SERIES_POINTS)
    return time[::step].round(5).tolist(), series[::step].round(2).tolist()


def _process_axis(data: np.ndarray, inverse: np.ndarray | None) -> dict[str, Any]:
    time = data[:, 0]
    ax, ay, az = data[:, 1].copy(), data[:, 2].copy(), data[:, 3].copy()
    if inverse is not None:
        stacked = inverse @ np.vstack([ax, ay, az])
        ax, ay, az = stacked[0].copy(), stacked[1].copy(), stacked[2].copy()
    sample_rate = len(time) / (time[-1] - time[0]) if time[-1] > time[0] else 3200.0
    ax, ay, az, gravity = _remove_gravity(ax, ay, az)
    noise = float(np.mean([_estimate_noise_level(a, sample_rate) for a in (ax, ay, az)]))
    vx = _correct_velocity_drift(_integrate_to_velocity(_lowpass_filter(ax, sample_rate), time))
    vy = _correct_velocity_drift(_integrate_to_velocity(_lowpass_filter(ay, sample_rate), time))
    vz = _correct_velocity_drift(_integrate_to_velocity(_lowpass_filter(az, sample_rate), time))
    direction, actual, confidence, angle_error, peaks = _detect_direction(
        {"x": vx, "y": vy, "z": vz}
    )
    return {
        "direction_vector": direction,
        "actual_direction": actual,
        "confidence": confidence,
        "angle_error": angle_error,
        "noise_level": noise,
        "peak_mag": max(abs(v) for v in peaks.values()),
        "gravity": gravity,
        "time": time,
        "vel": (vx, vy, vz),
    }


def analyze_axesmap(
    csv_x: bytes,
    csv_y: bytes,
    csv_z: bytes,
    *,
    current_axes_map: str | None = None,
    accel: float = 1500.0,
) -> dict[str, Any]:
    """Detects the accelerometer orientation from the three per-axis captures."""
    inverse = _parse_axes_map_to_inverse_matrix(current_axes_map)
    per_axis = [_process_axis(_parse_raw_accel(raw), inverse) for raw in (csv_x, csv_y, csv_z)]

    direction_vectors = [a["direction_vector"] for a in per_axis]
    actual_directions = [a["actual_direction"] for a in per_axis]
    confidences = [a["confidence"] for a in per_axis]
    angle_errors = [a["angle_error"] for a in per_axis]
    gravity = float(np.mean([a["gravity"] for a in per_axis]))
    noise_level = float(np.mean([a["noise_level"] for a in per_axis]))

    extrapolated = _detect_noise_only_axis(confidences, [a["peak_mag"] for a in per_axis])
    if extrapolated is not None:
        direction_vectors, actual_directions = _extrapolate_missing_axis(
            direction_vectors, actual_directions, extrapolated
        )
        confidences[extrapolated] = 0.0
        angle_errors[extrapolated] = 0.0

    rotation = _orthonormalize_rotation_matrix(np.array(actual_directions))
    roll, pitch, yaw = _extract_euler_xyz(rotation)
    axes_map = _format_direction_vector(direction_vectors)

    status, messages = _validate(
        direction_vectors, confidences, angle_errors, noise_level, gravity, accel
    )
    noise_grade = "ok" if noise_level <= 350 else "warning" if noise_level <= 700 else "error"

    mappings = []
    for i, axis in enumerate(MACHINE_AXES):
        dv = direction_vectors[i]
        idx = int(np.argmax(np.abs(dv)))
        mappings.append(
            {
                "machine_axis": axis,
                "accel_axis": ACCEL_AXES[idx],
                "sign": "-" if dv[idx] < 0 else "+",
                "angle_error": round(float(angle_errors[i]), 1),
                "confidence": round(float(confidences[i]), 2),
                "extrapolated": i == extrapolated,
            }
        )

    velocity_series = []
    for i, axis in enumerate(MACHINE_AXES):
        time = per_axis[i]["time"]
        vx, vy, vz = per_axis[i]["vel"]
        t, sx = _downsample(time, vx)
        _, sy = _downsample(time, vy)
        _, sz = _downsample(time, vz)
        m = mappings[i]
        velocity_series.append(
            {
                "axis": axis,
                "t": t,
                "vx": sx,
                "vy": sy,
                "vz": sz,
                "detected_axis": f"{m['sign']}{m['accel_axis']}",
                "confidence": m["confidence"],
                "extrapolated": m["extrapolated"],
            }
        )

    current_norm = (current_axes_map or "").strip().lower().replace(" ", "")
    detected_norm = axes_map.strip().lower().replace(" ", "")
    matches_current = (
        current_norm == detected_norm if current_norm and current_norm != "x,y,z" else None
    )

    return {
        "axes_map": axes_map,
        "status": status,
        "messages": messages,
        "mappings": mappings,
        "euler": {"x": round(roll, 1), "y": round(pitch, 1), "z": round(yaw, 1)},
        "gravity": round(gravity / 1000.0, 3),  # m/s^2
        "noise": round(noise_level, 0),
        "noise_grade": noise_grade,
        "current_axes_map": current_axes_map,
        "matches_current": matches_current,
        "accel": accel,
        "extrapolated_axis": extrapolated,
        "velocity_series": velocity_series,
    }


def _validate(
    direction_vectors: list[np.ndarray],
    confidences: list[float],
    angle_errors: list[float],
    noise_level: float,
    gravity: float,
    accel: float,
) -> tuple[str, list[str]]:
    messages: list[str] = []
    status = "ok"
    detected = [int(np.argmax(np.abs(dv))) for dv in direction_vectors]
    if len(set(detected)) != 3:
        status = "error"
        messages.append("Same accelerometer axis detected for multiple machine axes")
    avg_conf = float(np.mean(confidences))
    if avg_conf < MIN_CONFIDENCE:
        status = "warning" if status == "ok" else status
        messages.append(f"Low detection confidence ({avg_conf:.0%})")
    if max(angle_errors) > MAX_ANGLE_ERROR:
        status = "warning" if status == "ok" else status
        messages.append(f"High angle error ({max(angle_errors):.1f}°)")
    low, high = (
        EXPECTED_GRAVITY * (1 - GRAVITY_TOLERANCE),
        EXPECTED_GRAVITY * (1 + GRAVITY_TOLERANCE),
    )
    if not (low <= gravity <= high):
        status = "warning" if status == "ok" else status
        messages.append(f"Unusual gravity reading ({gravity / 1000:.2f} m/s²)")
    if accel and noise_level > accel * 0.3:
        status = "warning" if status == "ok" else status
        messages.append(f"High noise level ({noise_level:.0f} mm/s²)")
    if status == "ok":
        messages.append("Detection quality: good")
    return status, messages
