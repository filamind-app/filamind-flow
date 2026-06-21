from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.main import create_app
from app.services import temp_tuning


def test_plan_tower_command_and_bands() -> None:
    plan = temp_tuning.plan_tower(
        temp_tuning.TempTowerParams(start=240, factor=-0.5, band=10, height=50, heater="extruder")
    )
    assert "TUNING_TOWER COMMAND=SET_HEATER_TEMPERATURE HEATER=extruder" in plan["command"]
    assert "PARAMETER=TARGET START=240 FACTOR=-0.5 BAND=10" in plan["command"]
    bands = plan["bands"]
    assert len(bands) == 5  # ceil(50 / 10)
    # Band 0 midpoint z = 5 -> 240 + 5 * -0.5 = 237.5
    assert bands[0] == {"z_low": 0.0, "z_high": 10.0, "temp": 237.5}
    # Band 4 midpoint z = 45 -> 240 + 45 * -0.5 = 217.5
    assert bands[-1]["temp"] == pytest.approx(217.5)
    assert bands[-1]["z_high"] == 50.0


def test_temp_at_band() -> None:
    p = temp_tuning.TempTowerParams(start=200, factor=1.0, band=10, height=40)
    assert temp_tuning.temp_at_band(0, p) == pytest.approx(205.0)  # 200 + 5*1
    assert temp_tuning.temp_at_band(1, p) == pytest.approx(215.0)  # 200 + 15*1


@pytest.mark.parametrize(
    "bad",
    [
        temp_tuning.TempTowerParams(heater="nozzle"),  # not allowlisted
        temp_tuning.TempTowerParams(start=40),  # below floor
        temp_tuning.TempTowerParams(factor=0),  # zero
        temp_tuning.TempTowerParams(band=0),  # too small
        temp_tuning.TempTowerParams(height=0),  # zero
        temp_tuning.TempTowerParams(start=240, factor=-5, band=10, height=200),  # band temp < floor
    ],
)
def test_validate_rejects_bad(bad: temp_tuning.TempTowerParams) -> None:
    with pytest.raises(ValueError):
        temp_tuning.validate(bad)


class _FakeClient:
    def __init__(self, *, state: str = "ready") -> None:
        self.state = state
        self.scripts: list[str] = []

    async def query_objects(self, objects: list[str]) -> dict[str, Any]:
        return {"print_stats": {"state": self.state}} if "print_stats" in objects else {}

    async def run_gcode(self, script: str) -> None:
        self.scripts.append(script)


async def test_apply_when_ready(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeClient()
    monkeypatch.setattr(temp_tuning, "MoonrakerClient", lambda *a, **k: fake)
    res = await temp_tuning.apply_temp("http://x", "extruder", 225.0)
    assert res["ok"] is True
    assert res["code"] == "applied"
    assert fake.scripts == ["SET_HEATER_TEMPERATURE HEATER=extruder TARGET=225.0"]


async def test_apply_refuses_while_busy(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeClient(state="printing")
    monkeypatch.setattr(temp_tuning, "MoonrakerClient", lambda *a, **k: fake)
    res = await temp_tuning.apply_temp("http://x", "extruder", 225.0)
    assert res["code"] == "busy"
    assert fake.scripts == []


async def test_apply_unknown_heater(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeClient()
    monkeypatch.setattr(temp_tuning, "MoonrakerClient", lambda *a, **k: fake)
    res = await temp_tuning.apply_temp("http://x", "nozzle", 225.0)
    assert res["code"] == "unknown_heater"
    assert fake.scripts == []


async def test_apply_out_of_range(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeClient()
    monkeypatch.setattr(temp_tuning, "MoonrakerClient", lambda *a, **k: fake)
    res = await temp_tuning.apply_temp("http://x", "extruder", 500.0)
    assert res["code"] == "out_of_range"
    assert fake.scripts == []


def test_temp_routes(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeClient()
    monkeypatch.setattr(temp_tuning, "MoonrakerClient", lambda *a, **k: fake)
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: Settings()
    client = TestClient(app)

    plan = client.post(
        "/api/tuning/temp/plan",
        json={"start": 240, "factor": -0.5, "band": 10, "height": 50, "heater": "extruder"},
    )
    assert plan.status_code == 200
    assert plan.json()["bands"][0]["temp"] == pytest.approx(237.5)

    bad = client.post(
        "/api/tuning/temp/plan",
        json={"start": 240, "factor": 0, "band": 10, "height": 50, "heater": "extruder"},
    )
    assert bad.status_code == 422

    applied = client.post("/api/tuning/temp/apply", json={"heater": "extruder", "value": 220})
    assert applied.status_code == 200
    assert applied.json()["code"] == "applied"
