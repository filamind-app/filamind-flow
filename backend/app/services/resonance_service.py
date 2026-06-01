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

import glob
import os
import re
from typing import Any

from app.services import shaper_service
from app.services.moonraker_client import MoonrakerClient

#: Filenames Klipper produces for resonance data (raw accel + PSD calibration).
_PATTERNS = ("resonances_*.csv", "calibration_data_*.csv", "raw_data_*.csv")
#: Best-effort axis guess from the filename (…_x_… / …_y.csv).
_AXIS_RE = re.compile(r"_(x|y)(?:[._]|$)", re.IGNORECASE)
#: A live test can take a couple of minutes; give Moonraker room.
_LIVE_TEST_TIMEOUT = 600.0


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
            raw = handle.read(20_000_000)
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

    name = f"filamind_{ax}"
    before = {f["path"] for f in list_files(resonance_dirs)}
    try:
        await client.run_gcode(f"TEST_RESONANCES AXIS={ax.upper()} OUTPUT=raw_data NAME={name}")
    except Exception as exc:
        raise shaper_service.ShaperAnalysisError(f"Resonance test failed: {exc}") from exc

    after = list_files(resonance_dirs)
    fresh = [f for f in after if f["path"] not in before]
    candidates = fresh or [f for f in after if name in f["name"]]
    if not candidates:
        raise shaper_service.ShaperAnalysisError(
            "The resonance test finished but no output CSV was found"
        )
    return analyze_file(resonance_dirs, candidates[0]["path"], axis=ax, **kwargs)
