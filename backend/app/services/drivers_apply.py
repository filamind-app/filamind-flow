"""Apply driver tuning - the Motor Drivers widget's first *write* path.

Three mechanisms, in increasing scope:
  1. ``config_block`` - render a printer.cfg override block to copy (no write at all).
  2. ``apply_live`` - push values now via ``SET_TMC_CURRENT`` / ``SET_TMC_FIELD``;
     gated: refuses while the printer is *printing*. ``revert`` (``INIT_TMC``) restores
     the configured values.
  3. ``apply_autotune`` - apply a full native tune (current + StealthChop + SpreadCycle +
     CoolStep + velocity thresholds) computed in-house from the motor's datasheet, entirely via
     Klipper's built-in ``SET_TMC_*`` commands - no host extra. Same gate as ``apply_live``.

Live writes are reversible (INIT_TMC re-reads the config, a restart fully restores), but
they touch the driver, so the UI also requires an explicit confirm. The actual numbers
come from the recommender (read-only physics); this module only sends g-code.

Each result carries an i18n ``code`` (+ ``params``) for the UI to translate, alongside the
English ``message`` (kept as a fallback). Passthrough errors - Moonraker failures, field_policy /
ValueError validation text - surface their raw English text with no ``code`` (they are technical /
upstream strings, not localizable copy).
"""

from __future__ import annotations

import re
from typing import Any

import httpx

from app.services import drivers_store, field_policy, motor_mapping, printer_guard, reference_data
from app.services.moonraker_client import MoonrakerClient

#: Recommendation keys that map directly to ``SET_TMC_FIELD FIELD=`` names.
_FIELDS = ("pwm_grad", "pwm_ofs", "hstrt", "hend")

#: Full-tune register order for the config block (mirrors ``_AUTOTUNE_ORDER``); each becomes a
#: ``driver_<field>`` override in the ``[tmcXXXX <stepper>]`` section.
_CONFIG_FIELD_ORDER = (
    "pwm_autoscale",
    "pwm_autograd",
    "pwm_ofs",
    "pwm_grad",
    "toff",
    "tbl",
    "hstrt",
    "hend",
    "semin",
    "semax",
    "seup",
    "sedn",
    "seimin",
)
#: Velocity thresholds are the section's own mm/s options, NOT ``driver_`` register overrides.
_CONFIG_VELOCITY_KEYS = (
    "stealthchop_threshold",
    "coolstep_threshold",
    "high_velocity_threshold",
)

#: Field/current values must be plain numbers - never interpolate arbitrary text into g-code.
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
    stepper: str,
    model: str,
    run_current: float | None,
    fields: dict[str, Any],
    *,
    hold_current: float | None = None,
    velocity_fields: dict[str, Any] | None = None,
) -> str:
    """A printer.cfg override block the user can paste - pure, no side effects.

    Register fields become ``driver_<field>`` overrides; the velocity thresholds are the
    ``[tmcXXXX <stepper>]`` section's own mm/s options (``stealthchop_threshold`` etc.), NOT
    ``driver_`` overrides (writing ``driver_TPWMTHRS`` would be ignored). Persisting the full tune
    here is the native equivalent of the autotune extra's re-apply on every startup.
    """
    lines = [f"[{model} {stepper}]"]
    if run_current is not None:
        lines.append(f"run_current: {run_current}")
    if hold_current is not None:
        lines.append(f"hold_current: {hold_current}")
    for key in _CONFIG_FIELD_ORDER:
        if key in fields and fields[key] is not None:
            lines.append(f"driver_{key}: {_fmt(fields[key])}")
    vfields = velocity_fields or {}
    for key in _CONFIG_VELOCITY_KEYS:
        if key in vfields and vfields[key] is not None:
            lines.append(f"{key}: {_fmt(vfields[key])}")
    return "\n".join(lines) + "\n"


async def _is_busy(client: MoonrakerClient) -> bool:
    """True while the printer is printing, paused, or in an error state - block all register
    writes and motion then. Delegates to the shared :mod:`printer_guard` busy definition."""
    return await printer_guard.is_busy(client)


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


async def _resolve_current_cap(
    client: MoonrakerClient, stepper: str, data_dir: str
) -> float | None:
    """The binding run-current ceiling for this stepper: ``min(driver full-scale cap, mapped
    motor's rated current)``.

    The driver model (and a TMC2240's ``rref``) come from the stepper's live ``[tmcXXXX]``
    section; the motor rating from the Motor Drivers mapping + catalog specs. Returns ``None``
    when nothing is known - no fabricated cap (and a failed lookup never blocks the apply;
    the write itself would surface a real Moonraker error anyway).
    """
    try:
        cf = await client.query_objects(["configfile"])
    except httpx.HTTPError:
        return None
    configfile = cf.get("configfile")
    settings = configfile.get("settings") if isinstance(configfile, dict) else None
    settings = settings if isinstance(settings, dict) else {}
    model = ""
    rref: float | None = None
    for key, value in settings.items():
        if key.startswith("tmc") and key.split(" ", 1)[-1] == stepper and isinstance(value, dict):
            model = key.split(" ", 1)[0]
            raw_rref = value.get("rref")
            if isinstance(raw_rref, (int, float)) and not isinstance(raw_rref, bool):
                rref = float(raw_rref)
            break
    motor_rated: float | None = None
    mapped = motor_mapping.read_mapping(data_dir).get(stepper)
    if mapped:
        spec = reference_data.motor_spec_lookup(mapped)
        raw_max = spec.get("max_current_A") if spec else None
        if isinstance(raw_max, (int, float)) and not isinstance(raw_max, bool):
            motor_rated = float(raw_max)
    return field_policy.current_cap(model, motor_rated, rref)


async def apply_live(
    moonraker_url: str,
    stepper: str,
    run_current: float | None,
    hold_current: float | None,
    fields: dict[str, Any],
    *,
    data_dir: str = "",
    timeout: float = 20.0,
) -> dict[str, Any]:
    """Pushes the values to the driver now. Refuses while printing, and refuses a ``run_current``
    above the binding ceiling (driver full-scale cap / mapped motor rating) - the cap the UI
    displays is enforced here, on the write path itself. Reversible via ``revert``."""
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
        if run_current is not None:
            cap = await _resolve_current_cap(client, stepper, data_dir)
            if cap is not None and run_current > cap + 1e-9:
                cap_r = round(cap, 2)
                return _res(
                    False,
                    [],
                    f"Refusing run_current {run_current} A on {stepper}: it exceeds the "
                    f"{cap_r} A ceiling (driver full-scale limit / rated current of the "
                    "assigned motor).",
                    "overCurrentCap",
                    stepper=stepper,
                    requested=run_current,
                    cap=cap_r,
                )
        for cmd in commands:
            await client.run_gcode(cmd)
    except httpx.HTTPError as exc:
        return _res(False, [], f"Moonraker error: {exc}")
    # Record that this stepper's drivers were tuned, so the Machine Doctor's readiness track can
    # tell tuning has been done (the live writes themselves leave no host-side trace).
    drivers_store.write_tuned(data_dir, stepper, "apply")
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
    restore the configured run/hold current too (INIT_TMC alone doesn't - #93)."""
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


#: Fixed apply order for a native auto-tune: StealthChop enables first (so PWM_OFS/PWM_GRAD seed a
#: running auto-scale), then SpreadCycle hysteresis + chopper, then the CoolStep loop.
_AUTOTUNE_ORDER = (
    "pwm_autoscale",
    "pwm_autograd",
    "pwm_ofs",
    "pwm_grad",
    "toff",
    "tbl",
    "hstrt",
    "hend",
    "semin",
    "semax",
    "seup",
    "sedn",
    "seimin",
)
#: Velocity thresholds are applied last (they arm the mode switch once the registers they depend on
#: are set); CoolStep/StealthChop handoff before the high-velocity ceiling.
_AUTOTUNE_VELOCITY_ORDER = (
    "coolstep_threshold",
    "stealthchop_threshold",
    "high_velocity_threshold",
)


def _autotune_commands(
    stepper: str,
    run_current: float | None,
    hold_current: float | None,
    fields: dict[str, Any],
    velocity_fields: dict[str, Any],
    model: str | None,
) -> list[str]:
    """Build the ordered, validated g-code for a native auto-tune. Every field passes through the
    ``field_policy`` allowlist + clamp; a field not applicable to this model is skipped (not an
    error), and an out-of-range one raises ``PolicyError``. Velocity thresholds are sent as
    ``VELOCITY=`` (mm/s) so Klipper does the TSTEP conversion."""
    stepper = _safe_name(stepper)
    cmds: list[str] = []
    if run_current is not None:
        cmd = f"SET_TMC_CURRENT STEPPER={stepper} CURRENT={_safe_num(run_current)}"
        if hold_current is not None:
            cmd += f" HOLDCURRENT={_safe_num(hold_current)}"
        cmds.append(cmd)
    for field in _AUTOTUNE_ORDER:
        if field not in fields or fields[field] is None:
            continue
        if not field_policy.applies_to(field, model):
            continue
        num = _safe_num(field_policy.validate(field, fields[field], model))
        cmds.append(f"SET_TMC_FIELD STEPPER={stepper} FIELD={field} VALUE={num}")
    for field in _AUTOTUNE_VELOCITY_ORDER:
        if field not in velocity_fields or velocity_fields[field] is None:
            continue
        if not field_policy.applies_to(field, model):
            continue
        num = _safe_num(field_policy.validate(field, velocity_fields[field], model))
        reg = field_policy.register_name(field)
        cmds.append(f"SET_TMC_FIELD STEPPER={stepper} FIELD={reg} VELOCITY={num}")
    return cmds


async def apply_autotune(
    moonraker_url: str,
    stepper: str,
    run_current: float | None,
    hold_current: float | None,
    fields: dict[str, Any],
    velocity_fields: dict[str, Any],
    *,
    model: str | None = None,
    data_dir: str = "",
    timeout: float = 30.0,
) -> dict[str, Any]:
    """Apply a full native TMC tune live via ``SET_TMC_CURRENT`` / ``SET_TMC_FIELD`` - the whole
    register set computed in-house, with no host extra. Same guards as :func:`apply_live`: refused
    while printing, and run/hold current capped at the binding ceiling (driver full-scale limit /
    mapped motor rating). Reversible via :func:`revert` (``INIT_TMC``). The values come from
    :func:`native_autotune.compute_tune`; this only validates + sends g-code."""
    try:
        commands = _autotune_commands(
            stepper, run_current, hold_current, fields, velocity_fields, model
        )
    except (field_policy.PolicyError, ValueError) as exc:
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
        cap = await _resolve_current_cap(client, stepper, data_dir)
        if cap is not None:
            cap_r = round(cap, 2)
            for requested in (run_current, hold_current):
                if requested is not None and requested > cap + 1e-9:
                    return _res(
                        False,
                        [],
                        f"Refusing {requested} A on {stepper}: it exceeds the {cap_r} A ceiling "
                        "(driver full-scale limit / rated current of the assigned motor).",
                        "overCurrentCap",
                        stepper=stepper,
                        requested=requested,
                        cap=cap_r,
                    )
        for cmd in commands:
            await client.run_gcode(cmd)
    except httpx.HTTPError as exc:
        return _res(False, [], f"Moonraker error: {exc}")
    # Record the tune for the Machine Doctor readiness track (see apply_live).
    drivers_store.write_tuned(data_dir, stepper, "autotune")
    return _res(
        True,
        commands,
        f"Auto-tuned {stepper} - applied {len(commands)} change(s).",
        "autotuneApplied",
        n=len(commands),
        stepper=stepper,
    )


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
        "(live only - INIT_TMC or a restart restores the configured value).",
        "fieldSet",
        field=field,
        num=_safe_num(validated),
        stepper=stepper,
    )


#: CoolStep is a coupled loop - rather than five scattered 0-15 boxes, expose one toggle that
#: applies the recommended CoolStep set (or semin=0 to disable, which turns CoolStep off).
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
        "(live only - INIT_TMC or a restart restores the configured values).",
        "coolstepEnabled" if enable else "coolstepDisabled",
        stepper=stepper,
    )


async def home_axis(moonraker_url: str, axis: str, *, timeout: float = 120.0) -> dict[str, Any]:
    """Home a single axis (``G28 <axis>``) - a sensorless-homing test. Gated; refused
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
    requires the add-on installed and refused while printing. Accelerometer-based - it moves
    the toolhead for a while, so the UI warns and requires a confirm.
    """
    if not await motors_sync_available(moonraker_url):
        return _res(
            False,
            [],
            "The motors_sync add-on isn't installed - it aligns the microstep phase "
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
