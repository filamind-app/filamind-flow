from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.main import create_app
from app.services import fleet_store, version_store


def test_fleet_store_roundtrip(tmp_path: Path) -> None:
    data = str(tmp_path)
    assert fleet_store.read_fleet(data) == []

    fleet_store.save_device(data, {"id": "ebb36", "name": "Toolhead", "method": "can"})
    saved = fleet_store.get_device(data, "ebb36")
    assert saved is not None
    assert saved["name"] == "Toolhead"
    assert saved["method"] == "can"
    assert saved["baudrate"] == 250000  # defaulted

    # Unknown keys (e.g. a stray old_id) never land in the registry.
    fleet_store.save_device(data, {"id": "ebb36", "name": "Toolhead", "old_id": "x"})
    assert "old_id" not in fleet_store.get_device(data, "ebb36")  # type: ignore[operator]

    assert fleet_store.remove_device(data, "ebb36") is True
    assert fleet_store.remove_device(data, "ebb36") is False
    assert fleet_store.read_fleet(data) == []


def test_fleet_store_rename_keeps_one_row(tmp_path: Path) -> None:
    data = str(tmp_path)
    fleet_store.save_device(data, {"id": "old", "name": "Board"})
    fleet_store.save_device(data, {"id": "new", "name": "Board"}, old_id="old")

    fleet = fleet_store.read_fleet(data)
    assert [d["id"] for d in fleet] == ["new"]
    assert fleet_store.get_device(data, "old") is None


def test_attach_identity_and_managed(tmp_path: Path) -> None:
    data = str(tmp_path)
    fleet_store.save_device(data, {"id": "main", "name": "Mainboard", "method": "serial"})

    assert fleet_store.attach_identity(data, "missing", "x", "dfu") is None
    device = fleet_store.attach_identity(data, "main", "357236543131", "dfu")
    assert device is not None
    assert device["dfu_id"] == "357236543131"

    # Runtime id + attached bootloader id are both "managed".
    assert fleet_store.managed_identities(data) == {"main", "357236543131"}


def _client(tmp_path: Path) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: Settings(data_dir=str(tmp_path))
    return app


def test_fleet_routes(tmp_path: Path) -> None:
    client = TestClient(_client(tmp_path))

    assert client.get("/api/firmware/fleet").json() == {"devices": []}

    created = client.post(
        "/api/firmware/fleet/device",
        json={"id": "ebb36", "name": "Toolhead", "method": "can", "profile": "ebb36"},
    )
    assert created.status_code == 200
    assert created.json()["name"] == "Toolhead"

    listed = client.get("/api/firmware/fleet").json()["devices"]
    assert len(listed) == 1
    assert listed[0]["id"] == "ebb36"
    assert listed[0]["flashed_version"] is None  # nothing flashed yet

    # A flash record surfaces on the matching device.
    version_store.record_flash(
        str(tmp_path), "ebb36", "ebb36", {"version": "v0.13.0", "commit": "a"}
    )
    assert client.get("/api/firmware/fleet").json()["devices"][0]["flashed_version"] == "v0.13.0"

    attached = client.post(
        "/api/firmware/fleet/attach",
        json={"fleet_id": "ebb36", "hardware_id": "abc123", "kind": "serial"},
    )
    assert attached.status_code == 200
    assert attached.json()["serial_id"] == "abc123"

    assert (
        client.delete("/api/firmware/fleet/device", params={"device_id": "ebb36"}).status_code
        == 200
    )
    assert (
        client.delete("/api/firmware/fleet/device", params={"device_id": "ebb36"}).status_code
        == 404
    )
