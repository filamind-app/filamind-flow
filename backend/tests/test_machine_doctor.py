"""Tests for the Machine Doctor aggregator (grading + degradation; analyzers are stubbed)."""

from __future__ import annotations

from typing import Any

import pytest

from app.config import Settings
from app.services import machine_doctor


async def _clean(*_a: Any, **_k: Any) -> dict[str, Any]:
    return {"status": "ok", "findings": []}


def _stub_setup(
    monkeypatch: pytest.MonkeyPatch,
    *,
    tuning: bool = False,
    flow: bool = False,
    drivers: bool = False,
) -> None:
    """Stub the three setup pillars as done/undone. Undone setup counts as 0 in the score."""
    monkeypatch.setattr(
        machine_doctor.overview,
        "_tuning_block",
        lambda _d: {"available": True, "axes": ([{"axis": "x", "grade": "A"}] if tuning else [])},
    )
    monkeypatch.setattr(
        machine_doctor.max_flow_store,
        "read_last",
        lambda _d: {"max_flow_mm3s": 24} if flow else None,
    )
    monkeypatch.setattr(machine_doctor.drivers_store, "is_tuned", lambda _d: drivers)


def _stub_health(
    monkeypatch: pytest.MonkeyPatch,
    *,
    firmware: dict[str, Any] | None = None,
    services: list[dict[str, Any]] | None = None,
) -> None:
    """Stub the firmware + services health pillars. None = 'can't judge now' (blocked)."""
    fw = firmware or {"available": False, "mcus": []}
    units = services if services is not None else []

    async def _fw(*_a: Any, **_k: Any) -> dict[str, Any]:
        return fw

    async def _svc(*_a: Any, **_k: Any) -> dict[str, Any]:
        return {"source": "moonraker" if units else None, "units": units}

    monkeypatch.setattr(machine_doctor.overview, "_firmware_block", _fw)
    monkeypatch.setattr(machine_doctor, "_gather_services", _svc)


_FW_OK = {"available": True, "host_version": "v1", "mcus": [{}], "out_of_sync": 0}
_SVC_OK = [{"name": "klipper", "active": True}]


@pytest.mark.parametrize(
    ("score", "grade"),
    [(100, "A"), (90, "A"), (80, "B"), (70, "C"), (50, "D"), (44, "F"), (0, "F")],
)
def test_grade_thresholds(score: float, grade: str) -> None:
    assert machine_doctor._grade(score) == grade


async def test_run_scan_grades_and_links(monkeypatch: pytest.MonkeyPatch) -> None:
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
        monkeypatch.setattr(machine_doctor, name, _clean)
    # Health pillars measured-good and setup done, so the score isolates the config dent + blend.
    _stub_health(monkeypatch, firmware=_FW_OK, services=_SVC_OK)
    _stub_setup(monkeypatch, tuning=True, flow=True, drivers=True)

    report = await machine_doctor.run_scan(Settings())
    assert report["errors"] == 1 and report["warnings"] == 1
    # config = 100 - 25 - 8 = 67; blended: .45*67 + .13*100 + .12*100 + .12*95 + .09*100 + .09*100.
    assert report["score"] == pytest.approx(84.55, abs=0.05)
    assert report["grade"] == "B"
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

    monkeypatch.setattr(machine_doctor, "_scan_pins", boom)
    for name in (
        "_scan_drivers",
        "_scan_drift",
        "_scan_project",
        "_scan_firmware",
        "_scan_hardware",
        "_scan_install",
    ):
        monkeypatch.setattr(machine_doctor, name, _clean)
    # A fully-set-up, fully-healthy baseline so the readiness model doesn't drag: this test only
    # checks that a crashing analyzer degrades to "unknown" and still grades A.
    _stub_health(monkeypatch, firmware=_FW_OK, services=_SVC_OK)
    _stub_setup(monkeypatch, tuning=True, flow=True, drivers=True)

    report = await machine_doctor.run_scan(Settings())
    by_key = {c["key"]: c for c in report["categories"]}
    # The crash becomes an honest "unknown", not a failed scan or a fake "all clear".
    assert by_key["pins"]["status"] == "unknown"
    assert report["grade"] == "A"  # nothing broken, nothing undone


def test_pillar_helpers() -> None:
    # firmware: needs a known host version + MCUs, else "not measured"
    assert machine_doctor._firmware_pillar({"available": False})[0] is None
    assert machine_doctor._firmware_pillar(_FW_OK)[0] == 100.0
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

    # drivers: binary Get-Started task. A recorded apply/autotune = done (100); else undone.
    assert machine_doctor._drivers_pillar(True) == (100.0, {"tuned": True}, "measured")
    assert machine_doctor._drivers_pillar(False) == (None, {"tuned": False}, "undone")

    # firmware / services with no data can't be judged now (blocked), not "undone".
    assert machine_doctor._firmware_pillar({"available": False})[2] == "blocked"
    assert machine_doctor._services_pillar([])[2] == "blocked"


async def test_the_user_scenario(monkeypatch: pytest.MonkeyPatch) -> None:
    """config 92 (1 warning) + firmware 100 + services 90.9, and input shaping / max flow / motor
    drivers ALL not done: undone setup counts as 0, so the number falls to ~65/C - a printer that
    has run none of its tuning can't read in the 90s, and the verdict names the three pending steps.
    """

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
        monkeypatch.setattr(machine_doctor, name, _clean)
    monkeypatch.setattr(machine_doctor, "_scan_drift", drift_warn)
    # 10/11 services active = 90.9; firmware fully synced.
    services = [{"name": f"s{i}", "active": i > 0} for i in range(11)]
    _stub_health(monkeypatch, firmware=_FW_OK, services=services)
    _stub_setup(monkeypatch, tuning=False, flow=False, drivers=False)

    report = await machine_doctor.run_scan(Settings())
    # .45*92 + .13*100 + .12*90.909 + (.12+.09+.09)*0 = 41.4 + 13 + 10.909 = 65.31
    assert report["score"] == pytest.approx(65.3, abs=0.1)
    assert report["grade"] == "C"
    assert "cap_reason" not in report  # the grade comes straight off the readiness-aware score
    assert report["assessment"]["code"] == "setup_incomplete"
    assert report["assessment"]["params"]["pillars"] == ["tuning", "flow", "drivers"]
    assert report["setup"] == {"done": 0, "total": 3, "pending": ["tuning", "flow", "drivers"]}
    pillars = {p["key"]: p for p in report["pillars"]}
    assert pillars["drivers"]["status"] == "todo" and pillars["drivers"]["score"] is None


async def test_one_setup_step_done_raises_the_score(monkeypatch: pytest.MonkeyPatch) -> None:
    """Finishing a setup step lifts the number: doing max flow flips one 0 to its measured value."""
    for name in (
        "_scan_pins",
        "_scan_drivers",
        "_scan_drift",
        "_scan_project",
        "_scan_firmware",
        "_scan_hardware",
        "_scan_install",
    ):
        monkeypatch.setattr(machine_doctor, name, _clean)
    _stub_health(monkeypatch, firmware=_FW_OK, services=_SVC_OK)
    _stub_setup(monkeypatch, tuning=False, flow=True, drivers=False)  # only max flow done

    report = await machine_doctor.run_scan(Settings())
    # config 100, fw 100, svc 100, flow 100 measured; tuning + drivers undone → 0.
    # .45*100 + .13*100 + .12*100 + .09*100 + (.12+.09)*0 = 79.0
    assert report["score"] == pytest.approx(79.0, abs=0.1)
    assert report["setup"] == {"done": 1, "total": 3, "pending": ["tuning", "drivers"]}


async def test_run_scan_composites_pillars_and_assesses(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "_scan_pins",
        "_scan_drivers",
        "_scan_drift",
        "_scan_project",
        "_scan_firmware",
        "_scan_hardware",
        "_scan_install",
    ):
        monkeypatch.setattr(machine_doctor, name, _clean)
    # 2/3 active but a core unit (klipper) is down → services clamps to 40 (fail); firmware blocked.
    core_down = [
        {"name": "klipper", "active": False},
        {"name": "moonraker", "active": True},
        {"name": "webcamd", "active": True},
    ]
    _stub_health(monkeypatch, firmware=None, services=core_down)
    _stub_setup(monkeypatch, tuning=False, flow=False, drivers=False)

    report = await machine_doctor.run_scan(Settings())
    pillars = {p["key"]: p for p in report["pillars"]}
    assert pillars["config"]["score"] == 100.0
    assert pillars["services"]["score"] == 40.0 and pillars["services"]["status"] == "fail"
    assert pillars["firmware"]["score"] is None  # blocked → renormalized out of the composite
    # blocked firmware drops out; undone setup counts as 0:
    # (.45*100 + .12*40) / (.45 + .12 + .12 + .09 + .09) = 49.8 / 0.87 = 57.2 → D.
    assert report["score"] == pytest.approx(57.2, abs=0.1)
    assert report["grade"] == "D"
    # undone setup steps render as "todo" bars (not "unknown").
    assert pillars["tuning"]["status"] == "todo" and pillars["drivers"]["status"] == "todo"
    # a real fault (services fail) outranks undone setup in the verdict.
    assert report["assessment"]["code"] == "critical"
    assert report["assessment"]["params"]["pillar"] == "services"
    assert report["services"]["units"][0]["name"] == "klipper"


async def test_healthy_only_when_complete(monkeypatch: pytest.MonkeyPatch) -> None:
    """All health measured + all setup done + zero findings → A, healthy (the only such path)."""
    for name in (
        "_scan_pins",
        "_scan_drivers",
        "_scan_drift",
        "_scan_project",
        "_scan_firmware",
        "_scan_hardware",
        "_scan_install",
    ):
        monkeypatch.setattr(machine_doctor, name, _clean)
    _stub_health(monkeypatch, firmware=_FW_OK, services=_SVC_OK)
    _stub_setup(monkeypatch, tuning=True, flow=True, drivers=True)

    report = await machine_doctor.run_scan(Settings())
    assert report["grade"] == "A"
    assert report["assessment"]["code"] == "healthy"
    assert report["setup"] == {"done": 3, "total": 3, "pending": []}


async def test_blocked_setup_pillar_does_not_leave_a_phantom_ring_segment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Tuning archive unreadable (blocked) but max flow + drivers done + all health good → healthy,
    grade A. The blocked step must drop out of setup.total too, so the ring reads 2/2 (complete),
    never 2/3 next to a 'setup is complete' verdict."""
    for name in (
        "_scan_pins",
        "_scan_drivers",
        "_scan_drift",
        "_scan_project",
        "_scan_firmware",
        "_scan_hardware",
        "_scan_install",
    ):
        monkeypatch.setattr(machine_doctor, name, _clean)
    _stub_health(monkeypatch, firmware=_FW_OK, services=_SVC_OK)
    monkeypatch.setattr(
        machine_doctor.overview, "_tuning_block", lambda _d: {"available": False, "axes": []}
    )  # archive read raised → blocked, not undone
    monkeypatch.setattr(
        machine_doctor.max_flow_store, "read_last", lambda _d: {"max_flow_mm3s": 24}
    )
    monkeypatch.setattr(machine_doctor.drivers_store, "is_tuned", lambda _d: True)

    report = await machine_doctor.run_scan(Settings())
    assert report["grade"] == "A"
    assert report["assessment"]["code"] == "healthy"
    assert report["setup"] == {"done": 2, "total": 2, "pending": []}


async def test_clean_but_findings(monkeypatch: pytest.MonkeyPatch) -> None:
    """All pillars measured/ok and all setup done, but one warning remains → clean_but_findings."""

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
        monkeypatch.setattr(machine_doctor, name, _clean)
    monkeypatch.setattr(machine_doctor, "_scan_drift", drift_warn)
    _stub_health(monkeypatch, firmware=_FW_OK, services=_SVC_OK)
    _stub_setup(monkeypatch, tuning=True, flow=True, drivers=True)

    report = await machine_doctor.run_scan(Settings())
    assert report["setup"]["pending"] == []
    assert report["assessment"]["code"] == "clean_but_findings"
    assert report["assessment"]["params"]["warnings"] == 1


async def test_blocked_pillars_do_not_drag_or_list_as_setup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Moonraker fully down blocks firmware + services + tuning (available False). Blocked pillars
    renormalize OUT (never penalize); only genuinely-undone flow + drivers land in setup.pending."""
    for name in (
        "_scan_pins",
        "_scan_drivers",
        "_scan_drift",
        "_scan_project",
        "_scan_firmware",
        "_scan_hardware",
        "_scan_install",
    ):
        monkeypatch.setattr(machine_doctor, name, _clean)
    _stub_health(monkeypatch, firmware=None, services=None)  # both blocked
    monkeypatch.setattr(
        machine_doctor.overview, "_tuning_block", lambda _d: {"available": False, "axes": []}
    )  # tuning archive unreadable → blocked, not undone
    monkeypatch.setattr(machine_doctor.max_flow_store, "read_last", lambda _d: None)
    monkeypatch.setattr(machine_doctor.drivers_store, "is_tuned", lambda _d: False)

    report = await machine_doctor.run_scan(Settings())
    pillars = {p["key"]: p for p in report["pillars"]}
    assert pillars["tuning"]["status"] == "unknown" and pillars["tuning"]["reason"] == "blocked"
    assert pillars["firmware"]["reason"] == "blocked"
    # only the truly-undone setup steps are pending; blocked tuning is not.
    assert report["setup"]["pending"] == ["flow", "drivers"]
    # blocked tuning also drops out of the TOTAL (mirrors the composite), so it can't leave a
    # phantom empty ring segment next to a "setup complete" verdict: 2 knowable steps, 0 done.
    assert report["setup"]["total"] == 2 and report["setup"]["done"] == 0
    # config is the only non-blocked health pillar; flow + drivers count as 0:
    # (.45*100) / (.45 + .09 + .09) = 45 / 0.63 = 71.4.
    assert report["score"] == pytest.approx(71.4, abs=0.1)
