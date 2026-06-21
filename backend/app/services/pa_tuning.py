"""Pressure Advance tuning wizard - the first of the closed-loop tuning wizards.

Truly-closed-loop PA needs a sensor no printer has, so this is the realistic guided form: plan a
Klipper ``TUNING_TOWER`` that ramps PA up the print, the operator reads the best-looking Z height
off the result, and the wizard computes + applies the matching PA. Pure planning + one gated apply
(``SET_PRESSURE_ADVANCE``). Returns translatable ``{ok, code, params}`` on apply.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from app.services import printer_guard
from app.services.moonraker_client import MoonrakerClient

_DEFAULT_START = 0.0
_DEFAULT_FACTOR = 0.005  # PA (ADVANCE) added per mm of Z
_MAX_FACTOR = 0.2
_MAX_PA = 2.0  # refuse absurd PA on apply (Klipper PA is typically 0-1)
_SAMPLES = 6


@dataclass(frozen=True)
class PaTowerParams:
    start: float = _DEFAULT_START
    factor: float = _DEFAULT_FACTOR
    height: float = 50.0  # tower height (mm) the sample table spans


def validate(p: PaTowerParams) -> None:
    if not (0 <= p.start <= _MAX_PA):
        raise ValueError("start out of range")
    if not (0 < p.factor <= _MAX_FACTOR):
        raise ValueError("factor out of range")
    if not (0 < p.height <= 500):
        raise ValueError("height out of range")


def pa_at(height: float, p: PaTowerParams) -> float:
    """The PA value the tower reaches at a given Z height."""
    return round(p.start + p.factor * height, 4)


def plan_tower(p: PaTowerParams) -> dict[str, Any]:
    """The TUNING_TOWER command to run + a (height -> PA) sample table for the UI."""
    validate(p)
    command = (
        "TUNING_TOWER COMMAND=SET_PRESSURE_ADVANCE PARAMETER=ADVANCE "
        f"START={p.start} FACTOR={p.factor}"
    )
    samples = [
        {"height": round(p.height * i / _SAMPLES, 1), "pa": pa_at(p.height * i / _SAMPLES, p)}
        for i in range(_SAMPLES + 1)
    ]
    return {
        "command": command,
        "start": p.start,
        "factor": p.factor,
        "height": p.height,
        "samples": samples,
    }


async def apply_pa(moonraker_url: str, value: float, timeout: float = 10.0) -> dict[str, Any]:
    """Apply the chosen PA live via ``SET_PRESSURE_ADVANCE``; gated (refused while busy).
    Only a bounded float is interpolated into g-code."""
    if not (0 <= value <= _MAX_PA):
        return {"ok": False, "code": "out_of_range", "params": {"max": _MAX_PA}}
    client = MoonrakerClient(moonraker_url, timeout=timeout)
    try:
        if await printer_guard.is_busy(client):
            return {"ok": False, "code": "busy", "params": {}}
        await client.run_gcode(f"SET_PRESSURE_ADVANCE ADVANCE={round(value, 4)}")
    except httpx.HTTPError as exc:
        return {"ok": False, "code": "moonraker_error", "params": {"error": str(exc)}}
    return {"ok": True, "code": "applied", "params": {"value": round(value, 4)}}
