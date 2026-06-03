"""Read-only TMC stepper-driver inventory for the Motor Drivers widget.

Generic across every Klipper printer: drivers are *discovered* from the live config
(``configfile``), never assumed — any axis names, any number of Z / extruder steppers,
any TMC model (2209 / 2208 / 2130 / 2240 / 5160 / 2660 …). Model-specific differences
(temperature sensor only on 2240, the StallGuard register name) are handled by reading
what the running config actually exposes rather than a hard-coded table.

This phase is read-only; recommending / writing register values comes later.
"""

from __future__ import annotations

import re
from typing import Any

import httpx

from app.services import driver_catalog, motor_catalog, motor_mapping
from app.services.moonraker_client import MoonrakerClient

#: A TMC driver config section name, e.g. "tmc2209 stepper_x" / "tmc5160 stepper_y".
#: ``tmc`` is always followed by digits — the trailing token is the stepper section.
_DRIVER_SECTION = re.compile(r"^(tmc\d\w*)\s+(\S.*)$")

#: StallGuard threshold register, by the field Klipper exposes per model family:
#: 2209 -> sgthrs, 2240 -> sg4_thrs, 2130/5160/2660 -> sgt. Checked in this order.
_STALLGUARD_FIELDS = ("driver_sgthrs", "driver_sg4_thrs", "driver_sgt")


def _as_float(value: Any) -> float | None:
    # bool is a subclass of int — exclude it so True/False never become 1.0/0.0.
    if isinstance(value, bool):
        return None
    return float(value) if isinstance(value, (int, float)) else None


def _as_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    return int(value) if isinstance(value, (int, float)) else None


def _as_bool(value: Any) -> bool | None:
    return value if isinstance(value, bool) else None


def _axis_label(stepper: str) -> str | None:
    """Best-effort human axis label from a stepper section name (generic across printers)."""
    s = stepper.strip().lower()
    if s.startswith("stepper_"):
        return s[len("stepper_") :].upper() or None
    if s == "extruder":
        return "E"
    if s.startswith("extruder"):
        return "E" + s[len("extruder") :]
    return stepper  # unknown kinematics — show the raw section name


def _chopper_mode(stealthchop_threshold: float | None) -> str | None:
    """0 (or unset) => SpreadCycle always; > 0 => StealthChop below that velocity."""
    if stealthchop_threshold is None:
        return None
    return "SpreadCycle" if stealthchop_threshold == 0 else "StealthChop"


def _stallguard(config: dict[str, Any]) -> tuple[str | None, int | None]:
    """Returns (field, value) for whichever StallGuard register this model uses."""
    for field in _STALLGUARD_FIELDS:
        if field in config:
            return field.removeprefix("driver_"), _as_int(config.get(field))
    return None, None


def _registers(config: dict[str, Any]) -> dict[str, Any]:
    """The raw ``driver_*`` tuning registers, for an advanced collapsible view."""
    return {k.removeprefix("driver_"): v for k, v in config.items() if k.startswith("driver_")}


def _capabilities(config: dict[str, Any], temperature: float | None) -> dict[str, bool]:
    """Driver capabilities inferred from config presence — generic, no static table.

    (A curated per-model capability map is a later phase; inferring from the running
    config keeps this correct for any driver the printer actually has.)
    """
    return {
        "stealthchop": "stealthchop_threshold" in config or "driver_pwm_autoscale" in config,
        "spreadcycle": "driver_toff" in config,
        "coolstep": any(k in config for k in ("driver_semin", "driver_semax")),
        "stallguard": any(f in config for f in _STALLGUARD_FIELDS),
        "temperature": temperature is not None,
    }


def _parse_driver(
    name: str, get_status: dict[str, Any], sections: dict[str, Any]
) -> dict[str, Any]:
    """Builds one driver record from its object name + live get_status + config sections."""
    match = _DRIVER_SECTION.match(name)
    model = match.group(1) if match else name.split(" ", 1)[0]
    stepper = match.group(2) if match else name.split(" ", 1)[-1]

    config = sections.get(name)
    config = config if isinstance(config, dict) else {}
    stepper_cfg = sections.get(stepper)
    stepper_cfg = stepper_cfg if isinstance(stepper_cfg, dict) else {}

    temperature = _as_float(get_status.get("temperature"))
    drv_status = get_status.get("drv_status")
    drv_status = drv_status if isinstance(drv_status, dict) else None
    stealth = _as_float(config.get("stealthchop_threshold"))
    sg_field, sg_value = _stallguard(config)

    return {
        "stepper": stepper,
        "model": model,
        "axis": _axis_label(stepper),
        "run_current": _as_float(get_status.get("run_current")),
        "hold_current": _as_float(get_status.get("hold_current")),
        "run_current_config": _as_float(config.get("run_current")),
        "hold_current_config": _as_float(config.get("hold_current")),
        "sense_resistor": _as_float(config.get("sense_resistor")),
        "microsteps": _as_int(stepper_cfg.get("microsteps")),
        "interpolate": _as_bool(config.get("interpolate")),
        "stealthchop_threshold": stealth,
        "chopper_mode": _chopper_mode(stealth),
        "stallguard_field": sg_field,
        "stallguard_threshold": sg_value,
        "temperature": temperature,
        "drv_status": drv_status,
        "capabilities": _capabilities(config, temperature),
        "registers": _registers(config),
    }


def _sections(configfile: Any) -> dict[str, Any]:
    """Parsed config sections — prefer typed ``settings``, fall back to raw ``config``."""
    if not isinstance(configfile, dict):
        return {}
    for key in ("settings", "config"):
        section = configfile.get(key)
        if isinstance(section, dict):
            return section
    return {}


async def gather_drivers(moonraker_url: str, data_dir: str = "") -> dict[str, Any]:
    """Read-only TMC driver inventory: every ``tmcXXXX <stepper>`` the printer has.

    Each driver is annotated with its model's catalog reference (``info``) and the motor
    the user assigned to that stepper (``motor``, from ``<data_dir>/motor-mapping.json``).
    Returns ``{reachable, drivers}``; on an unreachable Moonraker returns
    ``reachable=False`` with an empty list instead of raising.
    """
    client = MoonrakerClient(moonraker_url)
    try:
        configfile = await client.query_objects(["configfile"])
        sections = _sections(configfile.get("configfile"))
        names = sorted(n for n in sections if _DRIVER_SECTION.match(n))
        live = await client.query_objects(names) if names else {}
    except httpx.HTTPError:
        return {"reachable": False, "drivers": []}

    mapping = motor_mapping.read_mapping(data_dir) if data_dir else {}
    drivers: list[dict[str, Any]] = []
    for name in names:
        get_status = live.get(name)
        get_status = get_status if isinstance(get_status, dict) else {}
        record = _parse_driver(name, get_status, sections)
        # Annotate with authoritative reference data for the model (None if unknown).
        record["info"] = driver_catalog.lookup(record["model"])
        # Attach the motor the user assigned to this stepper (None if unassigned).
        record["motor"] = motor_catalog.lookup(mapping.get(record["stepper"], ""))
        drivers.append(record)
    return {"reachable": True, "drivers": drivers}


async def gather_live(moonraker_url: str, stepper: str) -> dict[str, Any]:
    """Fast, focused live telemetry for ONE driver — for the live monitor's quick polling.

    Returns just that driver's ``get_status`` (temperature / run_current / drv_status) without
    re-reading the whole config. ``drv_status`` is ``None`` while the motor is disabled.
    """
    client = MoonrakerClient(moonraker_url)
    try:
        names = await client.list_objects()
        name = next(
            (n for n in names if _DRIVER_SECTION.match(n) and n.split(" ", 1)[-1] == stepper),
            None,
        )
        if name is None:
            return {"reachable": True, "stepper": stepper, "model": None, "drv_status": None}
        status = await client.query_objects([name])
    except httpx.HTTPError:
        return {"reachable": False, "stepper": stepper, "model": None, "drv_status": None}

    obj = status.get(name)
    obj = obj if isinstance(obj, dict) else {}
    drv_status = obj.get("drv_status")
    return {
        "reachable": True,
        "stepper": stepper,
        "model": name.split(" ", 1)[0],
        "temperature": _as_float(obj.get("temperature")),
        "run_current": _as_float(obj.get("run_current")),
        "drv_status": drv_status if isinstance(drv_status, dict) else None,
    }
