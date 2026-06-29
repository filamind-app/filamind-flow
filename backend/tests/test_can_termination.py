"""Tests for the CAN 120Ω termination advisory (board_topology._can_termination)."""

from __future__ import annotations

from typing import Any

from app.models.schemas import Topology
from app.services import board_topology, reference_data


def test_none_without_can() -> None:
    result = {"mcus": [{"name": "mcu", "connection": "usb"}], "can_buses": []}
    assert board_topology._can_termination(result) is None


def test_two_node_segment_carries_terminator_info(monkeypatch: Any) -> None:
    catalog = {
        "u2c-all": {
            "board_id": "u2c-all",
            "display_name": "BTT U2C",
            "canTermination": {"type": "jumper", "location": "120R jumper", "default": "unknown"},
        },
        "ebb": {
            "board_id": "ebb",
            "model": "EBB36",
            "canTermination": {"type": "jumper", "location": "120R cap", "default": "unknown"},
        },
    }
    monkeypatch.setattr(reference_data, "board_by_id", lambda i: catalog.get(i))
    result = {
        "mcus": [
            {"name": "toolhead", "connection": "canbus", "board_id": "ebb"},
            {"name": "mcu", "connection": "usb", "board_id": "main"},  # not a CAN node
        ],
        "can_buses": [{"interface": "can0", "board_id": "u2c-all"}],
    }
    term = board_topology._can_termination(result)
    assert term is not None
    assert {n["name"] for n in term["nodes"]} == {"can0", "toolhead"}  # adapter + 1 CAN MCU
    adapter = next(n for n in term["nodes"] if n["role"] == "adapter")
    assert adapter["board_name"] == "BTT U2C"
    assert adapter["termination"]["type"] == "jumper"
    codes = [f["code"] for f in term["findings"]]
    assert "rule" in codes and "both_ends" in codes


def test_three_nodes_flags_middle_off(monkeypatch: Any) -> None:
    monkeypatch.setattr(reference_data, "board_by_id", lambda i: None)
    result = {
        "mcus": [
            {"name": "t1", "connection": "canbus", "board_id": "x"},
            {"name": "t2", "connection": "canbus", "board_id": "y"},
        ],
        "can_buses": [{"interface": "can0", "board_id": "u2c"}],
    }
    term = board_topology._can_termination(result)
    assert len(term["nodes"]) == 3
    middle = next(f for f in term["findings"] if f["code"] == "middle_off")
    assert middle["level"] == "warning" and middle["count"] == 3
    # a node whose board has no catalog entry still appears, just without terminator info
    assert all(n["termination"] is None for n in term["nodes"])


def test_live_bus_off_raises_error_finding(monkeypatch: Any) -> None:
    """A bus-off controller is the runtime fingerprint of wrong 120Ω termination."""
    monkeypatch.setattr(reference_data, "board_by_id", lambda i: None)
    result = {
        "mcus": [{"name": "toolhead", "connection": "canbus", "board_id": "ebb"}],
        "can_buses": [{"interface": "can0", "board_id": "u2c"}],
    }
    live = {"can0": {"link_up": True, "state": "BUS-OFF", "errors_rx": 0, "errors_tx": 255}}
    term = board_topology._can_termination(result, live)
    err = next(f for f in term["findings"] if f["code"] == "bus_error")
    assert err["level"] == "error"
    assert err["interface"] == "can0" and err["state"] == "BUS-OFF"
    # the adapter node carries the live state for the UI to show
    adapter = next(n for n in term["nodes"] if n["role"] == "adapter")
    assert adapter["live_state"] == "BUS-OFF" and adapter["errors_tx"] == 255


def test_live_fields_survive_topology_schema_roundtrip(monkeypatch: Any) -> None:
    """The Topology response_model must NOT strip the live-state fields: the GET /api/topology route
    re-validates + re-serializes through Topology, so the schema has to declare live_state /
    errors_rx / errors_tx on nodes and interface / state on findings, or the live-CAN-health feature
    silently disappears from the API payload."""
    monkeypatch.setattr(reference_data, "board_by_id", lambda i: None)
    result = {
        "mcus": [{"name": "toolhead", "connection": "canbus", "board_id": "ebb"}],
        "can_buses": [{"interface": "can0", "board_id": "u2c"}],
    }
    live = {"can0": {"link_up": True, "state": "BUS-OFF", "errors_rx": 3, "errors_tx": 255}}
    term = board_topology._can_termination(result, live)
    dumped = Topology.model_validate({"can_termination": term}).model_dump()["can_termination"]
    adapter = next(n for n in dumped["nodes"] if n["role"] == "adapter")
    assert adapter["live_state"] == "BUS-OFF"
    assert adapter["errors_rx"] == 3 and adapter["errors_tx"] == 255
    err = next(f for f in dumped["findings"] if f["code"] == "bus_error")
    assert err["interface"] == "can0" and err["state"] == "BUS-OFF" and err["level"] == "error"


def test_live_high_error_counters_warn(monkeypatch: Any) -> None:
    """Elevated error counters on an error-active bus surface as a warning, not an error."""
    monkeypatch.setattr(reference_data, "board_by_id", lambda i: None)
    result = {
        "mcus": [{"name": "toolhead", "connection": "canbus", "board_id": "ebb"}],
        "can_buses": [{"interface": "can0", "board_id": "u2c"}],
    }
    live = {"can0": {"link_up": True, "state": "ERROR-ACTIVE", "errors_rx": 120, "errors_tx": 4}}
    term = board_topology._can_termination(result, live)
    err = next(f for f in term["findings"] if f["code"] == "bus_error")
    assert err["level"] == "warning" and err["interface"] == "can0"


def test_live_healthy_bus_has_no_error_finding(monkeypatch: Any) -> None:
    monkeypatch.setattr(reference_data, "board_by_id", lambda i: None)
    result = {
        "mcus": [{"name": "toolhead", "connection": "canbus", "board_id": "ebb"}],
        "can_buses": [{"interface": "can0", "board_id": "u2c"}],
    }
    live = {"can0": {"link_up": True, "state": "ERROR-ACTIVE", "errors_rx": 0, "errors_tx": 0}}
    term = board_topology._can_termination(result, live)
    assert not any(f["code"] == "bus_error" for f in term["findings"])
    # a down interface is not flagged (it isn't carrying the bus)
    down = {"can0": {"link_up": False, "state": "BUS-OFF"}}
    term2 = board_topology._can_termination(result, down)
    assert not any(f["code"] == "bus_error" for f in term2["findings"])
