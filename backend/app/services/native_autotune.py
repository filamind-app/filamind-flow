"""Native full TMC auto-tune - the register set the autotune extra would compute and apply,
worked out in our own code from the motor's datasheet and applied through Klipper's built-in
``SET_TMC_*`` commands. No host extra is required.

:func:`compute_tune` wraps the read-only :mod:`recommender` and adds the pieces a full autotune
sets on top of the run current + StealthChop/SpreadCycle registers: the StealthChop auto-scaling
enables, the vetted CoolStep loop, and the StealthChop->SpreadCycle velocity thresholds (derived
from the same StealthChop-saturation speed the recommender already computes, scaled to mm/s by the
stepper's ``rotation_distance``). Every value is re-validated on the write path by
:mod:`field_policy`, so an out-of-range or not-applicable field is rejected there, never silently
mask-truncated. :func:`run` resolves the assigned motor + live driver model + rotation_distance,
computes the tune, and applies it live (gated, reversible via ``INIT_TMC``).
"""

from __future__ import annotations

from typing import Any

import httpx

from app.services import drivers_apply, field_policy, motor_mapping, recommender, reference_data
from app.services import motor_constants as mc
from app.services.moonraker_client import MoonrakerClient


def _fits(field: str, value: float, model: str | None) -> bool:
    """Whether a computed register value is applicable to ``model`` AND within its register range.

    A value that would overflow its register (e.g. ``pwm_ofs`` > 255 for a high-resistance motor at
    a low supply voltage) is dropped from the tune rather than aborting the whole apply on the write
    path - the StealthChop auto-scale enables (always set) let the driver derive that register
    itself. This keeps the tune usable on any motor instead of hard-failing on an unusual one.
    """
    if not field_policy.applies_to(field, model):
        return False
    try:
        field_policy.validate(field, value, model)
    except field_policy.PolicyError:
        return False
    return True


def compute_tune(
    motor: dict[str, Any],
    model: str,
    *,
    volts: float = mc.DEFAULT_VOLTS,
    run_current: float | None = None,
    rotation_distance: float | None = None,
) -> dict[str, Any]:
    """Compute the full native auto-tune for a motor on a given driver ``model``.

    The caller must first check ``recommender.missing_specs(motor)`` is empty. ``rotation_distance``
    (mm per motor rev, read from the live config) is needed for the velocity thresholds; when it is
    unknown they are omitted (never fabricated). Returns the run current, a register ``fields`` map
    (applied via ``SET_TMC_FIELD VALUE=``), and a ``velocity_fields`` map (mm/s, applied via
    ``VELOCITY=``) - both already gated to the fields this model actually has.
    """
    rec = recommender.recommend(
        motor, volts=volts, run_current=run_current, is_2240=(model.lower() == "tmc2240")
    )

    # Register fields: StealthChop enables first (so PWM_OFS/PWM_GRAD seed a running auto-scale, as
    # the autotune write order does), then the SpreadCycle hysteresis + chopper, then CoolStep.
    fields: dict[str, int] = {}
    fields.update(mc.STEALTH_ENABLES)
    fields["pwm_ofs"] = rec["pwm_ofs"]
    fields["pwm_grad"] = rec["pwm_grad"]
    fields["toff"] = rec["toff"]
    fields["tbl"] = rec["tbl"]
    fields["hstrt"] = rec["hstrt"]
    fields["hend"] = rec["hend"]
    fields.update(mc.COOLSTEP_SET)
    fields = {k: v for k, v in fields.items() if _fits(k, v, model)}

    # Velocity thresholds (mm/s; Klipper TSTEP-encodes them). autotune ties both the StealthChop->
    # SpreadCycle handoff (TPWMTHRS) and CoolStep/StallGuard activation (TCOOLTHRS) to the
    # StealthChop PWM-saturation speed, and puts THIGH above it. All need rotation_distance to
    # become mm/s - omit them entirely when it is unknown.
    velocity_fields: dict[str, float] = {}
    rps = float(rec["max_pwm_rps"])
    if rotation_distance and rotation_distance > 0 and rps > 0:
        handoff = round(mc.velocity_mm_s(rps, rotation_distance), 2)
        high = round(mc.velocity_mm_s(rps * mc.THIGH_RPS_MULT, rotation_distance), 2)
        candidates = {
            "stealthchop_threshold": handoff,
            "coolstep_threshold": handoff,
            "high_velocity_threshold": high,
        }
        velocity_fields = {k: v for k, v in candidates.items() if field_policy.applies_to(k, model)}

    return {
        "run_current": rec["run_current"],
        "fields": fields,
        "velocity_fields": velocity_fields,
        "recommendation": rec,
    }


def _fail(message: str, code: str, **params: Any) -> dict[str, Any]:
    """An apply-result in the standard shape for a pre-flight refusal (no g-code sent)."""
    return {"ok": False, "applied": [], "message": message, "code": code, "params": params}


async def _resolve_context(
    moonraker_url: str, stepper: str, *, timeout: float
) -> tuple[str, float | None]:
    """The stepper's live TMC driver model + its ``rotation_distance`` (mm per motor rev), read
    from the printer's ``configfile``. Returns ``("", None)`` when the config can't be read."""
    client = MoonrakerClient(moonraker_url, timeout=timeout)
    try:
        cf = await client.query_objects(["configfile"])
    except httpx.HTTPError:
        return "", None
    configfile = cf.get("configfile")
    settings = configfile.get("settings") if isinstance(configfile, dict) else None
    settings = settings if isinstance(settings, dict) else {}
    model = ""
    for key, value in settings.items():
        if key.startswith("tmc") and key.split(" ", 1)[-1] == stepper and isinstance(value, dict):
            model = key.split(" ", 1)[0]
            break
    rotation_distance: float | None = None
    section = settings.get(stepper)
    if isinstance(section, dict):
        raw_rd = section.get("rotation_distance")
        if isinstance(raw_rd, (int, float)) and not isinstance(raw_rd, bool):
            rotation_distance = float(raw_rd)
    return model, rotation_distance


async def run(
    moonraker_url: str, data_dir: str, stepper: str, voltage: float, *, timeout: float = 30.0
) -> dict[str, Any]:
    """Compute and apply the full native tune for ``stepper``. Resolves the assigned motor (from
    the Motor Drivers mapping + catalog) and the live driver model + rotation_distance, then applies
    the tune via :func:`drivers_apply.apply_autotune` (gated, reversible). On success the applied
    set is echoed in ``params`` so the UI can offer a matching printer.cfg persist block."""
    mapped = motor_mapping.read_mapping(data_dir).get(stepper)
    motor = reference_data.motor_spec_lookup(mapped) if mapped else None
    if motor is None:
        return _fail(
            f"No motor is assigned to {stepper} - assign one with datasheet specs first.",
            "autotuneNoMotor",
            stepper=stepper,
        )
    missing = recommender.missing_specs(motor)
    if missing:
        return _fail(
            f"The motor assigned to {stepper} is missing datasheet specs "
            f"({', '.join(missing)}) needed to auto-tune.",
            "autotuneNoSpecs",
            stepper=stepper,
        )
    model, rotation_distance = await _resolve_context(moonraker_url, stepper, timeout=timeout)
    if not model:
        return _fail(
            f"Could not read the {stepper} driver model from the printer config.",
            "autotuneNoModel",
            stepper=stepper,
        )
    tune = compute_tune(motor, model, volts=voltage, rotation_distance=rotation_distance)
    result = await drivers_apply.apply_autotune(
        moonraker_url,
        stepper,
        tune["run_current"],
        None,
        tune["fields"],
        tune["velocity_fields"],
        model=model,
        data_dir=data_dir,
        timeout=timeout,
    )
    if result.get("ok"):
        result["params"] = {
            **result.get("params", {}),
            "model": model,
            "run_current": tune["run_current"],
            "hold_current": None,
            "fields": tune["fields"],
            "velocity_fields": tune["velocity_fields"],
        }
    return result
