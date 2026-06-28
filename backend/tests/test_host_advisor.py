"""Tests for the host health advisor (graded cards from the monitor signals)."""

from __future__ import annotations

from typing import Any

from app.services import host_control_service as hcs


def test_grade_bands() -> None:
    assert hcs._grade(95) == "A"
    assert hcs._grade(80) == "B"
    assert hcs._grade(65) == "C"
    assert hcs._grade(50) == "D"
    assert hcs._grade(10) == "F"


def test_cpu_card_temperature_and_throttle() -> None:
    cool = hcs._cpu_card({"temp_c": 45, "load": [0.2, 0.3, 0.4]}, {"flags": []})
    assert cool["status"] == "ok" and cool["grade"] == "A"

    hot = hcs._cpu_card({"temp_c": 84, "load": None}, {"flags": []})
    assert hot["status"] == "fail" and "temp_high" in hot["badges"]
    assert hot["fix_code"] == "cpu_temp"

    throttled = hcs._cpu_card({"temp_c": 50}, {"flags": ["undervoltage_now"], "undervoltage": True})
    assert throttled["status"] == "fail"
    assert "throttled" in throttled["badges"] and "undervolt" in throttled["badges"]
    assert throttled["fix_code"] == "cpu_throttled"


def test_mem_card_pressure_and_swap() -> None:
    ok = hcs._mem_card(
        {"total_kb": 8_000_000, "used_kb": 2_000_000, "swap_total_kb": 0, "swap_used_kb": 0}
    )
    assert ok["status"] == "ok" and ok["score"] == 75

    full = hcs._mem_card(
        {"total_kb": 8_000_000, "used_kb": 7_600_000, "swap_total_kb": 0, "swap_used_kb": 0}
    )
    assert full["status"] == "fail" and full["fix_code"] == "memory_pressure"

    swap = hcs._mem_card(
        {
            "total_kb": 8_000_000,
            "used_kb": 4_000_000,  # 50% used -> ok on its own
            "swap_total_kb": 1_000_000,
            "swap_used_kb": 800_000,  # 80% swap -> warn
        }
    )
    assert swap["status"] == "warn" and "swap_heavy" in swap["badges"]


def test_disk_card_uses_worst_mount() -> None:
    card = hcs._disk_card([{"label": "/", "pct": 40}, {"label": "data", "pct": 96}])
    assert card["status"] == "fail" and card["fix_code"] == "disk_full"
    assert card["score"] == 4  # 100 - 96
    assert hcs._disk_card([])["status"] == "unknown"


def test_clock_card_ntp() -> None:
    assert hcs._clock_card({"timezone": "UTC", "ntp_synced": True})["status"] == "ok"
    warn = hcs._clock_card({"timezone": "UTC", "ntp_synced": False, "ntp_enabled": True})
    assert warn["status"] == "warn" and warn["fix_code"] == "ntp_unsync"


async def test_services_card(monkeypatch: Any) -> None:
    async def units_ok() -> list[dict[str, Any]]:
        return [
            {"name": "klipper", "active": True},
            {"name": "moonraker", "active": True},
        ]

    monkeypatch.setattr(hcs, "list_units", units_ok)
    card = await hcs._services_card()
    assert card["status"] == "ok" and card["score"] == 100

    async def units_down() -> list[dict[str, Any]]:
        return [{"name": "klipper", "active": False}, {"name": "moonraker", "active": True}]

    monkeypatch.setattr(hcs, "list_units", units_down)
    card = await hcs._services_card()
    assert card["status"] == "fail" and card["fix_code"] == "service_down"


async def test_advisory_returns_five_cards(monkeypatch: Any) -> None:
    async def units() -> list[dict[str, Any]]:
        return [{"name": "klipper", "active": True}, {"name": "moonraker", "active": True}]

    async def throttle() -> dict[str, Any]:
        return {"supported": False, "flags": [], "undervoltage": None}

    async def timeb() -> dict[str, Any]:
        return {"timezone": "UTC", "ntp_synced": True, "ntp_enabled": True}

    monkeypatch.setattr(hcs, "list_units", units)
    monkeypatch.setattr(hcs, "_throttle_block", throttle)
    monkeypatch.setattr(hcs, "_time_block", timeb)
    result = await hcs.advisory("")
    ids = [c["id"] for c in result["cards"]]
    assert ids == ["cpu", "memory", "disk", "clock", "services"]
    for c in result["cards"]:
        assert c["grade"] in {"A", "B", "C", "D", "F"}
        assert 0 <= c["score"] <= 100
