from __future__ import annotations

import asyncio
from pathlib import Path

from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.main import create_app
from app.services import batch_service, devices_store, task_store


def _settings(tmp_path: Path) -> Settings:
    return Settings(data_dir=str(tmp_path))


def test_task_store_lifecycle() -> None:
    task = task_store.create_task()
    assert task.id.startswith("task_")
    assert task.status == "running"
    assert task_store.get_task(task.id) is task

    assert task_store.cancel_task(task.id) is True
    assert task.cancelled is True
    assert task_store.cancel_task("missing") is False
    assert task_store.get_task("missing") is None


def test_batch_no_devices(tmp_path: Path) -> None:
    task = task_store.create_task()
    asyncio.run(batch_service.run_batch("build-flash-all", _settings(tmp_path), task))
    assert task.status == "done"
    assert "No devices" in task.log


def test_batch_skips_unprofiled_device(tmp_path: Path) -> None:
    devices_store.save_device(str(tmp_path), {"id": "b1", "name": "Board", "method": "serial"})
    task = task_store.create_task()
    # No profile assigned → flashed nothing, touched no hardware.
    asyncio.run(batch_service.run_batch("flash-all", _settings(tmp_path), task))
    assert task.status == "done"
    assert "no profile assigned" in task.log


def test_batch_honours_precancel(tmp_path: Path) -> None:
    devices_store.save_device(str(tmp_path), {"id": "b1", "name": "Board", "method": "serial"})
    task = task_store.create_task()
    task.cancelled = True
    asyncio.run(batch_service.run_batch("build-flash-all", _settings(tmp_path), task))
    assert task.status == "cancelled"


def test_batch_routes(tmp_path: Path) -> None:
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: _settings(tmp_path)
    client = TestClient(app)

    started = client.post("/api/firmware/batch", json={"action": "build-all"})
    assert started.status_code == 200
    task_id = started.json()["task_id"]
    assert task_id.startswith("task_")

    status = client.get(f"/api/firmware/task/{task_id}")
    assert status.status_code == 200
    assert status.json()["status"] in ("running", "done", "cancelled", "failed")

    assert client.get("/api/firmware/task/missing").status_code == 404
    assert client.post("/api/firmware/task/missing/cancel").status_code == 404
    assert client.post(f"/api/firmware/task/{task_id}/cancel").status_code == 200
