"""Static lint of the live Klipper config, surfaced as findings for the Config Editor.

Complements ``config_service.gather_sanity`` (which is TMC current/microstep specific): this is a
structural pass that catches the errors that brick a ``FIRMWARE_RESTART`` or read as misconfigured.
It leans on AUTHORITATIVE sources rather than a hand-maintained rule list:

  * pin conflicts + electronics caveats - reuses ``board_topology.gather_pin_doctor``;
  * Klipper's OWN ``configfile.warnings`` (deprecated options etc., computed by Klipper itself) -
    zero false positives, always current with the running Klipper;
  * ``save_config_pending`` - a heads-up that calibration is unsaved;
  * a few unambiguous structural checks (no ``[printer]``, no stepper, heater min>=max).

Finding shape mirrors ``gather_sanity``: ``{level, rule, section, detail}``. Degrades to
``reachable=false`` when Moonraker is down."""

from __future__ import annotations

from typing import Any

import httpx

from app.services import board_topology
from app.services.moonraker_client import MoonrakerClient


def _to_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


async def _pin_findings(client: MoonrakerClient, data_dir: str) -> list[dict[str, Any]]:
    """Pin double-assignments + electronics caveats, lifted from the whole-config pin doctor."""
    out: list[dict[str, Any]] = []
    try:
        doctor = await board_topology.gather_pin_doctor(client, data_dir)
    except httpx.HTTPError:
        return out
    for mcu in doctor.get("mcus", []):
        for finding in mcu.get("findings", []):
            sections = finding.get("sections") or []
            section = sections[0] if sections else str(mcu.get("name") or "")
            if finding.get("kind") == "double_assign":
                out.append(
                    {
                        "level": "error",
                        "rule": "double_assigned_pin",
                        "section": section,
                        "detail": {"pin": finding.get("pin"), "sections": ", ".join(sections)},
                    }
                )
            else:  # caveat
                out.append(
                    {
                        "level": "warning",
                        "rule": "pin_caveat",
                        "section": section,
                        "detail": {"pin": finding.get("pin"), "message": finding.get("message")},
                    }
                )
    return out


_HEATER_PREFIXES = ("heater_bed", "extruder", "heater_generic")


def _structural_findings(sections: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    lowers = [str(h).lower() for h in sections]
    if not any(h == "printer" or h.startswith("printer ") for h in lowers):
        out.append(
            {"level": "error", "rule": "missing_printer", "section": "printer", "detail": {}}
        )
    has_stepper = any(h.startswith("stepper_") for h in lowers)
    has_extruder = any(h.startswith("extruder") for h in lowers)
    if not has_stepper and not has_extruder:
        out.append({"level": "warning", "rule": "no_stepper", "section": "", "detail": {}})
    for header, params in sections.items():
        if not isinstance(params, dict):
            continue
        if not str(header).lower().startswith(_HEATER_PREFIXES):
            continue
        mn = _to_float(params.get("min_temp"))
        mx = _to_float(params.get("max_temp"))
        if mn is not None and mx is not None and mn >= mx:
            out.append(
                {
                    "level": "error",
                    "rule": "heater_temp_range",
                    "section": str(header),
                    "detail": {"min_temp": mn, "max_temp": mx},
                }
            )
    return out


def _klipper_warnings(cfobj: dict[str, Any]) -> list[dict[str, Any]]:
    """Klipper's own config warnings (authoritative - deprecated options, etc.)."""
    out: list[dict[str, Any]] = []
    for warning in cfobj.get("warnings") or []:
        if isinstance(warning, dict):
            message = str(warning.get("message") or warning.get("type") or "").strip()
            if not message:
                continue
            out.append(
                {
                    "level": "warning",
                    "rule": "klipper_warning",
                    "section": str(warning.get("section") or ""),
                    "detail": {"message": message, "option": str(warning.get("option") or "")},
                }
            )
        elif isinstance(warning, str) and warning.strip():
            out.append(
                {
                    "level": "warning",
                    "rule": "klipper_warning",
                    "section": "",
                    "detail": {"message": warning.strip(), "option": ""},
                }
            )
    return out


async def lint_config(client: MoonrakerClient, data_dir: str = "") -> dict[str, Any]:
    """Run the structural lint over the live config. ``{reachable, findings, checked}``."""
    try:
        configfile = await client.query_objects(["configfile"])
    except httpx.HTTPError:
        return {"reachable": False, "findings": [], "checked": 0}
    cfobj = configfile.get("configfile")
    cfobj = cfobj if isinstance(cfobj, dict) else {}
    # Prefer typed `settings` (parsed values, lowercased headers); fall back to raw `config`.
    sections = cfobj.get("settings")
    if not isinstance(sections, dict) or not sections:
        sections = cfobj.get("config")
    sections = sections if isinstance(sections, dict) else {}

    findings: list[dict[str, Any]] = []
    findings += await _pin_findings(client, data_dir)
    findings += _klipper_warnings(cfobj)
    if cfobj.get("save_config_pending"):
        findings.append(
            {"level": "info", "rule": "save_config_pending", "section": "", "detail": {}}
        )
    findings += _structural_findings(sections)
    return {"reachable": True, "findings": findings, "checked": len(sections)}
