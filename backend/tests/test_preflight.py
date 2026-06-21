from __future__ import annotations

from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.main import create_app
from app.services import preflight_service


class _FakeClient:
    def __init__(
        self,
        *,
        klippy: str = "ready",
        state: str = "standby",
        homed: str = "xyz",
        raise_err: bool = False,
    ) -> None:
        self.klippy, self.state, self.homed, self.raise_err = klippy, state, homed, raise_err

    async def query_objects(self, objects: list[str]) -> dict[str, Any]:
        if self.raise_err:
            raise httpx.ConnectError("down")
        return {
            "webhooks": {"state": self.klippy},
            "print_stats": {"state": self.state},
            "toolhead": {"homed_axes": self.homed},
        }


def _codes(result: dict[str, Any]) -> dict[str, Any]:
    return {c["code"]: c for c in result["checks"]}


def _patch(monkeypatch: pytest.MonkeyPatch, fake: _FakeClient) -> None:
    monkeypatch.setattr(preflight_service, "MoonrakerClient", lambda *a, **k: fake)


async def test_preflight_ready(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch(monkeypatch, _FakeClient())
    r = await preflight_service.preflight("http://x")
    assert r["ready"] is True
    assert all(c["ok"] for c in r["checks"])


async def test_preflight_blocks_when_klippy_not_ready(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch(monkeypatch, _FakeClient(klippy="shutdown"))
    r = await preflight_service.preflight("http://x")
    assert r["ready"] is False
    assert _codes(r)["klippy"]["ok"] is False


async def test_preflight_blocks_when_printing(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch(monkeypatch, _FakeClient(state="printing"))
    r = await preflight_service.preflight("http://x")
    assert r["ready"] is False
    assert _codes(r)["idle"]["ok"] is False


async def test_preflight_unhomed_warns_not_blocks(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch(monkeypatch, _FakeClient(homed=""))
    r = await preflight_service.preflight("http://x")
    assert r["ready"] is True  # homed is warn-level, not a hard blocker
    assert _codes(r)["homed"]["ok"] is False
    assert _codes(r)["homed"]["level"] == "warn"


async def test_preflight_unreachable(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch(monkeypatch, _FakeClient(raise_err=True))
    r = await preflight_service.preflight("http://x")
    assert r["ready"] is False
    assert _codes(r)["unreachable"]["ok"] is False


def test_preflight_route(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch(monkeypatch, _FakeClient())
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: Settings()
    client = TestClient(app)
    r = client.get("/api/preflight")
    assert r.status_code == 200
    assert r.json()["ready"] is True
