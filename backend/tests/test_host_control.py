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
