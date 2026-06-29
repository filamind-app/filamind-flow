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
                    "restart_ms": 1000,
                    "bittiming": {
                        "bitrate": 1_000_000,
                        "sample_point": 0.875,
                        "sjw": 1,
                        "brp": 5,
                        "tq": 50,
                        "prop_seg": 7,
                        "phase_seg1": 7,
                        "phase_seg2": 2,
                    },
                    "bittiming_const": {
                        "name": "gs_usb",
                        "tseg1_min": 1,
                        "tseg1_max": 16,
                        "tseg2_min": 1,
                        "tseg2_max": 8,
                        "sjw_max": 4,
                        "brp_min": 1,
                        "brp_max": 1024,
                    },
                    "clock": {"freq": 48_000_000},
                    "ctrlmode": ["LISTEN-ONLY"],
                },
            },
        }
    ]
)


def _is_show(cmd: list[str]) -> bool:
    return "show" in cmd


def test_parse_live_extracts_fields() -> None:
    live = canbus_control._parse_live(json.loads(_IP_JSON)[0])
    assert live["link_up"] is True
    assert live["state"] == "ERROR-ACTIVE"
    assert (live["errors_rx"], live["errors_tx"]) == (1, 2)
    assert live["txqueuelen"] == 128
    assert live["bitrate"] == 1_000_000
    p = live["params"]
    assert p["sample_point"] == 0.875 and p["sjw"] == 1 and p["restart_ms"] == 1000
    assert p["flags"]["listen_only"] is True and p["flags"]["loopback"] is False
    lim = live["limits"]
    assert lim["sjw_max"] == 4 and lim["clock_freq"] == 48_000_000 and lim["fd_supported"] is False


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


async def test_set_bitrate_validates_and_cycles_bus(monkeypatch: Any) -> None:
    async def idle(_self: Any, _objs: Any) -> dict[str, Any]:
        return {"print_stats": {"state": "standby"}}

    monkeypatch.setattr("app.services.moonraker_client.MoonrakerClient.query_objects", idle)

    # out-of-range bitrate -> ValueError before anything runs
    async def show_up(cmd: Any, timeout: float = 10.0) -> tuple[int, str]:
        return (0, _IP_JSON) if _is_show(cmd) else (0, "")

    monkeypatch.setattr(canbus_control, "_run", show_up)
    with pytest.raises(ValueError):
        await canbus_control.set_bitrate("can0", 9_999_999, "http://x")

    # interface up -> brought DOWN, retimed, brought back UP (no refusal); ends up usable again
    calls: list[list[str]] = []

    async def run_up(cmd: Any, timeout: float = 10.0) -> tuple[int, str]:
        calls.append(list(cmd))
        return (0, _IP_JSON) if _is_show(cmd) else (0, "")

    monkeypatch.setattr(canbus_control, "_run", run_up)
    res = await canbus_control.set_bitrate("can0", 500_000, "http://x")
    assert res["ok"] is True and res["refused"] is False
    assert ["sudo", "-n", "ip", "link", "set", "can0", "down"] in calls
    assert ["sudo", "-n", "ip", "link", "set", "can0", "type", "can", "bitrate", "500000"] in calls
    assert ["sudo", "-n", "ip", "link", "set", "can0", "up"] in calls


async def test_set_bitrate_restart_firmware_restarts(monkeypatch: Any) -> None:
    """restart=True triggers a Klipper FIRMWARE_RESTART after re-upping the bus."""
    fw_called = {"n": 0}

    async def idle(_self: Any, _objs: Any) -> dict[str, Any]:
        return {"print_stats": {"state": "standby"}}

    async def fw(_self: Any) -> None:
        fw_called["n"] += 1

    async def run_up(cmd: Any, timeout: float = 10.0) -> tuple[int, str]:
        return (0, _IP_JSON) if _is_show(cmd) else (0, "")

    monkeypatch.setattr("app.services.moonraker_client.MoonrakerClient.query_objects", idle)
    monkeypatch.setattr("app.services.moonraker_client.MoonrakerClient.firmware_restart", fw)
    monkeypatch.setattr(canbus_control, "_run", run_up)
    res = await canbus_control.set_bitrate("can0", 500_000, "http://x", restart=True)
    assert res["ok"] is True and res["restarted"] is True
    assert fw_called["n"] == 1


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


_DOWN_JSON = _IP_JSON.replace('"UP", ', "")


def _idle_run_setup(monkeypatch: Any, show_json: str, calls: list[list[str]]) -> None:
    async def idle(_self: Any, _objs: Any) -> dict[str, Any]:
        return {"print_stats": {"state": "standby"}}

    async def fake_run(cmd: Any, timeout: float = 10.0) -> tuple[int, str]:
        calls.append(list(cmd))
        return (0, show_json) if _is_show(cmd) else (0, "")

    monkeypatch.setattr("app.services.moonraker_client.MoonrakerClient.query_objects", idle)
    monkeypatch.setattr(canbus_control, "_run", fake_run)


async def test_set_params_validates(monkeypatch: Any) -> None:
    _idle_run_setup(monkeypatch, _IP_JSON, [])
    # unknown key
    with pytest.raises(ValueError):
        await canbus_control.set_params("can0", {"bogus": 1}, "http://x")
    # sjw above the controller's reported sjw_max (4)
    with pytest.raises(ValueError):
        await canbus_control.set_params("can0", {"sjw": 8}, "http://x")
    # a flag must be boolean, not a number
    with pytest.raises(ValueError):
        await canbus_control.set_params("can0", {"listen_only": 1}, "http://x")
    # empty payload
    with pytest.raises(ValueError):
        await canbus_control.set_params("can0", {}, "http://x")


async def test_set_params_cycles_bus_when_up(monkeypatch: Any) -> None:
    """A timing/mode change on an UP bus is no longer refused: the bus is brought down, the change
    applied, and the bus brought back up so it resumes (the user no longer has to do it by hand)."""
    calls: list[list[str]] = []
    _idle_run_setup(monkeypatch, _IP_JSON, calls)  # _IP_JSON is link_up=True
    res = await canbus_control.set_params("can0", {"bitrate": 500_000}, "http://x")
    assert res["ok"] is True and res["refused"] is False
    assert ["sudo", "-n", "ip", "link", "set", "can0", "down"] in calls
    assert ["sudo", "-n", "ip", "link", "set", "can0", "up"] in calls
    # down precedes the up (down → change → up)
    down_i = calls.index(["sudo", "-n", "ip", "link", "set", "can0", "down"])
    up_i = calls.index(["sudo", "-n", "ip", "link", "set", "can0", "up"])
    assert down_i < up_i


async def test_set_params_restart_firmware_restarts(monkeypatch: Any) -> None:
    fw_called = {"n": 0}

    async def fw(_self: Any) -> None:
        fw_called["n"] += 1

    _idle_run_setup(monkeypatch, _IP_JSON, [])
    monkeypatch.setattr("app.services.moonraker_client.MoonrakerClient.firmware_restart", fw)
    res = await canbus_control.set_params("can0", {"sjw": 2}, "http://x", restart=True)
    assert res["ok"] is True and res["restarted"] is True
    assert fw_called["n"] == 1


async def test_restart_klipper_guards_and_calls(monkeypatch: Any) -> None:
    fw_called = {"n": 0}

    async def fw(_self: Any) -> None:
        fw_called["n"] += 1

    async def printing(_self: Any, _objs: Any) -> dict[str, Any]:
        return {"print_stats": {"state": "printing"}}

    monkeypatch.setattr("app.services.moonraker_client.MoonrakerClient.firmware_restart", fw)
    # refused while printing (a firmware restart would abort the print)
    monkeypatch.setattr("app.services.moonraker_client.MoonrakerClient.query_objects", printing)
    assert (await canbus_control.restart_klipper("http://x"))["refused"] is True
    assert fw_called["n"] == 0

    async def idle(_self: Any, _objs: Any) -> dict[str, Any]:
        return {"print_stats": {"state": "standby"}}

    monkeypatch.setattr("app.services.moonraker_client.MoonrakerClient.query_objects", idle)
    res = await canbus_control.restart_klipper("http://x")
    assert res["ok"] is True and fw_called["n"] == 1


async def test_set_params_builds_command_when_down(monkeypatch: Any) -> None:
    calls: list[list[str]] = []
    _idle_run_setup(monkeypatch, _DOWN_JSON, calls)
    res = await canbus_control.set_params(
        "can0",
        {"bitrate": 500_000, "sample_point": 0.85, "listen_only": True, "triple_sampling": False},
        "http://x",
    )
    assert res["ok"] is True
    set_cmd = next(c for c in calls if "set" in c and "type" in c)
    assert set_cmd[:7] == ["sudo", "-n", "ip", "link", "set", "can0", "type"]
    for tok in (
        "bitrate",
        "500000",
        "sample-point",
        "0.85",
        "listen-only",
        "on",
        "triple-sampling",
        "off",
    ):
        assert tok in set_cmd


async def test_set_params_txqueuelen_runs_separately(monkeypatch: Any) -> None:
    calls: list[list[str]] = []
    _idle_run_setup(monkeypatch, _IP_JSON, calls)  # up is fine: txqueuelen doesn't need down
    res = await canbus_control.set_params("can0", {"txqueuelen": 256}, "http://x")
    assert res["ok"] is True
    assert ["sudo", "-n", "ip", "link", "set", "can0", "txqueuelen", "256"] in calls
    # bad txqueuelen rejected
    with pytest.raises(ValueError):
        await canbus_control.set_params("can0", {"txqueuelen": -1}, "http://x")


# `ip -json` records that violate the expected shape (older kernels / odd drivers / VPN-style
# pseudo-CAN ifaces). The read path must degrade, never raise -> no 500 on the panel.
_MALFORMED_RECORDS = [
    {"ifname": "can0"},  # no linkinfo at all
    {"ifname": "can0", "linkinfo": None},  # null linkinfo
    {"ifname": "can0", "linkinfo": {"info_data": None}},  # null info_data
    {"ifname": "can0", "linkinfo": {"info_data": []}},  # info_data is a list, not a dict
    {"ifname": "can0", "linkinfo": {"info_data": {"bittiming": []}}},  # bittiming a list
    {"ifname": "can0", "linkinfo": {"info_data": {"berr_counter": "nope"}}},  # berr a string
    {"ifname": "can0", "linkinfo": {"info_data": {"clock": 7}}},  # clock not a dict
]


@pytest.mark.parametrize("record", _MALFORMED_RECORDS)
def test_parse_live_degrades_on_malformed_record(record: dict[str, Any]) -> None:
    live = canbus_control._parse_live(record)
    # No raise; missing fields surface as None rather than crashing the read.
    assert live["state"] is None
    assert live["errors_rx"] is None and live["errors_tx"] is None
    assert live["bitrate"] is None
    assert isinstance(live["params"], dict) and isinstance(live["limits"], dict)


async def test_all_live_status_skips_malformed_records(monkeypatch: Any) -> None:
    """A garbage entry in the `ip -json` array is skipped, not allowed to 500 the whole read."""
    payload = json.dumps(
        [{"ifname": "can0", "linkinfo": {"info_data": []}}, json.loads(_IP_JSON)[0]]
    )

    async def fake_run(cmd: Any, timeout: float = 10.0) -> tuple[int, str]:
        return (0, payload) if _is_show(cmd) else (0, "")

    monkeypatch.setattr(canbus_control, "_run", fake_run)
    live = await canbus_control._all_live_status()
    assert "can0" in live  # the well-formed second record still parsed


async def test_list_can_buses_survives_moonraker_failure(monkeypatch: Any, tmp_path: Any) -> None:
    """A non-HTTP Moonraker/catalog error must degrade to live `ip` data, not raise a 500."""

    async def boom(_self: Any) -> dict[str, Any]:
        raise RuntimeError("malformed system_info")

    async def fake_run(cmd: Any, timeout: float = 10.0) -> tuple[int, str]:
        return (0, _IP_JSON) if _is_show(cmd) else (0, "")

    monkeypatch.setattr("app.services.moonraker_client.MoonrakerClient.machine_system_info", boom)
    monkeypatch.setattr(canbus_control, "_run", fake_run)

    buses = await canbus_control.list_can_buses("http://x", str(tmp_path))
    # Moonraker enrichment was lost, but the live interface is still listed.
    assert [b["interface"] for b in buses] == ["can0"]
    assert buses[0]["driver"] is None  # no Moonraker enrichment
    assert buses[0]["link_up"] is True  # live data still present


async def test_set_restart(monkeypatch: Any) -> None:
    calls: list[list[str]] = []
    _idle_run_setup(monkeypatch, _IP_JSON, calls)
    res = await canbus_control.set_restart("can0", "http://x")
    assert res["ok"] is True
    assert ["sudo", "-n", "ip", "link", "set", "can0", "type", "can", "restart"] in calls

    async def printing(_self: Any, _objs: Any) -> dict[str, Any]:
        return {"print_stats": {"state": "printing"}}

    monkeypatch.setattr("app.services.moonraker_client.MoonrakerClient.query_objects", printing)
    assert (await canbus_control.set_restart("can0", "http://x"))["refused"] is True
