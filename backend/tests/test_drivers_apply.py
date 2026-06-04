from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.services import drivers_apply


class _FakeClient:
    """Records g-code and reports printing state + which steppers have the autotune extra."""

    def __init__(
        self,
        *,
        printing: bool = False,
        state: str | None = None,
        autotune: tuple[str, ...] = (),
        config: dict[str, Any] | None = None,
    ) -> None:
        # `state` overrides `printing` for the paused/error gate tests.
        self.state = state if state is not None else ("printing" if printing else "ready")
        self.autotune = set(autotune)
        self.config = config or {}  # extra configfile sections (e.g. tmc run_current)
        self.scripts: list[str] = []

    async def query_objects(self, objects: list[str]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        if "print_stats" in objects:
            out["print_stats"] = {"state": self.state}
        if "configfile" in objects:
            settings: dict[str, Any] = {f"autotune_tmc {s}": {} for s in self.autotune}
            settings.update(self.config)
            out["configfile"] = {"settings": settings}
        return out

    async def run_gcode(self, script: str) -> None:
        self.scripts.append(script)


def _patch(monkeypatch: pytest.MonkeyPatch, fake: _FakeClient) -> None:
    monkeypatch.setattr(drivers_apply, "MoonrakerClient", lambda *a, **k: fake)


def test_config_block_is_pure_text() -> None:
    text = drivers_apply.config_block(
        "stepper_x", "tmc2209", 1.4, {"pwm_grad": 14.0, "pwm_ofs": 33, "hstrt": 7, "hend": 6}
    )
    assert text.startswith("[tmc2209 stepper_x]")
    assert "run_current: 1.4" in text
    assert "driver_pwm_grad: 14" in text  # integral float renders as int
    assert "driver_hend: 6" in text


async def test_apply_live_sends_gcode(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeClient()
    _patch(monkeypatch, fake)
    res = await drivers_apply.apply_live(
        "http://x", "stepper_x", 1.4, 0.8, {"pwm_grad": 14.0, "pwm_ofs": 33}
    )
    assert res["ok"] is True
    assert "SET_TMC_CURRENT STEPPER=stepper_x CURRENT=1.4 HOLDCURRENT=0.8" in fake.scripts
    assert "SET_TMC_FIELD STEPPER=stepper_x FIELD=pwm_grad VALUE=14" in fake.scripts
    assert "SET_TMC_FIELD STEPPER=stepper_x FIELD=pwm_ofs VALUE=33" in fake.scripts


async def test_apply_refuses_while_printing(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeClient(printing=True)
    _patch(monkeypatch, fake)
    res = await drivers_apply.apply_live("http://x", "stepper_x", 1.4, None, {})
    assert res["ok"] is False
    assert "printing" in res["message"].lower()
    assert fake.scripts == []  # nothing was written


async def test_apply_rejects_unsafe_input(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeClient()
    _patch(monkeypatch, fake)
    # A g-code-injection attempt in the stepper name is rejected before any send.
    res = await drivers_apply.apply_live("http://x", "stepper_x\nM112", 1.4, None, {})
    assert res["ok"] is False
    assert fake.scripts == []
    # A non-numeric field value is rejected too.
    res2 = await drivers_apply.apply_live(
        "http://x", "stepper_x", None, None, {"pwm_grad": "1;M112"}
    )
    assert res2["ok"] is False
    assert fake.scripts == []


async def test_revert_restores_config_current(monkeypatch: pytest.MonkeyPatch) -> None:
    # INIT_TMC alone doesn't restore run_current (#93), so revert must SET_TMC_CURRENT
    # back to the configured value.
    fake = _FakeClient(config={"tmc2209 stepper_x": {"run_current": 1.1, "hold_current": 0.8}})
    _patch(monkeypatch, fake)
    res = await drivers_apply.revert("http://x", "stepper_x")
    assert res["ok"] is True
    assert fake.scripts == [
        "INIT_TMC STEPPER=stepper_x",
        "SET_TMC_CURRENT STEPPER=stepper_x CURRENT=1.1 HOLDCURRENT=0.8",
    ]


async def test_revert_without_config_current_just_inits(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeClient()  # no tmc config section → can't know the current, so INIT_TMC only
    _patch(monkeypatch, fake)
    res = await drivers_apply.revert("http://x", "stepper_x")
    assert res["ok"] is True
    assert fake.scripts == ["INIT_TMC STEPPER=stepper_x"]


async def test_autotune_unavailable_does_not_run(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeClient()  # no [autotune_tmc ...] sections
    _patch(monkeypatch, fake)
    res = await drivers_apply.run_autotune("http://x", "stepper_x")
    assert res["ok"] is False
    assert "not installed" in res["message"]
    assert fake.scripts == []


async def test_autotune_runs_when_installed(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeClient(autotune=("stepper_x",))
    _patch(monkeypatch, fake)
    res = await drivers_apply.run_autotune("http://x", "stepper_x")
    assert res["ok"] is True
    assert fake.scripts == ["AUTOTUNE_TMC STEPPER=stepper_x"]


async def test_set_stallguard_sends_field(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeClient()
    _patch(monkeypatch, fake)
    res = await drivers_apply.set_stallguard("http://x", "stepper_x", "sgthrs", 75)
    assert res["ok"] is True
    assert fake.scripts == ["SET_TMC_FIELD STEPPER=stepper_x FIELD=sgthrs VALUE=75"]


async def test_set_stallguard_rejects_bad_field(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeClient()
    _patch(monkeypatch, fake)
    res = await drivers_apply.set_stallguard("http://x", "stepper_x", "run_current", 1.0)
    assert res["ok"] is False
    assert fake.scripts == []


async def test_set_stallguard_refuses_while_printing(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeClient(printing=True)
    _patch(monkeypatch, fake)
    res = await drivers_apply.set_stallguard("http://x", "stepper_x", "sg4_thrs", 40)
    assert res["ok"] is False
    assert fake.scripts == []


async def test_set_stallguard_rejects_out_of_range(monkeypatch: pytest.MonkeyPatch) -> None:
    # The server now enforces the field range (the client's max= isn't trusted): a 2209 sgthrs
    # is 0-255, so 300 must be rejected before any g-code is sent (Klipper would mask-truncate).
    fake = _FakeClient()
    _patch(monkeypatch, fake)
    res = await drivers_apply.set_stallguard("http://x", "stepper_x", "sgthrs", 300)
    assert res["ok"] is False
    assert fake.scripts == []


async def test_set_stallguard_signed_sgt_round_trip(monkeypatch: pytest.MonkeyPatch) -> None:
    # sgt is signed -64..63: -64 is valid and sent verbatim; 64 is out of range and rejected.
    fake = _FakeClient()
    _patch(monkeypatch, fake)
    ok = await drivers_apply.set_stallguard("http://x", "stepper_z", "sgt", -64)
    assert ok["ok"] is True
    assert fake.scripts == ["SET_TMC_FIELD STEPPER=stepper_z FIELD=sgt VALUE=-64"]
    bad = await drivers_apply.set_stallguard("http://x", "stepper_z", "sgt", 64)
    assert bad["ok"] is False
    assert fake.scripts == ["SET_TMC_FIELD STEPPER=stepper_z FIELD=sgt VALUE=-64"]  # unchanged


async def test_writes_refused_while_paused(monkeypatch: pytest.MonkeyPatch) -> None:
    # _is_busy covers paused (and error), not just printing — a paused print still blocks writes.
    paused = _FakeClient(state="paused")
    _patch(monkeypatch, paused)
    assert (await drivers_apply.set_stallguard("http://x", "stepper_x", "sgthrs", 70))[
        "ok"
    ] is False
    assert (await drivers_apply.apply_live("http://x", "stepper_x", 1.0, None, {}))["ok"] is False
    assert (await drivers_apply.home_axis("http://x", "x"))["ok"] is False
    assert paused.scripts == []


async def test_set_field_sends_value(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeClient()
    _patch(monkeypatch, fake)
    res = await drivers_apply.set_field("http://x", "stepper_x", "hstrt", 6, model="tmc2209")
    assert res["ok"] is True
    assert fake.scripts == ["SET_TMC_FIELD STEPPER=stepper_x FIELD=hstrt VALUE=6"]


async def test_set_field_velocity_uses_velocity_param(monkeypatch: pytest.MonkeyPatch) -> None:
    # A velocity-threshold field writes its register (tpwmthrs) via VELOCITY= (mm/s) so Klipper
    # does the TSTEP conversion; the friendly name maps to the register name.
    fake = _FakeClient()
    _patch(monkeypatch, fake)
    res = await drivers_apply.set_field(
        "http://x", "stepper_x", "stealthchop_threshold", 100, model="tmc2209"
    )
    assert res["ok"] is True
    assert fake.scripts == ["SET_TMC_FIELD STEPPER=stepper_x FIELD=tpwmthrs VELOCITY=100"]


async def test_set_field_rejects_blocked_and_out_of_range(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeClient()
    _patch(monkeypatch, fake)
    # Blocked raw current-scaling field.
    assert (await drivers_apply.set_field("http://x", "stepper_x", "irun", 16))["ok"] is False
    # toff=0 disables the motor → rejected (floor is 1).
    assert (await drivers_apply.set_field("http://x", "stepper_x", "toff", 0))["ok"] is False
    # hstrt is a 3-bit field (0-7) → 8 is out of range.
    assert (await drivers_apply.set_field("http://x", "stepper_x", "hstrt", 8))["ok"] is False
    assert fake.scripts == []


async def test_set_field_rejects_not_applicable_to_model(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeClient()
    _patch(monkeypatch, fake)
    # sgt is not a 2209 field (the 2209 uses sgthrs) → rejected, nothing sent.
    res = await drivers_apply.set_field("http://x", "stepper_x", "sgt", 3, model="tmc2209")
    assert res["ok"] is False
    assert fake.scripts == []


async def test_set_field_refused_while_busy(monkeypatch: pytest.MonkeyPatch) -> None:
    paused = _FakeClient(state="paused")
    _patch(monkeypatch, paused)
    res = await drivers_apply.set_field("http://x", "stepper_x", "hstrt", 6, model="tmc2209")
    assert res["ok"] is False
    assert paused.scripts == []


async def test_coolstep_enable_writes_vetted_set(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeClient()
    _patch(monkeypatch, fake)
    res = await drivers_apply.set_coolstep("http://x", "stepper_x", True, model="tmc2209")
    assert res["ok"] is True
    assert fake.scripts == [
        "SET_TMC_FIELD STEPPER=stepper_x FIELD=semin VALUE=2",
        "SET_TMC_FIELD STEPPER=stepper_x FIELD=semax VALUE=4",
        "SET_TMC_FIELD STEPPER=stepper_x FIELD=seup VALUE=3",
        "SET_TMC_FIELD STEPPER=stepper_x FIELD=sedn VALUE=2",
        "SET_TMC_FIELD STEPPER=stepper_x FIELD=seimin VALUE=1",
    ]


async def test_coolstep_disable_sets_semin_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeClient()
    _patch(monkeypatch, fake)
    res = await drivers_apply.set_coolstep("http://x", "stepper_x", False, model="tmc2209")
    assert res["ok"] is True
    assert fake.scripts == ["SET_TMC_FIELD STEPPER=stepper_x FIELD=semin VALUE=0"]


async def test_coolstep_refused_while_busy(monkeypatch: pytest.MonkeyPatch) -> None:
    paused = _FakeClient(state="paused")
    _patch(monkeypatch, paused)
    res = await drivers_apply.set_coolstep("http://x", "stepper_x", True, model="tmc2209")
    assert res["ok"] is False
    assert paused.scripts == []


async def test_home_axis_sends_g28(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeClient()
    _patch(monkeypatch, fake)
    res = await drivers_apply.home_axis("http://x", "x")
    assert res["ok"] is True
    assert fake.scripts == ["G28 X"]


async def test_home_axis_rejects_bad_axis_and_printing(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeClient()
    _patch(monkeypatch, fake)
    assert (await drivers_apply.home_axis("http://x", "W"))["ok"] is False
    assert fake.scripts == []
    printing = _FakeClient(printing=True)
    _patch(monkeypatch, printing)
    assert (await drivers_apply.home_axis("http://x", "x"))["ok"] is False
    assert printing.scripts == []


async def test_motors_sync_unavailable_does_not_run(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeClient()  # no [motors_sync] section
    _patch(monkeypatch, fake)
    res = await drivers_apply.run_motors_sync("http://x")
    assert res["ok"] is False
    assert "isn't installed" in res["message"]
    assert fake.scripts == []


async def test_motors_sync_runs_when_installed(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeClient(config={"motors_sync": {}})
    _patch(monkeypatch, fake)
    assert (await drivers_apply.run_motors_sync("http://x"))["ok"] is True
    assert fake.scripts == ["SYNC_MOTORS"]


async def test_motors_sync_calibrate(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeClient(config={"motors_sync": {}})
    _patch(monkeypatch, fake)
    res = await drivers_apply.run_motors_sync("http://x", calibrate=True)
    assert res["ok"] is True
    assert fake.scripts == ["SYNC_MOTORS_CALIBRATE"]


async def test_motors_sync_refuses_while_printing(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeClient(printing=True, config={"motors_sync": {}})
    _patch(monkeypatch, fake)
    res = await drivers_apply.run_motors_sync("http://x")
    assert res["ok"] is False
    assert fake.scripts == []


def test_config_block_route() -> None:
    client = TestClient(create_app())
    res = client.post(
        "/api/drivers/config-block",
        json={
            "stepper": "stepper_y",
            "model": "tmc2209",
            "run_current": 1.2,
            "fields": {"hstrt": 5},
        },
    )
    assert res.status_code == 200
    assert "[tmc2209 stepper_y]" in res.json()["text"]


def test_apply_route_unreachable_is_graceful() -> None:
    from app.config import Settings, get_settings

    app = create_app()
    app.dependency_overrides[get_settings] = lambda: Settings(moonraker_url="http://127.0.0.1:1")
    client = TestClient(app)
    res = client.post("/api/drivers/apply", json={"stepper": "stepper_x", "run_current": 1.0})
    assert res.status_code == 200
    assert res.json()["ok"] is False  # Moonraker unreachable → reported, not a 500


def test_field_policy_route() -> None:
    client = TestClient(create_app())
    res = client.get("/api/drivers/field-policy/tmc2209")
    assert res.status_code == 200
    body = res.json()
    assert body["model"] == "tmc2209"
    # The 2209 exposes sgthrs (not the signed sgt / the 2240's sg4_thrs); blocked fields are absent.
    assert "sgthrs" in body["fields"] and "sgt" not in body["fields"]
    assert "irun" not in body["fields"]
    assert body["fields"]["toff"]["min"] == 1


def test_field_route_rejects_out_of_range_before_send() -> None:
    # Even unreachable, an out-of-range value is rejected by policy (never reaches Moonraker).
    from app.config import Settings, get_settings

    app = create_app()
    app.dependency_overrides[get_settings] = lambda: Settings(moonraker_url="http://127.0.0.1:1")
    client = TestClient(app)
    res = client.post(
        "/api/drivers/field",
        json={"stepper": "stepper_x", "field": "sgthrs", "value": 300, "model": "tmc2209"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is False and "255" in body["message"]
