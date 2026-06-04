from __future__ import annotations

import math

import pytest

from app.services import field_policy
from app.services.field_policy import PolicyError


def test_field_range_derives_from_mask_and_signedness() -> None:
    fr = field_policy.field_range
    pol = field_policy._POLICY
    assert fr(pol["sgthrs"]) == (0, 255)  # 8-bit unsigned
    assert fr(pol["sgt"]) == (-64, 63)  # 7-bit SIGNED (mask 0x7F)
    assert fr(pol["hstrt"]) == (0, 7)  # 3-bit
    assert fr(pol["tbl"]) == (0, 3)  # 2-bit
    assert fr(pol["toff"]) == (1, 15)  # 4-bit, but 0 disables the motor → floor 1
    assert fr(pol["pwm_grad"]) == (0, 255)


def test_validate_unsigned_range() -> None:
    assert field_policy.validate("sgthrs", 0) == 0
    assert field_policy.validate("sgthrs", 255) == 255
    for bad in (256, -1, 300, 70.5):
        with pytest.raises(PolicyError):
            field_policy.validate("sgthrs", bad)


def test_validate_signed_sgt() -> None:
    # sgt is a signed 7-bit value (-64..63) - the #1 sensorless polarity/sign trap.
    assert field_policy.validate("sgt", -64) == -64
    assert field_policy.validate("sgt", 63) == 63
    assert field_policy.validate("sgt", 0) == 0
    for bad in (64, -65, 200):
        with pytest.raises(PolicyError):
            field_policy.validate("sgt", bad)


def test_validate_toff_blocks_zero() -> None:
    assert field_policy.validate("toff", 1) == 1
    assert field_policy.validate("toff", 15) == 15
    with pytest.raises(PolicyError):
        field_policy.validate("toff", 0)  # 0 disables the driver → dropped axis
    with pytest.raises(PolicyError):
        field_policy.validate("toff", 16)


def test_validate_blocks_dangerous_fields() -> None:
    # Raw current-scaling + protection-defeat + positional-corruption fields are never editable.
    for blocked in ("irun", "ihold", "globalscaler", "cs", "vsense", "diss2g", "test_mode", "mres"):
        assert field_policy.is_blocked(blocked)
        with pytest.raises(PolicyError):
            field_policy.validate(blocked, 1)


def test_validate_unknown_field() -> None:
    with pytest.raises(PolicyError):
        field_policy.validate("not_a_field", 1)


def test_validate_per_model_applicability() -> None:
    # sgthrs is a 2209 field; sgt belongs to 2130/2240/5160/2660; sg4_thrs to the 2240.
    assert field_policy.validate("sgthrs", 40, model="tmc2209") == 40
    with pytest.raises(PolicyError):
        field_policy.validate("sgthrs", 40, model="tmc2240")
    with pytest.raises(PolicyError):
        field_policy.validate("sgt", 3, model="tmc2209")
    assert field_policy.validate("sgt", 3, model="tmc5160") == 3
    assert field_policy.validate("sg4_thrs", 40, model="tmc2240") == 40
    # model=None skips the applicability check (the field's own range still applies).
    assert field_policy.validate("sgthrs", 40) == 40


def test_validate_velocity_and_bool() -> None:
    assert field_policy.validate("stealthchop_threshold", 0) == 0
    assert field_policy.validate("stealthchop_threshold", 120.5) == 120.5  # mm/s, fractional ok
    with pytest.raises(PolicyError):
        field_policy.validate("stealthchop_threshold", -1)
    assert field_policy.validate("pwm_autoscale", 1) == 1  # 1-bit toggle
    with pytest.raises(PolicyError):
        field_policy.validate("pwm_autoscale", 2)


def test_code_cap_per_model() -> None:
    assert field_policy.code_cap("tmc2209") == 2.0
    assert field_policy.code_cap("TMC2209") == 2.0  # case-insensitive
    assert field_policy.code_cap("tmc2660") == 2.4
    assert field_policy.code_cap("tmc5160") == 10.6
    assert field_policy.code_cap("nope") is None
    # The 2240 has no constant — it's computed from rref = (36000/rref)/√2.
    assert field_policy.code_cap("tmc2240") is None  # no rref → unknown
    assert field_policy.code_cap("tmc2240", rref=12000) == pytest.approx(
        (36000 / 12000) / math.sqrt(2)
    )


def test_current_cap_binds_to_the_lower_of_code_and_motor() -> None:
    cc = field_policy.current_cap
    # 2209 code cap 2.0; the motor rating binds when lower.
    assert cc("tmc2209", motor_rated_A=1.5) == 1.5
    assert cc("tmc2209", motor_rated_A=3.0) == 2.0  # code cap binds
    assert cc("tmc2209") == 2.0  # no motor → just the code cap
    # 5160's 10.6 is only a sanity ceiling — a real 4 A motor binds.
    assert cc("tmc5160", motor_rated_A=4.0) == 4.0
    assert cc("tmc5160") == 10.6
    # 2240 cap from rref, motor still binds if lower.
    assert cc("tmc2240", motor_rated_A=1.8, rref=12000) == 1.8
    assert cc("tmc2240", rref=12000) == pytest.approx((36000 / 12000) / math.sqrt(2))
    assert cc("tmc2240") is None  # nothing known
    # Unknown model: only the motor rating is known.
    assert cc("mystery", motor_rated_A=1.0) == 1.0
    assert cc("mystery") is None


def test_policy_for_model_shapes_controls() -> None:
    p2209 = field_policy.policy_for("tmc2209")
    assert "sgthrs" in p2209 and "sgt" not in p2209 and "sg4_thrs" not in p2209
    assert p2209["sgthrs"] == {
        "risk": "safe",
        "control": "number",
        "signed": False,
        "requires_confirm": False,
        "min": 0,
        "max": 255,
    }
    assert p2209["toff"]["min"] == 1 and p2209["toff"]["requires_confirm"] is True
    assert p2209["stealthchop_threshold"].get("velocity") is True
    # Blocked fields never appear in the editable policy.
    assert not (set(field_policy.BLOCKED) & set(p2209))

    p2240 = field_policy.policy_for("tmc2240")
    assert {"sg4_thrs", "sgt", "slope_control", "irundelay"} <= set(p2240)
    assert "sgthrs" not in p2240
    assert p2240["sgt"]["signed"] is True
