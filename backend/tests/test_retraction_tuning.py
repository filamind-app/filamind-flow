from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.main import create_app
from app.services import retraction_tuning


def test_plan_tower_command_and_samples() -> None:
    plan = retraction_tuning.plan_tower(
        retraction_tuning.RetractionTowerParams(start=0.0, factor=0.05, height=50.0)
    )
    assert "TUNING_TOWER COMMAND=SET_RETRACTION PARAMETER=RETRACT_LENGTH" in plan["command"]
    assert "START=0.0 FACTOR=0.05" in plan["command"]
    assert plan["samples"][0] == {"height": 0.0, "value": 0.0}
    assert plan["samples"][-1]["height"] == 50.0
    assert plan["samples"][-1]["value"] == pytest.approx(2.5)  # 0 + 0.05 * 50


def test_retract_at() -> None:
    p = retraction_tuning.RetractionTowerParams(start=0.2, factor=0.04, height=40)
    assert retraction_tuning.retract_at(10, p) == pytest.approx(0.6)


@pytest.mark.parametrize(
    "bad",
    [
        retraction_tuning.RetractionTowerParams(start=-1),
        retraction_tuning.RetractionTowerParams(factor=0),
        retraction_tuning.RetractionTowerParams(factor=2.0),  # over the max factor
        retraction_tuning.RetractionTowerParams(height=0),
    ],
)
def test_validate_rejects_bad(bad: retraction_tuning.RetractionTowerParams) -> None:
    with pytest.raises(ValueError):
        retraction_tuning.validate(bad)


class _FakeClient:
    def __init__(self, *, state: str = "ready", has_fr: bool = True) -> None:
        self.state = state
        self.has_fr = has_fr
        self.scripts: list[str] = []

    async def query_objects(self, objects: list[str]) -> dict[str, Any]:
        if "configfile" in objects:
            settings = {"firmware_retraction": {}} if self.has_fr else {}
            return {"configfile": {"settings": settings}}
        if "print_stats" in objects:
            return {"print_stats": {"state": self.state}}
        return {}

    async def run_gcode(self, script: str) -> None:
        self.scripts.append(script)


async def test_apply_when_ready(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeClient()
    monkeypatch.setattr(retraction_tuning, "MoonrakerClient", lambda *a, **k: fake)
    res = await retraction_tuning.apply_retraction("http://x", 0.6)
    assert res["ok"] is True
    assert res["code"] == "applied"
    assert fake.scripts == ["SET_RETRACTION RETRACT_LENGTH=0.6"]


async def test_apply_refuses_while_busy(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeClient(state="printing")
    monkeypatch.setattr(retraction_tuning, "MoonrakerClient", lambda *a, **k: fake)
    res = await retraction_tuning.apply_retraction("http://x", 0.6)
    assert res["ok"] is False
    assert res["code"] == "busy"
    assert fake.scripts == []


async def test_apply_without_firmware_retraction(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeClient(has_fr=False)
    monkeypatch.setattr(retraction_tuning, "MoonrakerClient", lambda *a, **k: fake)
    res = await retraction_tuning.apply_retraction("http://x", 0.6)
    assert res["ok"] is False
    assert res["code"] == "no_firmware_retraction"
    assert fake.scripts == []


async def test_apply_out_of_range(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeClient()
    monkeypatch.setattr(retraction_tuning, "MoonrakerClient", lambda *a, **k: fake)
    res = await retraction_tuning.apply_retraction("http://x", 50.0)
    assert res["code"] == "out_of_range"
    assert fake.scripts == []


def test_retraction_routes(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeClient()
    monkeypatch.setattr(retraction_tuning, "MoonrakerClient", lambda *a, **k: fake)
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: Settings()
    client = TestClient(app)

    plan = client.post(
        "/api/tuning/retraction/plan", json={"start": 0, "factor": 0.05, "height": 50}
    )
    assert plan.status_code == 200
    assert plan.json()["samples"][-1]["value"] == pytest.approx(2.5)

    bad = client.post("/api/tuning/retraction/plan", json={"start": 0, "factor": 0, "height": 50})
    assert bad.status_code == 422

    applied = client.post("/api/tuning/retraction/apply", json={"value": 0.5})
    assert applied.status_code == 200
    assert applied.json()["code"] == "applied"
