from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import create_app


def test_health_returns_ok() -> None:
    client = TestClient(create_app())

    response = client.get("/api/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "filamind-flow"


def test_firmware_health_reports_the_install_checks() -> None:
    client = TestClient(create_app())

    response = client.get("/api/firmware/health")

    assert response.status_code == 200
    body = response.json()
    assert isinstance(body["healthy"], bool)
    names = {check["name"] for check in body["checks"]}
    assert {"sudoers", "sudo", "udev-dfu", "dfu-util"} <= names
    assert all(check["detail"] for check in body["checks"])
