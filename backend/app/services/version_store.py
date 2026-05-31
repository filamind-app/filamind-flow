"""Version tracking — captures the Klipper version a profile was built with, and
records what was flashed to each board.

This lets the UI show a firmware version even for a board Moonraker can't report
— most importantly an *unconfigured* Linux host MCU (no ``[mcu host]`` section),
whose running binary FilaMind installed but which never appears as a live MCU.

Two small JSON stores live under the data dir:
  * ``artifacts/<profile>.build_info.json`` — the Klipper version/commit/date a
    profile was last built with (mirrors KlipperFleet).
  * ``flashed.json`` — ``{board_id: {profile, version, commit, flashed_at}}``,
    written after a successful flash.
"""

from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime
from typing import Any

from app.services.firmware_profiles import artifacts_dir


async def get_klipper_version(klipper_dir: str) -> dict[str, str]:
    """Returns the installed Klipper's git version / commit / date."""
    klipper = os.path.abspath(os.path.expanduser(klipper_dir))
    info: dict[str, str] = {"version": "unknown", "commit": "unknown", "date": "unknown"}

    async def _git(*args: str) -> str | None:
        try:
            proc = await asyncio.create_subprocess_exec(
                "git",
                "-C",
                klipper,
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=5)
        except (OSError, NotImplementedError, asyncio.TimeoutError):
            return None
        if proc.returncode != 0:
            return None
        return stdout.decode(errors="replace").strip() or None

    if version := await _git("describe", "--tags", "--always", "--long", "--dirty"):
        info["version"] = version
    if commit := await _git("rev-parse", "HEAD"):
        info["commit"] = commit[:12]
    if date := await _git("log", "-1", "--format=%ci"):
        info["date"] = date
    return info


def _now() -> str:
    return datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S")


def _build_info_path(data_dir: str, profile: str) -> str:
    return os.path.join(artifacts_dir(data_dir), f"{profile}.build_info.json")


def write_build_info(data_dir: str, profile: str, version_info: dict[str, str]) -> None:
    """Stores the Klipper version a profile was just built with."""
    payload = {**version_info, "built_at": _now()}
    with open(_build_info_path(data_dir, profile), "w") as handle:
        json.dump(payload, handle, indent=2)


def read_build_info(data_dir: str, profile: str) -> dict[str, Any] | None:
    """Returns a profile's stored build info, or None."""
    try:
        with open(_build_info_path(data_dir, profile)) as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _flash_log_path(data_dir: str) -> str:
    return os.path.join(os.path.expanduser(data_dir), "flashed.json")


def flash_records(data_dir: str) -> dict[str, Any]:
    """Returns the per-board flash records ({board_id: {...}})."""
    try:
        with open(_flash_log_path(data_dir)) as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def record_flash(data_dir: str, board_id: str, profile: str, version_info: dict[str, Any]) -> None:
    """Records that ``board_id`` was flashed with ``profile`` at the given version."""
    records = flash_records(data_dir)
    records[board_id] = {
        "profile": profile,
        "version": version_info.get("version"),
        "commit": version_info.get("commit"),
        "flashed_at": _now(),
    }
    path = _flash_log_path(data_dir)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.tmp"
    with open(tmp, "w") as handle:
        json.dump(records, handle, indent=2)
    os.replace(tmp, path)


def flashed_version(data_dir: str, board_id: str) -> str | None:
    """The firmware version last flashed to a board, if recorded."""
    record = flash_records(data_dir).get(board_id)
    return record.get("version") if isinstance(record, dict) else None
