"""A saved hardware baseline for Board Topology, so a later read can announce what changed —
a board swapped, an MCU added or removed, a connection bus changed, a component count moved.

A single JSON file ``<data_dir>/topology-snapshot.json`` holds a compact per-MCU summary keyed by
the stable config section name (so a serial-path re-enumeration doesn't read as add/remove). Mirrors
the ``topology_overrides`` pattern: atomic write, graceful read.
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Any

_FILE = "topology-snapshot.json"


def _path(data_dir: str) -> str:
    return os.path.join(os.path.expanduser(data_dir), _FILE)


def _summary(mcus: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """A compact, diff-stable per-MCU summary keyed by section name (not the volatile serial id)."""
    out: dict[str, dict[str, Any]] = {}
    for m in mcus:
        name = str(m.get("name") or "")
        if not name:
            continue
        out[name] = {
            "board_id": m.get("board_id"),
            "mcu_id": m.get("mcu_id"),
            "connection": m.get("connection"),
            "components": len(m.get("components") or []),
        }
    return out


def read_snapshot(data_dir: str) -> dict[str, Any] | None:
    """The saved baseline (``{saved_at, mcus}``), or ``None`` if none / unreadable."""
    if not data_dir:
        return None
    try:
        with open(_path(data_dir), encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) and isinstance(data.get("mcus"), dict) else None


def save_snapshot(data_dir: str, mcus: list[dict[str, Any]]) -> dict[str, Any]:
    """Persist the current topology as the new baseline; returns the saved record."""
    snap = {"saved_at": datetime.now().isoformat(timespec="seconds"), "mcus": _summary(mcus)}
    path = _path(data_dir)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(snap, handle, ensure_ascii=False, indent=2)
    os.replace(tmp, path)
    return snap


#: Fields compared between baseline and current, mapped to the change kind they emit.
_FIELD_CHANGES = (
    ("board_id", "board_changed"),
    ("connection", "connection_changed"),
    ("mcu_id", "chip_changed"),
    ("components", "components_changed"),
)


def diff(
    baseline: dict[str, Any] | None, current_mcus: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Structured changes between a saved baseline and the current topology, keyed by MCU name.

    Each change is ``{mcu, kind, before, after}`` — ``kind`` ∈ added / removed / board_changed /
    connection_changed / chip_changed / components_changed. Plain-language rendering is the UI's job
    (so no English leaks into the backend)."""
    base = baseline.get("mcus", {}) if isinstance(baseline, dict) else {}
    cur = _summary(current_mcus)
    changes: list[dict[str, Any]] = []
    for name, c in cur.items():
        b = base.get(name)
        if b is None:
            changes.append({"mcu": name, "kind": "added", "before": None, "after": None})
            continue
        for field, kind in _FIELD_CHANGES:
            if b.get(field) != c.get(field):
                changes.append(
                    {
                        "mcu": name,
                        "kind": kind,
                        "before": None if b.get(field) is None else str(b.get(field)),
                        "after": None if c.get(field) is None else str(c.get(field)),
                    }
                )
    for name in base:
        if name not in cur:
            changes.append({"mcu": name, "kind": "removed", "before": None, "after": None})
    return changes
