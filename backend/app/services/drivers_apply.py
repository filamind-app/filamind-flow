"""Apply driver tuning — the Motor Drivers widget's first *write* path.

Three mechanisms, in increasing risk:
  1. ``config_block`` — render a printer.cfg override block to copy (no write at all).
  2. ``apply_live`` — push values now via ``SET_TMC_CURRENT`` / ``SET_TMC_FIELD``;
     gated: refuses while the printer is *printing*. ``revert`` (``INIT_TMC``) restores
     the configured values.
  3. ``run_autotune`` — drive the ``klipper_tmc_autotune`` extra's ``AUTOTUNE_TMC`` if it
     is configured (``[autotune_tmc <stepper>]`` present).

Live writes are reversible (INIT_TMC re-reads the config, a restart fully restores), but
they touch the driver, so the UI also requires an explicit confirm. The actual numbers
come from the recommender (read-only physics); this module only sends g-code.
"""

from __future__ import annotations

import re
from typing import Any

import httpx

from app.services.moonraker_client import MoonrakerClient

#: Recommendation keys that map directly to ``SET_TMC_FIELD FIELD=`` names.
_FIELDS = ("pwm_grad", "pwm_ofs", "hstrt", "hend")

#: Field/current values must be plain numbers — never interpolate arbitrary text into g-code.
_NUM = re.compile(r"^-?\d+(\.\d+)?$")
#: A stepper section name is a safe identifier (e.g. "stepper_x", "extruder1").
_NAME = re.compile(r"^[A-Za-z][\w-]*$")


def _safe_name(stepper: str) -> str:
    if not _NAME.match(stepper):
        raise ValueError(f"unsafe stepper name: {stepper!r}")
    return stepper


def _fmt(value: Any) -> str:
    """Render a number for g-code/config: integral floats (14.0) become ints (14)."""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def _safe_num(value: Any) -> str:
    text = _fmt(value)
    if not _NUM.match(text):
        raise ValueError(f"non-numeric value: {value!r}")
    return text


def config_block(
    stepper: str, model: str, run_current: float | None, fields: dict[str, Any]
) -> str:
    """A printer.cfg override block the user can paste — pure, no side effects."""
    lines = [f"[{model} {stepper}]"]
    if run_current is not None:
        lines.append(f"run_current: {run_current}")
    for key in _FIELDS:
        if key in fields and fields[key] is not None:
            lines.append(f"driver_{key}: {_fmt(fields[key])}")
    return "\n".join(lines) + "\n"


async def _is_printing(client: MoonrakerClient) -> bool:
    status = await client.query_objects(["print_stats"])
    stats = status.get("print_stats")
    stats = stats if isinstance(stats, dict) else {}
    return str(stats.get("state", "")).lower() == "printing"


def _commands(
    stepper: str, run_current: float | None, hold_current: float | None, fields: dict[str, Any]
) -> list[str]:
    """Builds the g-code commands for a live apply (validated, in a stable order)."""
    stepper = _safe_name(stepper)
    cmds: list[str] = []
    if run_current is not None:
        cmd = f"SET_TMC_CURRENT STEPPER={stepper} CURRENT={_safe_num(run_current)}"
        if hold_current is not None:
            cmd += f" HOLDCURRENT={_safe_num(hold_current)}"
        cmds.append(cmd)
    for key in _FIELDS:
        if key in fields and fields[key] is not None:
            cmds.append(
                f"SET_TMC_FIELD STEPPER={stepper} FIELD={key} VALUE={_safe_num(fields[key])}"
            )
    return cmds


async def apply_live(
    moonraker_url: str,
    stepper: str,
    run_current: float | None,
    hold_current: float | None,
    fields: dict[str, Any],
    *,
    timeout: float = 20.0,
) -> dict[str, Any]:
    """Pushes the values to the driver now. Refuses while printing. Reversible via ``revert``."""
    try:
        commands = _commands(stepper, run_current, hold_current, fields)
    except ValueError as exc:
        return {"ok": False, "applied": [], "message": str(exc)}
    if not commands:
        return {"ok": False, "applied": [], "message": "Nothing to apply."}

    client = MoonrakerClient(moonraker_url, timeout=timeout)
    try:
        if await _is_printing(client):
            return {
                "ok": False,
                "applied": [],
                "message": "Refusing to write to a driver while the printer is printing.",
            }
        for cmd in commands:
            await client.run_gcode(cmd)
    except httpx.HTTPError as exc:
        return {"ok": False, "applied": [], "message": f"Moonraker error: {exc}"}
    return {
        "ok": True,
        "applied": commands,
        "message": f"Applied {len(commands)} change(s) to {stepper}.",
    }


async def _restore_current_cmd(client: MoonrakerClient, stepper: str) -> str | None:
    """A ``SET_TMC_CURRENT`` restoring the stepper's *configured* run/hold current, or None.

    ``INIT_TMC`` re-applies register fields but NOT the run current set via
    ``SET_TMC_CURRENT`` (#93), so a full revert must restore the current explicitly.
    """
    cf = await client.query_objects(["configfile"])
    configfile = cf.get("configfile")
    settings = configfile.get("settings") if isinstance(configfile, dict) else None
    settings = settings if isinstance(settings, dict) else {}
    section = next(
        (
            value
            for key, value in settings.items()
            if key.startswith("tmc")
            and key.split(" ", 1)[-1] == stepper
            and isinstance(value, dict)
        ),
        None,
    )
    if section is None:
        return None
    run_current = section.get("run_current")
    if not isinstance(run_current, (int, float)) or isinstance(run_current, bool):
        return None
    cmd = f"SET_TMC_CURRENT STEPPER={stepper} CURRENT={_fmt(run_current)}"
    hold = section.get("hold_current")
    if isinstance(hold, (int, float)) and not isinstance(hold, bool):
        cmd += f" HOLDCURRENT={_fmt(hold)}"
    return cmd


async def revert(moonraker_url: str, stepper: str, *, timeout: float = 20.0) -> dict[str, Any]:
    """Undo a live apply: ``INIT_TMC`` re-applies the configured register fields, and we
    restore the configured run/hold current too (INIT_TMC alone doesn't — #93)."""
    try:
        stepper = _safe_name(stepper)
    except ValueError as exc:
        return {"ok": False, "applied": [], "message": str(exc)}
    client = MoonrakerClient(moonraker_url, timeout=timeout)
    try:
        if await _is_printing(client):
            return {"ok": False, "applied": [], "message": "Refusing to re-init while printing."}
        commands = [f"INIT_TMC STEPPER={stepper}"]
        current_cmd = await _restore_current_cmd(client, stepper)
        if current_cmd:
            commands.append(current_cmd)
        for cmd in commands:
            await client.run_gcode(cmd)
    except httpx.HTTPError as exc:
        return {"ok": False, "applied": [], "message": f"Moonraker error: {exc}"}
    return {
        "ok": True,
        "applied": commands,
        "message": f"Re-initialized {stepper} and restored its configured current.",
    }


async def autotune_available(moonraker_url: str, stepper: str) -> bool:
    """True if the klipper_tmc_autotune extra is configured for this stepper."""
    client = MoonrakerClient(moonraker_url)
    try:
        cf = await client.query_objects(["configfile"])
    except httpx.HTTPError:
        return False
    configfile = cf.get("configfile")
    settings = configfile.get("settings") if isinstance(configfile, dict) else None
    settings = settings if isinstance(settings, dict) else {}
    return f"autotune_tmc {stepper}" in settings


async def run_autotune(
    moonraker_url: str, stepper: str, *, timeout: float = 120.0
) -> dict[str, Any]:
    """Drives ``AUTOTUNE_TMC`` if the extra is installed for this stepper."""
    try:
        stepper = _safe_name(stepper)
    except ValueError as exc:
        return {"ok": False, "applied": [], "message": str(exc)}
    if not await autotune_available(moonraker_url, stepper):
        return {
            "ok": False,
            "applied": [],
            "message": "klipper_tmc_autotune is not installed for this stepper "
            "— use the recommendation or copy-to-config instead.",
        }
    client = MoonrakerClient(moonraker_url, timeout=timeout)
    cmd = f"AUTOTUNE_TMC STEPPER={stepper}"
    try:
        if await _is_printing(client):
            return {"ok": False, "applied": [], "message": "Refusing to autotune while printing."}
        await client.run_gcode(cmd)
    except httpx.HTTPError as exc:
        return {"ok": False, "applied": [], "message": f"Moonraker error: {exc}"}
    return {"ok": True, "applied": [cmd], "message": f"Ran AUTOTUNE_TMC on {stepper}."}
