from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.main import create_app
from app.services import rules_engine


def _rule(**over: Any) -> dict[str, Any]:
    base = {
        "name": "Cooldown",
        "enabled": True,
        "trigger": {"type": "temp_above", "heater": "extruder", "value": 200},
        "action": {"type": "notify", "message": "hot"},
    }
    base.update(over)
    return base


def test_validate_rule_ok_and_bad() -> None:
    r = rules_engine.validate_rule(_rule())
    assert r["trigger"]["heater"] == "extruder" and r["action"]["type"] == "notify"
    assert rules_engine._ID_RE.match(r["id"])
    for bad in [
        _rule(trigger={"type": "nope"}),
        _rule(trigger={"type": "temp_above", "heater": "nozzle", "value": 200}),
        _rule(trigger={"type": "temp_above", "heater": "extruder", "value": 999}),
        _rule(action={"type": "zap"}),
        _rule(action={"type": "gcode", "gcode": ""}),
    ]:
        with pytest.raises(ValueError):
            rules_engine.validate_rule(bad)


def test_condition_met() -> None:
    above = _rule(trigger={"type": "temp_above", "heater": "extruder", "value": 200})
    assert rules_engine.condition_met(above, {"extruder": {"temperature": 210}}) is True
    assert rules_engine.condition_met(above, {"extruder": {"temperature": 190}}) is False
    done = _rule(trigger={"type": "print_complete"})
    assert rules_engine.condition_met(done, {"print_stats": {"state": "complete"}}) is True
    err = _rule(trigger={"type": "print_error"})
    assert rules_engine.condition_met(err, {"webhooks": {"state": "shutdown"}}) is True


def test_objects_needed() -> None:
    objs = rules_engine.objects_needed([_rule(), _rule(trigger={"type": "print_complete"})])
    assert "print_stats" in objs and "webhooks" in objs and "extruder" in objs


def test_crud_and_engine_toggle(tmp_path: Path) -> None:
    d = str(tmp_path)
    assert rules_engine.load_state(d) == {"enabled": False, "rules": []}
    stored = rules_engine.upsert_rule(d, _rule())
    assert rules_engine.load_state(d)["rules"][0]["id"] == stored["id"]
    rules_engine.set_engine_enabled(d, True)
    assert rules_engine.load_state(d)["enabled"] is True
    assert rules_engine.delete_rule(d, stored["id"]) is True
    assert rules_engine.load_state(d)["rules"] == []


class _FakeClient:
    def __init__(self, status: dict[str, Any], *, busy: bool = False) -> None:
        self.status = status
        self.busy = busy
        self.scripts: list[str] = []

    async def query_objects(self, objects: list[str]) -> dict[str, Any]:
        if objects == ["print_stats"]:  # printer_guard.is_busy probe
            return {"print_stats": {"state": "printing" if self.busy else "ready"}}
        return self.status

    async def run_gcode(self, script: str) -> None:
        self.scripts.append(script)


async def test_tick_fires_on_rising_edge_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    d = str(tmp_path)
    rules_engine.upsert_rule(d, _rule())  # notify when extruder >= 200
    rules_engine.set_engine_enabled(d, True)
    fake = _FakeClient({"extruder": {"temperature": 210}})
    monkeypatch.setattr(rules_engine, "MoonrakerClient", lambda *a, **k: fake)

    prev = await rules_engine.tick(d, "http://x", {})
    assert len(rules_engine.read_log(d)) == 1  # fired
    # same condition still true -> no re-fire
    prev = await rules_engine.tick(d, "http://x", prev)
    assert len(rules_engine.read_log(d)) == 1


async def test_tick_disabled_is_noop(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    d = str(tmp_path)
    rules_engine.upsert_rule(d, _rule())  # engine left OFF
    fake = _FakeClient({"extruder": {"temperature": 210}})
    monkeypatch.setattr(rules_engine, "MoonrakerClient", lambda *a, **k: fake)
    assert await rules_engine.tick(d, "http://x", {}) == {}
    assert rules_engine.read_log(d) == []


async def test_gcode_action_gated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    d = str(tmp_path)
    rule = _rule(action={"type": "gcode", "gcode": "TURN_OFF_HEATERS"})
    rules_engine.upsert_rule(d, rule)
    rules_engine.set_engine_enabled(d, True)

    # busy -> skipped, no gcode sent
    busy = _FakeClient({"extruder": {"temperature": 210}}, busy=True)
    monkeypatch.setattr(rules_engine, "MoonrakerClient", lambda *a, **k: busy)
    await rules_engine.tick(d, "http://x", {})
    assert busy.scripts == []
    assert rules_engine.read_log(d)[0]["outcome"] == "skipped_busy"

    # ready -> runs (fresh prev so it's a rising edge again)
    ready = _FakeClient({"extruder": {"temperature": 210}})
    monkeypatch.setattr(rules_engine, "MoonrakerClient", lambda *a, **k: ready)
    await rules_engine.tick(d, "http://x", {})
    assert ready.scripts == ["TURN_OFF_HEATERS"]
    assert rules_engine.read_log(d)[0]["outcome"] == "ran"


def test_rules_routes(tmp_path: Path) -> None:
    app = create_app(Settings(data_dir=str(tmp_path), rules_tick_seconds=0))  # loop off in tests
    app.dependency_overrides[get_settings] = lambda: Settings(data_dir=str(tmp_path))
    client = TestClient(app)

    assert client.get("/api/rules").json() == {"enabled": False, "rules": [], "log": []}
    created = client.post("/api/rules", json=_rule())
    assert created.status_code == 200
    rid = created.json()["id"]

    assert client.put("/api/rules/engine", json={"enabled": True}).json()["enabled"] is True
    view = client.get("/api/rules").json()
    assert view["enabled"] is True and len(view["rules"]) == 1

    bad = client.post("/api/rules", json=_rule(action={"type": "gcode", "gcode": ""}))
    assert bad.status_code == 422

    assert client.delete(f"/api/rules/{rid}").status_code == 204
    assert client.delete(f"/api/rules/{rid}").status_code == 404
