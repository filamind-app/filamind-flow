"""Tests for the generalized touchscreen selector (KlipperScreen / Guppyscreen / FilaMind)."""

from __future__ import annotations

from typing import Any

import pytest

from app.services import kiosk_service as k


def _patch_units(monkeypatch: Any, installed: dict[str, bool], active: dict[str, bool]) -> None:
    async def fake_installed(unit: str) -> bool:
        return installed.get(unit, False)

    async def fake_active(unit: str) -> bool:
        return active.get(unit, False)

    async def fake_enabled(unit: str) -> bool:
        return False

    monkeypatch.setattr(k, "_unit_installed", fake_installed)
    monkeypatch.setattr(k, "_is_active", fake_active)
    monkeypatch.setattr(k, "_is_enabled", fake_enabled)


async def test_touch_status_reports_all_three(monkeypatch: Any) -> None:
    _patch_units(
        monkeypatch,
        installed={"KlipperScreen.service": True, "guppyscreen.service": True},
        active={"KlipperScreen.service": True},
    )
    st = await k.touch_status()
    assert st["active"] == "klipperscreen"
    assert st["screens"]["guppyscreen"]["installed"] is True
    assert st["screens"]["filamind"]["installed"] is False


async def test_switch_touch_stops_others_and_starts_target(monkeypatch: Any) -> None:
    _patch_units(
        monkeypatch,
        installed={"KlipperScreen.service": True, "guppyscreen.service": True},
        active={"KlipperScreen.service": True},
    )
    done: list[tuple[str, str]] = []

    async def fake_do(action: str, unit: str) -> dict[str, Any]:
        done.append((action, unit))
        return {"cmd": f"{action} {unit}", "ok": True, "output": None}

    monkeypatch.setattr(k, "_do", fake_do)
    await k.switch_touch("guppyscreen", persist=True)
    assert ("stop", "KlipperScreen.service") in done  # the active one is stopped
    assert ("enable", "guppyscreen.service") in done  # persisted as boot default
    assert ("start", "guppyscreen.service") in done


async def test_switch_to_uninstalled_screen_errors(monkeypatch: Any) -> None:
    _patch_units(monkeypatch, installed={"KlipperScreen.service": True}, active={})
    with pytest.raises(k.KioskNotInstalledError):
        await k.switch_touch("filamind")


async def test_switch_to_unknown_screen_is_value_error(monkeypatch: Any) -> None:
    _patch_units(monkeypatch, installed={}, active={})
    with pytest.raises(ValueError):
        await k.switch_touch("bogus")
