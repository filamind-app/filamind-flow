"""Beacon eddy-current probe firmware.

A Beacon probe carries its own STM32 + firmware, flashed not over Katapult / DFU
but by the Beacon Klipper plugin's own ``update_firmware.py``. We discover probes
off ``/dev/serial/by-id`` (they self-identify as ``Beacon_Beacon_Rev<X>``), find
the plugin's checkout via Moonraker's ``update_manager``, flash through it, and
read the newest version in that checkout to flag when an update is available.
"""

from __future__ import annotations

import asyncio
import glob
import os
import re
from collections.abc import AsyncIterator
from typing import Any

import httpx

from app.config import Settings

_BEACON_GLOB = "/dev/serial/by-id/*Beacon_Beacon_Rev*"
_BEACON_RE = re.compile(r"Beacon_Beacon_(Rev[A-Za-z0-9]+)_([A-Za-z0-9]+)")


def _parse_beacon(by_id: str) -> dict[str, str] | None:
    """Parses a Beacon /dev/serial/by-id path into id / revision / serial."""
    match = _BEACON_RE.search(os.path.basename(by_id))
    if not match:
        return None
    revision, serial = match.group(1), match.group(2)
    return {"id": by_id, "name": f"Beacon {revision}", "revision": revision, "serial": serial}


def discover_beacons() -> list[dict[str, str]]:
    """Finds connected Beacon probes off /dev/serial/by-id."""
    probes: list[dict[str, str]] = []
    seen: set[str] = set()
    for dev in sorted(glob.glob(_BEACON_GLOB)):
        parsed = _parse_beacon(dev)
        if parsed and parsed["serial"] not in seen:
            seen.add(parsed["serial"])
            probes.append(parsed)
    return probes


async def beacon_repo_path(moonraker_url: str) -> str | None:
    """Resolves the Beacon plugin's checkout path from Moonraker's update_manager."""
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(f"{moonraker_url}/server/config")
            payload = resp.json()
    except (httpx.HTTPError, ValueError):
        return None
    config = (payload.get("result") or {}).get("config") or {}
    for key, section in config.items():
        if key.startswith("update_manager") and "beacon" in key.lower():
            path = section.get("path") if isinstance(section, dict) else None
            if path:
                return os.path.expanduser(str(path))
    return None


async def remote_version(repo_path: str) -> str | None:
    """The newest Beacon firmware version available in the plugin's checkout."""

    async def _git(*args: str) -> str | None:
        try:
            proc = await asyncio.create_subprocess_exec(
                "git",
                "-C",
                repo_path,
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
            out, _ = await asyncio.wait_for(proc.communicate(), timeout=5)
        except (OSError, asyncio.TimeoutError, NotImplementedError):
            return None
        return out.decode(errors="replace").strip() if proc.returncode == 0 else None

    return await _git("describe", "--tags", "--abbrev=0") or None


async def gather_beacons(moonraker_url: str) -> dict[str, Any]:
    """Discovered probes + the plugin path + the available version (for the UI)."""
    repo = await beacon_repo_path(moonraker_url)
    available = await remote_version(repo) if repo else None
    return {"probes": discover_beacons(), "repo": repo, "available_version": available}


async def flash_beacon(device: str, settings: Settings) -> AsyncIterator[str]:
    """Updates a Beacon probe through the plugin's ``update_firmware.py``."""
    repo = await beacon_repo_path(settings.moonraker_url)
    if not repo:
        yield "!! Could not find the Beacon plugin via Moonraker's update_manager.\n"
        return
    script = os.path.join(repo, "update_firmware.py")
    if not os.path.isfile(script):
        yield f"!! Beacon updater not found at {script}.\n"
        return
    yield f">>> Updating Beacon {device} via update_firmware.py…\n"
    try:
        proc = await asyncio.create_subprocess_exec(
            "python3",
            script,
            "update",
            device,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
    except (OSError, NotImplementedError) as exc:
        yield f"!! cannot run update_firmware.py: {exc}\n"
        return
    assert proc.stdout is not None
    while True:
        raw = await proc.stdout.readline()
        if not raw:
            break
        yield raw.decode(errors="replace")
    await proc.wait()
    yield ">>> Beacon update complete — verify it reconnects in Mainsail.\n"
