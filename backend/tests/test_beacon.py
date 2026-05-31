from __future__ import annotations

from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.main import create_app
from app.services import beacon_service


def test_parse_beacon_reads_revision_and_serial() -> None:
    parsed = beacon_service._parse_beacon("/dev/serial/by-id/usb-Beacon_Beacon_RevH_BSC512-if00")
    assert parsed == {
        "id": "/dev/serial/by-id/usb-Beacon_Beacon_RevH_BSC512-if00",
        "name": "Beacon RevH",
        "revision": "RevH",
        "serial": "BSC512",
    }
    assert beacon_service._parse_beacon("/dev/serial/by-id/usb-Klipper_stm32-if00") is None


def test_beacon_route_graceful_without_hardware() -> None:
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: Settings(moonraker_url="http://127.0.0.1:1")
    client = TestClient(app)

    response = client.get("/api/firmware/beacon")

    assert response.status_code == 200
    body = response.json()
    assert body["probes"] == []  # no Beacon probe in CI
    assert "available_version" in body and "repo" in body
