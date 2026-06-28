"""Tests for the host CAN-bus control service (status parse + link/bitrate guards)."""

from __future__ import annotations

import json
from typing import Any

import pytest

from app.services import canbus_control

# One CAN interface as `ip -details -statistics -json link show type can` reports it.
_IP_JSON = json.dumps(
    [
        {
            "ifname": "can0",
            "flags": ["NOARP", "UP", "LOWER_UP", "ECHO"],
            "txqlen": 128,
            "linkinfo": {
                "info_kind": "can",
                "info_data": {
                    "state": "ERROR-ACTIVE",
                    "berr_counter": {"tx": 2, "rx": 1},
                    "bittiming": {"bitrate": 1_000_000},
                },
            },
        }
    ]
)


def _is_show(cmd: list[str]) -> bool:
    return "show" in cmd


def test_parse_live_extracts_fields() -> None:
    entry = json.loads(_IP_JSON)[0]
    live = canbus_control._parse_live(entry)
    assert live == {
        "link_up": True,
        "state": "ERROR-ACTIVE",
        "errors_rx": 1,
        "errors_tx": 2,
        "txqueuelen": 128,
        "bitrate": 1_000_000,
    }


async def test_all_live_status_handles_missing_ip(monkeypatch: Any) -> None:
    async def missing(_cmd: Any, timeout: float = 10.0) -> tuple[int, str]:
        return 127, "ip: not found"

    monkeypatch.setattr(canbus_control, "_run", missing)
    assert await canbus_control._all_live_status() == {}


async def test_list_can_buses_merges_moonraker_and_live(monkeypatch: Any, tmp_path: Any) -> None:
    """Driver + adapter match come from Moonraker; link/state/errors/txqueue from live `ip`."""

    async def fake_system_info(_self: Any) -> dict[str, Any]:
        return {"canbus": {"can0": {"driver": "gs_usb", "bitrate": 1_000_000}}}

    async def fake_run(cmd: Any, timeout: float = 10.0) -> tuple[int, str]:
        return (0, _IP_JSON) if _is_show(cmd) else (0, "")

    monkeypatch.setattr(
        "app.services.moonraker_client.MoonrakerClient.machine_system_info", fake_system_info
    )
    monkeypatch.setattr(canbus_control, "_run", fake_run)

    buses = await canbus_control.list_can_buses("http://x", str(tmp_path))
    assert len(buses) == 1
    bus = buses[0]
    assert bus["interface"] == "can0"
    assert bus["driver"] == "gs_usb"
    assert bus["link_up"] is True
    assert bus["state"] == "ERROR-ACTIVE"
    assert bus["bitrate"] == 1_000_000
    assert (bus["errors_rx"], bus["errors_tx"]) == (1, 2)
    assert bus["txqueuelen"] == 128
    # gs_usb is a USB-CAN adapter -> suggested catalog board.
    assert bus["board_match"] == "suggested"


async def test_set_link_refused_while_printing(monkeypatch: Any) -> None:
    async def fake_run(cmd: Any, timeout: float = 10.0) -> tuple[int, str]:
        return (0, _IP_JSON) if _is_show(cmd) else (0, "")

    async def printing(_self: Any, _objs: Any) -> dict[str, Any]:
        return {"print_stats": {"state": "printing"}}

    monkeypatch.setattr(canbus_control, "_run", fake_run)
    monkeypatch.setattr("app.services.moonraker_client.MoonrakerClient.query_objects", printing)

    res = await canbus_control.set_link("can0", False, "http://x")
    assert res["refused"] is True and res["ok"] is False


async def test_set_link_runs_when_idle(monkeypatch: Any) -> None:
    calls: list[list[str]] = []

    async def fake_run(cmd: Any, timeout: float = 10.0) -> tuple[int, str]:
        calls.append(list(cmd))
        return (0, _IP_JSON) if _is_show(cmd) else (0, "")

    async def idle(_self: Any, _objs: Any) -> dict[str, Any]:
        return {"print_stats": {"state": "standby"}}

    monkeypatch.setattr(canbus_control, "_run", fake_run)
    monkeypatch.setattr("app.services.moonraker_client.MoonrakerClient.query_objects", idle)

    res = await canbus_control.set_link("can0", True, "http://x")
    assert res["ok"] is True and res["refused"] is False
    assert ["sudo", "-n", "ip", "link", "set", "can0", "up"] in calls


async def test_set_link_rejects_unknown_iface(monkeypatch: Any) -> None:
    async def fake_run(cmd: Any, timeout: float = 10.0) -> tuple[int, str]:
        return (0, _IP_JSON) if _is_show(cmd) else (0, "")

    monkeypatch.setattr(canbus_control, "_run", fake_run)
    # bad shape -> ValueError (mapped to 400 by the route)
    with pytest.raises(ValueError):
        await canbus_control.set_link("eth0", True, "http://x")
    # well-formed but not a discovered CAN iface -> ValueError
    with pytest.raises(ValueError):
        await canbus_control.set_link("can7", True, "http://x")


async def test_set_bitrate_validates_and_requires_down(monkeypatch: Any) -> None:
    async def idle(_self: Any, _objs: Any) -> dict[str, Any]:
        return {"print_stats": {"state": "standby"}}

    monkeypatch.setattr("app.services.moonraker_client.MoonrakerClient.query_objects", idle)

    # out-of-range bitrate -> ValueError before anything runs
    async def show_up(cmd: Any, timeout: float = 10.0) -> tuple[int, str]:
        return (0, _IP_JSON) if _is_show(cmd) else (0, "")

    monkeypatch.setattr(canbus_control, "_run", show_up)
    with pytest.raises(ValueError):
        await canbus_control.set_bitrate("can0", 9_999_999, "http://x")

    # interface is up -> refused (must be down first)
    res = await canbus_control.set_bitrate("can0", 500_000, "http://x")
    assert res["refused"] is True

    # interface down -> runs the ip type-can bitrate command
    down_json = _IP_JSON.replace('"UP", ', "")
    calls: list[list[str]] = []

    async def show_down(cmd: Any, timeout: float = 10.0) -> tuple[int, str]:
        calls.append(list(cmd))
        return (0, down_json) if _is_show(cmd) else (0, "")

    monkeypatch.setattr(canbus_control, "_run", show_down)
    res = await canbus_control.set_bitrate("can0", 500_000, "http://x")
    assert res["ok"] is True
    assert ["sudo", "-n", "ip", "link", "set", "can0", "type", "can", "bitrate", "500000"] in calls


async def test_set_action_reports_missing_sudo(monkeypatch: Any) -> None:
    async def idle(_self: Any, _objs: Any) -> dict[str, Any]:
        return {"print_stats": {"state": "standby"}}

    async def nosudo(cmd: Any, timeout: float = 10.0) -> tuple[int, str]:
        if _is_show(cmd):
            return 0, _IP_JSON
        return 1, "sudo: a password is required"

    monkeypatch.setattr("app.services.moonraker_client.MoonrakerClient.query_objects", idle)
    monkeypatch.setattr(canbus_control, "_run", nosudo)
    res = await canbus_control.set_link("can0", False, "http://x")
    assert res["ok"] is False and res["needs_setup"] is True
