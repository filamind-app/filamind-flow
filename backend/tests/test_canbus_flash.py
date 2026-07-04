"""Tests for the USB-CAN adapter (U2C) flash - especially the software auto-entry into DFU.

The adapter's candleLight / budgetcan firmware exposes a DFU runtime interface, so a running adapter
is put into DFU with ``dfu-util -e`` (no BOOT button). These cover: already-in-DFU (flash direct),
running (auto-detach then flash), auto-detach that doesn't take (manual fallback), and nothing on
USB (refuse). Every dfu-util / systemctl call is faked - no hardware, no downloads, no sleeps.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from app.services import canbus_flash

_DFU_LINE = "Found DFU: [0483:df11] ver=2200, devnum=6, cfg=1, intf=0, path=..., alt=0"
_RUNTIME_LINE = "Found Runtime: [1d50:606f] ver=0100, devnum=6, cfg=1, intf=2, path=..."
_FLASH_OK = "Download\t[=========================] 100%\nFile downloaded successfully\n"


class _FakeResp:
    def __init__(self, content: bytes) -> None:
        self.content = content

    def raise_for_status(self) -> None:  # pragma: no cover - always ok in these tests
        pass


class _FakeClient:
    """Stands in for httpx.AsyncClient - always serves a plausibly-sized firmware blob."""

    def __init__(self, *a: Any, **k: Any) -> None:
        pass

    async def __aenter__(self) -> _FakeClient:
        return self

    async def __aexit__(self, *a: Any) -> bool:
        return False

    async def get(self, url: str) -> _FakeResp:
        return _FakeResp(b"\x00" * 4096)


def _install(monkeypatch, state: dict[str, Any]) -> list[list[str]]:
    """Fake every subprocess canbus_flash makes, driven by ``state`` (dfu/runtime/detach_works).

    ``dfu-util -l`` reflects the current state; a successful ``dfu-util -e`` flips runtime→dfu.
    Returns the recorded command list so a test can assert what ran."""
    calls: list[list[str]] = []

    async def fake_run(cmd: list[str], timeout: float = 120.0) -> tuple[int, str]:
        calls.append(list(cmd))
        if cmd[:4] == ["sudo", "-n", "dfu-util", "-l"]:
            if state["dfu"]:
                return 0, _DFU_LINE
            if state["runtime"]:
                return 0, _RUNTIME_LINE
            return 0, "No DFU capable USB device available"
        if cmd[:4] == ["sudo", "-n", "dfu-util", "-e"]:
            if state.get("detach_works", True):
                state["dfu"], state["runtime"] = True, False
            return 0, "Detaching...\n"
        if "-D" in cmd:  # the actual flash write
            return 0, _FLASH_OK
        return 0, ""  # systemctl stop/start klipper

    started: list[int] = []
    monkeypatch.setattr(canbus_flash, "_run", fake_run)
    monkeypatch.setattr(canbus_flash.httpx, "AsyncClient", _FakeClient)
    monkeypatch.setattr(canbus_flash, "_DETACH_SETTLE_S", 0.0)
    monkeypatch.setattr(canbus_flash, "_start_klipper_detached", lambda: started.append(1))
    state["_started"] = started
    return calls


def _stopped_klipper(calls: list[list[str]]) -> bool:
    return any(c[:5] == ["sudo", "-n", "systemctl", "stop", "klipper"] for c in calls)


def _detached(calls: list[list[str]]) -> bool:
    return any(c[:4] == ["sudo", "-n", "dfu-util", "-e"] for c in calls)


def _flashed(calls: list[list[str]]) -> bool:
    return any("-D" in c for c in calls)


async def test_dfu_status_reports_runtime(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """A running gs_usb adapter (not in DFU) is reported as ``runtime`` (the auto-flash cue)."""
    _install(monkeypatch, {"dfu": False, "runtime": True})
    status = await canbus_flash.dfu_status()
    assert status == {"present": False, "runtime": True, "detail": _RUNTIME_LINE, "sudo": True}


async def test_flash_auto_detaches_running_adapter(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """The headline: a running adapter is put into DFU in software (no BOOT button) and flashed,
    with Klipper stopped for the detach and restarted afterwards."""
    state = {"dfu": False, "runtime": True, "detach_works": True}
    calls = _install(monkeypatch, state)
    res = await canbus_flash.flash("u2c-v2")
    assert res["ok"] is True
    assert _stopped_klipper(calls) and _detached(calls) and _flashed(calls)
    assert state["_started"] == [1]  # Klipper restart fired (the finally)
    assert "File downloaded successfully" in res["output"]


async def test_flash_direct_when_already_in_dfu(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """An adapter already in DFU (manual BOOT entry, or a prior detach) is flashed directly -
    no detach, and Klipper is left alone (it already lost the bus when the adapter entered DFU)."""
    calls = _install(monkeypatch, {"dfu": True, "runtime": False})
    res = await canbus_flash.flash("u2c-v1")
    assert res["ok"] is True
    assert _flashed(calls)
    assert not _detached(calls)
    assert not _stopped_klipper(calls)


async def test_flash_falls_back_to_manual_when_detach_fails(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """If the software detach doesn't land the adapter in DFU, we refuse with the manual BOOT
    instructions rather than flashing the live gs_usb interface - and Klipper is restarted."""
    state = {"dfu": False, "runtime": True, "detach_works": False}
    calls = _install(monkeypatch, state)
    res = await canbus_flash.flash("u2c-v2")
    assert res["ok"] is False
    assert "BOOT button" in res["output"]
    assert _detached(calls) and not _flashed(calls)  # tried the detach, never wrote firmware
    assert state["_started"] == [1]  # Klipper still brought back


async def test_flash_refused_when_no_adapter(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """No DFU device and no running adapter on USB - refuse before Klipper or dfu-util -e."""
    calls = _install(monkeypatch, {"dfu": False, "runtime": False})
    res = await canbus_flash.flash("u2c-v2")
    assert res["ok"] is False
    assert "No DFU device" in res["output"]
    assert not _detached(calls) and not _stopped_klipper(calls) and not _flashed(calls)


async def test_flash_unknown_revision(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """An unknown revision id is rejected before any USB work."""
    calls = _install(monkeypatch, {"dfu": True, "runtime": False})
    res = await canbus_flash.flash("nope")
    assert res["ok"] is False
    assert "Unknown adapter revision" in res["output"]
    assert calls == []


async def test_flash_reports_missing_sudo(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """When passwordless sudo for dfu-util isn't granted, the flash explains the one-time setup."""

    async def no_sudo(cmd: list[str], timeout: float = 120.0) -> tuple[int, str]:
        return 1, "sudo: a password is required"

    monkeypatch.setattr(canbus_flash, "_run", no_sudo)
    res = await canbus_flash.flash("u2c-v2")
    assert res["ok"] is False
    assert "Passwordless sudo" in res["output"]


async def test_dfu_status_ignores_host_warning(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """A working sudo that only prints 'sudo: unable to resolve host ...' (merged from stderr on
    many SBC hosts) must NOT read as a denial - the adapter is detected, sudo reported True."""

    async def warn_run(cmd: list[str], timeout: float = 120.0) -> tuple[int, str]:
        return 0, "sudo: unable to resolve host cb1: Name or service not known\n" + _DFU_LINE

    monkeypatch.setattr(canbus_flash, "_run", warn_run)
    status = await canbus_flash.dfu_status()
    assert status["sudo"] is True and status["present"] is True


async def test_klipper_restarted_even_if_stop_is_cancelled(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """If the request is cancelled during the Klipper stop (CancelledError, a BaseException), the
    finally must still restart Klipper - the printer must never be left headless."""
    state = {"dfu": False, "runtime": True}
    _install(monkeypatch, state)

    async def cancel_stop(action: str) -> None:
        if action == "stop":
            raise asyncio.CancelledError

    monkeypatch.setattr(canbus_flash, "_klipper", cancel_stop)
    with pytest.raises(asyncio.CancelledError):
        await canbus_flash.flash("u2c-v2")
    assert state["_started"] == [1]  # the finally restarted Klipper despite the cancellation
