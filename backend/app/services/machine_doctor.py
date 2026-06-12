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

    score = max(0.0, 100.0 - 25.0 * errors - 8.0 * warnings)
    return {
        "grade": _grade(score),
        "score": round(score, 1),
        "errors": errors,
        "warnings": warnings,
        "categories": categories,
    }
