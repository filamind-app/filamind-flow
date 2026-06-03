from __future__ import annotations

import math

from fastapi.testclient import TestClient

from app.main import create_app
from app.services import motor_constants as mc
from app.services import recommender

# A representative LDO-class motor (R, L, holding torque, rated current, steps).
_MOTOR = {
    "manufacturer": "LDO Motors",
    "model": "test-42sth48-2004",
    "resistance_ohm": 1.6,
    "inductance_H": 0.003,
    "holding_torque_Nm": 0.59,
    "max_current_A": 2.0,
    "steps_per_rev": 200,
}


def test_motor_constants_formulas() -> None:
    cbemf = mc.cbemf(0.59, 2.0)
    assert cbemf == 0.1475
    # pwm_grad / pwm_ofs match the upstream ceil() formulas exactly.
    assert mc.pwmgrad(cbemf, 200, 24.0) == 14
    assert mc.pwmofs(1.6, 1.1, 24.0) == 28
    assert math.isclose(mc.maxpwmrps(28, 14), (255 - 28) / (math.pi * 14), rel_tol=1e-9)
    assert mc.maxpwmrps(0, 0) == 0.0
    # Hysteresis returns encoded (hstrt, hend) field values in the TMC valid ranges.
    hstrt, hend = mc.hysteresis(1.6, 0.003, 1.1, volts=24.0, tblank_cycles=32, toff=3)
    assert 0 <= hstrt <= 7
    assert 3 <= hend <= 15


def test_recommend_picks_conservative_current() -> None:
    rec = recommender.recommend(_MOTOR, volts=24.0)
    # Defaults to ~70% of the rated 2.0 A when no current is given.
    assert rec["run_current"] == 1.4
    assert "70%" in rec["run_current_basis"]
    assert rec["pwm_grad"] == 14  # independent of current
    assert rec["pwm_ofs"] == mc.pwmofs(1.6, 1.4, 24.0)


def test_recommend_honours_provided_current_and_voltage() -> None:
    rec = recommender.recommend(_MOTOR, volts=48.0, run_current=1.1)
    assert rec["run_current"] == 1.1
    assert rec["run_current_basis"] == "your value"
    assert rec["voltage"] == 48.0
    assert rec["pwm_ofs"] == mc.pwmofs(1.6, 1.1, 48.0)


def test_missing_specs() -> None:
    assert recommender.missing_specs(_MOTOR) == []
    assert recommender.missing_specs({"model": "x", "resistance_ohm": None}) == [
        "resistance_ohm",
        "inductance_H",
        "holding_torque_Nm",
        "max_current_A",
    ]


def test_recommend_route() -> None:
    from app.services import motor_catalog

    model = str(motor_catalog.all_motors()[0]["model"])
    client = TestClient(create_app())

    ok = client.post("/api/drivers/recommend", json={"motor_model": model, "voltage": 24})
    assert ok.status_code == 200
    body = ok.json()
    assert body["motor_model"] == model
    assert body["run_current"] > 0
    assert isinstance(body["pwm_grad"], int)

    assert (
        client.post("/api/drivers/recommend", json={"motor_model": "nope-xyz"}).status_code == 404
    )
