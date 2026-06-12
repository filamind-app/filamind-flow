from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.services import flash_service, health_service


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


async def test_sudo_ready_probes_authorisation_not_systemctl_version(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`sudo -n -l systemctl stop klipper` (a non-destructive authorisation check that the
    NOPASSWD rules actually grant) — not `systemctl --version`, which they don't."""
    captured: list[str] = []

    class _Proc:
        async def wait(self) -> int:
            return 0

    async def fake_exec(*cmd: str, **kwargs: Any) -> _Proc:
        captured.extend(cmd)
        return _Proc()

    monkeypatch.setattr(flash_service.asyncio, "create_subprocess_exec", fake_exec)
    assert await flash_service._sudo_ready() is True
    assert captured[:3] == ["sudo", "-n", "-l"]
    assert captured[-2:] == ["stop", "klipper"]
    assert any(c.endswith("systemctl") for c in captured)
    assert "--version" not in captured


async def _aval(value: bool):  # type: ignore[no-untyped-def]
    return value


async def test_health_sudoers_passes_on_capability_without_the_named_file(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When the NOPASSWD rules live in another sudoers file, the capability probe passes and
    the 'sudoers' check must not false-fail on a missing /etc/sudoers.d/filamind."""
    monkeypatch.setattr(health_service, "_sudo_ready", lambda: _aval(True))
    monkeypatch.setattr(health_service.os.path, "isfile", lambda p: False)
    by_name = {c["name"]: c["ok"] for c in (await health_service.gather_health())["checks"]}
    assert by_name["sudo"] is True
    assert by_name["sudoers"] is True


async def test_health_sudoers_fails_when_capability_and_file_both_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(health_service, "_sudo_ready", lambda: _aval(False))
    monkeypatch.setattr(health_service.os.path, "isfile", lambda p: False)
    by_name = {c["name"]: c["ok"] for c in (await health_service.gather_health())["checks"]}
    assert by_name["sudo"] is False
    assert by_name["sudoers"] is False
