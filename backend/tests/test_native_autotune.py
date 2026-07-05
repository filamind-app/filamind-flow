from __future__ import annotations

from app.services import motor_constants as mc
from app.services import native_autotune, recommender

#: A synthetic motor with round datasheet numbers (locks the equivalence without a catalog dep).
_MOTOR = {
    "model": "SYNTH-1",
    "manufacturer": "Test",
    "name": "Synth",
    "resistance_ohm": 1.0,
    "inductance_H": 0.002,
    "holding_torque_Nm": 0.5,
    "max_current_A": 2.0,
    "steps_per_rev": 200,
}


def test_compute_tune_matches_recommender_and_adds_full_set() -> None:
    rec = recommender.recommend(_MOTOR, volts=24.0)
    tune = native_autotune.compute_tune(_MOTOR, "tmc2209", volts=24.0, rotation_distance=40.0)
    # Core StealthChop/SpreadCycle values are exactly the (already-tested) recommender's.
    assert tune["run_current"] == rec["run_current"]
    assert tune["fields"]["pwm_ofs"] == rec["pwm_ofs"]
    assert tune["fields"]["pwm_grad"] == rec["pwm_grad"]
    assert tune["fields"]["hstrt"] == rec["hstrt"]
    assert tune["fields"]["hend"] == rec["hend"]
    # The full-equivalence additions: StealthChop enables + the vetted CoolStep loop.
    for k, v in mc.STEALTH_ENABLES.items():
        assert tune["fields"][k] == v
    for k, v in mc.COOLSTEP_SET.items():
        assert tune["fields"][k] == v
    # Velocity thresholds tie to the StealthChop-saturation speed, scaled by rotation_distance.
    handoff = round(rec["max_pwm_rps"] * 40.0, 2)
    assert tune["velocity_fields"]["stealthchop_threshold"] == handoff
    assert tune["velocity_fields"]["coolstep_threshold"] == handoff
    assert (
        tune["velocity_fields"]["coolstep_threshold"]
        == tune["velocity_fields"]["stealthchop_threshold"]
    )


def test_compute_tune_omits_thresholds_without_rotation_distance() -> None:
    tune = native_autotune.compute_tune(_MOTOR, "tmc2209", volts=24.0, rotation_distance=None)
    assert tune["velocity_fields"] == {}
    # The register set (no rotation_distance needed) is still fully present.
    assert tune["fields"]["pwm_ofs"] > 0 and tune["fields"]["semin"] == 2


def test_compute_tune_model_gating() -> None:
    # 2209 has CoolStep + StealthChop threshold but NO high-velocity (THIGH) register.
    t2209 = native_autotune.compute_tune(_MOTOR, "tmc2209", rotation_distance=40.0)
    assert "high_velocity_threshold" not in t2209["velocity_fields"]
    assert "stealthchop_threshold" in t2209["velocity_fields"]
    assert "semin" in t2209["fields"]
    # 5160 is a high-voltage model: THIGH applies, above the handoff.
    t5160 = native_autotune.compute_tune(_MOTOR, "tmc5160", rotation_distance=40.0)
    assert "high_velocity_threshold" in t5160["velocity_fields"]
    assert (
        t5160["velocity_fields"]["high_velocity_threshold"]
        > t5160["velocity_fields"]["stealthchop_threshold"]
    )


def test_compute_tune_drops_overflowing_register_seed() -> None:
    # A high-resistance motor at a low supply voltage makes pwm_ofs overflow its 8-bit register
    # (ceil(374*5*1.75/12) = 273 > 255). It must be DROPPED from the tune (auto-scale covers it),
    # not left in to abort the whole apply. pwm_grad (in range) and the run current still apply.
    overflow_motor = {**_MOTOR, "resistance_ohm": 5.0, "max_current_A": 2.5}
    tune = native_autotune.compute_tune(
        overflow_motor, "tmc2209", volts=12.0, rotation_distance=40.0
    )
    assert "pwm_ofs" not in tune["fields"]
    assert "pwm_grad" in tune["fields"] and 0 <= tune["fields"]["pwm_grad"] <= 255
    assert tune["fields"]["semin"] == 2  # the rest of the tune is intact
    assert tune["run_current"] > 0


async def test_run_without_mapped_motor_refuses(tmp_path: object) -> None:
    # No motor assigned to the stepper → a clean pre-flight refusal, no Moonraker call.
    res = await native_autotune.run("http://x", str(tmp_path), "stepper_x", 24.0)
    assert res["ok"] is False and res["code"] == "autotuneNoMotor"
    assert res["applied"] == []
