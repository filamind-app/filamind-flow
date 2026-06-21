from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.main import create_app
from app.services import flow_tuning


def test_compute_under_extrusion() -> None:
    # Commanded 100, only 95 came out -> rotation_distance shrinks, flow > 100%.
    r = flow_tuning.compute(100, 95, 22.0)
    assert r["new_rotation_distance"] == pytest.approx(20.9)  # 22 * 95/100
    assert r["flow_percent"] == pytest.approx(105.3, abs=0.05)  # 100/95 * 100


def test_compute_over_extrusion() -> None:
    r = flow_tuning.compute(100, 104, 22.0)
    assert r["new_rotation_distance"] == pytest.approx(22.88)  # 22 * 104/100
    assert r["flow_percent"] == pytest.approx(96.2, abs=0.05)


@pytest.mark.parametrize("args", [(0, 95, 22), (100, 0, 22), (100, 95, 0), (-1, 95, 22)])
def test_compute_rejects_nonpositive(args: tuple[float, float, float]) -> None:
    with pytest.raises(ValueError):
        flow_tuning.compute(*args)


class _FakeClient:
    def __init__(self, *, rd: float | None = 22.0) -> None:
        self.rd = rd

    async def query_objects(self, objects: list[str]) -> dict[str, Any]:
        if "configfile" in objects:
            extruder = {"rotation_distance": self.rd} if self.rd is not None else {}
            return {"configfile": {"settings": {"extruder": extruder}}}
        return {}


async def test_extruder_rotation_distance(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeClient(rd=22.6789)
    monkeypatch.setattr(flow_tuning, "MoonrakerClient", lambda *a, **k: fake)
    res = await flow_tuning.extruder_rotation_distance("http://x")
    assert res["rotation_distance"] == pytest.approx(22.6789)


async def test_extruder_rotation_distance_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeClient(rd=None)
    monkeypatch.setattr(flow_tuning, "MoonrakerClient", lambda *a, **k: fake)
    res = await flow_tuning.extruder_rotation_distance("http://x")
    assert res["rotation_distance"] is None


def test_flow_routes(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeClient(rd=22.0)
    monkeypatch.setattr(flow_tuning, "MoonrakerClient", lambda *a, **k: fake)
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: Settings()
    client = TestClient(app)

    extr = client.get("/api/tuning/flow/extruder")
    assert extr.status_code == 200
    assert extr.json()["rotation_distance"] == pytest.approx(22.0)

    comp = client.post(
        "/api/tuning/flow/compute",
        json={"requested": 100, "measured": 95, "current_rotation_distance": 22.0},
    )
    assert comp.status_code == 200
    assert comp.json()["new_rotation_distance"] == pytest.approx(20.9)

    bad = client.post(
        "/api/tuning/flow/compute",
        json={"requested": 0, "measured": 95, "current_rotation_distance": 22.0},
    )
    assert bad.status_code == 422
