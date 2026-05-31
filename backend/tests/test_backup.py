from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.main import create_app
from app.services import backup_service, devices_store
from app.services.firmware_profiles import profiles_dir


def test_backup_roundtrip(tmp_path: Path) -> None:
    source = str(tmp_path / "src")
    devices_store.save_device(source, {"id": "b1", "name": "Board", "profile": "ebb"})
    with open(os.path.join(profiles_dir(source), "ebb.config"), "w") as handle:
        handle.write("CONFIG_MACH_STM32F1=y\n")

    blob = backup_service.export_backup(source)
    assert blob[:2] == b"PK"  # ZIP magic

    restored = str(tmp_path / "dst")
    summary = backup_service.import_backup(restored, blob)
    assert summary["restored_devices"] is True
    assert summary["restored_profiles"] == ["ebb"]

    device = devices_store.get_device(restored, "b1")
    assert device is not None and device["name"] == "Board"
    assert os.path.isfile(os.path.join(profiles_dir(restored), "ebb.config"))


def test_import_rejects_non_backup(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="ZIP"):
        backup_service.import_backup(str(tmp_path), b"definitely not a zip")


def test_backup_routes(tmp_path: Path) -> None:
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: Settings(data_dir=str(tmp_path))
    client = TestClient(app)

    export = client.get("/api/firmware/backup/export")
    assert export.status_code == 200
    assert export.headers["content-type"] == "application/zip"

    imported = client.post("/api/firmware/backup/import", content=export.content)
    assert imported.status_code == 200
    assert "restored_profiles" in imported.json()

    assert client.post("/api/firmware/backup/import", content=b"garbage").status_code == 400
