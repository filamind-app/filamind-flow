from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.main import create_app
from app.services import material_service, material_store, reference_data


def _catalog_hotend() -> tuple[str, float]:
    """A real catalog hotend that publishes a max-flow ceiling (the catalog ships these)."""
    row = next(
        h
        for h in reference_data.hotends()
        if isinstance(h.get("expected_max_flow_mm3s"), (int, float))
        and not isinstance(h.get("expected_max_flow_mm3s"), bool)
        and h["expected_max_flow_mm3s"] > 0
    )
    return str(row["name"]), float(row["expected_max_flow_mm3s"])


def test_material_store_roundtrip(tmp_path: Path) -> None:
    data = str(tmp_path)
    assert material_store.read_materials(data) == []

    rec = material_store.save_material(
        data, {"name": "PolyTerra PLA", "material": "PLA", "max_volumetric_flow": 12.0}
    )
    assert rec["id"] == "polyterra-pla"  # slug derived from the name
    assert rec["diameter"] == 1.75  # defaulted

    got = material_store.get_material(data, "polyterra-pla")
    assert got is not None
    assert got["max_volumetric_flow"] == 12.0

    assert material_store.remove_material(data, "polyterra-pla") is True
    assert material_store.remove_material(data, "polyterra-pla") is False
    assert material_store.read_materials(data) == []


def test_material_store_id_collision_gets_a_suffix(tmp_path: Path) -> None:
    data = str(tmp_path)
    a = material_store.save_material(data, {"name": "Generic PLA"})
    b = material_store.save_material(data, {"name": "Generic PLA"})
    assert a["id"] == "generic-pla"
    assert b["id"] == "generic-pla-2"  # kept distinct
    assert {m["id"] for m in material_store.read_materials(data)} == {
        "generic-pla",
        "generic-pla-2",
    }


def test_material_store_rename_keeps_one_row(tmp_path: Path) -> None:
    data = str(tmp_path)
    material_store.save_material(data, {"id": "old", "name": "X"})
    material_store.save_material(data, {"id": "new", "name": "X"}, old_id="old")
    assert [m["id"] for m in material_store.read_materials(data)] == ["new"]
    assert material_store.get_material(data, "old") is None


def _client(tmp_path: Path) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: Settings(data_dir=str(tmp_path))
    return TestClient(app)


def test_material_routes(tmp_path: Path) -> None:
    client = _client(tmp_path)
    assert client.get("/api/material").json() == []

    created = client.post(
        "/api/material",
        json={"name": "PETG HF", "material": "PETG", "max_volumetric_flow": 20},
    )
    assert created.status_code == 200
    body = created.json()
    assert body["id"] == "petg-hf"
    assert body["material"] == "PETG"

    listed = client.get("/api/material").json()
    assert len(listed) == 1
    assert listed[0]["id"] == "petg-hf"

    assert client.delete("/api/material/petg-hf").json() == {"ok": True}
    assert client.delete("/api/material/petg-hf").status_code == 404
    assert client.get("/api/material").json() == []


def test_check_flow_against_catalog_ceiling() -> None:
    name, ceiling = _catalog_hotend()
    assert material_service.check_flow(0, name)["code"] == "unset"
    assert material_service.check_flow(5, None)["code"] == "no_ceiling"
    over = material_service.check_flow(ceiling + 5, name)
    assert over["code"] == "exceeds"
    assert over["level"] == "warn"
    under = material_service.check_flow(ceiling * 0.5, name)
    assert under["code"] == "within"
    assert under["level"] == "ok"
    assert 0 <= under["params"]["headroom"] <= 100


def test_material_flow_check_route(tmp_path: Path) -> None:
    name, ceiling = _catalog_hotend()
    client = _client(tmp_path)
    client.post("/api/material", json={"name": "Speedy", "max_volumetric_flow": ceiling + 10})

    over = client.get("/api/material/speedy/flow-check", params={"hotend": name})
    assert over.status_code == 200
    assert over.json()["code"] == "exceeds"

    assert client.get("/api/material/does-not-exist/flow-check").status_code == 404


class _FakeClient:
    """Records g-code and reports the printer state (drives printer_guard.is_busy)."""

    def __init__(self, *, state: str = "ready") -> None:
        self.state = state
        self.scripts: list[str] = []

    async def query_objects(self, objects: list[str]) -> dict[str, Any]:
        return {"print_stats": {"state": self.state}} if "print_stats" in objects else {}

    async def run_gcode(self, script: str) -> None:
        self.scripts.append(script)


async def test_apply_material_preheats_when_ready(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeClient()
    monkeypatch.setattr(material_service, "MoonrakerClient", lambda *a, **k: fake)
    res = await material_service.apply_material(
        "http://x", {"name": "PLA", "nozzle_temp": 210, "bed_temp": 60}
    )
    assert res["ok"] is True
    assert res["code"] == "applied"
    assert fake.scripts == ["M104 S210", "M140 S60"]


async def test_apply_material_refuses_while_busy(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeClient(state="printing")
    monkeypatch.setattr(material_service, "MoonrakerClient", lambda *a, **k: fake)
    res = await material_service.apply_material(
        "http://x", {"name": "PLA", "nozzle_temp": 210, "bed_temp": 60}
    )
    assert res["ok"] is False
    assert res["code"] == "busy"
    assert fake.scripts == []  # nothing written while busy


async def test_apply_material_no_temps(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeClient()
    monkeypatch.setattr(material_service, "MoonrakerClient", lambda *a, **k: fake)
    res = await material_service.apply_material(
        "http://x", {"name": "X", "nozzle_temp": 0, "bed_temp": 0}
    )
    assert res["code"] == "no_temps"
    assert fake.scripts == []


def test_apply_route(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeClient()
    monkeypatch.setattr(material_service, "MoonrakerClient", lambda *a, **k: fake)
    client = _client(tmp_path)
    client.post("/api/material", json={"name": "PLA", "nozzle_temp": 200, "bed_temp": 55})
    r = client.post("/api/material/pla/apply")
    assert r.status_code == 200
    assert r.json()["code"] == "applied"
    assert client.post("/api/material/nope/apply").status_code == 404
