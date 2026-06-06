"""Phase 0 reference-data layer — curated Klipper datasets reused across upcoming widgets.

Static JSON datasets baked under ``app/data/reference/``:

* ``stallguard_profiles.json`` — per-driver StallGuard slip-detection tuning constants
  (base + per-driver overrides + the StallGuard field name per model). Backs the planned
  Max-Flow widget and the Motor Drivers auto-SGT / slip-detection enhancement.
* ``hotend_table.json`` — hotend melt-zone + expected max-flow + suggested test presets.
* ``board_patterns.json`` — board / MCU identification patterns.
* ``macros.json`` — built-in Klipper calibration macro definitions.

Read once at import — small, static reference data (mirrors ``motor_catalog`` / ``driver_catalog``).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_DIR = Path(__file__).resolve().parent.parent / "data" / "reference"


def _load(name: str) -> dict[str, Any]:
    try:
        with (_DIR / name).open(encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


_STALLGUARD = _load("stallguard_profiles.json")
_HOTENDS = _load("hotend_table.json")
_BOARDS = _load("board_patterns.json")
_MACROS = _load("macros.json")
_HARDWARE = _load("hardware.json")


# ── StallGuard ───────────────────────────────────────────────────────────────
def stallguard_profiles() -> dict[str, Any]:
    """The full StallGuard dataset (``base`` + per-driver ``overrides`` + ``field_by_driver``)."""
    return _STALLGUARD


def stallguard_field(driver: str) -> str | None:
    """The StallGuard threshold field for a driver model (e.g. tmc2209 -> ``sgthrs``)."""
    fields = _STALLGUARD.get("field_by_driver", {})
    return fields.get(driver.lower()) if isinstance(fields, dict) else None


def resolved_profile(driver: str) -> dict[str, Any]:
    """The effective slip-detection constants for a driver = ``base`` merged with its overrides.

    Always returns the base set (so an unknown driver falls back to the validated SG2 defaults).
    """
    base = _STALLGUARD.get("base", {})
    merged: dict[str, Any] = dict(base) if isinstance(base, dict) else {}
    overrides = _STALLGUARD.get("overrides", {})
    driver_ov = overrides.get(driver.lower()) if isinstance(overrides, dict) else None
    if isinstance(driver_ov, dict):
        merged.update(driver_ov)
    return {"driver": driver.lower(), "field": stallguard_field(driver), "constants": merged}


# ── Hotends / boards / macros ────────────────────────────────────────────────
def hotends() -> list[dict[str, Any]]:
    """Hotend melt-zone / expected-flow / test-preset table."""
    rows = _HOTENDS.get("hotends", [])
    return [r for r in rows if isinstance(r, dict)] if isinstance(rows, list) else []


def board_patterns() -> dict[str, Any]:
    """Board + MCU identification patterns (``board_patterns`` + ``mcu_patterns``)."""
    return _BOARDS


def macros() -> list[dict[str, Any]]:
    """Built-in Klipper calibration macro definitions."""
    rows = _MACROS.get("builtin_macros", [])
    return [r for r in rows if isinstance(r, dict)] if isinstance(rows, list) else []


# ── Hardware reference DB ─────────────────────────────────────────────────────
def hardware_items() -> list[dict[str, Any]]:
    """Every hardware component row (category / manufacturer / name / specs)."""
    rows = _HARDWARE.get("items", [])
    return [r for r in rows if isinstance(r, dict)] if isinstance(rows, list) else []


def hardware_categories() -> list[str]:
    """The hardware component categories, in dataset order."""
    rows = _HARDWARE.get("categories", [])
    return [str(c) for c in rows] if isinstance(rows, list) else []


def hardware_manufacturers() -> list[dict[str, Any]]:
    """The manufacturer directory (name / country / website / specialty / categories)."""
    rows = _HARDWARE.get("manufacturers", [])
    return [r for r in rows if isinstance(r, dict)] if isinstance(rows, list) else []
