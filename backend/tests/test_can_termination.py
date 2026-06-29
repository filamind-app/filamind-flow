"""Tests for the CAN 120Ω termination advisory (board_topology._can_termination)."""

from __future__ import annotations

from typing import Any

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
