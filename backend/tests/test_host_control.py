from __future__ import annotations

import pytest

from app.services import host_control_service as hc


async def test_monitor_returns_all_blocks() -> None:
    # Smoke test: works on any OS because every read degrades gracefully (missing /proc, /sys and
    # commands just yield empty/None). The contract the frontend depends on must always be present.
    snap = await hc.monitor("~/printer_data/config/filamind")
    for key in (
        "host",
        "cpu",
        "memory",
        "disk",
        "throttle",
        "processes",
        "network",
        "time",
        "locale",
    ):
        assert key in snap
    assert isinstance(snap["host"]["hostname"], str)
    assert isinstance(snap["disk"], list)
    assert isinstance(snap["processes"], list)
    assert set(snap["memory"]) == {
        "total_kb",
        "available_kb",
        "used_kb",
        "swap_total_kb",
        "swap_used_kb",
    }


def test_memory_parser(monkeypatch: pytest.MonkeyPatch) -> None:
    meminfo = "MemTotal: 1000 kB\nMemAvailable: 250 kB\nSwapTotal: 400 kB\nSwapFree: 100 kB\n"
    monkeypatch.setattr(hc, "_read", lambda path: meminfo)
    mem = hc._memory_block()
    assert mem["total_kb"] == 1000
    assert mem["available_kb"] == 250
    assert mem["used_kb"] == 750  # total - available
    assert mem["swap_used_kb"] == 300  # swap_total - swap_free


async def test_throttle_parses_pi_flags(monkeypatch: pytest.MonkeyPatch) -> None:
    # 0x50000 = bit16 (undervoltage_occurred) + bit18 (throttled_occurred).
    async def fake_run(cmd: list[str], timeout: float = 5.0) -> str:
        return "throttled=0x50000\n"

    monkeypatch.setattr(hc, "_run", fake_run)
    t = await hc._throttle_block()
    assert t["supported"] is True
    assert t["undervoltage"] is True
    assert "undervoltage_occurred" in t["flags"]
    assert "throttled_occurred" in t["flags"]


async def test_throttle_unsupported_when_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_run(cmd: list[str], timeout: float = 5.0) -> str:
        return ""  # vcgencmd not installed (most non-Pi boards)

    monkeypatch.setattr(hc, "_run", fake_run)
    t = await hc._throttle_block()
    assert t["supported"] is False
    assert t["flags"] == []


async def test_time_block_reads_timedatectl(monkeypatch: pytest.MonkeyPatch) -> None:
    show = (
        "Timezone=Europe/Berlin\nNTP=yes\nNTPSynchronized=yes\nTimeUSec=Sat 2026-06-14 10:00:00\n"
    )

    async def fake_run(cmd: list[str], timeout: float = 5.0) -> str:
        return show

    monkeypatch.setattr(hc, "_run", fake_run)
    tb = await hc._time_block()
    assert tb["timezone"] == "Europe/Berlin"
    assert tb["ntp_enabled"] is True
    assert tb["ntp_synced"] is True


async def test_run_returns_empty_on_missing_binary() -> None:
    # A read-only command that does not exist must not raise — it yields "".
    assert await hc._run(["definitely-not-a-real-binary-xyz"]) == ""


# ── Services (Phase 2) ─────────────────────────────────────────────────────────


def test_unit_name_validation() -> None:
    assert hc._valid_unit("moonraker")
    assert hc._valid_unit("klipper-mcu.service")
    assert hc._valid_unit("getty@tty1.service")  # instanced template
    assert not hc._valid_unit("")
    assert not hc._valid_unit("../etc/passwd")  # path traversal
    assert not hc._valid_unit("foo; rm -rf /")  # shell metachars / spaces


def test_protected_and_critical_flags() -> None:
    assert hc._is_protected("ssh")
    assert hc._is_protected("filamind-flow.service")
    assert hc._is_protected("systemd-journald")
    assert not hc._is_protected("moonraker")
    # Critical (warn) but not protected (still manageable).
    assert hc._is_critical("moonraker")
    assert hc._is_critical("systemd-tmpfiles-clean")  # systemd-* prefix
    assert not hc._is_critical("myrandomapp")


def _svc_runner(units: str, files: str):
    async def fake(cmd: list[str], timeout: float = 10.0) -> tuple[int, str]:
        if "list-units" in cmd:
            return 0, units
        if "list-unit-files" in cmd:
            return 0, files
        return 0, ""

    return fake


async def test_list_units_merges_state(monkeypatch: pytest.MonkeyPatch) -> None:
    units = (
        "moonraker.service loaded active running API host\n"
        "ssh.service loaded active running OpenBSD Secure Shell server\n"
        "myapp.service loaded active running My app\n"
    )
    files = (
        "moonraker.service enabled enabled\n"
        "ssh.service enabled enabled\n"
        "myapp.service enabled enabled\n"
        "dormant.service disabled disabled\n"  # installed but not loaded
    )
    monkeypatch.setattr(hc, "_run_rc", _svc_runner(units, files))
    svcs = {s["name"]: s for s in await hc.list_units()}
    assert svcs["moonraker"]["active"] is True
    assert svcs["moonraker"]["enabled"] == "enabled"
    assert svcs["moonraker"]["critical"] is True and svcs["moonraker"]["protected"] is False
    assert svcs["ssh"]["protected"] is True
    assert svcs["myapp"]["critical"] is False
    # A unit present only in list-unit-files shows up as inactive.
    assert svcs["dormant"]["active"] is False and svcs["dormant"]["enabled"] == "disabled"


async def test_manage_unit_refuses_destructive_on_protected() -> None:
    res = await hc.manage_unit("ssh", "stop")
    assert res["ok"] is False and res["refused"] is True
    # unmask is not destructive, so it is allowed even on a protected unit (would shell out).


async def test_manage_unit_rejects_bad_action() -> None:
    with pytest.raises(ValueError):
        await hc.manage_unit("myapp", "obliterate")


async def test_manage_unit_runs_allowed_action(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake(cmd: list[str], timeout: float = 10.0) -> tuple[int, str]:
        assert cmd == ["sudo", "-n", "systemctl", "restart", "myapp.service"]
        return 0, ""

    monkeypatch.setattr(hc, "_run_rc", fake)
    res = await hc.manage_unit("myapp", "restart")
    assert res["ok"] is True and res["refused"] is False


async def test_delete_unit_requires_matching_confirm() -> None:
    res = await hc.delete_unit("myapp", "wrong")
    assert res["ok"] is False and res["refused"] is True


async def test_delete_unit_refuses_protected() -> None:
    res = await hc.delete_unit("ssh", "ssh")
    assert res["ok"] is False and res["refused"] is True


async def test_delete_unit_refuses_vendor_path(monkeypatch: pytest.MonkeyPatch) -> None:
    # A unit whose fragment lives under /lib/systemd (vendor) must not be deletable.
    async def fake(cmd: list[str], timeout: float = 10.0) -> tuple[int, str]:
        if "show" in cmd:
            return 0, "FragmentPath=/lib/systemd/system/myapp.service\nDescription=x\n"
        return 0, ""

    monkeypatch.setattr(hc, "_run_rc", fake)
    res = await hc.delete_unit("myapp", "myapp")
    assert res["ok"] is False and res["refused"] is True


async def test_delete_unit_removes_user_installed(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []

    async def fake(cmd: list[str], timeout: float = 10.0) -> tuple[int, str]:
        calls.append(cmd)
        if "show" in cmd:
            return 0, "FragmentPath=/etc/systemd/system/myapp.service\nDescription=x\n"
        return 0, ""

    monkeypatch.setattr(hc, "_run_rc", fake)
    res = await hc.delete_unit("myapp", "myapp")
    assert res["ok"] is True and res["refused"] is False
    assert any(c[:3] == ["sudo", "-n", "rm"] for c in calls)
    assert any("daemon-reload" in c for c in calls)
