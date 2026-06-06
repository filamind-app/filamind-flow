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

Each result carries an i18n ``code`` (+ ``params``) for the UI to translate, alongside the
English ``message`` (kept as a fallback). Passthrough errors — Moonraker failures, field_policy /
ValueError validation text — surface their raw English text with no ``code`` (they are technical /
upstream strings, not localizable copy).
"""

from __future__ import annotations

import re
from typing import Any

import httpx

from app.services import field_policy
from app.services.moonraker_client import MoonrakerClient

#: Recommendation keys that map directly to ``SET_TMC_FIELD FIELD=`` names.
_FIELDS = ("pwm_grad", "pwm_ofs", "hstrt", "hend")

#: Field/current values must be plain numbers — never interpolate arbitrary text into g-code.
_NUM = re.compile(r"^-?\d+(\.\d+)?$")
#: A stepper section name is a safe identifier (e.g. "stepper_x", "extruder1").
_NAME = re.compile(r"^[A-Za-z][\w-]*$")


def _res(
    ok: bool, applied: list[str], message: str, code: str | None = None, **params: Any
) -> dict[str, Any]:
    """Build an apply-result dict. ``code`` + ``params`` drive UI translation (``t(code, params)``);
    ``message`` is the English fallback (kept byte-identical). Passthrough errors omit ``code``."""
    return {"ok": ok, "applied": applied, "message": message, "code": code, "params": params}


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


async def _is_busy(client: MoonrakerClient) -> bool:
    """True while the printer is printing, paused, or in an error state — block all register
    writes and motion then (not just while actively printing). Reads ``print_stats.state``."""
    status = await client.query_objects(["print_stats"])
    stats = status.get("print_stats")
    stats = stats if isinstance(stats, dict) else {}
    return str(stats.get("state", "")).lower() in ("printing", "paused", "error")


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
        return _res(False, [], str(exc))
    if not commands:
        return _res(False, [], "Nothing to apply.", "nothingToApply")

    client = MoonrakerClient(moonraker_url, timeout=timeout)
    try:
        if await _is_busy(client):
            return _res(
                False,
                [],
                "Refusing to write to a driver while the printer is busy (printing or paused).",
                "busyApply",
            )
        for cmd in commands:
            await client.run_gcode(cmd)
    except httpx.HTTPError as exc:
        return _res(False, [], f"Moonraker error: {exc}")
    return _res(
        True,
        commands,
        f"Applied {len(commands)} change(s) to {stepper}.",
        "applied",
        n=len(commands),
        stepper=stepper,
    )


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
        return _res(False, [], str(exc))
    client = MoonrakerClient(moonraker_url, timeout=timeout)
    try:
        if await _is_busy(client):
            return _res(
                False,
                [],
                "Refusing to re-init while the printer is busy (printing or paused).",
                "busyReinit",
            )
        commands = [f"INIT_TMC STEPPER={stepper}"]
        current_cmd = await _restore_current_cmd(client, stepper)
        if current_cmd:
            commands.append(current_cmd)
        for cmd in commands:
            await client.run_gcode(cmd)
    except httpx.HTTPError as exc:
        return _res(False, [], f"Moonraker error: {exc}")
    return _res(
        True,
        commands,
        f"Re-initialized {stepper} and restored its configured current.",
        "reinitialized",
        stepper=stepper,
    )


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
        return _res(False, [], str(exc))
    if not await autotune_available(moonraker_url, stepper):
        return _res(
            False,
            [],
            "klipper_tmc_autotune is not installed for this stepper "
            "— use the recommendation or copy-to-config instead.",
            "autotuneNotInstalled",
        )
    client = MoonrakerClient(moonraker_url, timeout=timeout)
    cmd = f"AUTOTUNE_TMC STEPPER={stepper}"
    try:
        if await _is_busy(client):
            return _res(
                False,
                [],
                "Refusing to autotune while the printer is busy (printing or paused).",
                "busyAutotune",
            )
        await client.run_gcode(cmd)
    except httpx.HTTPError as exc:
        return _res(False, [], f"Moonraker error: {exc}")
    return _res(True, [cmd], f"Ran AUTOTUNE_TMC on {stepper}.", "autotuneRan", stepper=stepper)


#: StallGuard threshold field names, by model family (2209 / 2130-5160 / 2240).
_SG_FIELDS = ("sgthrs", "sgt", "sg4_thrs")
#: Axes that can be homed individually for a sensorless test.
_AXES = ("X", "Y", "Z")


async def set_stallguard(
    moonraker_url: str, stepper: str, field: str, value: float, *, timeout: float = 20.0
) -> dict[str, Any]:
    """Set a StallGuard threshold (sensorless-homing sensitivity) via SET_TMC_FIELD. Gated."""
    try:
        stepper = _safe_name(stepper)
    except ValueError as exc:
        return _res(False, [], str(exc))
    if field not in _SG_FIELDS:
        return _res(False, [], f"unknown StallGuard field: {field!r}")
    # Server-enforced range (the client's max= is not trusted): sgthrs/sg4_thrs are unsigned
    # 0-255, sgt is a signed -64..63 - a UI sending 300 would otherwise mask-truncate in Klipper.
    try:
        num = _safe_num(field_policy.validate(field, value))
    except (field_policy.PolicyError, ValueError) as exc:
        return _res(False, [], str(exc))
    client = MoonrakerClient(moonraker_url, timeout=timeout)
    cmd = f"SET_TMC_FIELD STEPPER={stepper} FIELD={field} VALUE={num}"
    try:
        if await _is_busy(client):
            return _res(
                False,
                [],
                "Refusing to write while the printer is busy (printing or paused).",
                "busyWrite",
            )
        await client.run_gcode(cmd)
    except httpx.HTTPError as exc:
        return _res(False, [], f"Moonraker error: {exc}")
    return _res(
        True,
        [cmd],
        f"Set {field} = {num} on {stepper}.",
        "stallguardSet",
        field=field,
        num=num,
        stepper=stepper,
    )


async def set_field(
    moonraker_url: str,
    stepper: str,
    field: str,
    value: float,
    *,
    model: str | None = None,
    timeout: float = 20.0,
) -> dict[str, Any]:
    """Write one TMC register field live via ``SET_TMC_FIELD``, behind the ``field_policy``
    allowlist + per-field clamp (rejecting blocked / unknown / out-of-range / not-applicable).

    Velocity-threshold fields are sent as ``VELOCITY=`` in mm/s so Klipper does the TSTEP
    conversion itself (and refuses it on a driver with no clock, e.g. the TMC2660). Gated:
    refused while the printer is busy (printing / paused / error). Reversible via ``revert``
    (``INIT_TMC``); a power-cycle or ``FIRMWARE_RESTART`` also restores the configured value.
    """
    try:
        stepper = _safe_name(stepper)
        validated = field_policy.validate(field, value, model)
    except (field_policy.PolicyError, ValueError) as exc:
        return _res(False, [], str(exc))
    reg = field_policy.register_name(field)
    param = "VELOCITY" if field_policy.is_velocity(field) else "VALUE"
    cmd = f"SET_TMC_FIELD STEPPER={stepper} FIELD={reg} {param}={_safe_num(validated)}"
    client = MoonrakerClient(moonraker_url, timeout=timeout)
    try:
        if await _is_busy(client):
            return _res(
                False,
                [],
                "Refusing to write while the printer is busy (printing or paused).",
                "busyWrite",
            )
        await client.run_gcode(cmd)
    except httpx.HTTPError as exc:
        return _res(False, [], f"Moonraker error: {exc}")
    return _res(
        True,
        [cmd],
        f"Set {field} = {_safe_num(validated)} on {stepper} "
        "(live only — INIT_TMC or a restart restores the configured value).",
        "fieldSet",
        field=field,
        num=_safe_num(validated),
        stepper=stepper,
    )


#: CoolStep is a coupled loop — rather than five scattered 0-15 boxes, expose one toggle that
#: applies the klipper_tmc_autotune-vetted set (or semin=0 to disable, which turns CoolStep off).
_COOLSTEP_ON = {"semin": 2, "semax": 4, "seup": 3, "sedn": 2, "seimin": 1}
_COOLSTEP_OFF = {"semin": 0}


async def set_coolstep(
    moonraker_url: str,
    stepper: str,
    enable: bool,
    *,
    model: str | None = None,
    timeout: float = 20.0,
) -> dict[str, Any]:
    """Enable CoolStep with a single vetted register set (semin/semax/seup/sedn/seimin), or
    disable it (semin=0). Each field still passes the field_policy clamp; gated like any write."""
    try:
        stepper = _safe_name(stepper)
        targets = _COOLSTEP_ON if enable else _COOLSTEP_OFF
        cmds = []
        for fld, val in targets.items():
            num = _safe_num(field_policy.validate(fld, val, model))
            cmds.append(f"SET_TMC_FIELD STEPPER={stepper} FIELD={fld} VALUE={num}")
    except (field_policy.PolicyError, ValueError) as exc:
        return _res(False, [], str(exc))
    client = MoonrakerClient(moonraker_url, timeout=timeout)
    try:
        if await _is_busy(client):
            return _res(
                False,
                [],
                "Refusing to write while the printer is busy (printing or paused).",
                "busyWrite",
            )
        for cmd in cmds:
            await client.run_gcode(cmd)
    except httpx.HTTPError as exc:
        return _res(False, [], f"Moonraker error: {exc}")
    state = "enabled" if enable else "disabled"
    return _res(
        True,
        cmds,
        f"CoolStep {state} on {stepper} "
        "(live only — INIT_TMC or a restart restores the configured values).",
        "coolstepEnabled" if enable else "coolstepDisabled",
        stepper=stepper,
    )


async def home_axis(moonraker_url: str, axis: str, *, timeout: float = 120.0) -> dict[str, Any]:
    """Home a single axis (``G28 <axis>``) — a sensorless-homing test. Gated; refused
    while printing. The caller (UI) warns about crash risk and requires a confirm."""
    ax = str(axis).strip().upper()
    if ax not in _AXES:
        return _res(False, [], f"unknown axis: {axis!r}")
    client = MoonrakerClient(moonraker_url, timeout=timeout)
    cmd = f"G28 {ax}"
    try:
        if await _is_busy(client):
            return _res(
                False,
                [],
                "Refusing to home while the printer is busy (printing or paused).",
                "busyHome",
            )
        await client.run_gcode(cmd)
    except httpx.HTTPError as exc:
        return _res(False, [], f"Moonraker error: {exc}")
    return _res(True, [cmd], f"Homed {ax}.", "homed", ax=ax)


async def motors_sync_available(moonraker_url: str) -> bool:
    """True if the motors_sync add-on is configured (a ``[motors_sync]`` section)."""
    client = MoonrakerClient(moonraker_url)
    try:
        cf = await client.query_objects(["configfile"])
    except httpx.HTTPError:
        return False
    configfile = cf.get("configfile")
    settings = configfile.get("settings") if isinstance(configfile, dict) else None
    settings = settings if isinstance(settings, dict) else {}
    return any(key == "motors_sync" or key.startswith("motors_sync ") for key in settings)


async def run_motors_sync(
    moonraker_url: str, *, calibrate: bool = False, timeout: float = 600.0
) -> dict[str, Any]:
    """Drive the motors_sync add-on to align multi-motor axes (dual/quad-Z, dual-X).

    ``SYNC_MOTORS`` aligns now; ``SYNC_MOTORS_CALIBRATE`` runs the longer calibration. Gated:
    requires the add-on installed and refused while printing. Accelerometer-based — it moves
    the toolhead for a while, so the UI warns and requires a confirm.
    """
    if not await motors_sync_available(moonraker_url):
        return _res(
            False,
            [],
            "The motors_sync add-on isn't installed — it aligns the microstep phase "
            "of multiple motors on one axis (dual/quad-Z, dual-X) using an accelerometer.",
            "motorsyncNotInstalled",
        )
    client = MoonrakerClient(moonraker_url, timeout=timeout)
    cmd = "SYNC_MOTORS_CALIBRATE" if calibrate else "SYNC_MOTORS"
    try:
        if await _is_busy(client):
            return _res(
                False,
                [],
                "Refusing to sync motors while the printer is busy (printing or paused).",
                "busySync",
            )
        await client.run_gcode(cmd)
    except httpx.HTTPError as exc:
        return _res(False, [], f"Moonraker error: {exc}")
    return _res(True, [cmd], f"Ran {cmd}.", "syncRan", cmd=cmd)
