from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.main import create_app
from app.services import pa_tuning


def test_plan_tower_command_and_samples() -> None:
    plan = pa_tuning.plan_tower(pa_tuning.PaTowerParams(start=0.0, factor=0.005, height=50.0))
    assert "TUNING_TOWER COMMAND=SET_PRESSURE_ADVANCE PARAMETER=ADVANCE" in plan["command"]
    assert "START=0.0 FACTOR=0.005" in plan["command"]
    assert plan["samples"][0] == {"height": 0.0, "pa": 0.0}
    assert plan["samples"][-1]["height"] == 50.0
    assert plan["samples"][-1]["pa"] == pytest.approx(0.25)  # 0 + 0.005 * 50


def test_pa_at() -> None:
    p = pa_tuning.PaTowerParams(start=0.02, factor=0.01, height=40)
    assert pa_tuning.pa_at(10, p) == pytest.approx(0.12)


@pytest.mark.parametrize(
    "bad",
    [
        pa_tuning.PaTowerParams(start=-1),
        pa_tuning.PaTowerParams(factor=0),
        pa_tuning.PaTowerParams(factor=1.0),  # over the max factor
        pa_tuning.PaTowerParams(height=0),
    ],
)
def test_validate_rejects_bad(bad: pa_tuning.PaTowerParams) -> None:
    with pytest.raises(ValueError):
        pa_tuning.validate(bad)


class _FakeClient:
    def __init__(self, *, state: str = "ready") -> None:
        self.state = state
        self.scripts: list[str] = []

    async def query_objects(self, objects: list[str]) -> dict[str, Any]:
        return {"print_stats": {"state": self.state}} if "print_stats" in objects else {}

    async def run_gcode(self, script: str) -> None:
        self.scripts.append(script)


async def test_apply_pa_when_ready(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeClient()
    monkeypatch.setattr(pa_tuning, "MoonrakerClient", lambda *a, **k: fake)
    res = await pa_tuning.apply_pa("http://x", 0.045)
    assert res["ok"] is True
    assert res["code"] == "applied"
    assert fake.scripts == ["SET_PRESSURE_ADVANCE ADVANCE=0.045"]


async def test_apply_pa_refuses_while_busy(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeClient(state="printing")
    monkeypatch.setattr(pa_tuning, "MoonrakerClient", lambda *a, **k: fake)
    res = await pa_tuning.apply_pa("http://x", 0.045)
    assert res["ok"] is False
    assert res["code"] == "busy"
    assert fake.scripts == []


async def test_apply_pa_out_of_range(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeClient()
    monkeypatch.setattr(pa_tuning, "MoonrakerClient", lambda *a, **k: fake)
    res = await pa_tuning.apply_pa("http://x", 5.0)
    assert res["code"] == "out_of_range"
    assert fake.scripts == []


def test_tuning_routes(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeClient()
    monkeypatch.setattr(pa_tuning, "MoonrakerClient", lambda *a, **k: fake)
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: Settings()
    client = TestClient(app)

    plan = client.post("/api/tuning/pa/plan", json={"start": 0, "factor": 0.005, "height": 50})
    assert plan.status_code == 200
    assert plan.json()["samples"][-1]["pa"] == pytest.approx(0.25)

    bad = client.post("/api/tuning/pa/plan", json={"start": 0, "factor": 0, "height": 50})
    assert bad.status_code == 422

    applied = client.post("/api/tuning/pa/apply", json={"value": 0.04})
    assert applied.status_code == 200
    assert applied.json()["code"] == "applied"
