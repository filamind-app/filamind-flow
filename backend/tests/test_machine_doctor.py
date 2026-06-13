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
    # A board caveat describes by-design electronics (e.g. a mains-switched pin) — it must be
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
    # in_sync=False without a known host version is a meaningless comparison — no finding.
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

    report = await machine_doctor.run_scan(Settings())
    by_key = {c["key"]: c for c in report["categories"]}
    # The crash becomes an honest "unknown", not a failed scan or a fake "all clear".
    assert by_key["pins"]["status"] == "unknown"
    assert report["grade"] == "A"  # nothing scored against what could not be checked


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

    # tuning: mean of letter grades; none → "not measured"
    assert machine_doctor._tuning_pillar({"axes": []})[0] is None
    two_axes = {"axes": [{"grade": "A"}, {"grade": "C"}]}
    assert machine_doctor._tuning_pillar(two_axes)[0] == pytest.approx((95 + 72) / 2)

    # flow: vs the rated max if known, else 100 for a clean measurement
    assert machine_doctor._flow_pillar(None)[0] is None
    rated = {"max_flow_mm3s": 24, "expected_max_flow_mm3s": 30}
    assert machine_doctor._flow_pillar(rated)[0] == 80.0
    assert machine_doctor._flow_pillar({"max_flow_mm3s": 24})[0] == 100.0


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
    # composite renormalizes over the two measured pillars:
    # (0.45*100 + 0.15*40) / (0.45 + 0.15) = 51 / 0.6 = 85.0
    assert report["score"] == pytest.approx(85.0)
    assert report["assessment"]["code"] == "critical"
    assert report["assessment"]["params"]["pillar"] == "services"
    assert report["services"]["units"][0]["name"] == "klipper"
