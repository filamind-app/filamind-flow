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
    # Lossless applies to ports AGGREGATED from the flat rows — hardware-verified
    # boards (e.g. SV08, mapped from the printer's own config) add their own ports.
    agg = sum(
        p.get("count", 1)
        for b in boards
        if not b.get("verified_on_hardware")
        for p in b.get("ports", [])
    )
    assert agg == flat_port_rows, f"port aggregation not lossless: {agg} != {flat_port_rows}"
    with_ports = [b for b in boards if b.get("ports")]
    assert with_ports, "some boards must own ports[]"
    cats = {p["category"] for b in with_ports for p in b["ports"]}
    assert {"motor", "fan", "thermistor"} <= cats


def test_sv08_fully_ingested() -> None:
    """Gold proof: the printer under test (Sovol SV08) is fully in the catalog —
    mainboard + toolhead, verified against the unit's own printer.cfg."""
    boards = reference_data.boards()
    main = reference_data.board_by_id("sovol-sv08")
    tool = reference_data.board_by_id("sovol-sv08-toolhead")
    assert main and tool, "SV08 mainboard + toolhead must both exist"
    assert main["manufacturer"] == "Sovol"
    assert main.get("verified_on_hardware") and tool.get("verified_on_hardware")
    # mainboard drives X, Y and 4 Z steppers (quad-gantry CoreXY)
    main_motors = [p for p in main["ports"] if p["category"] == "motor"]
    assert len(main_motors) == 6, "SV08 mainboard has X, Y + 4 Z motors"
    # every mainboard motor records its real Klipper step pin
    assert all("step" in str(p.get("pins", "")).lower() for p in main_motors)
    # toolhead carries the extruder + hotend + probe + accelerometer
    tool_cats = {p["category"] for p in tool["ports"]}
    assert {"motor", "heater-hotend", "probe", "accelerometer"} <= tool_cats
    _ = boards


def test_sv08_data_is_usable_not_just_viewable() -> None:
    """The board data must be machine/human-usable: every port has a usage hint + the
    Klipper config key, motors carry a structured pin map (role/invert/pull-up), and the
    board ships config-affecting electronics + a copy-ready config snippet."""
    main = reference_data.board_by_id("sovol-sv08")
    assert main is not None
    # every port: usage hint + the Klipper key it feeds
    for p in main["ports"]:
        assert p.get("hint"), f"{p['label']} has no usage hint"
        assert "configKey" in p
    # motors expose a structured pin map with roles + invert/pull-up flags
    mx = next(p for p in main["ports"] if p["label"] == "Motor X")
    keys = {pm["configKey"] for pm in mx["pinMap"]}
    assert {"step_pin", "dir_pin", "enable_pin", "uart_pin"} <= keys
    assert any(pm["invert"] for pm in mx["pinMap"])  # dir/enable inverted
    # electronics that affect config decisions (SSR bed, PT1000 pull-up, etc.)
    assert main.get("electronics") and "Bed heating" in main["electronics"]
    assert main.get("configNotes") and main.get("configSnippet")
    assert "PT1000" in reference_data.board_by_id("sovol-sv08-toolhead")["electronics"].get(
        "Hotend sensor", ""
    )


def test_every_board_port_has_usage_hint() -> None:
    """Usability floor: every port on every board tells you how to use it in printer.cfg."""
    boards = reference_data.boards()
    missing = [
        (b["board_id"], p.get("label"))
        for b in boards
        for p in b.get("ports", [])
        if not p.get("hint") or not p.get("configKey")
    ]
    assert not missing, f"{len(missing)} ports lack a usage hint/configKey, e.g. {missing[:5]}"


def test_boards_enriched_media_links_are_safe() -> None:
    """Phase 5+6: some boards carry enriched specs + link-only media. Any media URL
    must be a real http(s) link (never a fabricated/relative path)."""
    boards = reference_data.boards()
    with_media = [b for b in boards if b.get("media")]
    assert with_media, "some boards should have enriched media links"
    url_keys = (
        "productUrl",
        "repoUrl",
        "wikiUrl",
        "imageUrl",
        "pinoutUrl",
        "schematicUrl",
        "datasheetUrl",
    )
    for b in with_media:
        for k in url_keys:
            v = b["media"].get(k)
            if v:
                assert v.startswith(("http://", "https://")), f"{b['board_id']}.{k} not a URL"


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
