"""Tests for the canonical board catalog entities (aggregated ports) + /boards routes."""

from __future__ import annotations

from typing import Any

from app.services import board_search, reference_data

BOARDS: list[dict[str, Any]] = [
    {
        "board_id": "btt-octopus",
        "manufacturer": "BigTreeTech",
        "model": "Octopus",
        "display_name": "BigTreeTech Octopus",
        "boardClass": "mainboard",
        "specs": {"MCU": "STM32F446"},
        "ports": [{"label": "MOTOR1", "category": "motor", "count": 1}],
        "portsSummary": {"motor": 1},
        "linkStatus": "exact",
        "aliases": ["Octopus / Pro"],
    },
    {
        "board_id": "ebb36",
        "manufacturer": "BigTreeTech",
        "model": "EBB36",
        "display_name": "BigTreeTech EBB36",
        "boardClass": "toolhead",
        "specs": {},
        "ports": [],
        "portsSummary": {},
        "linkStatus": "spec-only",
        "aliases": [],
    },
]


def test_board_search_summaries_omit_ports() -> None:
    out = board_search.search(BOARDS, limit=10)
    assert out["total"] == 2
    assert "ports" not in out["boards"][0]  # summaries are lightweight
    assert out["boards"][0]["portCount"] == 1


def test_board_search_filters() -> None:
    assert board_search.search(BOARDS, board_class="toolhead")["total"] == 1
    assert board_search.search(BOARDS, q="octopus")["total"] == 1
    assert board_search.search(BOARDS, q="octopus / pro")["total"] == 1  # alias match
    assert board_search.search(BOARDS, manufacturer="bigtreetech")["total"] == 2


# ── shipped dataset ───────────────────────────────────────────────────────────
def test_boards_dataset_aggregated_and_lossless() -> None:
    boards = reference_data.boards()
    assert len(boards) > 100, "boards entity should be built from MCU & Boards"
    ids = [b["board_id"] for b in boards]
    assert all(ids), "every board has a board_id"
    assert len(ids) == len(set(ids)), "board_id collisions"
    # Lossless: aggregated port counts equal the original flat port-row count.
    items = reference_data.hardware_items()
    flat_port_rows = sum(
        1
        for i in items
        if i.get("category") == "MCU & Boards"
        and str(i.get("subsection", "")).startswith("Board connectors")
    )
    agg = sum(p.get("count", 1) for b in boards for p in b.get("ports", []))
    assert agg == flat_port_rows, f"port aggregation not lossless: {agg} != {flat_port_rows}"
    with_ports = [b for b in boards if b.get("ports")]
    assert with_ports, "some boards must own ports[]"
    cats = {p["category"] for b in with_ports for p in b["ports"]}
    assert {"motor", "fan", "thermistor"} <= cats


def test_route_boards_list_and_detail() -> None:
    from fastapi.testclient import TestClient

    from app.main import create_app

    client = TestClient(create_app())
    lst = client.get("/api/hardware/boards", params={"limit": 5})
    assert lst.status_code == 200
    body = lst.json()
    assert body["total"] > 100
    assert body["count"] == 5
    assert "ports" not in body["boards"][0]

    bid = body["boards"][0]["board_id"]
    detail = client.get(f"/api/hardware/boards/{bid}")
    assert detail.status_code == 200
    assert detail.json()["board_id"] == bid
    assert "ports" in detail.json()

    assert client.get("/api/hardware/boards/__nope__").status_code == 404
