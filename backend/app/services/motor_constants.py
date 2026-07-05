"""Pure stepper-motor physics (datasheet parameters → TMC register values).

No klippy dependency: each function takes the motor's datasheet parameters plus the
operating conditions and returns a computed register value. Used by the recommender to
suggest StealthChop PWM (``pwm_grad`` / ``pwm_ofs``) and SpreadCycle hysteresis
(``hstrt`` / ``hend``) from a motor's specs - powering both the recommendation and the
native full auto-tune, with no host extra installed.

Formulas derive each value from the datasheet parameters and operating point.
"""

from __future__ import annotations

import math

#: TMC internal clock (Hz) and default supply voltage - autotune's defaults.
DEFAULT_FCLK = 12.5e6
DEFAULT_VOLTS = 24.0

#: ``tblank`` cycles indexed by the ``TBL`` setting; the TMC2240 uses a different table.
TBLANK_CYCLES = (16, 24, 32, 40)
TBLANK_CYCLES_2240 = (16, 24, 36, 54)


def cbemf(holding_torque_nm: float, max_current_a: float) -> float:
    """Back-EMF constant (V·s/rad) from holding torque and rated phase current."""
    return holding_torque_nm / (2.0 * max_current_a)


def pwmgrad(
    cbemf_v: float, steps_per_rev: int, volts: float = DEFAULT_VOLTS, fclk: float = DEFAULT_FCLK
) -> int:
    """StealthChop ``PWM_GRAD`` register value."""
    return math.ceil(cbemf_v * 2 * math.pi * fclk * 1.46 / (volts * 256.0 * steps_per_rev))


def pwmofs(resistance_ohm: float, current_a: float, volts: float = DEFAULT_VOLTS) -> int:
    """StealthChop ``PWM_OFS`` register value at the given coil current."""
    return math.ceil(374 * resistance_ohm * current_a / volts)


def maxpwmrps(pwm_ofs: int, pwm_grad: int) -> float:
    """Maximum revolutions/sec before StealthChop PWM saturates (0 if undefined)."""
    if pwm_grad <= 0:
        return 0.0
    return (255 - pwm_ofs) / (math.pi * pwm_grad)


def hysteresis(
    resistance_ohm: float,
    inductance_h: float,
    current_a: float,
    *,
    volts: float = DEFAULT_VOLTS,
    tblank_cycles: int = 24,
    toff: int = 3,
    extra: int = 0,
    fclk: float = DEFAULT_FCLK,
) -> tuple[int, int]:
    """SpreadCycle hysteresis register values ``(hstrt, hend)`` - faithful to autotune."""
    tsd = (12.0 + 32.0 * toff) / fclk
    dcoilblank = volts * (tblank_cycles / fclk) / inductance_h
    dcoilsd = resistance_ohm * current_a * 2.0 * tsd / inductance_h
    raw = extra + math.ceil(
        max(0.5 + ((dcoilblank + dcoilsd) * 2 * 248 * 32 / current_a) / 32 - 8, -2)
    )
    htotal = min(raw, 14)
    hstrt = max(min(htotal, 8), 1)
    hend = min(htotal - hstrt, 12)
    return hstrt - 1, hend + 3


# --- StealthChop -> SpreadCycle -> CoolStep velocity thresholds (native full auto-tune) -------
# The full tune adds the register set the autotune extra applies on top of the PWM / hysteresis
# values above: the StealthChop auto-scaling enables, the vetted CoolStep loop, and the velocity
# thresholds. The thresholds are expressed as velocities (rev/s); Klipper's
# ``SET_TMC_FIELD ... VELOCITY=`` converts mm/s (rev/s * rotation_distance) to the TSTEP register,
# so this module only needs the rev/s (the caller supplies the stepper's rotation_distance).

#: THIGH sits above the StealthChop handoff - autotune keeps SpreadCycle/fullstep engaged from
#: about twice the PWM-saturation speed upward.
THIGH_RPS_MULT = 2.0

#: Fixed StealthChop enables autotune always writes: seed PWM_OFS/PWM_GRAD, then let the driver
#: auto-scale and auto-gradient around them at runtime.
STEALTH_ENABLES: dict[str, int] = {"pwm_autoscale": 1, "pwm_autograd": 1}

#: The autotune-vetted CoolStep loop (kept in step with ``drivers_apply._COOLSTEP_ON``).
COOLSTEP_SET: dict[str, int] = {"semin": 2, "semax": 4, "seup": 3, "sedn": 2, "seimin": 1}


def velocity_mm_s(rps: float, rotation_distance: float) -> float:
    """Convert a motor speed (rev/s) to mm/s via the stepper's ``rotation_distance`` (mm per motor
    rev) - the value to pass as ``SET_TMC_FIELD ... VELOCITY=``. Returns 0 when either input is
    non-positive (i.e. the threshold is undefined and must be omitted, never fabricated)."""
    if rps <= 0.0 or rotation_distance <= 0.0:
        return 0.0
    return rps * rotation_distance
