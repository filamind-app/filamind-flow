from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.main import create_app
from app.services import material_store


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
