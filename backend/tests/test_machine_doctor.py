"""Tests for the Machine Doctor aggregator (grading + degradation; analyzers are stubbed)."""

from __future__ import annotations

from typing import Any

import pytest

from app.config import Settings
from app.services import machine_doctor


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

    report = await machine_doctor.run_scan(Settings())
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

    report = await machine_doctor.run_scan(Settings())
    by_key = {c["key"]: c for c in report["categories"]}
    # The crash becomes an honest "unknown", not a failed scan or a fake "all clear".
    assert by_key["pins"]["status"] == "unknown"
    assert report["grade"] == "A"  # nothing scored against what could not be checked
