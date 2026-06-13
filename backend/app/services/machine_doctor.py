"""Machine Doctor — one scan, one graded report.

A thin aggregator over analyzers that already exist (no new analysis code): the pin doctor,
the TMC value-sanity check, disk-vs-live drift, the project include/lint graph, per-MCU
firmware sync, the hardware-change diff against the saved baseline, and the install health
checks. Each source's findings are normalized into ``{code, level, params, link}`` — the
frontend translates ``code`` + ``params`` (no English leaks from here) and turns ``link``
into a deep-link button into the widget that fixes the problem.

The headline is an A-F grade in the Input Shaping idiom: transparent scoring
(``100 - 25*errors - 8*warnings``, floored at 0) so a user can see exactly why their
printer scored a B.
"""

from __future__ import annotations

import asyncio
from typing import Any

from app.config import Settings
from app.services import (
    board_topology,
    config_service,
    firmware_service,
    health_service,
    max_flow_store,
    overview,
    services_service,
    topology_snapshot,
)
from app.services.moonraker_client import MoonrakerClient

#: Grade thresholds over the 0-100 score.
_GRADES = (("A", 90), ("B", 78), ("C", 62), ("D", 45))


def _grade(score: float) -> str:
    for letter, floor in _GRADES:
        if score >= floor:
            return letter
    return "F"


#: Weighted health pillars. Each contributes a 0-100 sub-score; weights are renormalized over the
#: pillars that COULD be measured, so an unmeasurable signal (no shaper runs yet, Moonraker down)
#: never penalizes the grade — it just drops out. Config integrity (the original additive score)
#: always contributes, so the denominator is never zero.
_PILLAR_WEIGHTS = {"config": 0.45, "firmware": 0.15, "services": 0.15, "tuning": 0.15, "flow": 0.10}
_PILLAR_ORDER = ("config", "firmware", "services", "tuning", "flow")
_CRITICAL_SERVICES = ("klipper", "moonraker")
_TUNING_GRADE_SCORE = {"A": 95.0, "B": 85.0, "C": 72.0, "D": 53.0, "F": 30.0}


def _pillar_status(score: float | None) -> str:
    if score is None:
        return "unknown"
    if score < 45:
        return "fail"
    if score < 78:
        return "warn"
    return "ok"


def _firmware_pillar(fw: dict[str, Any]) -> tuple[float | None, dict[str, Any]]:
    """Sync health: penalize each MCU whose firmware is out of sync with a KNOWN host version."""
    oos = int(fw.get("out_of_sync") or 0)
    detail = {"out_of_sync": oos, "mcus": len(fw.get("mcus") or [])}
    if not fw.get("available") or not fw.get("host_version") or not fw.get("mcus"):
        return None, detail  # can't judge sync without a host version + MCUs
    return max(0.0, 100.0 - 34.0 * oos), detail


def _services_pillar(units: list[dict[str, Any]]) -> tuple[float | None, dict[str, Any]]:
    if not units:
        return None, {"active": 0, "total": 0}
    active = sum(1 for s in units if s.get("active"))
    total = len(units)
    score = 100.0 * active / total
    down_critical = any(
        not s.get("active") and any(c in str(s.get("name", "")) for c in _CRITICAL_SERVICES)
        for s in units
    )
    if down_critical:  # a core unit down is a hard problem, not a fractional dent
        score = min(score, 40.0)
    return score, {"active": active, "total": total}


def _tuning_pillar(tuning: dict[str, Any]) -> tuple[float | None, dict[str, Any]]:
    """Mean of the latest per-axis shaper grade (derived from the archive's stored letter grade)."""
    scores: list[float] = []
    for axis in tuning.get("axes") or []:
        letter = str(axis.get("grade") or "").strip()[:1].upper()
        if letter in _TUNING_GRADE_SCORE:
            scores.append(_TUNING_GRADE_SCORE[letter])
    if not scores:
        return None, {"axes": 0}
    return sum(scores) / len(scores), {"axes": len(scores)}


def _flow_pillar(last: dict[str, Any] | None) -> tuple[float | None, dict[str, Any]]:
    if not last or not isinstance(last.get("max_flow_mm3s"), (int, float)):
        return None, {}
    mf = float(last["max_flow_mm3s"])
    expected = last.get("expected_max_flow_mm3s")
    detail = {"max_flow_mm3s": mf, "expected_max_flow_mm3s": expected}
    if isinstance(expected, (int, float)) and not isinstance(expected, bool) and expected > 0:
        return min(100.0, 100.0 * mf / float(expected)), detail
    return 100.0, detail  # a clean measurement exists; no rated value to compare against


def _assessment(grade: str, pillars: list[dict[str, Any]]) -> dict[str, Any]:
    """A translatable verdict code: ``healthy``, or ``attention`` / ``critical`` naming the
    weakest measured pillar. No English here — the frontend renders the code + params."""
    failing = sorted(
        (p for p in pillars if p["score"] is not None and p["status"] in ("warn", "fail")),
        key=lambda p: p["score"],
    )
    if not failing:
        return {"code": "healthy", "params": {"grade": grade}}
    worst = failing[0]
    code = "critical" if worst["status"] == "fail" else "attention"
    return {"code": code, "params": {"grade": grade, "pillar": worst["key"]}}


async def _gather_services(client: MoonrakerClient) -> dict[str, Any]:
    """Running printer-stack services + state. Prefer Moonraker's curated ``service_state`` (no
    sudo, no OS noise); fall back to a read-only systemd list when Moonraker is unreachable."""
    try:
        info = await client.machine_system_info()
        state = info.get("service_state")
        if isinstance(state, dict) and state:
            units = [
                {
                    "name": str(name),
                    "active": (svc or {}).get("active_state") == "active",
                    "sub_state": (svc or {}).get("sub_state"),
                }
                for name, svc in sorted(state.items())
            ]
            return {"source": "moonraker", "units": units}
    except Exception:
        pass
    try:
        units = await services_service.list_all_services()
        if units:
            return {"source": "systemd", "units": units}
    except Exception:
        pass
    return {"source": None, "units": []}


def _finding(
    code: str, level: str, params: dict[str, Any], link: dict[str, Any] | None = None
) -> dict[str, Any]:
    return {"code": code, "level": level, "params": params, "link": link}


def _config_link(section: str) -> dict[str, Any]:
    return {"kind": "config_section", "value": section}


def _stepper_of(section: str) -> str | None:
    """``tmc2209 stepper_x`` → ``stepper_x`` (None for single-token headers)."""
    parts = section.split(None, 1)
    return parts[1].strip() if len(parts) > 1 else None


async def _scan_pins(client: MoonrakerClient, data_dir: str) -> dict[str, Any]:
    out = await board_topology.gather_pin_doctor(client, data_dir)
    findings: list[dict[str, Any]] = []
    for mcu in out.get("mcus", []):
        for f in mcu.get("findings", []):
            sections = f.get("sections") or []
            owner = str(sections[0]).rsplit(".", 1)[0] if sections else None
            if f.get("kind") == "double_assign":
                findings.append(
                    _finding(
                        "pins.double_assign",
                        "error",
                        {"pin": f.get("pin"), "mcu": mcu.get("name")},
                        _config_link(owner) if owner else None,
                    )
                )
            else:
                findings.append(
                    _finding(
                        # A board caveat is a heads-up about electronics that are wired BY DESIGN
                        # (e.g. a mains-switched pin) — informational, never scored.
                        "pins.caveat",
                        "info",
                        {"pin": f.get("pin"), "mcu": mcu.get("name")},
                        _config_link(owner) if owner else None,
                    )
                )
    return {"status": "ok" if out.get("reachable") else "unknown", "findings": findings}


async def _scan_drivers(client: MoonrakerClient, data_dir: str) -> dict[str, Any]:
    out = await config_service.gather_sanity(client, data_dir)
    findings: list[dict[str, Any]] = []
    for f in out.get("findings", []):
        section = str(f.get("section", ""))
        stepper = _stepper_of(section)
        link: dict[str, Any] | None
        if stepper:
            link = {"kind": "stepper", "value": stepper}
        else:
            link = _config_link(section) if section else None
        findings.append(
            _finding(
                "drivers." + str(f.get("rule")),
                str(f.get("level", "warning")),
                {"section": section, **(f.get("detail") or {})},
                link,
            )
        )
    return {"status": "ok" if out.get("reachable") else "unknown", "findings": findings}


async def _scan_drift(client: MoonrakerClient) -> dict[str, Any]:
    out = await config_service.gather_drift(client, "printer.cfg")
    findings: list[dict[str, Any]] = []
    if out.get("save_config_pending"):
        findings.append(
            _finding("drift.pending", "warning", {}, {"kind": "widget", "value": "config-editor"})
        )
    for d in out.get("drifts", []):
        findings.append(
            _finding(
                "drift.param",
                "warning",
                {"section": d["section"], "key": d["key"], "disk": d["disk"], "live": d["live"]},
                _config_link(str(d["section"])),
            )
        )
    for w in out.get("warnings", []):
        findings.append(_finding("drift.klipper_warning", "warning", {"text": str(w)}, None))
    return {"status": "ok" if out.get("reachable") else "unknown", "findings": findings}


async def _scan_project(client: MoonrakerClient) -> dict[str, Any]:
    out = await config_service.gather_project(client)
    findings: list[dict[str, Any]] = []
    for lt in out.get("lint", []):
        if lt.get("level") == "info":
            continue  # section overrides are normal Klipper practice, not doctor findings
        code = "project." + str(lt.get("rule"))
        findings.append(
            _finding(
                code,
                str(lt.get("level", "warning")),
                {"file": lt.get("file"), "message": lt.get("message")},
                {"kind": "config_file", "value": lt.get("file")},
            )
        )
    return {"status": "ok" if out.get("reachable") else "unknown", "findings": findings}


async def _scan_firmware(settings: Settings) -> dict[str, Any]:
    out = await firmware_service.gather_status(
        settings.moonraker_url, settings.klipper_dir, settings.katapult_dir, settings.data_dir
    )
    findings: list[dict[str, Any]] = []
    host = out.get("host")
    host_version = host.get("version") if isinstance(host, dict) else None
    for mcu in out.get("mcus", []):
        # in_sync=False is only a real finding when we know what the host runs — without a host
        # version the comparison is meaningless, and reporting it would be a fake warning.
        if mcu.get("in_sync") is False and host_version:
            findings.append(
                _finding(
                    "firmware.out_of_sync",
                    "warning",
                    {
                        "mcu": mcu.get("name"),
                        "mcu_version": mcu.get("version"),
                        "host_version": host_version,
                    },
                    {"kind": "topology_node", "value": mcu.get("name")},
                )
            )
    status = "ok" if out.get("reachable", True) else "unknown"
    return {"status": status, "findings": findings}


async def _scan_hardware(client: MoonrakerClient, data_dir: str) -> dict[str, Any]:
    baseline = topology_snapshot.read_snapshot(data_dir)
    if baseline is None:
        return {
            "status": "unknown",
            "findings": [_finding("hardware.no_baseline", "info", {}, None)],
        }
    topo = await board_topology.gather_topology(client, data_dir)
    if topo.get("reachable") is False:
        return {"status": "unknown", "findings": []}
    changes = topology_snapshot.diff(baseline, topo.get("mcus", []))
    findings = [
        _finding(
            "hardware.changed",
            "warning",
            {"mcu": c.get("mcu"), "kind": c.get("kind"), "after": c.get("after")},
            {"kind": "topology_node", "value": c.get("mcu")},
        )
        for c in changes
    ]
    return {"status": "ok", "findings": findings}


async def _scan_install(settings: Settings) -> dict[str, Any]:
    out = await health_service.gather_health()
    findings = [
        _finding(
            "install.check_failed",
            "warning",
            {"name": c.get("name"), "detail": c.get("detail")},
            {"kind": "widget", "value": "firmware-upgrade", "tab": "status"},
        )
        for c in out.get("checks", [])
        if not c.get("ok")
    ]
    return {"status": "ok", "findings": findings}


_CATEGORIES = ("pins", "drivers", "drift", "project", "firmware", "hardware", "install")


async def run_scan(settings: Settings) -> dict[str, Any]:
    """Run every analyzer concurrently and fold the results into one graded report.

    A category whose analyzer raises degrades to ``status: "unknown"`` with no findings —
    the report says what it could not check instead of failing the whole scan.
    """
    client = MoonrakerClient(settings.moonraker_url)
    scans = {
        "pins": _scan_pins(client, settings.data_dir),
        "drivers": _scan_drivers(client, settings.data_dir),
        "drift": _scan_drift(client),
        "project": _scan_project(client),
        "firmware": _scan_firmware(settings),
        "hardware": _scan_hardware(client, settings.data_dir),
        "install": _scan_install(settings),
    }
    results = await asyncio.gather(*scans.values(), return_exceptions=True)

    categories: list[dict[str, Any]] = []
    errors = 0
    warnings = 0
    for key, result in zip(scans.keys(), results, strict=True):
        if isinstance(result, BaseException):
            categories.append(
                {"key": key, "status": "unknown", "errors": 0, "warnings": 0, "findings": []}
            )
            continue
        findings = result["findings"]
        cat_errors = sum(1 for f in findings if f["level"] == "error")
        cat_warnings = sum(1 for f in findings if f["level"] == "warning")
        errors += cat_errors
        warnings += cat_warnings
        status = result["status"]
        if status == "ok" and (cat_errors or cat_warnings):
            status = "fail" if cat_errors else "warn"
        categories.append(
            {
                "key": key,
                "status": status,
                "errors": cat_errors,
                "warnings": cat_warnings,
                "findings": findings,
            }
        )

    # Config integrity — the original transparent additive score; always measured.
    config_score = max(0.0, 100.0 - 25.0 * errors - 8.0 * warnings)

    # The other pillars draw on data the app already computes elsewhere; each degrades to None
    # ("not measured") rather than penalizing the grade. Firmware + services are concurrent.
    fw_block, services = await asyncio.gather(
        overview._firmware_block(settings),
        _gather_services(client),
    )
    tuning = overview._tuning_block(settings.data_dir)
    last_flow = max_flow_store.read_last(settings.data_dir)

    fw_score, fw_detail = _firmware_pillar(fw_block)
    svc_score, svc_detail = _services_pillar(services["units"])
    tun_score, tun_detail = _tuning_pillar(tuning)
    flow_score, flow_detail = _flow_pillar(last_flow)
    raw = {
        "config": (config_score, {"errors": errors, "warnings": warnings}),
        "firmware": (fw_score, fw_detail),
        "services": (svc_score, svc_detail),
        "tuning": (tun_score, tun_detail),
        "flow": (flow_score, flow_detail),
    }
    pillars = [
        {
            "key": key,
            "score": round(raw[key][0], 1) if raw[key][0] is not None else None,
            "weight": _PILLAR_WEIGHTS[key],
            "status": _pillar_status(raw[key][0]),
            "detail": raw[key][1],
        }
        for key in _PILLAR_ORDER
    ]
    contributing = [(p["key"], p["score"]) for p in pillars if p["score"] is not None]
    total_w = sum(_PILLAR_WEIGHTS[k] for k, _ in contributing)
    composite = (
        sum(_PILLAR_WEIGHTS[k] * s for k, s in contributing) / total_w if total_w else config_score
    )
    grade = _grade(composite)

    stats = {
        "max_flow": last_flow,
        "tuning": tuning.get("axes") if tuning.get("available") else None,
        "firmware": (
            {
                "host_version": fw_block.get("host_version"),
                "out_of_sync": fw_block.get("out_of_sync"),
                "mcu_count": len(fw_block.get("mcus") or []),
            }
            if fw_block.get("available")
            else None
        ),
    }

    return {
        "grade": grade,
        "score": round(composite, 1),
        "errors": errors,
        "warnings": warnings,
        "categories": categories,
        "pillars": pillars,
        "assessment": _assessment(grade, pillars),
        "services": services,
        "stats": stats,
    }
