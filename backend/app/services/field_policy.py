"""Server-side TMC register-edit safety policy — the one load-bearing primitive for the
Motor Drivers widget's advanced-register editing (P10).

The hardware reality this guards against: ``SET_TMC_FIELD VALUE=`` *silently mask-truncates*
(a 5-bit field given 300 becomes ``300 & 31 = 12``, no error), and ``SET_TMC_CURRENT`` accepts
any value Klipper's own ``max_cur`` allows — which can still cook an under-rated motor. So the
server is the real protection layer. This module is that layer:

* an **allowlist** — only catalogued fields are editable; everything else is display-only;
* a **per-field clamp** whose range is derived from the register **bit-mask** (the silicon
  fact), with **per-model signedness** (``sgt`` is a signed 7-bit value, ``sgthrs`` is not);
* a **blocklist** of raw current-scaling and protection-defeat fields that must NEVER be
  written live (current goes only through the current-aware ``SET_TMC_CURRENT`` path);
* a **per-model current cap** ``I_cap = min(code_cap[model], motor_rated_A)`` (the 2240 cap is
  computed from its ``rref``), to reject a valid-but-over-rated-for-this-motor current.

Ranges are computed from the mask rather than hand-typed so the clamp provably matches the
register width (see ``test_field_policy``). Out-of-range values are *rejected*, not silently
clamped — a truncated safety/threshold value is worse than a clear error.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

Risk = Literal["safe", "risky", "dangerous"]
Control = Literal["number", "toggle", "select", "velocity"]


class PolicyError(ValueError):
    """A register edit rejected by policy (unknown / blocked / not-applicable / out-of-range)."""


@dataclass(frozen=True)
class FieldPolicy:
    """Editability policy for one TMC register field. ``mask`` is the register bit-mask (the
    silicon fact); the numeric range is derived from it unless ``lo``/``hi`` override it
    (e.g. ``toff`` is a 4-bit field but 0 disables the driver, so its floor is 1)."""

    risk: Risk = "safe"
    mask: int = 0  # register bit-mask; range derived via popcount (0 for bool/velocity/blocked)
    signed: bool = False
    control: Control = "number"
    #: Models this field exists on; ``None`` = every model that has the register.
    models: frozenset[str] | None = None
    blocked: bool = False  # dangerous → never written live, even if requested
    current_aware: bool = False  # current goes only through SET_TMC_CURRENT, never here
    velocity: bool = False  # user value is mm/s (≥0); Klipper converts it to a TSTEP register
    requires_confirm: bool = False
    enum: tuple[int, ...] | None = None  # explicit allowed values (overrides the mask range)
    lo: float | None = None  # explicit lower bound (overrides the mask-derived min)
    hi: float | None = None  # explicit upper bound (overrides the mask-derived max)
    #: The TMC register field name to send in ``SET_TMC_FIELD FIELD=`` when it differs from the
    #: policy key (e.g. the friendly ``stealthchop_threshold`` writes the ``tpwmthrs`` register).
    reg: str | None = None
    note: str | None = None


def _bits(mask: int) -> int:
    return bin(mask).count("1")


def field_range(fp: FieldPolicy) -> tuple[float, float]:
    """The inclusive [min, max] for a field, from explicit overrides else the mask + signedness.

    Unsigned n-bit field → ``[0, 2**n - 1]``; signed → ``[-2**(n-1), 2**(n-1) - 1]``.
    """
    bits = _bits(fp.mask)
    if fp.signed:
        lo: float = -(2 ** (bits - 1)) if bits else 0
        hi: float = (2 ** (bits - 1)) - 1 if bits else 0
    else:
        lo, hi = 0, (2**bits - 1) if bits else 0
    if fp.lo is not None:
        lo = fp.lo
    if fp.hi is not None:
        hi = fp.hi
    return lo, hi


# --- The editable-field allowlist (grouped as in the deep-analysis catalog) ------------------
# Model sets for fields that aren't on every driver.
_STEALTH = frozenset({"tmc2130", "tmc2208", "tmc2209", "tmc2240", "tmc5160"})  # have StealthChop
_COOLSTEP = frozenset({"tmc2130", "tmc2209", "tmc2240", "tmc5160"})
_SGT_MODELS = frozenset({"tmc2130", "tmc2240", "tmc5160", "tmc2660"})  # signed COOLCONF sgt
_HV = frozenset({"tmc2130", "tmc2240", "tmc5160"})

_POLICY: dict[str, FieldPolicy] = {
    # Group 2 — SpreadCycle / chopper
    "toff": FieldPolicy(
        "risky", mask=0xF, lo=1, requires_confirm=True, note="0 disables the motor"
    ),
    "tbl": FieldPolicy("risky", mask=0x3, control="select"),
    "hstrt": FieldPolicy("safe", mask=0x7),
    "hend": FieldPolicy("safe", mask=0xF),
    "tpfd": FieldPolicy("safe", mask=0xF, models=frozenset({"tmc2240", "tmc5160"})),
    "chm": FieldPolicy("risky", mask=0x1, control="toggle", models=_HV, requires_confirm=True),
    "vhighfs": FieldPolicy("safe", mask=0x1, control="toggle", models=_HV),
    "vhighchm": FieldPolicy("safe", mask=0x1, control="toggle", models=_HV),
    # Group 3 — StealthChop PWM
    "pwm_ofs": FieldPolicy("safe", mask=0xFF, models=_STEALTH),
    "pwm_grad": FieldPolicy("safe", mask=0xFF, models=_STEALTH),
    "pwm_freq": FieldPolicy("risky", mask=0x3, control="select", models=_STEALTH),
    "pwm_autoscale": FieldPolicy("safe", mask=0x1, control="toggle", models=_STEALTH),
    "pwm_autograd": FieldPolicy("safe", mask=0x1, control="toggle", models=_STEALTH),
    "pwm_reg": FieldPolicy("safe", mask=0xF, models=_STEALTH),
    "pwm_lim": FieldPolicy("safe", mask=0xF, models=_STEALTH),
    # Group 4 — CoolStep
    "semin": FieldPolicy("risky", mask=0xF, models=_COOLSTEP, requires_confirm=True),
    "semax": FieldPolicy("safe", mask=0xF, models=_COOLSTEP),
    "seup": FieldPolicy("safe", mask=0x3, control="select", models=_COOLSTEP),
    "sedn": FieldPolicy("safe", mask=0x3, control="select", models=_COOLSTEP),
    "seimin": FieldPolicy("risky", mask=0x1, control="toggle", models=_COOLSTEP),
    "sfilt": FieldPolicy("safe", mask=0x1, control="toggle", models=_COOLSTEP),
    # Group 5 — StallGuard (polarity differs by model — see the UI labels)
    "sgthrs": FieldPolicy("safe", mask=0xFF, models=frozenset({"tmc2209"})),
    "sg4_thrs": FieldPolicy("safe", mask=0xFF, models=frozenset({"tmc2240"})),
    "sgt": FieldPolicy("safe", mask=0x7F, signed=True, models=_SGT_MODELS),
    # Group 6 — velocity thresholds (mm/s on the user side; Klipper TSTEP-encodes via VELOCITY=).
    # Keyed by friendly name; `reg` is the register field SET_TMC_FIELD actually writes.
    "stealthchop_threshold": FieldPolicy(
        "safe", control="velocity", velocity=True, reg="tpwmthrs", models=_STEALTH
    ),
    "coolstep_threshold": FieldPolicy(
        "safe", control="velocity", velocity=True, reg="tcoolthrs", models=_COOLSTEP
    ),
    "high_velocity_threshold": FieldPolicy(
        "safe", control="velocity", velocity=True, reg="thigh", models=_HV
    ),
    "tpowerdown": FieldPolicy("safe", mask=0xFF),
    "iholddelay": FieldPolicy("safe", mask=0xF),
    "irundelay": FieldPolicy("safe", mask=0xF, models=frozenset({"tmc2240"})),
    "slope_control": FieldPolicy("safe", mask=0x3, control="select", models=frozenset({"tmc2240"})),
    # Group 7 — misc motion-quality (bool tuning that's safe to flip live)
    "intpol": FieldPolicy("safe", mask=0x1, control="toggle"),
    "multistep_filt": FieldPolicy("safe", mask=0x1, control="toggle"),
}

#: Raw current-scaling + protection-defeat + positional-corruption fields — NEVER written live.
#: Current goes only through the current-aware SET_TMC_CURRENT path (enforcing ``current_cap``);
#: ``mres``/``microsteps`` would desync Klipper's step distance mid-session → positional error.
BLOCKED: frozenset[str] = frozenset(
    {
        # raw current scaling (bypass the current cap)
        "irun",
        "ihold",
        "globalscaler",
        "cs",
        "current_range",
        "vsense",
        "i_scale_analog",
        "internal_rsense",
        # protection-defeat (only outcome is a destroyed driver on the next fault)
        "diss2g",
        "diss2vs",
        "test_mode",
        "direct_mode",
        "stop_enable",
        "overvoltage_vth",
        "overtempprewarning_vth",
        "s2vs_level",
        "s2g_level",
        "short_filter",
        "shortdelay",
        # positional-corruption / auto-managed
        "mres",
        "microsteps",
        "dedge",
    }
)


def is_blocked(field: str) -> bool:
    return field in BLOCKED


def is_velocity(field: str) -> bool:
    """Whether a field takes a velocity (mm/s) value, written via ``SET_TMC_FIELD VELOCITY=``."""
    fp = _POLICY.get(field)
    return bool(fp and fp.velocity)


def register_name(field: str) -> str:
    """The TMC register field name to put in ``SET_TMC_FIELD FIELD=`` — the policy's ``reg``
    override when set (e.g. ``stealthchop_threshold`` → ``tpwmthrs``), else the field itself."""
    fp = _POLICY.get(field)
    return fp.reg if fp and fp.reg else field


def _applicable(fp: FieldPolicy, model: str | None) -> bool:
    """Whether the field exists on this model (``models=None`` means every model that has it)."""
    if model is None or fp.models is None:
        return True
    return model.lower() in fp.models


def validate(field: str, value: float, model: str | None = None) -> float | int:
    """Validate a requested field write against policy, returning the accepted numeric value.

    Rejects (raises :class:`PolicyError`) when the field is blocked, unknown, not applicable to
    the model, or out of range — out-of-range values are *not* silently clamped, because a
    mask-truncated threshold is more dangerous than a clear error.
    """
    if field in BLOCKED:
        raise PolicyError(
            f"{field!r} cannot be edited live — it bypasses the current cap or driver protection; "
            "use copy-to-config instead."
        )
    fp = _POLICY.get(field)
    if fp is None:
        raise PolicyError(f"{field!r} is not an editable field.")
    if not _applicable(fp, model):
        raise PolicyError(f"{field!r} is not available on {model}.")
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise PolicyError(f"non-numeric value for {field!r}: {value!r}")

    if fp.velocity:
        if value < 0:
            raise PolicyError(f"{field!r} (velocity) must be ≥ 0 mm/s, got {value}.")
        return value
    if fp.enum is not None:
        if int(value) not in fp.enum or value != int(value):
            raise PolicyError(f"{field!r} must be one of {fp.enum}, got {value}.")
        return int(value)

    lo, hi = field_range(fp)
    if value < lo or value > hi:
        raise PolicyError(f"{field!r} must be in [{int(lo)}, {int(hi)}], got {value}.")
    # All non-velocity register fields are integers.
    if value != int(value):
        raise PolicyError(f"{field!r} must be a whole number, got {value}.")
    return int(value)


def policy_for(model: str) -> dict[str, dict[str, object]]:
    """The editable-field policy for one model, as plain dicts for the API / UI to render the
    correct control + range per field. Blocked and non-applicable fields are omitted."""
    out: dict[str, dict[str, object]] = {}
    for name, fp in _POLICY.items():
        if fp.blocked or not _applicable(fp, model):
            continue
        lo, hi = field_range(fp)
        entry: dict[str, object] = {
            "risk": fp.risk,
            "control": fp.control,
            "signed": fp.signed,
            "requires_confirm": fp.requires_confirm,
        }
        if fp.velocity:
            entry["velocity"] = True
        elif fp.enum is not None:
            entry["enum"] = list(fp.enum)
        else:
            entry["min"], entry["max"] = int(lo), int(hi)
        if fp.note:
            entry["note"] = fp.note
        out[name] = entry
    return out


# --- Per-model current cap (I_cap) -----------------------------------------------------------
#: Hard current ceilings that already bound ``SET_TMC_CURRENT`` in Klipper, per driver model.
#: 2160/5160's 10.6 A is a *sanity* ceiling far above any real board — the motor rating binds.
_CODE_CAP: dict[str, float] = {
    "tmc2130": 2.0,
    "tmc2208": 2.0,
    "tmc2209": 2.0,
    "tmc2660": 2.4,
    "tmc5160": 10.6,
    "tmc2160": 10.6,
}


def code_cap(model: str, rref: float | None = None) -> float | None:
    """The driver model's full-scale current ceiling. The 2240 has no constant — its limit is
    ``IFS_rms(range 3) = (36000 / rref) / √2`` from the configured external reference resistor."""
    m = model.lower()
    if m == "tmc2240":
        if rref and rref > 0:
            return (36000.0 / rref) / math.sqrt(2)
        return None
    return _CODE_CAP.get(m)


def current_cap(
    model: str, motor_rated_A: float | None = None, rref: float | None = None
) -> float | None:
    """``I_cap = min(code_cap[model], motor_rated_A)`` — the binding run-current ceiling. The
    motor's datasheet rating is almost always the real limit. Returns ``None`` if nothing is
    known (don't fabricate a cap)."""
    caps = [c for c in (code_cap(model, rref), motor_rated_A) if c is not None and c > 0]
    return min(caps) if caps else None
