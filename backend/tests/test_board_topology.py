"""Tests for board/MCU topology detection (pure analysis + the read-only route)."""

from __future__ import annotations

from typing import Any

from app.services import board_topology, reference_data

PATTERNS: dict[str, Any] = {
    "board_patterns": [{"pattern": "bigtreetech|btt", "board": "BigTreeTech", "confidence": 0.6}],
    "mcu_patterns": [
        {"pattern": "stm32f103", "mcu": "STM32F103"},
        {"pattern": "stm32f446", "mcu": "STM32F446"},
    ],
}

SECTIONS: dict[str, Any] = {
    "mcu": {
        "serial": "/dev/serial/by-id/usb-Klipper_stm32f103xe_ABC-if00",
        "restart_method": "command",
    },
    "mcu toolhead_mcu": {"serial": "/dev/serial/by-id/usb-Klipper_stm32f103xe_DEF-if00"},
    "stepper_x": {"step_pin": "PE2"},
    "mcu can0": {"canbus_uuid": "11223344556677"},
}


def test_analyze_detects_mcus_primary_first() -> None:
    out = board_topology.analyze(SECTIONS, PATTERNS)
    assert out["mcu_count"] == 3
    names = [m["name"] for m in out["mcus"]]
    assert names[0] == "mcu"  # primary first
    assert set(names) == {"mcu", "toolhead_mcu", "can0"}
    assert out["host"] == {"name": "host", "role": "sbc"}


def test_analyze_connection_types_and_chip() -> None:
    by_name = {m["name"]: m for m in board_topology.analyze(SECTIONS, PATTERNS)["mcus"]}
    assert by_name["mcu"]["connection"] == "usb"
    assert by_name["mcu"]["mcu"] == "STM32F103"  # matched from the serial
    assert by_name["can0"]["connection"] == "canbus"
    assert by_name["can0"]["identifier"] == "11223344556677"


def test_analyze_board_guess() -> None:
    sections = {"mcu": {"serial": "/dev/serial/by-id/usb-btt_octopus_v1-if00"}}
    out = board_topology.analyze(sections, PATTERNS)
    assert out["mcus"][0]["board"] == "BigTreeTech"
    assert out["mcus"][0]["confidence"] == 0.6


def test_analyze_resolves_board_id_from_matchpatterns() -> None:
    """Phase 8: the connection signature is matched against the catalog boards'
    folded matchPatterns to emit a board_id link (a *suggested* match)."""
    catalog = [
        {
            "board_id": "btt-octopus",
            "model": "Octopus",
            "display_name": "BigTreeTech Octopus",
            "aliases": [],
            "matchPatterns": [{"pattern": "octopus", "confidence": 0.6}],
        }
    ]
    sections = {"mcu": {"serial": "/dev/serial/by-id/usb-btt_octopus_v1-if00"}}
    m = board_topology.analyze(sections, PATTERNS, boards=catalog)["mcus"][0]
    assert m["board_id"] == "btt-octopus"
    assert m["board_match"] == "suggested"
    assert m["board_match_confidence"] == 0.6


def test_analyze_board_id_null_when_chip_only() -> None:
    """A chip-only signature (no board hint) yields no board_id — never a false match."""
    catalog = [
        {"board_id": "btt-octopus", "model": "Octopus", "matchPatterns": [{"pattern": "octopus"}]}
    ]
    sections = {"mcu": {"serial": "/dev/serial/by-id/usb-Klipper_stm32f103_X-if00"}}
    m = board_topology.analyze(sections, PATTERNS, boards=catalog)["mcus"][0]
    assert m["board_id"] is None
    assert m["board_match"] is None


def test_analyze_uart_and_unknown() -> None:
    sections = {
        "mcu a": {"serial": "/dev/ttyAMA0"},  # not usb -> uart
        "mcu b": {"baud": 250000},  # baud only -> uart
        "mcu c": {},  # nothing -> unknown
    }
    by_name = {m["name"]: m for m in board_topology.analyze(sections, PATTERNS)["mcus"]}
    assert by_name["a"]["connection"] == "uart"
    assert by_name["b"]["connection"] == "uart"
    assert by_name["c"]["connection"] == "unknown"


def test_analyze_ignores_non_mcu_and_bad_input() -> None:
    assert board_topology.analyze({"stepper_x": {"step_pin": "PE2"}}, PATTERNS)["mcu_count"] == 0
    assert board_topology.analyze({}, PATTERNS)["mcu_count"] == 0
    assert board_topology.analyze("nope", PATTERNS)["mcu_count"] == 0  # type: ignore[arg-type]


def test_analyze_with_real_reference_data() -> None:
    # Uses the shipped board_patterns.json — just assert it runs and returns the right shape.
    out = board_topology.analyze(SECTIONS, reference_data.board_patterns())
    assert out["mcu_count"] == 3
    assert all("connection" in m for m in out["mcus"])


def test_sections_helper() -> None:
    assert board_topology._sections({"settings": {"mcu": {}}}) == {"mcu": {}}
    assert board_topology._sections({"config": {"mcu": {}}}) == {"mcu": {}}
    assert board_topology._sections(None) == {}


# ── route ────────────────────────────────────────────────────────────────────
def test_route_topology_unreachable() -> None:
    from fastapi.testclient import TestClient

    from app.config import Settings, get_settings
    from app.main import create_app

    app = create_app()
    app.dependency_overrides[get_settings] = lambda: Settings(moonraker_url="http://127.0.0.1:1")
    resp = TestClient(app).get("/api/topology")
    assert resp.status_code == 200
    assert resp.json()["reachable"] is False


def test_route_topology_ok(monkeypatch: Any) -> None:
    from fastapi.testclient import TestClient

    from app.main import create_app

    async def fake_gather(_client: Any) -> dict[str, Any]:
        return {
            "reachable": True,
            "host": {"name": "host"},
            "mcus": [{"name": "mcu"}],
            "mcu_count": 1,
        }

    monkeypatch.setattr(board_topology, "gather_topology", fake_gather)
    resp = TestClient(create_app()).get("/api/topology")
    assert resp.status_code == 200
    assert resp.json()["mcu_count"] == 1
