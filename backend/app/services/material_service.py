"""Material brain - the 'smart' layer over the stored filament profiles (material brain §12, PR 2).

The headline check: cross-reference a profile's max volumetric flow against the configured hotend's
ceiling (taken from the hardware catalog via ``max_flow_service.hotend_hint``), so a profile that
asks for more flow than the hotend can deliver is flagged BEFORE it shows up as under-extrusion.

Pure + testable; returns a translatable ``{code, level, params}`` verdict (frontend renders
``material.flowCheck.<code>``).
"""

from __future__ import annotations

from typing import Any

from app.services import max_flow_service


def _ceiling(hotend: str | None) -> tuple[float | None, str]:
    """Catalog ``expected_max_flow_mm3s`` for a hotend name (+ its canonical label), if known."""
    row = max_flow_service.hotend_hint(hotend)
    if not row:
        return None, (hotend or "")
    value = row.get("expected_max_flow_mm3s")
    label = str(row.get("name") or hotend or "")
    if isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0:
        return float(value), label
    return None, label


def check_flow(material_flow: float, hotend: str | None) -> dict[str, Any]:
    """Verdict on whether ``material_flow`` (mm3/s) fits under the hotend's catalog ceiling.

    Codes: ``unset`` (no flow recorded) · ``no_ceiling`` (unknown hotend) ·
    ``exceeds`` (over the ceiling, warn) · ``within`` (ok, with % headroom).
    """
    if material_flow <= 0:
        return {"code": "unset", "level": "ok", "params": {}}
    ceiling, label = _ceiling(hotend)
    flow = round(material_flow, 1)
    if ceiling is None:
        return {"code": "no_ceiling", "level": "ok", "params": {"flow": flow}}
    if material_flow > ceiling:
        return {
            "code": "exceeds",
            "level": "warn",
            "params": {"flow": flow, "ceiling": round(ceiling, 1), "hotend": label},
        }
    return {
        "code": "within",
        "level": "ok",
        "params": {
            "flow": flow,
            "ceiling": round(ceiling, 1),
            "hotend": label,
            "headroom": round((1 - material_flow / ceiling) * 100),
        },
    }
