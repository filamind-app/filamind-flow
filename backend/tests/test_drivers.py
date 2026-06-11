from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.main import create_app
from app.services import drivers_service

# A deliberately mixed, multi-model printer to prove generic (not SV08-specific) parsing:
# a 2209 on X (SpreadCycle, sgthrs), a 2240 on Z (StealthChop, sg4_thrs, temperature),
# and a 2209 on the extruder. No assumptions about axis count or kinematics.
_SETTINGS: dict[str, Any] = {
    "stepper_x": {
        "microsteps": 16,
        "rotation_distance": 40,
        # Mirror the real SV08 printer.cfg: a stray space after the colon (#104) — still sensorless.
        "endstop_pin": "tmc2209_stepper_x: virtual_endstop",
    },
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
    "stepper_z": {"microsteps": 32, "endstop_pin": "probe:z_virtual_endstop"},
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

    async def list_objects(self) -> list[str]:
        return ["configfile", "print_stats", *_LIVE.keys()]

    async def query_endstops(self) -> dict[str, Any]:
        return {"x": "open", "y": "TRIGGERED", "z": "open"}

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

    # Homing method is classified from endstop_pin, not from "has a StallGuard field" (#101).
    assert x["homing_method"] == "sensorless"  # tmc2209_stepper_x:virtual_endstop
    assert z["homing_method"] == "probe"  # probe:z_virtual_endstop — NOT sensorless
    assert e["homing_method"] == "inherited"  # extruder has no endstop_pin

    # Effective run-current cap (P10): a 2209 with no assigned motor falls back to its 2.0 A
    # code cap; the 2240 has no fixed cap and no rref/motor here, so it's unknown (None).
    assert x["current_cap"] == 2.0
    assert z["current_cap"] is None
    assert z["rref"] is None

    # Each driver is annotated with authoritative catalog reference data.
    assert x["info"]["interface"] == "UART"
    assert x["info"]["sensorless"] is True
    assert z["info"]["model"] == "tmc2240"
    assert z["info"]["interface"] == "UART/SPI"
    assert z["info"]["temperature"] is True  # the 2240 has a sensor


def test_driver_catalog_lookup() -> None:
    from app.services import reference_data

    assert reference_data.driver_info_lookup("tmc2209")["sensorless"] is True
    assert reference_data.driver_info_lookup("tmc2208")["sensorless"] is False
    # Aliases resolve to their base model (2226 is configured as [tmc2209]).
    assert reference_data.driver_info_lookup("tmc2226")["model"] == "tmc2209"
    assert reference_data.driver_info_lookup("TMC2240")["temperature"] is True  # case-insensitive
    assert reference_data.driver_info_lookup("nope") is None


def test_drivers_catalog_route() -> None:
    client = TestClient(create_app())
    response = client.get("/api/drivers/catalog")
    assert response.status_code == 200
    body = response.json()
    assert body["source"]
    models = {d["model"] for d in body["drivers"]}
    assert {"tmc2209", "tmc2240", "tmc5160"} <= models


def test_driver_live_route(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(drivers_service, "MoonrakerClient", lambda *a, **k: _FakeClient())
    client = TestClient(create_app())
    res = client.get("/api/drivers/live/stepper_z")
    assert res.status_code == 200
    body = res.json()
    assert body["reachable"] is True
    assert body["model"] == "tmc2240"
    assert body["temperature"] == 42.5
    assert body["drv_status"]["sg_result"] == 120


def test_driver_live_idle(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(drivers_service, "MoonrakerClient", lambda *a, **k: _FakeClient())
    client = TestClient(create_app())
    body = client.get("/api/drivers/live/stepper_x").json()
    assert body["model"] == "tmc2209"
    assert body["drv_status"] is None  # idle — motor disabled


def test_motor_catalog_route() -> None:
    client = TestClient(create_app())
    response = client.get("/api/drivers/motors")
    assert response.status_code == 200
    body = response.json()
    assert body["count"] == len(body["motors"]) > 100  # the full baked catalog
    assert body["manufacturers"]
    first = body["motors"][0]
    assert {"manufacturer", "model", "resistance_ohm", "holding_torque_Nm"} <= first.keys()
    # Models must be unique — duplicate keys break the picker's filtered v-for (#89).
    models = [m["model"] for m in body["motors"]]
    assert len(models) == len(set(models)), "duplicate motor models in the catalog"


def test_motor_mapping_roundtrip(tmp_path: Any) -> None:
    from app.services import reference_data

    model = str(reference_data.motor_specs()[0]["model"])
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
    from app.services import motor_mapping, reference_data

    model = str(reference_data.motor_specs()[0]["model"])
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


def test_classify_homing() -> None:
    c = drivers_service._classify_homing
    # sensorless: a TMC virtual endstop
    assert c({"endstop_pin": "tmc2209_stepper_x:virtual_endstop"}, "tmc2209")[0] == "sensorless"
    assert c({"endstop_pin": "^tmc5160_stepper_y:virtual_endstop"}, "tmc5160")[0] == "sensorless"
    # whitespace after the colon is still a sensorless virtual endstop — Klipper strips it,
    # and the real SV08 printer.cfg has exactly this on stepper_x (#104).
    assert c({"endstop_pin": "tmc2209_stepper_x: virtual_endstop"}, "tmc2209")[0] == "sensorless"
    # probe-homed Z (with or without a stray space)
    assert c({"endstop_pin": "probe:z_virtual_endstop"}, "tmc2209")[0] == "probe"
    assert c({"endstop_pin": "probe: z_virtual_endstop"}, "tmc2209")[0] == "probe"
    # physical switch (real pin, with inversion prefix / off-board chip)
    assert c({"endstop_pin": "^PG6"}, "tmc2209")[0] == "physical"
    assert c({"endstop_pin": "!EBBCan:PB6"}, "tmc2240")[0] == "physical"
    # extra stepper with no endstop_pin → inherited
    assert c({"microsteps": 16}, "tmc2209")[0] == "inherited"
    # TMC2208 can't do sensorless — flagged misconfigured
    method, _pin, note = c({"endstop_pin": "tmc2208_stepper_x:virtual_endstop"}, "tmc2208")
    assert method == "sensorless" and note is not None and "2208" in note
    # explicit override off downgrades a virtual pin away from sensorless
    assert (
        c({"endstop_pin": "tmc2209_x:virtual_endstop", "use_sensorless_homing": False}, "tmc2209")[
            0
        ]
        == "other_virtual"
    )


def test_endstops_route(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(drivers_service, "MoonrakerClient", lambda *a, **k: _FakeClient())
    client = TestClient(create_app())
    body = client.get("/api/drivers/endstops").json()
    assert body["reachable"] is True
    assert body["states"] == {"x": "open", "y": "TRIGGERED", "z": "open"}


def test_chopper_mode() -> None:
    assert drivers_service._chopper_mode(0.0) == "SpreadCycle"
    assert drivers_service._chopper_mode(5.0) == "StealthChop"
    # Unset threshold => Klipper's default 0 => SpreadCycle, not an unknown mode (#85).
    assert drivers_service._chopper_mode(None) == "SpreadCycle"


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
