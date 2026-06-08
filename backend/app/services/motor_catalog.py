"""The stepper-motor catalog (datasheet parameters for 200+ motors).

Loads ``app/data/motor_catalog.json`` and indexes it by model, backing the Motor Drivers
motor picker. Read once at import — small, static reference data.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_CATALOG_PATH = Path(__file__).resolve().parent.parent / "data" / "motor_catalog.json"

_EMPTY: dict[str, Any] = {"source": "", "count": 0, "manufacturers": [], "motors": []}


def _load() -> dict[str, Any]:
    try:
        with _CATALOG_PATH.open(encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return _EMPTY
    return data if isinstance(data, dict) else _EMPTY


_DATA = _load()
_MOTORS: list[dict[str, Any]] = [m for m in _DATA.get("motors", []) if isinstance(m, dict)]
_BY_MODEL: dict[str, dict[str, Any]] = {
    str(m["model"]).lower(): m for m in _MOTORS if m.get("model")
}


def all_motors() -> list[dict[str, Any]]:
    """Every catalogued motor (sorted by manufacturer, model)."""
    return _MOTORS


def manufacturers() -> list[str]:
    """Distinct manufacturer names."""
    mans = _DATA.get("manufacturers", [])
    return [str(m) for m in mans] if isinstance(mans, list) else []


def lookup(model: str) -> dict[str, Any] | None:
    """The motor entry for a catalog model name, or None if not found."""
    return _BY_MODEL.get(model.lower()) if model else None


def source() -> str:
    return str(_DATA.get("source", ""))
