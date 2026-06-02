"""Connected resonance capture.

Two printer-side conveniences on top of the pure ``shaper_service`` analysis:

1. **Import** the resonance CSVs Klipper writes on the printer host (``/tmp`` by
   default) — list them and analyse one by path, so the user need not download
   and re-upload anything.
2. **Live test** — trigger ``TEST_RESONANCES`` on a chosen axis via Moonraker,
   wait for the run, then analyse the CSV it produced.

These only do something useful when FilaMind runs on the printer host. Listing /
analysing files is read-only and safe. Running a live test **moves the toolhead**,
so it is print-guarded and refuses unless a ``[resonance_tester]`` is configured.
"""

from __future__ import annotations

import asyncio
import glob
import os
import re
import time
from typing import Any

from app.services import shaper_service
from app.services.moonraker_client import MoonrakerClient

#: Klipper writes raw accelerometer data from a background process, so the
#: TEST_RESONANCES gcode returns before the (large) CSV is flushed. Poll until a
#: matching file's size has been stable for this long before reading it.
_POLL_INTERVAL = 0.5
_FILE_SETTLE = 2.0
_FILE_WAIT_TIMEOUT = 120.0

#: Filenames Klipper produces for resonance data (raw accel + PSD calibration).
_PATTERNS = ("resonances_*.csv", "calibration_data_*.csv", "raw_data_*.csv")
#: Best-effort axis guess from the filename (…_x_… / …_y.csv).
_AXIS_RE = re.compile(r"_(x|y)(?:[._]|$)", re.IGNORECASE)
#: A live test can take a couple of minutes; give Moonraker room.
_LIVE_TEST_TIMEOUT = 600.0
#: MEASURE_AXES_NOISE just dwells ~2 s reading the accelerometer.
_NOISE_TIMEOUT = 30.0

#: Klipper's MEASURE_AXES_NOISE output, one line per accelerometer chip:
#: "Axes noise for <label>-axis accelerometer: <x> (x), <y> (y), <z> (z)".
_NOISE_RE = re.compile(
    r"Axes noise for (?P<label>\S+?)-axis accelerometer:\s*"
    r"(?P<x>[-+\d.eE]+) \(x\),\s*(?P<y>[-+\d.eE]+) \(y\),\s*(?P<z>[-+\d.eE]+) \(z\)"
)
#: Per Klipper's docs, ~1-100 is normal; ~1000+ means a problem.
_NOISE_OK = 100.0
_NOISE_HIGH = 1000.0


def resolve_dirs(resonance_dirs: str) -> list[str]:
    """Expands the comma-separated resonance-directory setting to expanded paths."""
    return [os.path.expanduser(d.strip()) for d in resonance_dirs.split(",") if d.strip()]


def list_files(resonance_dirs: str) -> list[dict[str, Any]]:
    """Lists resonance CSVs found in the configured directories, newest first."""
    found: dict[str, dict[str, Any]] = {}
    for directory in resolve_dirs(resonance_dirs):
        for pattern in _PATTERNS:
            for path in glob.glob(os.path.join(directory, pattern)):
                if not os.path.isfile(path):
                    continue
                name = os.path.basename(path)
                axis = _AXIS_RE.search(name)
                found[path] = {
                    "name": name,
                    "path": path,
                    "size": os.path.getsize(path),
                    "mtime": os.path.getmtime(path),
                    "axis": axis.group(1).lower() if axis else None,
                }
    return sorted(found.values(), key=lambda f: f["mtime"], reverse=True)


def _is_allowed(path: str, resonance_dirs: str) -> bool:
    """True if ``path`` resolves inside one of the configured directories."""
    real = os.path.realpath(path)
    return any(
        real == os.path.realpath(d) or real.startswith(os.path.realpath(d) + os.sep)
        for d in resolve_dirs(resonance_dirs)
    )


def analyze_file(resonance_dirs: str, path: str, **kwargs: Any) -> dict[str, Any]:
    """Reads a resonance CSV from the host (within the allowed dirs) and analyses it."""
    if not _is_allowed(path, resonance_dirs):
        raise shaper_service.ShaperAnalysisError(
            "File is outside the allowed resonance directories"
        )
    try:
        with open(path, "rb") as handle:
            # A live capture can be tens of MB (a long sweep). Read generously so a
            # large file isn't silently truncated mid-row, which corrupts the parse.
            raw = handle.read(128_000_000)
    except OSError as exc:
        raise shaper_service.ShaperAnalysisError(f"Could not read {path}: {exc}") from exc
    result = shaper_service.analyze(raw, **kwargs)
    result["source_file"] = os.path.basename(path)
    return result


async def _is_printing(client: MoonrakerClient) -> bool:
    try:
        data = await client.query_objects(["print_stats"])
    except Exception:
        return False
    stats = data.get("print_stats")
    return isinstance(stats, dict) and stats.get("state") in ("printing", "paused")


async def _has_resonance_tester(client: MoonrakerClient) -> bool:
    # `resonance_tester` is a config *section*, not a queryable status object, so
    # it never shows up in /printer/objects/list — check the parsed config map.
    try:
        data = await client.query_objects(["configfile"])
    except Exception:
        return False
    config = data.get("configfile", {}).get("config", {})
    return isinstance(config, dict) and "resonance_tester" in config


async def _homed_axes(client: MoonrakerClient) -> str:
    """Returns Klipper's homed-axes string (e.g. 'xyz'), or '' if unknown."""
    try:
        data = await client.query_objects(["toolhead"])
    except Exception:
        return ""
    toolhead = data.get("toolhead", {})
    return str(toolhead.get("homed_axes", "")) if isinstance(toolhead, dict) else ""


def _parse_noise(messages: list[str]) -> list[dict[str, Any]]:
    """Extracts per-chip noise dicts from MEASURE_AXES_NOISE console lines."""
    chips: list[dict[str, Any]] = []
    for message in messages:
        match = _NOISE_RE.search(message)
        if match:
            chips.append(
                {
                    "label": match.group("label"),
                    "x": float(match.group("x")),
                    "y": float(match.group("y")),
                    "z": float(match.group("z")),
                }
            )
    return chips


async def measure_noise(moonraker_url: str) -> dict[str, Any]:
    """Runs ``MEASURE_AXES_NOISE`` and returns the accelerometer's idle noise floor.

    A pre-flight check for the sensor mount — **does not move the toolhead** (it just
    dwells while reading the accelerometer). Print-guarded and requires a configured
    resonance tester. The result is parsed from the G-code console output.
    """
    client = MoonrakerClient(moonraker_url, timeout=_NOISE_TIMEOUT)
    if await _is_printing(client):
        raise shaper_service.ShaperAnalysisError(
            "Printer is printing or paused — refusing to measure noise"
        )
    if not await _has_resonance_tester(client):
        raise shaper_service.ShaperAnalysisError(
            "No [resonance_tester] / accelerometer is configured on this printer"
        )

    # Snapshot existing console lines so we read only the ones this run produces.
    try:
        seen = {(e.get("time"), e.get("message")) for e in await client.gcode_store(50)}
    except Exception:
        seen = set()

    try:
        await client.run_gcode("MEASURE_AXES_NOISE")
    except Exception as exc:
        raise shaper_service.ShaperAnalysisError(f"Noise measurement failed: {exc}") from exc

    try:
        store = await client.gcode_store(50)
    except Exception as exc:
        raise shaper_service.ShaperAnalysisError(f"Could not read the result: {exc}") from exc

    fresh = [
        str(e.get("message", "")) for e in store if (e.get("time"), e.get("message")) not in seen
    ]
    chips = _parse_noise(fresh) or _parse_noise([str(e.get("message", "")) for e in store])
    if not chips:
        raise shaper_service.ShaperAnalysisError("MEASURE_AXES_NOISE produced no readable output")

    values = [v for chip in chips for v in (chip["x"], chip["y"], chip["z"])]
    max_noise = max(values)
    grade = "good" if max_noise < _NOISE_OK else "high" if max_noise >= _NOISE_HIGH else "elevated"
    return {
        "chips": chips,
        "max_noise": max_noise,
        "grade": grade,
        "ok": max_noise < _NOISE_OK,
        "threshold": _NOISE_OK,
    }


async def run_live_test(
    moonraker_url: str, resonance_dirs: str, *, axis: str = "x", **kwargs: Any
) -> dict[str, Any]:
    """Triggers ``TEST_RESONANCES`` on an axis, then analyses the resulting CSV.

    Print-guarded and requires a configured resonance tester. The Moonraker call
    blocks for the duration of the test (the toolhead moves).
    """
    ax = axis.lower()
    if ax not in ("x", "y"):
        raise shaper_service.ShaperAnalysisError("axis must be 'x' or 'y'")

    client = MoonrakerClient(moonraker_url, timeout=_LIVE_TEST_TIMEOUT)
    if await _is_printing(client):
        raise shaper_service.ShaperAnalysisError(
            "Printer is printing or paused — refusing to run a resonance test"
        )
    if not await _has_resonance_tester(client):
        raise shaper_service.ShaperAnalysisError(
            "No [resonance_tester] / accelerometer is configured on this printer"
        )

    # TEST_RESONANCES moves to the probe point, which requires homed axes —
    # home first if the printer isn't already fully homed.
    homed = await _homed_axes(client)
    if not all(axis in homed for axis in "xyz"):
        try:
            await client.run_gcode("G28")
        except Exception as exc:
            raise shaper_service.ShaperAnalysisError(f"Homing failed: {exc}") from exc

    name = f"filamind_{ax}"
    before = {f["path"] for f in list_files(resonance_dirs)}
    try:
        await client.run_gcode(f"TEST_RESONANCES AXIS={ax.upper()} OUTPUT=raw_data NAME={name}")
    except Exception as exc:
        raise shaper_service.ShaperAnalysisError(f"Resonance test failed: {exc}") from exc

    target = await _await_new_file(resonance_dirs, before, name)
    return analyze_file(resonance_dirs, target, axis=ax, **kwargs)


async def _await_new_file(resonance_dirs: str, before: set[str], name: str) -> str:
    """Waits for the fresh resonance CSV to appear and finish being written.

    Returns the path once a matching file's size has been stable for ``_FILE_SETTLE``
    seconds, so the (background-written) capture isn't read while still flushing.
    """
    deadline = time.monotonic() + _FILE_WAIT_TIMEOUT
    last_size = -1
    stable_at: float | None = None
    while time.monotonic() < deadline:
        after = list_files(resonance_dirs)
        fresh = [f for f in after if f["path"] not in before]
        candidates = fresh or [f for f in after if name in f["name"]]
        if candidates:
            path = candidates[0]["path"]
            try:
                size = os.path.getsize(path)
            except OSError:
                size = -1
            if size > 0 and size == last_size:
                if stable_at is None:
                    stable_at = time.monotonic()
                elif time.monotonic() - stable_at >= _FILE_SETTLE:
                    return path
            else:
                stable_at = None
                last_size = size
        await asyncio.sleep(_POLL_INTERVAL)
    raise shaper_service.ShaperAnalysisError(
        "Timed out waiting for the resonance CSV to finish writing"
    )
