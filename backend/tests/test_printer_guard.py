"""Tests for the unified printer guard (shared busy definition + exclusive actuating slot)."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.services import printer_guard


class _Client:
    def __init__(self, state: str = "ready") -> None:
        self.state = state

    async def query_objects(self, objects: list[str]) -> dict[str, Any]:
        return {"print_stats": {"state": self.state}}


@pytest.mark.parametrize(
    ("state", "busy"),
    [("printing", True), ("paused", True), ("error", True), ("ready", False), ("standby", False)],
)
async def test_is_busy_states(state: str, busy: bool) -> None:
    assert await printer_guard.is_busy(_Client(state)) is busy


async def test_is_busy_can_ignore_error_state() -> None:
    assert await printer_guard.is_busy(_Client("error"), block_on_error=False) is False


async def test_acquire_is_exclusive_and_names_the_holder() -> None:
    assert printer_guard.status() == {"locked": False, "operation": None}
    async with printer_guard.acquire("resonance_test"):
        assert printer_guard.status() == {"locked": True, "operation": "resonance_test"}
        with pytest.raises(printer_guard.GuardBusyError) as exc_info:
            async with printer_guard.acquire("max_flow"):
                pass
        assert exc_info.value.operation == "resonance_test"
    # Released on exit — a new operation can run.
    assert printer_guard.status() == {"locked": False, "operation": None}
    async with printer_guard.acquire("max_flow"):
        assert printer_guard.status()["operation"] == "max_flow"


async def test_acquire_releases_on_error() -> None:
    with pytest.raises(RuntimeError, match="boom"):
        async with printer_guard.acquire("homing"):
            raise RuntimeError("boom")
    assert printer_guard.status() == {"locked": False, "operation": None}


async def test_guarded_stream_emits_error_line_when_slot_taken() -> None:
    async def inner():
        yield "line 1\n"

    async with printer_guard.acquire("vibrations_profile"):
        chunks = [c async for c in printer_guard.guarded_stream("firmware_flash", inner())]
    assert chunks == ["ERROR: another operation is already running: vibrations_profile\n"]
    # Free slot → the stream runs and the slot is held during it.
    chunks = [c async for c in printer_guard.guarded_stream("firmware_flash", inner())]
    assert chunks == ["line 1\n"]
    assert printer_guard.status()["locked"] is False


def test_route_guard_status_reports_slot_and_print_state(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.api.routes import guard as guard_route

    monkeypatch.setattr(guard_route, "MoonrakerClient", lambda *a, **k: _Client("printing"))
    client = TestClient(create_app())
    body = client.get("/api/guard/status").json()
    assert body == {
        "locked": False,
        "operation": None,
        "print_state": "printing",
        "reachable": True,
    }


def test_route_drivers_apply_refused_while_slot_taken(monkeypatch: pytest.MonkeyPatch) -> None:
    # Hold the slot (as if a resonance test is running) → a driver write returns the soft
    # guardLocked error without touching the printer.
    from app.services import drivers_apply

    called = []

    async def fake_apply(*a: Any, **k: Any) -> dict[str, Any]:
        called.append(1)
        return {"ok": True, "applied": [], "message": "", "code": None, "params": {}}

    monkeypatch.setattr(drivers_apply, "apply_live", fake_apply)
    printer_guard._current_op = "resonance_test"
    try:
        client = TestClient(create_app())
        body = client.post(
            "/api/drivers/apply", json={"stepper": "stepper_x", "run_current": 0.5, "fields": {}}
        ).json()
    finally:
        printer_guard._current_op = None
    assert body["ok"] is False
    assert body["code"] == "guardLocked"
    assert body["params"]["operation"] == "resonance_test"
    assert called == []  # the apply never ran
