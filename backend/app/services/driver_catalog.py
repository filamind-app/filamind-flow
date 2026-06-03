"""The curated TMC driver capability map.

Loads ``app/data/driver_catalog.json`` (interface, current cap, chopper modes,
StallGuard field, sensorless / temperature support per model) and indexes it by model
name + aliases so a detected driver can be annotated with authoritative reference data.
Read once at import — it's small, static reference data.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_CATALOG_PATH = Path(__file__).resolve().parent.parent / "data" / "driver_catalog.json"


def _load() -> dict[str, Any]:
    try:
        with _CATALOG_PATH.open(encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return {"source": "", "drivers": []}
    return data if isinstance(data, dict) else {"source": "", "drivers": []}


def _index(drivers: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Maps every model name and alias (lower-case) to its catalog entry."""
    by_model: dict[str, dict[str, Any]] = {}
    for entry in drivers:
        model = str(entry.get("model", "")).lower()
        if model:
            by_model[model] = entry
        aliases = entry.get("aliases")
        if isinstance(aliases, list):
            for alias in aliases:
                by_model[str(alias).lower()] = entry
    return by_model


_DATA = _load()
_DRIVERS: list[dict[str, Any]] = [d for d in _DATA.get("drivers", []) if isinstance(d, dict)]
_BY_MODEL = _index(_DRIVERS)


def lookup(model: str) -> dict[str, Any] | None:
    """The catalog entry for a Klipper driver model (e.g. 'tmc2209'), or None if unknown."""
    return _BY_MODEL.get(model.lower())


def all_drivers() -> list[dict[str, Any]]:
    """Every catalog entry — the full capability map."""
    return _DRIVERS


def source() -> str:
    """Provenance note for the catalog."""
    return str(_DATA.get("source", ""))
