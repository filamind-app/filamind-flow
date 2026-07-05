"""Machine Doctor - one scan, one graded report.

A thin aggregator over analyzers that already exist (no new analysis code): the pin doctor,
the TMC value-sanity check, disk-vs-live drift, the project include/lint graph, per-MCU
firmware sync, the hardware-change diff against the saved baseline, and the install health
checks. Each source's findings are normalized into ``{code, level, params, link}`` - the
frontend translates ``code`` + ``params`` (no English leaks from here) and turns ``link``
into a deep-link button into the widget that fixes the problem.

The headline SCORE is a weighted blend of the MEASURED health pillars (config integrity, firmware
sync, services, input shaping, max flow) - the exact bars shown in the Health breakdown. Config
integrity is the transparent additive pillar (``100 - 25*errors - 8*warnings``, floored at 0);
pillars that can't be judged right now (Moonraker/host down) renormalize out, so the score always
equals the visible weighted bars. An UNDONE setup step (input shaping / max flow never run) is not a
fault, so it doesn't lower the number - but it CAPS the letter grade (can't be an ``A``), is named
in the verdict, and is tracked under Setup completeness, so a half-set-up printer never reads as A.
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
#: pillars that COULD be measured, so a signal we can't judge now (Moonraker down) drops out of the
#: NUMBER. Config integrity (the original additive score) always contributes, so the denominator is
#: never zero. (An undone setup pillar also drops out of the number but caps the grade - see
#: _cap_grade / _SETUP_PILLARS.)
_PILLAR_WEIGHTS = {"config": 0.45, "firmware": 0.15, "services": 0.15, "tuning": 0.15, "flow": 0.10}
_PILLAR_ORDER = ("config", "firmware", "services", "tuning", "flow")
_CRITICAL_SERVICES = ("klipper", "moonraker")
_TUNING_GRADE_SCORE = {"A": 95.0, "B": 85.0, "C": 72.0, "D": 53.0, "F": 30.0}
_GRADE_RANK = {"A": 0, "B": 1, "C": 2, "D": 3, "F": 4}
#: Pillars that represent a Get-Started checklist task. When one is UNDONE (never run) it does NOT
#: lower the number (it isn't a fault), but it caps the grade and is listed in the verdict.
_SETUP_PILLARS = ("tuning", "flow")

#: A pillar's ``reason`` when its score is None: ``undone`` = a setup task never run (holds the
#: grade); ``blocked`` = can't be judged right now (Moonraker/host down) - never penalizes.


def _status_for(score: float | None, reason: str) -> str:
    """Bar/label status. ``todo`` (undone setup) is distinct from ``unknown`` (can't judge now)."""
    if score is None:
        return "todo" if reason == "undone" else "unknown"
    if score < 45:
        return "fail"
    if score < 78:
        return "warn"
    return "ok"


def _firmware_pillar(fw: dict[str, Any]) -> tuple[float | None, dict[str, Any], str]:
    """Sync health: penalize each MCU whose firmware is out of sync with a KNOWN host version."""
    oos = int(fw.get("out_of_sync") or 0)
    detail = {"out_of_sync": oos, "mcus": len(fw.get("mcus") or [])}
    if not fw.get("available") or not fw.get("host_version") or not fw.get("mcus"):
        return None, detail, "blocked"  # can't judge sync now (no host version + MCUs to read)
    return max(0.0, 100.0 - 34.0 * oos), detail, "measured"


def _services_pillar(units: list[dict[str, Any]]) -> tuple[float | None, dict[str, Any], str]:
    if not units:
        return None, {"active": 0, "total": 0}, "blocked"  # host unreachable/unreadable
    active = sum(1 for s in units if s.get("active"))
    total = len(units)
    score = 100.0 * active / total
    down_critical = any(
        not s.get("active") and any(c in str(s.get("name", "")) for c in _CRITICAL_SERVICES)
        for s in units
    )
    if down_critical:  # a core unit down is a hard problem, not a fractional dent
        score = min(score, 40.0)
    return score, {"active": active, "total": total}, "measured"


def _tuning_pillar(tuning: dict[str, Any]) -> tuple[float | None, dict[str, Any], str]:
    """Mean of the latest per-axis shaper grade (derived from the archive's stored letter grade)."""
    scores: list[float] = []
    for axis in tuning.get("axes") or []:
        letter = str(axis.get("grade") or "").strip()[:1].upper()
        if letter in _TUNING_GRADE_SCORE:
            scores.append(_TUNING_GRADE_SCORE[letter])
    if not scores:
        # available=True + no graded axes = the Input-Shaping task was never run (undone);
        # available=False only on an archive-read exception = can't judge now (blocked).
        return None, {"axes": 0}, ("undone" if tuning.get("available") else "blocked")
    return sum(scores) / len(scores), {"axes": len(scores)}, "measured"


def _flow_pillar(last: dict[str, Any] | None) -> tuple[float | None, dict[str, Any], str]:
    if not last or not isinstance(last.get("max_flow_mm3s"), (int, float)):
        return None, {}, "undone"  # no recorded run = the Max-Flow test was never done
    mf = float(last["max_flow_mm3s"])
    expected = last.get("expected_max_flow_mm3s")
    detail = {"max_flow_mm3s": mf, "expected_max_flow_mm3s": expected}
    if isinstance(expected, (int, float)) and not isinstance(expected, bool) and expected > 0:
        return min(100.0, 100.0 * mf / float(expected)), detail, "measured"
    return (
        100.0,
        detail,
        "measured",
    )  # a clean measurement exists; no rated value to compare against


def _cap_grade(base: str, undone_count: int, errors: int, warnings: int) -> tuple[str, str | None]:
    """Cap the letter grade so it can only WORSEN: an error can't be A/B (cap C); an undone setup
    step or any warning can't be an A (cap B). Returns (grade, cap_reason|None)."""
    cap: str | None = None
    cap_reason: str | None = None
    if errors > 0:
        cap, cap_reason = "C", "errors"
    elif undone_count >= 1 or warnings > 0:
        cap, cap_reason = "B", ("setup" if undone_count else "warnings")
    if cap is None:
        return base, None
    final = base if _GRADE_RANK[base] >= _GRADE_RANK[cap] else cap  # keep the worse of the two
    return final, (cap_reason if final != base else None)


def _assessment(
    grade: str, pillars: list[dict[str, Any]], errors: int, warnings: int, undone: list[str]
) -> dict[str, Any]:
    """A translatable verdict code (no English here - the frontend renders code + params). Priority:
    a real broken pillar > unfinished setup > residual findings > healthy. ``healthy`` is reachable
    only when nothing is broken, nothing is undone, and there are no errors/warnings."""
    failing = sorted(
        (p for p in pillars if p["score"] is not None and p["status"] in ("warn", "fail")),
        key=lambda p: p["score"],
    )
    if failing:
        worst = failing[0]
        code = "critical" if worst["status"] == "fail" else "attention"
        return {"code": code, "params": {"grade": grade, "pillar": worst["key"]}}
    if undone:  # nothing broken, but Get-Started setup isn't finished
        return {"code": "setup_incomplete", "params": {"grade": grade, "pillars": undone}}
    if errors or warnings:  # clean pillars, but findings remain (drove the config dent)
        return {
            "code": "clean_but_findings",
            "params": {"grade": grade, "errors": errors, "warnings": warnings},
        }
    return {"code": "healthy", "params": {"grade": grade}}


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
                        # (e.g. a mains-switched pin) - informational, never scored.
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
        # in_sync=False is only a real finding when we know what the host runs - without a host
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

    A category whose analyzer raises degrades to ``status: "unknown"`` with no findings -
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

    # Config integrity - the original transparent additive score; always measured.
    config_score = max(0.0, 100.0 - 25.0 * errors - 8.0 * warnings)

    # The other pillars draw on data the app already computes elsewhere; each degrades to None
    # ("not measured") rather than penalizing the grade. Firmware + services are concurrent.
    fw_block, services = await asyncio.gather(
        overview._firmware_block(settings),
        _gather_services(client),
    )
    tuning = overview._tuning_block(settings.data_dir)
    last_flow = max_flow_store.read_last(settings.data_dir)

    raw: dict[str, tuple[float | None, dict[str, Any], str]] = {
        "config": (config_score, {"errors": errors, "warnings": warnings}, "measured"),
        "firmware": _firmware_pillar(fw_block),
        "services": _services_pillar(services["units"]),
        "tuning": _tuning_pillar(tuning),
        "flow": _flow_pillar(last_flow),
    }
    pillars: list[dict[str, Any]] = []
    contributing: list[tuple[str, float]] = []
    for key in _PILLAR_ORDER:
        raw_score, detail, reason = raw[key]
        pillars.append(
            {
                "key": key,
                "score": round(raw_score, 1) if raw_score is not None else None,
                "weight": _PILLAR_WEIGHTS[key],
                "status": _status_for(raw_score, reason),
                "reason": reason,
                "detail": detail,
            }
        )
        if raw_score is not None:
            contributing.append((key, raw_score))
    total_w = sum(_PILLAR_WEIGHTS[k] for k, _ in contributing)
    composite = (
        sum(_PILLAR_WEIGHTS[k] * s for k, s in contributing) / total_w if total_w else config_score
    )
    # The headline score IS the weighted-pillar composite shown in the Health breakdown - config
    # integrity (100 - 25*errors - 8*warnings) is just its biggest pillar, blended with firmware /
    # services / tuning / max-flow. Unmeasured pillars renormalize out (never count against you), so
    # the number always equals the visible weighted bars.
    # UNDONE setup steps (input shaping / max flow never run) don't lower the number (they aren't a
    # fault) but they cap the letter grade and are named in the verdict + a Setup-completeness list.
    undone = [p["key"] for p in pillars if p["status"] == "todo"]
    grade, cap_reason = _cap_grade(_grade(composite), len(undone), errors, warnings)
    setup = {
        "done": sum(1 for k in _SETUP_PILLARS if raw[k][2] == "measured"),
        "total": len(_SETUP_PILLARS),
        "pending": undone,
    }
    score = composite

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
        "score": round(score, 1),
        "errors": errors,
        "warnings": warnings,
        "categories": categories,
        "pillars": pillars,
        "assessment": _assessment(grade, pillars, errors, warnings, undone),
        "setup": setup,
        "cap_reason": cap_reason,
        "services": services,
        "stats": stats,
    }
