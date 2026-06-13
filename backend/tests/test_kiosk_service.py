"""Tests for the FilaMind Kiosk service — status derivation + the reversible-swap command
sequences (systemctl is stubbed; nothing is actually started)."""

from __future__ import annotations

import pytest

from app.services import kiosk_service


class FakeCtl:
    """Stubs ``kiosk_service._run``: answers read-only queries from canned state and records the
    privileged ``sudo systemctl`` actions so a test can assert the exact sequence."""

    def __init__(
        self,
        *,
        kiosk_installed: bool = True,
        kiosk_active: bool = False,
        kiosk_enabled: bool = False,
        screen_installed: bool = True,
        screen_active: bool = True,
        fail_start_kiosk: bool = False,
    ) -> None:
        self.kiosk_installed = kiosk_installed
        self.kiosk_active = kiosk_active
        self.kiosk_enabled = kiosk_enabled
        self.screen_installed = screen_installed
        self.screen_active = screen_active
        self.fail_start_kiosk = fail_start_kiosk
        self.actions: list[str] = []

    def _is_kiosk(self, unit: str) -> bool:
        return "filamind-kiosk" in unit

    async def run(self, cmd: list[str]) -> tuple[int, str]:
        if cmd[:2] == ["systemctl", "list-unit-files"]:
            unit = cmd[2]
            installed = self.kiosk_installed if self._is_kiosk(unit) else self.screen_installed
            return (0, f"{unit} enabled\n" if installed else "0 unit files listed.\n")
        if cmd[:2] == ["systemctl", "is-active"]:
            unit = cmd[3]
            active = self.kiosk_active if self._is_kiosk(unit) else self.screen_active
            return (0 if active else 3, "active\n" if active else "inactive\n")
        if cmd[:2] == ["systemctl", "is-enabled"]:
            unit = cmd[2]
            enabled = self.kiosk_enabled if self._is_kiosk(unit) else True
            return (0, "enabled\n" if enabled else "disabled\n")
        if cmd[:3] == ["sudo", "-n", "systemctl"]:
            action, unit = cmd[3], cmd[4]
            self.actions.append(f"{action} {unit}")
            if action == "start" and self._is_kiosk(unit) and self.fail_start_kiosk:
                return (1, "Job for filamind-kiosk.service failed")
            return (0, "")
        raise AssertionError(f"unexpected command: {cmd}")


def _install(monkeypatch: pytest.MonkeyPatch, ctl: FakeCtl) -> FakeCtl:
    monkeypatch.setattr(kiosk_service, "_run", ctl.run)
    return ctl


async def test_status_mode_klipperscreen(monkeypatch: pytest.MonkeyPatch) -> None:
    _install(monkeypatch, FakeCtl(kiosk_installed=True, kiosk_active=False, screen_active=True))
    out = await kiosk_service.status()
    assert out["mode"] == "klipperscreen"
    assert out["kiosk_installed"] is True
    assert out["kiosk_active"] is False
    assert out["screen_active"] is True
    assert out["url"] == "http://localhost:8090"


async def test_status_mode_kiosk(monkeypatch: pytest.MonkeyPatch) -> None:
    _install(monkeypatch, FakeCtl(kiosk_active=True, screen_active=False, kiosk_enabled=True))
    out = await kiosk_service.status()
    assert out["mode"] == "kiosk"
    assert out["kiosk_enabled"] is True


async def test_status_mode_none_when_not_installed(monkeypatch: pytest.MonkeyPatch) -> None:
    _install(monkeypatch, FakeCtl(kiosk_installed=False, screen_active=False))
    out = await kiosk_service.status()
    assert out["mode"] == "none"
    assert out["kiosk_installed"] is False
    # An uninstalled kiosk is never probed for active/enabled.
    assert out["kiosk_active"] is False
    assert out["kiosk_enabled"] is False


async def test_switch_to_kiosk_not_installed_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    _install(monkeypatch, FakeCtl(kiosk_installed=False))
    with pytest.raises(kiosk_service.KioskNotInstalledError):
        await kiosk_service.switch_to_kiosk()


async def test_switch_to_kiosk_temporary_just_starts(monkeypatch: pytest.MonkeyPatch) -> None:
    ctl = _install(monkeypatch, FakeCtl(kiosk_installed=True, screen_active=True))
    out = await kiosk_service.switch_to_kiosk(persist=False)
    # Temporary swap: only starts the kiosk (Conflicts= stops KlipperScreen) — no enable/disable.
    assert ctl.actions == ["start filamind-kiosk.service"]
    assert out["action"] == "kiosk"
    assert out["persist"] is False
    assert all(step["ok"] for step in out["steps"])


async def test_switch_to_kiosk_persist_flips_boot_default(monkeypatch: pytest.MonkeyPatch) -> None:
    ctl = _install(monkeypatch, FakeCtl(kiosk_installed=True))
    await kiosk_service.switch_to_kiosk(persist=True)
    assert ctl.actions == [
        "disable KlipperScreen.service",
        "enable filamind-kiosk.service",
        "start filamind-kiosk.service",
    ]


async def test_switch_failure_recovers_klipperscreen(monkeypatch: pytest.MonkeyPatch) -> None:
    ctl = _install(monkeypatch, FakeCtl(kiosk_installed=True, fail_start_kiosk=True))
    out = await kiosk_service.switch_to_kiosk(persist=False)
    # Kiosk start failed → KlipperScreen is brought back so the screen never stays dark.
    assert ctl.actions == ["start filamind-kiosk.service", "start KlipperScreen.service"]
    assert out["steps"][0]["ok"] is False


async def test_restore_screen_temporary(monkeypatch: pytest.MonkeyPatch) -> None:
    ctl = _install(
        monkeypatch, FakeCtl(kiosk_installed=True, kiosk_active=True, screen_active=False)
    )
    out = await kiosk_service.restore_screen(persist=False)
    assert ctl.actions == ["stop filamind-kiosk.service", "start KlipperScreen.service"]
    assert out["action"] == "klipperscreen"


async def test_restore_screen_persist(monkeypatch: pytest.MonkeyPatch) -> None:
    ctl = _install(monkeypatch, FakeCtl(kiosk_installed=True, kiosk_active=True))
    await kiosk_service.restore_screen(persist=True)
    assert ctl.actions == [
        "stop filamind-kiosk.service",
        "disable filamind-kiosk.service",
        "enable KlipperScreen.service",
        "start KlipperScreen.service",
    ]
