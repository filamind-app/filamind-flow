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
    # Uses the catalog-derived patterns — just assert it runs and returns the right shape.
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

    async def fake_gather(_client: Any, _data_dir: str = "") -> dict[str, Any]:
        return {
            "reachable": True,
            "host": {"name": "host", "role": "sbc"},
            "mcus": [{"name": "mcu", "connection": "usb"}],
            "mcu_count": 1,
        }

    monkeypatch.setattr(board_topology, "gather_topology", fake_gather)
    resp = TestClient(create_app()).get("/api/topology")
    assert resp.status_code == 200
    assert resp.json()["mcu_count"] == 1


def test_analyze_attaches_components_to_primary_mcu() -> None:
    """Phase P3: a component is attached to the MCU named by its primary pin's chip prefix."""
    by_name = {m["name"]: m for m in board_topology.analyze(SECTIONS, PATTERNS)["mcus"]}
    # stepper_x has a bare step_pin (PE2) -> lives on the primary mcu, classified as a motor.
    assert {"section": "stepper_x", "kind": "motor"} in by_name["mcu"]["components"]


def test_analyze_component_edges_across_mcus() -> None:
    """A CAN toolhead's components (chip-prefixed pins) attach to the CAN MCU, not the primary."""
    sections = {
        "mcu": {"serial": "/dev/serial/by-id/usb-Klipper_stm32f446_X-if00"},
        "mcu EBBCan": {"canbus_uuid": "aabbccddeeff"},
        "stepper_x": {"step_pin": "PE2", "dir_pin": "PE3"},
        "tmc2209 stepper_x": {"uart_pin": "PE1"},
        "extruder": {"step_pin": "EBBCan: PD0", "heater_pin": "EBBCan: PB13"},
        "heater_bed": {"heater_pin": "PA1"},
        "fan": {"pin": "PA2"},
        "adxl345": {"cs_pin": "EBBCan: PB12"},
    }
    by_name = {m["name"]: m for m in board_topology.analyze(sections, PATTERNS)["mcus"]}
    main = {c["section"] for c in by_name["mcu"]["components"]}
    ebb = {c["section"] for c in by_name["EBBCan"]["components"]}
    assert {"stepper_x", "tmc2209 stepper_x", "heater_bed", "fan"} <= main
    assert {"extruder", "adxl345"} <= ebb  # CAN-toolhead components attach to EBBCan
    kinds = {c["section"]: c["kind"] for m in by_name.values() for c in m["components"]}
    assert kinds["tmc2209 stepper_x"] == "driver"
    assert kinds["adxl345"] == "sensor"
    assert kinds["fan"] == "fan"


def test_analyze_never_invents_phantom_mcu() -> None:
    """A component pin referencing an undeclared chip is dropped — never turned into an MCU node."""
    sections = {"mcu": {"serial": "x"}, "stepper_x": {"step_pin": "ghost: PA1"}}
    out = board_topology.analyze(sections, PATTERNS)
    assert out["mcu_count"] == 1
    assert all(c["section"] != "stepper_x" for c in out["mcus"][0]["components"])


def test_analyze_joins_chip_to_db_mcu_entity() -> None:
    """Phase P4: the detected chip resolves to a canonical DB MCU entity (mcu_id + family)."""
    by_name = {m["name"]: m for m in board_topology.analyze(SECTIONS, PATTERNS)["mcus"]}
    # SECTIONS' primary mcu is an stm32f103 (from its serial) — a real DB MCU entity.
    assert by_name["mcu"]["mcu_id"] == "stm32f103"
    assert by_name["mcu"]["mcu_family"] == "STM32F1"


def test_host_node_links_to_catalog_host() -> None:
    """Phase P5: the host's CPU/SoC string links to a catalog host entity (best-effort)."""
    hosts = [
        {"host_id": "btt-cb1", "name": "BIGTREETECH CB1", "soc": "Allwinner H616", "cpu": "A53"},
        {"host_id": "rpi4", "name": "Raspberry Pi 4", "soc": "BCM2711", "cpu": "A72"},
    ]
    node = board_topology.host_node(
        {"cpu_info": {"model": "Allwinner H616 (4x Cortex-A53)"}}, hosts
    )
    assert node["host_id"] == "btt-cb1"
    assert node["host_match"] == "suggested"
    assert node["role"] == "sbc"
    # many SBCs leave cpu_info empty and put the board string in distribution.name (real CB1 shape)
    via_distro = board_topology.host_node(
        {"cpu_info": {"model": ""}, "distribution": {"name": "BIGTREETECH-CB1 3.1.0-trunk trixie"}},
        hosts,
    )
    assert via_distro["host_id"] == "btt-cb1"
    assert via_distro["name"].startswith("BIGTREETECH-CB1")
    # no system info -> graceful stub, no link
    stub = board_topology.host_node({}, hosts)
    assert stub["host_id"] is None and stub["name"] == "host"


def test_analyze_fingerprints_board_from_pins() -> None:
    """Phase P8: when the serial reveals only the chip, the printer's used pin set is matched
    against each board's verbatim pin-map (containment) to resolve a board_id."""
    board = {
        "board_id": "acme-x",
        "model": "X",
        "ports": [
            {
                "pinMap": [
                    {"pin": p}
                    for p in (
                        "PE2",
                        "PE3",
                        "PE4",
                        "PB0",
                        "PB1",
                        "PB2",
                        "PA0",
                        "PA1",
                        "PA2",
                        "PD5",
                        "PD6",
                        "PD7",
                    )
                ]
            }
        ],
    }
    sections = {
        "mcu": {"serial": "/dev/ttyUSB0"},  # signature reveals no board
        "stepper_x": {"step_pin": "PE2", "dir_pin": "PE3", "enable_pin": "PE4"},
        "stepper_y": {"step_pin": "PB0", "dir_pin": "PB1", "enable_pin": "PB2"},
        "heater_bed": {"heater_pin": "PA0"},
        "extruder": {"step_pin": "PA1", "heater_pin": "PA2"},
    }
    m = board_topology.analyze(sections, PATTERNS, boards=[board])["mcus"][0]
    assert m["board_id"] == "acme-x"
    assert m["board_match"] == "suggested"
    assert m["board_match_confidence"] >= 0.6


def _board(board_id: str, pins: list[str]) -> dict[str, Any]:
    return {"board_id": board_id, "ports": [{"pinMap": [{"pin": p} for p in pins]}]}


def test_fingerprint_suppresses_ambiguous_sparse_match() -> None:
    """A toolhead-like MCU with only a few *generic* pins that several small boards share equally
    (a tie in containment, low Jaccard) must NOT yield a confident board — better no match than a
    wrong one. Reproduces the real SV08 CAN-toolhead case (its board isn't in the catalog)."""
    used = {"PA1", "PA5", "PA6", "PA8", "PB6", "PB8", "PB9", "PB10"}
    # Two distinct boards each contain the SAME 6 of the 8 used pins plus their own filler pins,
    # so both tie at containment 6/8 = 0.75 with a low Jaccard (6/22 ≈ 0.27) → ambiguous.
    shared = ["PA1", "PA5", "PA6", "PA8", "PB6", "PB8"]
    board_a = _board("small-a", shared + [f"A{i}" for i in range(14)])
    board_b = _board("small-b", shared + [f"B{i}" for i in range(14)])
    assert board_topology._fingerprint_board(used, [board_a, board_b]) == (None, 0.0)
    # But a single clear winner with a fitting pin-map (high Jaccard) is still accepted.
    fit = _board("fit-x", sorted(used | {"PC0", "PC1"}))
    board_id, conf = board_topology._fingerprint_board(used, [fit, board_a])
    assert board_id == "fit-x" and conf >= 0.6


# ── per-MCU board overrides (the only write path) ────────────────────────────
def test_apply_overrides_confirms_chosen_board() -> None:
    """A saved override replaces the auto suggestion: chosen board wins, match=confirmed."""
    result = {
        "mcus": [
            {"name": "mcu", "board_id": "auto-guess", "board_match": "suggested"},
            {"name": "toolhead_mcu", "board_id": None, "board_match": None},
            {"name": "other", "board_id": "x", "board_match": "suggested"},
        ]
    }
    overrides = {
        "mcu": {"board_id": "sovol-sv08"},
        "toolhead_mcu": {"board_id": "ebb36"},
    }
    board_topology.apply_overrides(result, overrides)
    by_name = {m["name"]: m for m in result["mcus"]}
    assert by_name["mcu"]["board_id"] == "sovol-sv08"
    assert by_name["mcu"]["board_match"] == "confirmed"
    assert by_name["mcu"]["board_match_confidence"] == 1.0
    # An override can set a board where there was no suggestion at all.
    assert by_name["toolhead_mcu"]["board_id"] == "ebb36"
    assert by_name["toolhead_mcu"]["board_match"] == "confirmed"
    # An MCU without an override is untouched.
    assert by_name["other"]["board_match"] == "suggested"


def test_overrides_store_roundtrip(tmp_path: Any) -> None:
    from app.services import topology_overrides

    data_dir = str(tmp_path)
    assert topology_overrides.read_overrides(data_dir) == {}
    topology_overrides.set_override(data_dir, "toolhead_mcu", "ebb36")
    saved = topology_overrides.read_overrides(data_dir)
    assert saved["toolhead_mcu"]["board_id"] == "ebb36" and saved["toolhead_mcu"]["at"]
    # Clearing removes just that entry.
    topology_overrides.set_override(data_dir, "mcu", "sovol-sv08")
    topology_overrides.clear_override(data_dir, "toolhead_mcu")
    after = topology_overrides.read_overrides(data_dir)
    assert "toolhead_mcu" not in after and after["mcu"]["board_id"] == "sovol-sv08"


def test_overrides_store_rejects_bad_input(tmp_path: Any) -> None:
    import pytest

    from app.services import topology_overrides

    with pytest.raises(ValueError):
        topology_overrides.set_override(str(tmp_path), "", "sovol-sv08")
    with pytest.raises(ValueError):
        topology_overrides.set_override(str(tmp_path), "mcu", "")


def test_route_override_sets_and_clears(monkeypatch: Any, tmp_path: Any) -> None:
    from fastapi.testclient import TestClient

    from app.config import Settings, get_settings
    from app.main import create_app
    from app.services import reference_data

    sections = {"mcu": {"serial": "/dev/serial/by-id/usb-Klipper_stm32f103xe_X-if00"}}

    async def fake_query(_self: Any, _objects: Any) -> dict[str, Any]:
        return {"configfile": {"settings": sections}}

    async def fake_sysinfo(_self: Any) -> dict[str, Any]:
        return {}

    monkeypatch.setattr("app.services.moonraker_client.MoonrakerClient.query_objects", fake_query)
    monkeypatch.setattr(
        "app.services.moonraker_client.MoonrakerClient.machine_system_info", fake_sysinfo
    )
    real_board_id = reference_data.boards()[0]["board_id"]

    app = create_app()
    app.dependency_overrides[get_settings] = lambda: Settings(data_dir=str(tmp_path))
    client = TestClient(app)

    # Unknown board id is rejected.
    assert (
        client.post(
            "/api/topology/override", json={"mcu_name": "mcu", "board_id": "nope"}
        ).status_code
        == 404
    )

    # Setting an override confirms the board on that MCU.
    resp = client.post(
        "/api/topology/override", json={"mcu_name": "mcu", "board_id": real_board_id}
    )
    assert resp.status_code == 200
    mcu = next(m for m in resp.json()["mcus"] if m["name"] == "mcu")
    assert mcu["board_id"] == real_board_id
    assert mcu["board_match"] == "confirmed"
    assert mcu["board_match_confidence"] == 1.0

    # Clearing reverts to the auto suggestion (no longer confirmed).
    resp = client.post("/api/topology/override/clear", json={"mcu_name": "mcu"})
    assert resp.status_code == 200
    mcu = next(m for m in resp.json()["mcus"] if m["name"] == "mcu")
    assert mcu["board_match"] != "confirmed"
