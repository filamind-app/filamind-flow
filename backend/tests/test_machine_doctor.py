"""Tests for the Machine Doctor aggregator (grading + degradation; analyzers are stubbed)."""

from __future__ import annotations

from typing import Any

import pytest

from app.config import Settings
from app.services import machine_doctor


def _stub_pillar_inputs(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stub the extra-pillar data sources to 'not measured' so a test isolates config integrity."""

    async def _fw_down(*_a: Any, **_k: Any) -> dict[str, Any]:
        return {"available": False, "mcus": []}

    async def _no_services(*_a: Any, **_k: Any) -> dict[str, Any]:
        return {"source": None, "units": []}

    monkeypatch.setattr(machine_doctor.overview, "_firmware_block", _fw_down)
    monkeypatch.setattr(machine_doctor, "_gather_services", _no_services)
    monkeypatch.setattr(
        machine_doctor.overview, "_tuning_block", lambda _d: {"available": True, "axes": []}
    )
    monkeypatch.setattr(machine_doctor.max_flow_store, "read_last", lambda _d: None)


@pytest.mark.parametrize(
    ("score", "grade"),
    [(100, "A"), (90, "A"), (80, "B"), (70, "C"), (50, "D"), (44, "F"), (0, "F")],
)
def test_grade_thresholds(score: float, grade: str) -> None:
    assert machine_doctor._grade(score) == grade


async def test_run_scan_grades_and_links(monkeypatch: pytest.MonkeyPatch) -> None:
    async def clean(*_a: Any, **_k: Any) -> dict[str, Any]:
        return {"status": "ok", "findings": []}

    async def pins(*_a: Any, **_k: Any) -> dict[str, Any]:
        return {
            "status": "ok",
            "findings": [
                machine_doctor._finding(
                    "pins.double_assign",
                    "error",
                    {"pin": "PA1", "mcu": "mcu"},
                    {"kind": "config_section", "value": "fan"},
                )
            ],
        }

    async def firmware(*_a: Any, **_k: Any) -> dict[str, Any]:
        return {
            "status": "ok",
            "findings": [
                machine_doctor._finding(
                    "firmware.out_of_sync",
                    "warning",
                    {"mcu": "toolhead_mcu"},
                    {"kind": "topology_node", "value": "toolhead_mcu"},
                )
            ],
        }

    monkeypatch.setattr(machine_doctor, "_scan_pins", pins)
    monkeypatch.setattr(machine_doctor, "_scan_firmware", firmware)
    for name in (
        "_scan_drivers",
        "_scan_drift",
        "_scan_project",
        "_scan_hardware",
        "_scan_install",
    ):
        monkeypatch.setattr(machine_doctor, name, clean)
    _stub_pillar_inputs(monkeypatch)

    report = await machine_doctor.run_scan(Settings())
    # Only config integrity is measured here → composite == config score.
    # 1 error (25) + 1 warning (8) → 67 → C.
    assert report["score"] == 67.0 and report["grade"] == "C"
    assert report["errors"] == 1 and report["warnings"] == 1
    by_key = {c["key"]: c for c in report["categories"]}
    assert by_key["pins"]["status"] == "fail"
    assert by_key["firmware"]["status"] == "warn"
    assert by_key["drivers"]["status"] == "ok"
    # Findings keep their deep links for the frontend.
    assert by_key["pins"]["findings"][0]["link"] == {"kind": "config_section", "value": "fan"}


async def test_pin_caveats_are_informational(monkeypatch: pytest.MonkeyPatch) -> None:
    # A board caveat describes by-design electronics (e.g. a mains-switched pin) - it must be
    # listed but never scored: a healthy printer full of caveat notes still grades A.
    async def doctor_out(*_a: Any, **_k: Any) -> dict[str, Any]:
        return {
            "reachable": True,
            "mcus": [
                {
                    "name": "mcu",
                    "findings": [
                        {"kind": "caveat", "pin": "PA0", "sections": ["heater_bed.heater_pin"]}
                    ],
                }
            ],
            "total": 1,
        }

    from app.services import board_topology

    monkeypatch.setattr(board_topology, "gather_pin_doctor", doctor_out)

    from app.services.moonraker_client import MoonrakerClient

    out = await machine_doctor._scan_pins(MoonrakerClient("http://x"), "")
    assert out["findings"][0]["level"] == "info"


async def test_firmware_out_of_sync_needs_a_host_version(monkeypatch: pytest.MonkeyPatch) -> None:
    # in_sync=False without a known host version is a meaningless comparison - no finding.
    async def status(*_a: Any, **_k: Any) -> dict[str, Any]:
        return {
            "reachable": True,
            "host": {"version": None, "state": "ready"},
            "mcus": [{"name": "mcu", "in_sync": False, "version": "v0.13.0"}],
        }

    from app.services import firmware_service

    monkeypatch.setattr(firmware_service, "gather_status", status)
    out = await machine_doctor._scan_firmware(Settings())
    assert out["findings"] == []


async def test_run_scan_degrades_a_crashing_analyzer(monkeypatch: pytest.MonkeyPatch) -> None:
    async def boom(*_a: Any, **_k: Any) -> dict[str, Any]:
        raise RuntimeError("analyzer exploded")

    async def clean(*_a: Any, **_k: Any) -> dict[str, Any]:
        return {"status": "ok", "findings": []}

    monkeypatch.setattr(machine_doctor, "_scan_pins", boom)
    for name in (
        "_scan_drivers",
        "_scan_drift",
        "_scan_project",
        "_scan_firmware",
        "_scan_hardware",
        "_scan_install",
    ):
        monkeypatch.setattr(machine_doctor, name, clean)
    _stub_pillar_inputs(monkeypatch)
    # A fully-set-up baseline (tuning + max flow done) so the setup-cap doesn't mask what this test
    # checks: that a crashing analyzer degrades to "unknown" and still grades A.
    monkeypatch.setattr(
        machine_doctor.overview,
        "_tuning_block",
        lambda _d: {"available": True, "axes": [{"axis": "x", "grade": "A"}]},
    )
    monkeypatch.setattr(
        machine_doctor.max_flow_store, "read_last", lambda _d: {"max_flow_mm3s": 24}
    )

    report = await machine_doctor.run_scan(Settings())
    by_key = {c["key"]: c for c in report["categories"]}
    # The crash becomes an honest "unknown", not a failed scan or a fake "all clear".
    assert by_key["pins"]["status"] == "unknown"
    assert report["grade"] == "A"  # nothing broken, nothing undone → not capped


def test_pillar_helpers() -> None:
    # firmware: needs a known host version + MCUs, else "not measured"
    assert machine_doctor._firmware_pillar({"available": False})[0] is None
    one_synced = {"available": True, "host_version": "v1", "mcus": [{}], "out_of_sync": 0}
    assert machine_doctor._firmware_pillar(one_synced)[0] == 100.0
    two_oos = {"available": True, "host_version": "v1", "mcus": [{}, {}], "out_of_sync": 2}
    assert machine_doctor._firmware_pillar(two_oos)[0] == pytest.approx(32.0)

    # services: fraction active, but a down CORE unit clamps to <= 40 even at a high fraction
    assert machine_doctor._services_pillar([])[0] is None
    half = [{"name": "webcamd", "active": True}, {"name": "crowsnest", "active": False}]
    assert machine_doctor._services_pillar(half)[0] == 50.0
    core_down = [
        {"name": "klipper", "active": False},
        {"name": "moonraker", "active": True},
        {"name": "webcamd", "active": True},
    ]
    assert machine_doctor._services_pillar(core_down)[0] == 40.0

    # tuning: mean of letter grades; none → not measured. reason distinguishes undone vs blocked.
    assert machine_doctor._tuning_pillar({"available": True, "axes": []}) == (
        None,
        {"axes": 0},
        "undone",
    )
    assert machine_doctor._tuning_pillar({"available": False, "axes": []})[2] == "blocked"
    two_axes = {"available": True, "axes": [{"grade": "A"}, {"grade": "C"}]}
    assert machine_doctor._tuning_pillar(two_axes)[0] == pytest.approx((95 + 72) / 2)
    assert machine_doctor._tuning_pillar(two_axes)[2] == "measured"

    # flow: a missing run reads as UNDONE (never run), not blocked.
    assert machine_doctor._flow_pillar(None) == (None, {}, "undone")
    rated = {"max_flow_mm3s": 24, "expected_max_flow_mm3s": 30}
    assert machine_doctor._flow_pillar(rated)[0] == 80.0
    assert machine_doctor._flow_pillar({"max_flow_mm3s": 24})[0] == 100.0

    # firmware / services with no data can't be judged now (blocked), not "undone".
    assert machine_doctor._firmware_pillar({"available": False})[2] == "blocked"
    assert machine_doctor._services_pillar([])[2] == "blocked"


async def test_run_scan_composites_pillars_and_assesses(monkeypatch: pytest.MonkeyPatch) -> None:
    async def clean(*_a: Any, **_k: Any) -> dict[str, Any]:
        return {"status": "ok", "findings": []}

    for name in (
        "_scan_pins",
        "_scan_drivers",
        "_scan_drift",
        "_scan_project",
        "_scan_firmware",
        "_scan_hardware",
        "_scan_install",
    ):
        monkeypatch.setattr(machine_doctor, name, clean)

    async def fw_down(*_a: Any, **_k: Any) -> dict[str, Any]:
        return {"available": False, "mcus": []}

    async def services(*_a: Any, **_k: Any) -> dict[str, Any]:
        # 2/3 active but a core unit (klipper) is down → pillar clamps to 40 (fail).
        return {
            "source": "moonraker",
            "units": [
                {"name": "klipper", "active": False},
                {"name": "moonraker", "active": True},
                {"name": "webcamd", "active": True},
            ],
        }

    monkeypatch.setattr(machine_doctor.overview, "_firmware_block", fw_down)
    monkeypatch.setattr(machine_doctor, "_gather_services", services)
    monkeypatch.setattr(
        machine_doctor.overview, "_tuning_block", lambda _d: {"available": True, "axes": []}
    )
    monkeypatch.setattr(machine_doctor.max_flow_store, "read_last", lambda _d: None)

    report = await machine_doctor.run_scan(Settings())
    pillars = {p["key"]: p for p in report["pillars"]}
    assert pillars["config"]["score"] == 100.0
    assert pillars["services"]["score"] == 40.0 and pillars["services"]["status"] == "fail"
    assert pillars["firmware"]["score"] is None  # not measured → excluded from the composite
    # The score IS the weighted-pillar blend shown in the Health breakdown, renormalized over the
    # two measured pillars: (0.45*100 + 0.15*40) / (0.45 + 0.15) = 51 / 0.6 = 85.0 → grade B. A
    # perfect config but a down Klipper service pulls the score below 100, matching the shown bars.
    assert report["score"] == pytest.approx(85.0)
    assert report["grade"] == "B"
    # undone tuning/flow stay out of the number but render as a "todo" bar (not "unknown").
    assert pillars["tuning"]["status"] == "todo" and pillars["flow"]["status"] == "todo"
    # a real fault (services fail) outranks undone setup in the verdict.
    assert report["assessment"]["code"] == "critical"
    assert report["assessment"]["params"]["pillar"] == "services"
    assert report["services"]["units"][0]["name"] == "klipper"


def test_cap_grade() -> None:
    cap = machine_doctor._cap_grade
    assert cap("A", 2, 0, 0) == ("B", "setup")  # undone setup → can't be A
    assert cap("A", 0, 0, 1) == ("B", "warnings")  # a warning → can't be A
    assert cap("A", 0, 1, 0) == ("C", "errors")  # an error → can't be A/B
    assert cap("A", 0, 0, 0) == ("A", None)  # clean → no cap
    assert cap("D", 2, 0, 0) == ("D", None)  # cap never RAISES a grade
    assert cap("B", 1, 0, 0) == ("B", None)  # already at the cap → no cap_reason


async def test_the_user_scenario(monkeypatch: pytest.MonkeyPatch) -> None:
    """config 92 (1 warning) + firmware 100 + services 91, input shaping + max flow NOT DONE: the
    number stays the honest measured blend (93.4) but the grade is held at B and the verdict names
    the undone steps - never a healthy A."""

    async def clean(*_a: Any, **_k: Any) -> dict[str, Any]:
        return {"status": "ok", "findings": []}

    async def drift_warn(*_a: Any, **_k: Any) -> dict[str, Any]:
        return {
            "status": "ok",
            "findings": [machine_doctor._finding("drift.changed", "warning", {}, None)],
        }

    for name in (
        "_scan_pins",
        "_scan_drivers",
        "_scan_project",
        "_scan_firmware",
        "_scan_hardware",
        "_scan_install",
    ):
        monkeypatch.setattr(machine_doctor, name, clean)
    monkeypatch.setattr(machine_doctor, "_scan_drift", drift_warn)

    async def fw_ok(*_a: Any, **_k: Any) -> dict[str, Any]:
        return {"available": True, "host_version": "v1", "mcus": [{}], "out_of_sync": 0}

    async def services(*_a: Any, **_k: Any) -> dict[str, Any]:
        return {
            "source": "moonraker",
            "units": [{"name": f"s{i}", "active": i > 0} for i in range(11)],  # 10/11 active = 90.9
        }

    monkeypatch.setattr(machine_doctor.overview, "_firmware_block", fw_ok)
    monkeypatch.setattr(machine_doctor, "_gather_services", services)
    monkeypatch.setattr(
        machine_doctor.overview, "_tuning_block", lambda _d: {"available": True, "axes": []}
    )
    monkeypatch.setattr(machine_doctor.max_flow_store, "read_last", lambda _d: None)

    report = await machine_doctor.run_scan(Settings())
    assert report["score"] == pytest.approx(93.4, abs=0.1)  # honest measured blend, unchanged
    assert report["grade"] == "B"  # held at B: setup unfinished
    assert report["cap_reason"] == "setup"
    assert report["assessment"]["code"] == "setup_incomplete"
    assert report["assessment"]["params"]["pillars"] == ["tuning", "flow"]
    assert report["setup"] == {"done": 0, "total": 2, "pending": ["tuning", "flow"]}


async def test_healthy_only_when_complete(monkeypatch: pytest.MonkeyPatch) -> None:
    """All pillars measured + zero findings → A, healthy. This is the ONLY path to 'healthy'."""

    async def clean(*_a: Any, **_k: Any) -> dict[str, Any]:
        return {"status": "ok", "findings": []}

    for name in (
        "_scan_pins",
        "_scan_drivers",
        "_scan_drift",
        "_scan_project",
        "_scan_firmware",
        "_scan_hardware",
        "_scan_install",
    ):
        monkeypatch.setattr(machine_doctor, name, clean)

    async def fw_ok(*_a: Any, **_k: Any) -> dict[str, Any]:
        return {"available": True, "host_version": "v1", "mcus": [{}], "out_of_sync": 0}

    async def services(*_a: Any, **_k: Any) -> dict[str, Any]:
        return {"source": "moonraker", "units": [{"name": "klipper", "active": True}]}

    monkeypatch.setattr(machine_doctor.overview, "_firmware_block", fw_ok)
    monkeypatch.setattr(machine_doctor, "_gather_services", services)
    monkeypatch.setattr(
        machine_doctor.overview,
        "_tuning_block",
        lambda _d: {"available": True, "axes": [{"axis": "x", "grade": "A"}]},
    )
    monkeypatch.setattr(
        machine_doctor.max_flow_store, "read_last", lambda _d: {"max_flow_mm3s": 24}
    )

    report = await machine_doctor.run_scan(Settings())
    assert report["grade"] == "A" and report["cap_reason"] is None
    assert report["assessment"]["code"] == "healthy"
    assert report["setup"] == {"done": 2, "total": 2, "pending": []}


async def test_blocked_pillars_do_not_cap_for_setup(monkeypatch: pytest.MonkeyPatch) -> None:
    """Moonraker fully down blocks firmware + services + tuning (available False). Only genuinely
    UNDONE flow lands in setup.pending; blocked pillars never appear there or cap for 'setup'."""

    async def clean(*_a: Any, **_k: Any) -> dict[str, Any]:
        return {"status": "ok", "findings": []}

    for name in (
        "_scan_pins",
        "_scan_drivers",
        "_scan_drift",
        "_scan_project",
        "_scan_firmware",
        "_scan_hardware",
        "_scan_install",
    ):
        monkeypatch.setattr(machine_doctor, name, clean)

    async def fw_down(*_a: Any, **_k: Any) -> dict[str, Any]:
        return {"available": False, "mcus": []}

    async def no_services(*_a: Any, **_k: Any) -> dict[str, Any]:
        return {"source": None, "units": []}

    monkeypatch.setattr(machine_doctor.overview, "_firmware_block", fw_down)
    monkeypatch.setattr(machine_doctor, "_gather_services", no_services)
    monkeypatch.setattr(
        machine_doctor.overview, "_tuning_block", lambda _d: {"available": False, "axes": []}
    )
    monkeypatch.setattr(machine_doctor.max_flow_store, "read_last", lambda _d: None)

    report = await machine_doctor.run_scan(Settings())
    pillars = {p["key"]: p for p in report["pillars"]}
    assert pillars["tuning"]["status"] == "unknown" and pillars["tuning"]["reason"] == "blocked"
    assert pillars["firmware"]["reason"] == "blocked"
    assert report["setup"]["pending"] == ["flow"]  # only the truly-undone flow, not blocked tuning
