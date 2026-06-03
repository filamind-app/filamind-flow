"""Pure stepper-motor physics — a faithful port of klipper_tmc_autotune's
``motor_constants.py`` (datasheet parameters → TMC register values).

No klippy dependency: each function takes the motor's datasheet parameters plus the
operating conditions and returns the value autotune would compute. Used by the
recommender to suggest StealthChop PWM (``pwm_grad`` / ``pwm_ofs``) and SpreadCycle
hysteresis (``hstrt`` / ``hend``) from a motor's specs — so a recommendation works even
without the ``klipper_tmc_autotune`` host extra installed.

Formulas mirror the upstream exactly; see the original for derivation.
"""

from __future__ import annotations

import math

#: TMC internal clock (Hz) and default supply voltage — autotune's defaults.
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
    """SpreadCycle hysteresis register values ``(hstrt, hend)`` — faithful to autotune."""
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
