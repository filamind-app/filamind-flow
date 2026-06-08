"""Driver-tuning recommender: a motor's datasheet specs + supply voltage → a suggested
run current and the StealthChop / SpreadCycle register values, via the pure
``motor_constants`` physics. Compute-only (read-only); applying the values is a later,
gated step.
"""

from __future__ import annotations

from typing import Any

from app.services import motor_constants as mc

#: A conservative default run current as a fraction of the motor's rated phase current.
#: (Run motors below their rating to limit heat; the user can override.)
DEFAULT_CURRENT_FRACTION = 0.7

#: The datasheet fields a recommendation needs.
_REQUIRED = ("resistance_ohm", "inductance_H", "holding_torque_Nm", "max_current_A")


def missing_specs(motor: dict[str, Any]) -> list[str]:
    """Which required datasheet fields are absent/empty for this motor."""
    return [k for k in _REQUIRED if not motor.get(k)]


def recommend(
    motor: dict[str, Any],
    *,
    volts: float = mc.DEFAULT_VOLTS,
    run_current: float | None = None,
    toff: int = 3,
    tbl: int = 2,
    extra_hysteresis: int = 0,
    is_2240: bool = False,
) -> dict[str, Any]:
    """Computes the recommended run current + registers. Caller must first check
    ``missing_specs`` is empty."""
    resistance = float(motor["resistance_ohm"])
    inductance = float(motor["inductance_H"])
    torque = float(motor["holding_torque_Nm"])
    max_current = float(motor["max_current_A"])
    steps = int(motor.get("steps_per_rev") or 200)

    provided = run_current is not None and run_current > 0.0
    current = (
        float(run_current)
        if run_current is not None and run_current > 0.0
        else round(DEFAULT_CURRENT_FRACTION * max_current, 2)
    )

    cbemf = mc.cbemf(torque, max_current)
    pwm_grad = mc.pwmgrad(cbemf, steps, volts)
    pwm_ofs = mc.pwmofs(resistance, current, volts)
    rps = mc.maxpwmrps(pwm_ofs, pwm_grad)

    tbl = max(0, min(tbl, 3))
    tblank = (mc.TBLANK_CYCLES_2240 if is_2240 else mc.TBLANK_CYCLES)[tbl]
    hstrt, hend = mc.hysteresis(
        resistance,
        inductance,
        current,
        volts=volts,
        tblank_cycles=tblank,
        toff=toff,
        extra=extra_hysteresis,
    )

    return {
        "motor_model": str(motor.get("model", "")),
        "motor_name": f"{motor.get('manufacturer', '')} "
        f"{motor.get('name') or motor.get('model', '')}".strip(),
        "run_current": current,
        "run_current_basis": (
            "your value"
            if provided
            else f"{int(DEFAULT_CURRENT_FRACTION * 100)}% of the rated {max_current} A"
        ),
        "pwm_grad": pwm_grad,
        "pwm_ofs": pwm_ofs,
        "hstrt": hstrt,
        "hend": hend,
        "max_pwm_rps": round(rps, 2),
        "cbemf": round(cbemf, 5),
        "voltage": volts,
        "toff": toff,
        "tbl": tbl,
    }
