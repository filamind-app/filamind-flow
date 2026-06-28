"""T1b: connection-aware narrowing of same-chip fingerprint candidates (tricky CAN toolheads)."""

from __future__ import annotations

from typing import Any

from app.services import board_topology as bt


def _board(board_id: str, board_class: str, pins: list[str]) -> dict[str, Any]:
    return {
        "board_id": board_id,
        "boardClass": board_class,
        "ports": [{"pinMap": [{"pin": p} for p in pins]}],
    }


def test_board_role() -> None:
    assert bt._board_role({"boardClass": "CAN Toolhead"}) == "toolhead"
    assert bt._board_role({"boardClass": "Mainboard"}) == "mainboard"
    assert bt._board_role({"boardClass": "Control Board"}) == "mainboard"
    assert bt._board_role({"boardClass": "Stepper Driver"}) is None
    assert bt._board_role({}) is None


def test_narrow_by_connection() -> None:
    th = _board("ebb", "CAN Toolhead", [])
    mb = _board("octopus", "Mainboard", [])
    # CAN -> prefer toolhead-class boards
    assert bt._narrow_by_connection([th, mb], "canbus") == [th]
    # non-CAN connections are left untouched (a USB toolhead must still be considered)
    assert bt._narrow_by_connection([th, mb], "usb") == [th, mb]
    # no toolhead among candidates -> fall back to the full set (never over-narrow to nothing)
    assert bt._narrow_by_connection([mb], "canbus") == [mb]


def test_connection_narrowing_disambiguates_can_toolhead() -> None:
    """A CAN toolhead's few generic pins are contained in BOTH a same-chip toolhead and a same-chip
    mainboard, so the guard rejects the ambiguous full-catalog match. Narrowing to the toolhead by
    the CAN connection then resolves it confidently - without loosening the guard."""
    used = {f"PA{i}" for i in range(8)}  # 8 generic pins, all on both boards
    toolhead = _board("ebb-sb2209", "CAN Toolhead", [*used, *(f"PB{i}" for i in range(12))])
    mainboard = _board("big-main", "Mainboard", [*used, *(f"PC{i}" for i in range(12))])

    # Both: containment 1.0, jaccard 8/20=0.4 (< floor), margin 0 -> ambiguous -> no match.
    assert bt._fingerprint_board(used, [toolhead, mainboard]) == (None, 0.0)

    # CAN narrowing leaves only the toolhead; a single confident candidate now resolves.
    narrowed = bt._narrow_by_connection([toolhead, mainboard], "canbus")
    board_id, conf = bt._fingerprint_board(used, narrowed)
    assert board_id == "ebb-sb2209" and conf > 0.0


def test_usb_mcu_not_narrowed() -> None:
    """A USB MCU keeps the full same-chip candidate set (no toolhead bias)."""
    used = {f"PA{i}" for i in range(8)}
    toolhead = _board("ebb", "CAN Toolhead", [*used, *(f"PB{i}" for i in range(12))])
    mainboard = _board("main", "Mainboard", [*used, *(f"PC{i}" for i in range(12))])
    assert bt._narrow_by_connection([toolhead, mainboard], "usb") == [toolhead, mainboard]
