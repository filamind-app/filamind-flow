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
        autotune: tuple[str, ...] = (),
        config: dict[str, Any] | None = None,
    ) -> None:
        self.printing = printing
        self.autotune = set(autotune)
        self.config = config or {}  # extra configfile sections (e.g. tmc run_current)
        self.scripts: list[str] = []

    async def query_objects(self, objects: list[str]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        if "print_stats" in objects:
            out["print_stats"] = {"state": "printing" if self.printing else "ready"}
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
