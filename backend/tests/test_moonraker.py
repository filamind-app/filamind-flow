from __future__ import annotations

from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.main import create_app


def test_moonraker_status_unreachable() -> None:
    app = create_app()
    # Point at a closed port so the probe fails fast and predictably.
    app.dependency_overrides[get_settings] = lambda: Settings(moonraker_url="http://127.0.0.1:1")
    client = TestClient(app)

    response = client.get("/api/moonraker/status")

    assert response.status_code == 200
    body = response.json()
    assert body["reachable"] is False
    assert body["moonraker_url"] == "http://127.0.0.1:1"
