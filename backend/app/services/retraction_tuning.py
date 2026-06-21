"""Retraction tuning wizard - the second of the closed-loop tuning wizards.

Same guided shape as Pressure Advance: plan a Klipper ``TUNING_TOWER`` that ramps the firmware
retraction length up the print, the operator reads the best-looking Z height off the result, and
the wizard computes + applies the matching length. Pure planning + one gated apply
(``SET_RETRACTION``), which needs a configured ``[firmware_retraction]`` section. Returns a
translatable ``{ok, code, params}`` on apply.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from app.services import printer_guard
from app.services.moonraker_client import MoonrakerClient

_DEFAULT_START = 0.0
_DEFAULT_FACTOR = 0.05  # retract length (mm) added per mm of Z
_MAX_FACTOR = 1.0
_MAX_RETRACT = 10.0  # refuse absurd retraction on apply (firmware retraction is typically 0-8mm)
_SAMPLES = 6


@dataclass(frozen=True)
class RetractionTowerParams:
    start: float = _DEFAULT_START
    factor: float = _DEFAULT_FACTOR
    height: float = 50.0  # tower height (mm) the sample table spans


def validate(p: RetractionTowerParams) -> None:
    if not (0 <= p.start <= _MAX_RETRACT):
        raise ValueError("start out of range")
    if not (0 < p.factor <= _MAX_FACTOR):
        raise ValueError("factor out of range")
    if not (0 < p.height <= 500):
        raise ValueError("height out of range")


def retract_at(height: float, p: RetractionTowerParams) -> float:
    """The retraction length the tower reaches at a given Z height."""
    return round(p.start + p.factor * height, 4)


def plan_tower(p: RetractionTowerParams) -> dict[str, Any]:
    """The TUNING_TOWER command to run + a (height -> retract length) sample table for the UI."""
    validate(p)
    command = (
        "TUNING_TOWER COMMAND=SET_RETRACTION PARAMETER=RETRACT_LENGTH "
        f"START={p.start} FACTOR={p.factor}"
    )
    samples = []
    for i in range(_SAMPLES + 1):
        z = p.height * i / _SAMPLES
        samples.append({"height": round(z, 1), "value": retract_at(z, p)})
    return {
        "command": command,
        "start": p.start,
        "factor": p.factor,
        "height": p.height,
        "samples": samples,
    }


def _has_firmware_retraction(configfile: Any) -> bool:
    """True if the live config has a ``[firmware_retraction]`` section (it is a singleton)."""
    if not isinstance(configfile, dict):
        return False
    for key in ("settings", "config"):
        section = configfile.get(key)
        if isinstance(section, dict) and "firmware_retraction" in section:
            return True
    return False


async def apply_retraction(
    moonraker_url: str, value: float, timeout: float = 10.0
) -> dict[str, Any]:
    """Apply the chosen retraction length live via ``SET_RETRACTION``; gated (refused while busy).
    Needs a configured ``[firmware_retraction]``. Only a bounded float is interpolated into g-code.
    """
    if not (0 <= value <= _MAX_RETRACT):
        return {"ok": False, "code": "out_of_range", "params": {"max": _MAX_RETRACT}}
    client = MoonrakerClient(moonraker_url, timeout=timeout)
    try:
        configfile = await client.query_objects(["configfile"])
        if not _has_firmware_retraction(configfile.get("configfile")):
            return {"ok": False, "code": "no_firmware_retraction", "params": {}}
        if await printer_guard.is_busy(client):
            return {"ok": False, "code": "busy", "params": {}}
        await client.run_gcode(f"SET_RETRACTION RETRACT_LENGTH={round(value, 4)}")
    except httpx.HTTPError as exc:
        return {"ok": False, "code": "moonraker_error", "params": {"error": str(exc)}}
    return {"ok": True, "code": "applied", "params": {"value": round(value, 4)}}
