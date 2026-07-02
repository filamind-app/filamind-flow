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

    # Both: containment 1.0, jaccard 8/20=0.4 (< floor), margin 0 -> ambiguous -> no single
    # match, but the tie comes back as an honest candidates shortlist.
    no_id, no_conf, tied = bt._fingerprint_board(used, [toolhead, mainboard])
    assert (no_id, no_conf) == (None, 0.0)
    assert set(tied) == {"ebb-sb2209", "big-main"}

    # CAN narrowing leaves only the toolhead; a single confident candidate now resolves.
    narrowed = bt._narrow_by_connection([toolhead, mainboard], "canbus")
    board_id, conf, _cands = bt._fingerprint_board(used, narrowed)
    assert board_id == "ebb-sb2209" and conf > 0.0


def test_usb_mcu_not_narrowed() -> None:
    """A USB MCU keeps the full same-chip candidate set (no toolhead bias)."""
    used = {f"PA{i}" for i in range(8)}
    toolhead = _board("ebb", "CAN Toolhead", [*used, *(f"PB{i}" for i in range(12))])
    mainboard = _board("main", "Mainboard", [*used, *(f"PC{i}" for i in range(12))])
    assert bt._narrow_by_connection([toolhead, mainboard], "usb") == [toolhead, mainboard]


def test_fingerprint_pool_excludes_pseudo_boards() -> None:
    """Printer presets duplicate their real mainboard's pin-map and host entries aren't MCU
    boards - both must never be fingerprint candidates (they zero the ambiguity margin and let a
    real match lose to catalog order)."""
    main = _board("octopus", "Mainboard", [f"PA{i}" for i in range(12)])
    preset = _board("voron-24-preset", "printer-preset", [f"PA{i}" for i in range(12)])
    host = _board("pi4", "host", [f"PA{i}" for i in range(12)])
    pool = bt._fingerprint_candidates([main, preset, host], None, "usb")
    assert pool == [main]


def test_fingerprint_toolhead_floor_allows_sparse_pinmaps() -> None:
    """Toolhead boards legitimately document only 6-9 pins (EBB36 class) - the fingerprint floor
    must not exclude exactly the boards whose only board-level signal is the fingerprint."""
    used = {"PA1", "PA5", "PB6", "PB8", "PB9", "PB10"}
    ebb = _board("ebb36", "CAN Toolhead", sorted(used))  # 6-pin map: below the old floor of 10
    board_id, conf, _ = bt._fingerprint_board(used, [ebb])
    assert board_id == "ebb36" and conf > 0.9


def test_resolve_board_id_matches_section_name_against_aliases() -> None:
    """`[mcu ebb36]` must resolve against catalog names/aliases even with no matchPatterns hit -
    a unique name is a suggestion; several same-name variants are an honest shortlist."""
    boards = [
        {"board_id": "ebb36-v1", "display_name": "BTT EBB36 v1.1", "aliases": ["EBB36"]},
        {"board_id": "ebb36-v2", "display_name": "BTT EBB36 v1.2", "aliases": ["EBB36"]},
        {"board_id": "octopus", "display_name": "BTT Octopus", "aliases": []},
    ]
    # two variants share the name -> no silent pick, both surfaced as candidates
    bid, conf, cands = bt._resolve_board_id(None, "can-uuid-reveals-nothing", boards, "ebb36")
    assert bid is None and conf == 0.0
    assert set(cands) == {"ebb36-v1", "ebb36-v2"}
    # a unique name hit resolves as a suggestion
    bid, conf, cands = bt._resolve_board_id(None, "sig", boards[1:], "ebb36")
    assert bid == "ebb36-v2" and conf > 0.0 and cands == []
    # nothing matches -> truly unknown, no invented candidates
    bid, conf, cands = bt._resolve_board_id(None, "sig", boards, "toolboard9")
    assert bid is None and cands == []
