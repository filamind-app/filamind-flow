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
import contextlib
import glob
import os
import re
import time
from typing import Any

from app.services import axes_map_service, shaper_service, spectrogram_service
from app.services.moonraker_client import MoonrakerClient

#: Klipper writes raw accelerometer data from a background process, so the
#: TEST_RESONANCES gcode returns before the (large) CSV is flushed. Poll until a
#: matching file's size has been stable for this long before reading it.
_POLL_INTERVAL = 0.5
_FILE_SETTLE = 2.0
_FILE_WAIT_TIMEOUT = 120.0

#: Filenames Klipper produces for resonance data (raw accel + PSD calibration).
_PATTERNS = ("resonances_*.csv", "calibration_data_*.csv", "raw_data_*.csv")
#: Intermediate raw-accel files ACCELEROMETER_MEASURE writes (axes-map etc.). These
#: are transient — captured, read, then deleted by the orchestrators — so they are
#: matched for the capture-await but kept OUT of the user-facing import list (which
#: uses _PATTERNS only) to avoid clutter.
_CAPTURE_PATTERNS = ("*-axesmap_*.csv", "*-filamind_static-*.csv", "*-vib_*.csv")
_ALL_PATTERNS = _PATTERNS + _CAPTURE_PATTERNS
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
#: A sustain-frequency hold is a slow TEST_RESONANCES sweep this wide (Hz) around the
#: target — close enough to a constant hold, using only stock Klipper g-code.
_STATIC_BAND = 3.0


def resolve_dirs(resonance_dirs: str) -> list[str]:
    """Expands the comma-separated resonance-directory setting to expanded paths."""
    return [os.path.expanduser(d.strip()) for d in resonance_dirs.split(",") if d.strip()]


def list_files(resonance_dirs: str, patterns: tuple[str, ...] = _PATTERNS) -> list[dict[str, Any]]:
    """Lists resonance CSVs found in the configured directories, newest first."""
    found: dict[str, dict[str, Any]] = {}
    for directory in resolve_dirs(resonance_dirs):
        for pattern in patterns:
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


async def _ensure_test_ready(client: MoonrakerClient) -> None:
    """Shared guards + homing for any live capture (raises ShaperAnalysisError)."""
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


async def _run_resonances(
    client: MoonrakerClient, resonance_dirs: str, *, axis_arg: str, name: str, extra: str = ""
) -> str:
    """Runs one ``TEST_RESONANCES`` (an axis or a ``dx,dy`` vector, plus any ``extra``
    params like ``FREQ_START=…``) and returns the raw-accel CSV path it wrote."""
    before = {f["path"] for f in list_files(resonance_dirs, _ALL_PATTERNS)}
    try:
        await client.run_gcode(
            f"TEST_RESONANCES AXIS={axis_arg} OUTPUT=raw_data NAME={name}{extra}"
        )
    except Exception as exc:
        raise shaper_service.ShaperAnalysisError(f"Resonance test failed: {exc}") from exc
    return await _await_new_file(resonance_dirs, before, name)


async def _capture(
    client: MoonrakerClient,
    resonance_dirs: str,
    *,
    axis_arg: str,
    name: str,
    analyze_axis: str | None,
    **kwargs: Any,
) -> dict[str, Any]:
    """Runs one ``TEST_RESONANCES`` and analyses the CSV it writes."""
    target = await _run_resonances(client, resonance_dirs, axis_arg=axis_arg, name=name)
    return analyze_file(resonance_dirs, target, axis=analyze_axis, **kwargs)


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
    await _ensure_test_ready(client)
    return await _capture(
        client,
        resonance_dirs,
        axis_arg=ax.upper(),
        name=f"filamind_{ax}",
        analyze_axis=ax,
        **kwargs,
    )


async def compare_belts(moonraker_url: str, resonance_dirs: str, **kwargs: Any) -> dict[str, Any]:
    """Runs a belt-direction resonance test on each CoreXY belt and returns both.

    Excites the ``(1,1)`` and ``(1,-1)`` diagonals — the two belts — so their
    responses can be overlaid to spot a tension mismatch. **Moves the toolhead**
    (two sweeps). Print-guarded; requires a configured resonance tester.
    """
    client = MoonrakerClient(moonraker_url, timeout=_LIVE_TEST_TIMEOUT)
    await _ensure_test_ready(client)
    belt_a = await _capture(
        client, resonance_dirs, axis_arg="1,1", name="belt_a", analyze_axis=None, **kwargs
    )
    belt_b = await _capture(
        client, resonance_dirs, axis_arg="1,-1", name="belt_b", analyze_axis=None, **kwargs
    )
    return {"belt_a": belt_a, "belt_b": belt_b}


async def run_static_excitation(
    moonraker_url: str,
    resonance_dirs: str,
    *,
    axis: str = "x",
    freq: float = 50.0,
    duration: float = 15.0,
    max_freq: float = 200.0,
) -> dict[str, Any]:
    """Holds an axis vibrating near ``freq`` for ``duration`` s (a slow, narrow
    ``TEST_RESONANCES`` sweep around the target — no custom macro needed) so the user
    can touch parts to find the resonance source, then returns a time-frequency
    spectrogram + an energy-vs-time timeline.

    **Moves the toolhead** (buzzes in place at the probe point). Print-guarded.
    """
    ax = axis.lower()
    if ax not in ("x", "y"):
        raise shaper_service.ShaperAnalysisError("axis must be 'x' or 'y'")
    freq = max(5.0, min(float(freq), max_freq - _STATIC_BAND))
    duration = max(3.0, min(float(duration), 120.0))

    client = MoonrakerClient(moonraker_url, timeout=_LIVE_TEST_TIMEOUT)
    await _ensure_test_ready(client)

    half = _STATIC_BAND / 2.0
    freq_start = max(1.0, freq - half)
    freq_end = freq + half
    hz_per_sec = (freq_end - freq_start) / duration
    extra = f" FREQ_START={freq_start:.2f} FREQ_END={freq_end:.2f} HZ_PER_SEC={hz_per_sec:.4f}"
    target = await _run_resonances(
        client, resonance_dirs, axis_arg=ax.upper(), name="filamind_static", extra=extra
    )

    if not _is_allowed(target, resonance_dirs):
        raise shaper_service.ShaperAnalysisError("Capture landed outside the allowed dirs")
    with open(target, "rb") as handle:
        raw = handle.read(128_000_000)
    result = spectrogram_service.compute_spectrogram(
        raw, freq=freq, duration=duration, axis=ax, max_freq=max_freq
    )
    result["source_file"] = os.path.basename(target)
    with contextlib.suppress(OSError):  # transient capture
        os.remove(target)
    return result


async def _accel_chip(client: MoonrakerClient) -> str | None:
    """The accelerometer chip name for ACCELEROMETER_MEASURE (None = printer default)."""
    try:
        data = await client.query_objects(["configfile"])
    except Exception:
        return None
    config = data.get("configfile", {}).get("config", {})
    if not isinstance(config, dict):
        return None
    rt = config.get("resonance_tester", {})
    chip = rt.get("accel_chip") or rt.get("accel_chip_x") if isinstance(rt, dict) else None
    if isinstance(chip, str) and chip.strip():
        return chip.strip()
    for section in config:
        if section.split(" ", 1)[0] in (
            "adxl345",
            "lis2dw",
            "lis3dh",
            "mpu9250",
            "mpu6050",
            "icm20948",
        ):
            return section
    return None


def _axes_map_of(config: dict[str, Any], chip: str | None) -> str | None:
    """The configured ``axes_map`` for the chip's section, if any."""
    if not chip:
        return None
    section = config.get(chip, {})
    value = section.get("axes_map") if isinstance(section, dict) else None
    return value.strip() if isinstance(value, str) and value.strip() else None


async def _bed_center(client: MoonrakerClient) -> tuple[float, float] | None:
    """(mid_x, mid_y) from the toolhead's axis limits, or None if unavailable."""
    try:
        data = await client.query_objects(["toolhead"])
    except Exception:
        return None
    toolhead = data.get("toolhead", {})
    lo, hi = toolhead.get("axis_minimum"), toolhead.get("axis_maximum")
    if isinstance(lo, list) and isinstance(hi, list) and len(lo) >= 2 and len(hi) >= 2:
        return (lo[0] + hi[0]) / 2.0, (lo[1] + hi[1]) / 2.0
    return None


async def _capture_axesmap_segment(
    client: MoonrakerClient, resonance_dirs: str, chip: str | None, axis_label: str, move_gcode: str
) -> str:
    """Brackets one constant-velocity stroke with ACCELEROMETER_MEASURE start/stop and
    returns the raw-accel CSV Klipper wrote for it."""
    name = f"axesmap_{axis_label}"
    measure = (
        f"ACCELEROMETER_MEASURE CHIP={chip} NAME={name}"
        if chip
        else f"ACCELEROMETER_MEASURE NAME={name}"
    )
    before = {f["path"] for f in list_files(resonance_dirs, _ALL_PATTERNS)}
    await client.run_gcode(measure)  # start
    await client.run_gcode("G4 P500")
    await client.run_gcode(move_gcode)
    await client.run_gcode("M400")
    await client.run_gcode("G4 P500")
    await client.run_gcode(measure)  # stop -> flush CSV
    return await _await_new_file(resonance_dirs, before, name)


async def calibrate_axes_map(
    moonraker_url: str,
    resonance_dirs: str,
    *,
    z_height: float = 20.0,
    speed: float = 80.0,
    accel: float = 1500.0,
    travel_speed: float = 120.0,
) -> dict[str, Any]:
    """Detects the accelerometer's ``axes_map`` by jogging the toolhead +X/+Y/+Z.

    **Moves the toolhead** (three 30 mm strokes around bed center + a 30 mm Z rise).
    Print-guarded; requires a configured resonance tester + accelerometer.
    """
    client = MoonrakerClient(moonraker_url, timeout=_LIVE_TEST_TIMEOUT)
    await _ensure_test_ready(client)

    chip = await _accel_chip(client)
    try:
        cfg = (await client.query_objects(["configfile"])).get("configfile", {}).get("config", {})
    except Exception:
        cfg = {}
    current_map = _axes_map_of(cfg if isinstance(cfg, dict) else {}, chip)

    center = await _bed_center(client)
    if center is None:
        raise shaper_service.ShaperAnalysisError(
            "Could not determine the bed center from the printer config"
        )
    mid_x, mid_y = center

    try:
        toolhead = (await client.query_objects(["toolhead"])).get("toolhead", {})
        old_accel = toolhead.get("max_accel")
        old_scv = toolhead.get("square_corner_velocity")
    except Exception:
        old_accel = old_scv = None

    f_travel = int(travel_speed * 60)
    f_move = int(speed * 60)
    moves = {
        "x": f"G1 X{mid_x + 15:.1f} Y{mid_y - 15:.1f} Z{z_height:.1f} F{f_move}",
        "y": f"G1 X{mid_x + 15:.1f} Y{mid_y + 15:.1f} Z{z_height:.1f} F{f_move}",
        "z": f"G1 X{mid_x + 15:.1f} Y{mid_y + 15:.1f} Z{z_height + 30:.1f} F{f_move}",
    }
    paths: dict[str, str] = {}
    try:
        await client.run_gcode(f"SET_VELOCITY_LIMIT ACCEL={int(accel)} SQUARE_CORNER_VELOCITY=5.0")
        await client.run_gcode("G90")
        await client.run_gcode(
            f"G1 X{mid_x - 15:.1f} Y{mid_y - 15:.1f} Z{z_height:.1f} F{f_travel}"
        )
        await client.run_gcode("M400")
        for axis in ("x", "y", "z"):
            paths[axis] = await _capture_axesmap_segment(
                client, resonance_dirs, chip, axis, moves[axis]
            )
    except shaper_service.ShaperAnalysisError:
        raise
    except Exception as exc:
        raise shaper_service.ShaperAnalysisError(f"Axes-map calibration failed: {exc}") from exc
    finally:
        if old_accel:
            scv = f" SQUARE_CORNER_VELOCITY={old_scv}" if old_scv else ""
            with contextlib.suppress(Exception):
                await client.run_gcode(f"SET_VELOCITY_LIMIT ACCEL={int(old_accel)}{scv}")

    raws = []
    for axis in ("x", "y", "z"):
        if not _is_allowed(paths[axis], resonance_dirs):
            raise shaper_service.ShaperAnalysisError("Capture landed outside the allowed dirs")
        with open(paths[axis], "rb") as handle:
            raws.append(handle.read(64_000_000))
    result = axes_map_service.analyze_axesmap(
        raws[0], raws[1], raws[2], current_axes_map=current_map, accel=accel
    )
    result["chip"] = chip or "adxl345"
    result["source_files"] = [os.path.basename(paths[a]) for a in ("x", "y", "z")]
    for path in paths.values():  # best-effort cleanup of the transient captures
        with contextlib.suppress(OSError):
            os.remove(path)
    return result


async def _await_new_file(resonance_dirs: str, before: set[str], name: str) -> str:
    """Waits for the fresh resonance CSV to appear and finish being written.

    Returns the path once a matching file's size has been stable for ``_FILE_SETTLE``
    seconds, so the (background-written) capture isn't read while still flushing.
    """
    deadline = time.monotonic() + _FILE_WAIT_TIMEOUT
    last_size = -1
    stable_at: float | None = None
    while time.monotonic() < deadline:
        after = list_files(resonance_dirs, _ALL_PATTERNS)
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
