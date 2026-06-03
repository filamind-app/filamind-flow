from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.main import create_app
from app.services import driver_catalog, drivers_service

# A deliberately mixed, multi-model printer to prove generic (not SV08-specific) parsing:
# a 2209 on X (SpreadCycle, sgthrs), a 2240 on Z (StealthChop, sg4_thrs, temperature),
# and a 2209 on the extruder. No assumptions about axis count or kinematics.
_SETTINGS: dict[str, Any] = {
    "stepper_x": {"microsteps": 16, "rotation_distance": 40},
    "tmc2209 stepper_x": {
        "run_current": 1.1,
        "hold_current": 0.8,
        "sense_resistor": 0.11,
        "interpolate": True,
        "stealthchop_threshold": 0.0,
        "driver_toff": 3,
        "driver_hstrt": 5,
        "driver_hend": 0,
        "driver_sgthrs": 70,
        "driver_pwm_autoscale": True,
        "driver_semin": 0,
    },
    "stepper_z": {"microsteps": 32},
    "tmc2240 stepper_z": {
        "run_current": 0.8,
        "hold_current": 0.5,
        "sense_resistor": 0.05,
        "interpolate": True,
        "stealthchop_threshold": 999999.0,
        "driver_toff": 3,
        "driver_sg4_thrs": 40,
        "driver_semin": 2,
        "driver_semax": 4,
    },
    "extruder": {"microsteps": 16},
    "tmc2209 extruder": {
        "run_current": 0.6,
        "hold_current": 0.4,
        "sense_resistor": 0.11,
        "interpolate": True,
        "stealthchop_threshold": 5.0,
        "driver_toff": 3,
        "driver_sgthrs": 100,
    },
}

_LIVE: dict[str, Any] = {
    "tmc2209 stepper_x": {
        "run_current": 1.08,
        "hold_current": 0.79,
        "drv_status": None,  # idle — motor disabled
        "temperature": None,  # 2209 has no sensor
    },
    "tmc2240 stepper_z": {
        "run_current": 0.8,
        "hold_current": 0.5,
        "drv_status": {"otpw": 0, "sg_result": 120, "cs_actual": 16},
        "temperature": 42.5,
    },
    "tmc2209 extruder": {
        "run_current": 0.6,
        "hold_current": 0.4,
        "drv_status": None,
        "temperature": None,
    },
}


class _FakeClient:
    """Stand-in for MoonrakerClient: serves the configfile, then per-driver get_status."""

    def __init__(self) -> None:
        self.queried: list[list[str]] = []

    async def query_objects(self, objects: list[str]) -> dict[str, Any]:
        self.queried.append(objects)
        if "configfile" in objects:
            return {"configfile": {"settings": _SETTINGS}}
        return {name: _LIVE[name] for name in objects if name in _LIVE}


def test_drivers_status_unreachable() -> None:
    """An unreachable Moonraker yields reachable=False, not an error."""
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: Settings(moonraker_url="http://127.0.0.1:1")
    client = TestClient(app)

    response = client.get("/api/drivers/status")

    assert response.status_code == 200
    body = response.json()
    assert body["reachable"] is False
    assert body["drivers"] == []


def test_drivers_status_parses_mixed_models(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(drivers_service, "MoonrakerClient", lambda *a, **k: _FakeClient())
    client = TestClient(create_app())

    response = client.get("/api/drivers/status")

    assert response.status_code == 200
    body = response.json()
    assert body["reachable"] is True
    by_stepper = {d["stepper"]: d for d in body["drivers"]}
    assert set(by_stepper) == {"stepper_x", "stepper_z", "extruder"}

    x = by_stepper["stepper_x"]
    assert x["model"] == "tmc2209"
    assert x["axis"] == "X"
    assert x["run_current"] == 1.08  # live (quantised)
    assert x["run_current_config"] == 1.1  # configured
    assert x["microsteps"] == 16
    assert x["chopper_mode"] == "SpreadCycle"  # threshold == 0
    assert x["stallguard_field"] == "sgthrs"
    assert x["stallguard_threshold"] == 70
    assert x["temperature"] is None
    assert x["drv_status"] is None  # idle
    assert x["capabilities"]["stallguard"] is True
    assert x["capabilities"]["temperature"] is False
    # raw driver_* registers are stripped of the prefix and exclude non-driver_ keys.
    assert x["registers"]["sgthrs"] == 70
    assert "run_current" not in x["registers"]

    z = by_stepper["stepper_z"]
    assert z["model"] == "tmc2240"
    assert z["axis"] == "Z"
    assert z["chopper_mode"] == "StealthChop"  # threshold > 0
    assert z["stallguard_field"] == "sg4_thrs"  # model-specific field
    assert z["stallguard_threshold"] == 40
    assert z["temperature"] == 42.5  # 2240 has a sensor
    assert z["drv_status"] == {"otpw": 0, "sg_result": 120, "cs_actual": 16}
    assert z["capabilities"]["temperature"] is True
    assert z["capabilities"]["coolstep"] is True  # semin/semax present

    e = by_stepper["extruder"]
    assert e["axis"] == "E"
    assert e["chopper_mode"] == "StealthChop"  # threshold 5.0

    # Each driver is annotated with authoritative catalog reference data.
    assert x["info"]["interface"] == "UART"
    assert x["info"]["sensorless"] is True
    assert z["info"]["model"] == "tmc2240"
    assert z["info"]["interface"] == "UART/SPI"
    assert z["info"]["temperature"] is True  # the 2240 has a sensor


def test_driver_catalog_lookup() -> None:
    assert driver_catalog.lookup("tmc2209")["sensorless"] is True
    assert driver_catalog.lookup("tmc2208")["sensorless"] is False
    # Aliases resolve to their base model (2226 is configured as [tmc2209]).
    assert driver_catalog.lookup("tmc2226")["model"] == "tmc2209"
    assert driver_catalog.lookup("TMC2240")["temperature"] is True  # case-insensitive
    assert driver_catalog.lookup("nope") is None


def test_drivers_catalog_route() -> None:
    client = TestClient(create_app())
    response = client.get("/api/drivers/catalog")
    assert response.status_code == 200
    body = response.json()
    assert body["source"]
    models = {d["model"] for d in body["drivers"]}
    assert {"tmc2209", "tmc2240", "tmc5160"} <= models


def test_motor_catalog_route() -> None:
    client = TestClient(create_app())
    response = client.get("/api/drivers/motors")
    assert response.status_code == 200
    body = response.json()
    assert body["count"] == len(body["motors"]) > 100  # the full baked catalog
    assert body["manufacturers"]
    first = body["motors"][0]
    assert {"manufacturer", "model", "resistance_ohm", "holding_torque_Nm"} <= first.keys()


def test_motor_mapping_roundtrip(tmp_path: Any) -> None:
    from app.services import motor_catalog

    model = str(motor_catalog.all_motors()[0]["model"])
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: Settings(
        moonraker_url="http://127.0.0.1:1", data_dir=str(tmp_path)
    )
    client = TestClient(app)

    assert client.get("/api/drivers/mapping").json()["mapping"] == {}
    saved = client.post("/api/drivers/mapping", json={"stepper": "stepper_x", "motor_model": model})
    assert saved.json()["mapping"] == {"stepper_x": model}
    assert client.get("/api/drivers/mapping").json()["mapping"]["stepper_x"] == model
    # An empty motor_model clears the assignment.
    cleared = client.post("/api/drivers/mapping", json={"stepper": "stepper_x"})
    assert cleared.json()["mapping"] == {}


def test_status_attaches_assigned_motor(tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.services import motor_catalog, motor_mapping

    model = str(motor_catalog.all_motors()[0]["model"])
    motor_mapping.assign(str(tmp_path), "stepper_x", model)
    monkeypatch.setattr(drivers_service, "MoonrakerClient", lambda *a, **k: _FakeClient())

    app = create_app()
    app.dependency_overrides[get_settings] = lambda: Settings(
        moonraker_url="http://x", data_dir=str(tmp_path)
    )
    client = TestClient(app)

    drivers = client.get("/api/drivers/status").json()["drivers"]
    x = next(d for d in drivers if d["stepper"] == "stepper_x")
    assert x["motor"] is not None
    assert x["motor"]["model"] == model
    # An unassigned stepper has no motor.
    z = next(d for d in drivers if d["stepper"] == "stepper_z")
    assert z["motor"] is None


def test_chopper_mode() -> None:
    assert drivers_service._chopper_mode(0.0) == "SpreadCycle"
    assert drivers_service._chopper_mode(5.0) == "StealthChop"
    assert drivers_service._chopper_mode(None) is None


def test_axis_label() -> None:
    assert drivers_service._axis_label("stepper_x") == "X"
    assert drivers_service._axis_label("stepper_z1") == "Z1"
    assert drivers_service._axis_label("extruder") == "E"
    assert drivers_service._axis_label("extruder1") == "E1"
    # Unknown kinematics: fall back to the raw section name rather than guessing.
    assert drivers_service._axis_label("dual_carriage") == "dual_carriage"


def test_stallguard_field_order() -> None:
    assert drivers_service._stallguard({"driver_sgthrs": 70}) == ("sgthrs", 70)
    assert drivers_service._stallguard({"driver_sg4_thrs": 40}) == ("sg4_thrs", 40)
    assert drivers_service._stallguard({"driver_sgt": 3}) == ("sgt", 3)
    assert drivers_service._stallguard({}) == (None, None)
