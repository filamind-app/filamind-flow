"""Accelerometer (vibration) fallback for the Max-Flow slip detector.

When the extruder driver can't expose a live StallGuard load (e.g. a TMC2209 whose toolhead MCU
doesn't surface ``SG_RESULT``), the slip point can instead be read from a toolhead accelerometer:
as the extruder gear starts to grind/skip it produces a sharp rise in vibration intensity and
irregular impulsive "clicks". This module captures the ADXL345 (or other configured chip) during
each flow step, reduces it to per-window vibration-RMS samples, and reuses the same jump detector
as the StallGuard path — just with ratio-based thresholds tuned for vibration rather than SG load.

Experimental by design: the absolute scale of the vibration depends on the printer, so detection
is purely *relative* (a jump versus the recent clean baseline). It reuses the proven
accelerometer-capture plumbing from :mod:`app.services.resonance_service` (the Input Shaping side).
"""

from __future__ import annotations

import io
from collections.abc import Callable
from typing import Any

import numpy as np

from app.services import max_flow, resonance_service, task_store
from app.services.max_flow import StepMeasurement
from app.services.moonraker_client import MoonrakerClient

#: Ratio-based detection thresholds for vibration RMS (scale-independent). Absolute trips are
#: disabled (vibration units vary by machine); slip is a jump versus the recent clean baseline.
ACCEL_CONSTANTS: dict[str, float] = {
    "CV_HIGH_VARIANCE": 1.0e9,  # disable the absolute CV ceiling
    "CV_JUMP_RATIO_COARSE": 2.2,  # within-step spread doubling+ = grinding irregularity
    "CV_JUMP_MIN_COARSE": 0.0,
    "IQR_ABSOLUTE_TRIGGER": 1.0e9,  # disable the absolute IQR trip
    "IQR_RATIO_COARSE": 2.2,
    "IQR_RATIO_MIN_ABS": 0.0,
    "OUTLIER_MAD_RATIO": 5.0,
    "OUTLIER_MIN_REL": 0.5,  # the step's vibration level must jump ≥50% above the run + MAD band
}

#: Per-step accelerometer capture is split into this many windows → one vibration-RMS sample each.
_WINDOWS = 8


def _parse_accel(text: str) -> np.ndarray:
    """Parse a Klipper raw-accel CSV (``#time,accel_x,accel_y,accel_z``) to an Nx4 float array."""
    if not any(ln.strip() and not ln.strip().startswith("#") for ln in text.splitlines()):
        return np.empty((0, 4))  # no data rows — skip numpy's empty-input warning
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
    if data.size == 0 or data.shape[1] < 4:
        return np.empty((0, 4))
    return np.asarray(data[:, :4], dtype=float)


def step_energy_samples(csv_text: str, windows: int = _WINDOWS) -> list[float]:
    """Per-window vibration-RMS (the AC component of the accel magnitude) for one flow step.

    The acceleration magnitude is split into ``windows`` equal time slices; each yields the
    standard deviation of the magnitude in that slice (its RMS about the local mean = how hard it
    is vibrating). Returns one value per window — the "samples" the jump detector consumes.
    """
    data = _parse_accel(csv_text)
    if data.shape[0] < 4:
        return []
    mag = np.sqrt(data[:, 1] ** 2 + data[:, 2] ** 2 + data[:, 3] ** 2)
    chunks = np.array_split(mag, max(1, min(windows, mag.shape[0] // 2)))
    return [float(np.std(chunk)) for chunk in chunks if chunk.size >= 2]


def analyze(measurements: list[StepMeasurement]) -> max_flow.FlowResult:
    """Find the slip point from per-step vibration samples (reuses the StallGuard jump detector)."""
    return max_flow.analyze(measurements, "accel", constants=ACCEL_CONSTANTS)


async def detect_chip(client: MoonrakerClient) -> str | None:
    """The configured accelerometer chip name (e.g. ``adxl345``), or None if none is configured."""
    return await resonance_service._accel_chip(client)


async def ramp(
    client: MoonrakerClient,
    chip: str | None,
    resonance_dirs: str,
    steps: list[tuple[float, float, float]],
    samples_per_step: int,
    total: int,
    progress_cb: Callable[[int, int, dict[str, Any]], None] | None = None,
    cancel_cb: Callable[[], bool] | None = None,
) -> list[StepMeasurement]:
    """Run the flow ramp while capturing the accelerometer each step; stop at the first slip.

    ``steps`` are ``(flow_mm3s, feedrate_mm_min, extrude_mm)`` tuples. Each step brackets its
    extrusion with ``ACCELEROMETER_MEASURE`` (start/stop), waits for the CSV to finish flushing,
    reduces it to vibration samples, and the run stops as soon as a slip is detected.
    """
    import contextlib
    import os

    measurements: list[StepMeasurement] = []
    for index, (flow, feedrate, extrude_mm) in enumerate(steps):
        if cancel_cb is not None and cancel_cb():
            raise task_store.TaskCancelled()
        if progress_cb is not None:
            progress_cb(index + 1, total, {"flow": flow, "phase": "ramp"})
        name = f"maxflow_{index}"
        measure = (
            f"ACCELEROMETER_MEASURE CHIP={chip} NAME={name}"
            if chip
            else (f"ACCELEROMETER_MEASURE NAME={name}")
        )
        before = {
            f["path"]
            for f in resonance_service.list_files(resonance_dirs, resonance_service._ALL_PATTERNS)
        }
        await client.run_gcode(measure)  # start capture
        sub_mm = extrude_mm / samples_per_step
        for _ in range(samples_per_step):
            await client.run_gcode(f"G1 E{sub_mm:.4f} F{feedrate:.0f}")
        await client.run_gcode("M400")
        await client.run_gcode(measure)  # stop → flush CSV
        path = await resonance_service._await_new_file(resonance_dirs, before, name)
        with open(path, "rb") as handle:
            csv_text = handle.read().decode("utf-8", errors="replace")
        with contextlib.suppress(OSError):
            os.remove(path)  # the capture is transient — don't clutter the import list
        measurements.append(
            StepMeasurement(flow_mm3s=flow, sg_samples=step_energy_samples(csv_text))
        )
        if analyze(measurements).slip_flow is not None:
            break
    return measurements
