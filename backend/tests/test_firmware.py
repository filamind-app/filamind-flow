from __future__ import annotations

from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.main import create_app

_TOOL_KEYS = {"klipper", "katapult", "flashtool", "dfu_util", "avrdude", "can_utils"}


def test_firmware_status_unreachable() -> None:
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: Settings(
        moonraker_url="http://127.0.0.1:1",
        klipper_dir="/nonexistent/klipper",
        katapult_dir="/nonexistent/katapult",
    )
    client = TestClient(app)

    response = client.get("/api/firmware/status")

    assert response.status_code == 200
    body = response.json()
    assert body["reachable"] is False
    assert body["host"]["version"] is None
    assert body["mcus"] == []
    assert set(body["tools"]) == _TOOL_KEYS
    assert body["tools"]["klipper"] is False
