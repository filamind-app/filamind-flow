"""Tests for manual topology additions (store CRUD + merge into the topology)."""

from __future__ import annotations

import pytest

from app.services import board_topology, manual_additions


def test_store_add_update_remove(tmp_path: object) -> None:
    d = str(tmp_path)
    # add an MCU
    eid, store = manual_additions.add_or_update(
        d, {"kind": "mcu", "name": "toolhead", "board_id": "ebb36-v1", "connection": "canbus"}
    )
    assert eid in store and store[eid]["name"] == "toolhead"
    assert store[eid]["connection"] == "canbus"
    # update it (same id -> edit, not a new entry)
    _eid2, store = manual_additions.add_or_update(
        d, {"id": eid, "kind": "mcu", "name": "toolhead2"}
    )
    assert _eid2 == eid
    assert manual_additions.read_additions(d)[eid]["name"] == "toolhead2"
    assert len(manual_additions.read_additions(d)) == 1
    # remove
    manual_additions.remove(d, eid)
    assert manual_additions.read_additions(d) == {}
    # remove again is a no-op
    manual_additions.remove(d, eid)


def test_store_validates_required_fields(tmp_path: object) -> None:
    d = str(tmp_path)
    with pytest.raises(ValueError):
        manual_additions.add_or_update(d, {"kind": "mcu"})  # no name
    with pytest.raises(ValueError):
        manual_additions.add_or_update(d, {"kind": "canbus"})  # no interface
    with pytest.raises(ValueError):
        manual_additions.add_or_update(d, {"kind": "bogus", "name": "x"})  # bad kind
    # unknown connection falls back to "unknown"
    _eid, store = manual_additions.add_or_update(
        d, {"kind": "mcu", "name": "m", "connection": "weird"}
    )
    assert next(iter(store.values()))["connection"] == "unknown"


def test_apply_manual_additions_merges_nodes() -> None:
    result = {
        "host": {"name": "host", "role": "sbc", "displays": []},
        "mcus": [{"name": "mcu", "connection": "usb"}],
        "can_buses": [],
        "mcu_count": 1,
    }
    additions = {
        "manual-a": {"kind": "mcu", "name": "toolhead", "board_id": "ebb", "connection": "canbus"},
        "manual-b": {"kind": "canbus", "interface": "can0", "board_id": "u2c-all"},
        "manual-c": {"kind": "display", "name": "KNOMI2", "display_kind": "knomi"},
    }
    board_topology.apply_manual_additions(result, additions)

    th = next(m for m in result["mcus"] if m["name"] == "toolhead")
    assert th["manual_id"] == "manual-a"
    assert th["board_id"] == "ebb" and th["board_match"] == "confirmed"
    bus = next(b for b in result["can_buses"] if b["interface"] == "can0")
    assert bus["manual_id"] == "manual-b" and bus["board_match"] == "confirmed"
    disp = next(d for d in result["host"]["displays"] if d["name"] == "KNOMI2")
    assert disp["manual_id"] == "manual-c" and disp["kind"] == "knomi"
    # primary mcu stays first after re-sort
    assert result["mcus"][0]["name"] == "mcu"


def test_apply_manual_additions_skips_duplicates() -> None:
    result = {
        "host": {"name": "host", "role": "sbc", "displays": [{"kind": "touch", "name": "KS"}]},
        "mcus": [{"name": "mcu", "connection": "usb"}],
        "can_buses": [{"interface": "can0", "driver": "gs_usb"}],
    }
    additions = {
        "x": {"kind": "mcu", "name": "mcu"},  # collides with detected mcu -> skipped
        "y": {"kind": "canbus", "interface": "can0"},  # collides -> skipped
        "z": {"kind": "display", "display_kind": "touch", "name": "KS"},  # collides -> skipped
    }
    board_topology.apply_manual_additions(result, additions)
    assert len(result["mcus"]) == 1
    assert len(result["can_buses"]) == 1
    assert len(result["host"]["displays"]) == 1
