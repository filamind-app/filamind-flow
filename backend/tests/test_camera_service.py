"""Tests for the webcam discovery + snapshot-proxy helpers (pure URL logic + listing)."""

from __future__ import annotations

from typing import Any

import pytest

from app.services import camera_service as cam


def test_host_root_drops_moonraker_port() -> None:
    # Webcam paths live on the host's main web server (port 80), not Moonraker's port.
    assert cam.host_root("http://localhost:7125") == "http://localhost"
    assert cam.host_root("http://192.168.0.59:7125") == "http://192.168.0.59"
    assert cam.host_root("https://printer.local:7125") == "https://printer.local"


def test_resolve_url_relative_and_absolute() -> None:
    assert (
        cam.resolve_url("http://localhost:7125", "/webcam/?action=snapshot")
        == "http://localhost/webcam/?action=snapshot"
    )
    # missing leading slash is tolerated
    assert (
        cam.resolve_url("http://localhost:7125", "webcam/?action=snapshot")
        == "http://localhost/webcam/?action=snapshot"
    )
    # an already-absolute URL is passed through untouched
    absolute = "http://192.168.0.59:8080/?action=snapshot"
    assert cam.resolve_url("http://localhost:7125", absolute) == absolute


def test_pick_named_then_default() -> None:
    cams = [{"name": "cam1"}, {"name": "Nozzle"}]
    assert cam.pick(cams, "nozzle")["name"] == "Nozzle"  # case-insensitive
    assert cam.pick(cams, None)["name"] == "cam1"  # default = first
    assert cam.pick(cams, "missing")["name"] == "cam1"  # unknown name → default
    assert cam.pick([], None) is None


class _CamClient:
    """Stub MoonrakerClient exposing only list_webcams()."""

    def __init__(self, webcams: list[dict[str, Any]]) -> None:
        self._webcams = webcams

    async def list_webcams(self) -> list[dict[str, Any]]:
        return self._webcams


async def test_list_cameras_filters_disabled_and_normalizes() -> None:
    client = _CamClient(
        [
            {
                "name": "cam1",
                "service": "mjpegstreamer-adaptive",
                "snapshot_url": "/webcam/?action=snapshot",
                "stream_url": "/webcam/?action=stream",
                "enabled": True,
            },
            {"name": "off", "service": "x", "enabled": False},  # filtered out
        ]
    )
    out = await cam.list_cameras(client)  # type: ignore[arg-type]
    assert len(out) == 1
    assert out[0]["name"] == "cam1"
    assert out[0]["snapshot_url"] == "/webcam/?action=snapshot"


async def test_snapshot_raises_when_no_camera() -> None:
    with pytest.raises(cam.CameraUnavailable):
        await cam.snapshot("http://localhost:7125", _CamClient([]))  # type: ignore[arg-type]


# ── route-level ────────────────────────────────────────────────────────────────
def test_route_camera_list_empty_when_unreachable() -> None:
    from fastapi.testclient import TestClient

    from app.main import create_app

    # No Moonraker in the test env → list_webcams errors → endpoint degrades to "no cameras".
    resp = TestClient(create_app()).get("/api/camera/list")
    assert resp.status_code == 200
    body = resp.json()
    assert body["available"] is False
    assert body["cameras"] == []


def test_route_snapshot_passes_through_image(monkeypatch: pytest.MonkeyPatch) -> None:
    from fastapi.testclient import TestClient

    from app.api.routes import camera as camera_route
    from app.main import create_app

    async def fake_snapshot(*_a: object, **_k: object) -> tuple[bytes, str]:
        return b"\xff\xd8jpeg", "image/jpeg"

    monkeypatch.setattr(camera_route.camera_service, "snapshot", fake_snapshot)
    resp = TestClient(create_app()).get("/api/camera/snapshot")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/jpeg"
    assert resp.headers["x-content-type-options"] == "nosniff"


def test_route_snapshot_forces_octet_stream_for_non_image(monkeypatch: pytest.MonkeyPatch) -> None:
    from fastapi.testclient import TestClient

    from app.api.routes import camera as camera_route
    from app.main import create_app

    async def fake_snapshot(*_a: object, **_k: object) -> tuple[bytes, str]:
        return b"<html>nope</html>", "text/html"  # a misconfigured webcam URL

    monkeypatch.setattr(camera_route.camera_service, "snapshot", fake_snapshot)
    resp = TestClient(create_app()).get("/api/camera/snapshot")
    assert resp.status_code == 200
    # never served as HTML same-origin
    assert resp.headers["content-type"] == "application/octet-stream"
    assert resp.headers["x-content-type-options"] == "nosniff"
