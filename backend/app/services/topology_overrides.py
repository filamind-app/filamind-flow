"""Persistent per-MCU board overrides for Board Topology.

The topology suggests a catalog board for each MCU from its serial / CAN signature plus a pin-map
fingerprint, but a serial id usually reveals only the chip — so the suggestion can be absent or
wrong. This store lets the user *confirm* the suggestion or pick the correct board; the choice is
remembered across reboots and applied on every topology read (the first write path in the
otherwise read-only widget).

A single JSON file ``<data_dir>/topology-overrides.json`` maps each MCU's stable section name
(unique within a Klipper config) to the chosen ``board_id``. Mirrors the ``motor_mapping`` /
``shaper_archive`` patterns: atomic writes, graceful reads.
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Any

_FILE = "topology-overrides.json"
_MAX_KEY_LEN = 200


def _path(data_dir: str) -> str:
    return os.path.join(os.path.expanduser(data_dir), _FILE)


def read_overrides(data_dir: str) -> dict[str, dict[str, Any]]:
    """The saved per-MCU board overrides ``{mcu_name: {board_id, at}}`` (empty if missing)."""
    if not data_dir:
        return {}
    try:
        with open(_path(data_dir), encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(data, dict):
        return {}
    out: dict[str, dict[str, Any]] = {}
    for key, val in data.items():
        if isinstance(val, dict) and val.get("board_id"):
            out[str(key)] = {"board_id": str(val["board_id"]), "at": val.get("at")}
    return out


def _write(data_dir: str, overrides: dict[str, dict[str, Any]]) -> None:
    path = _path(data_dir)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(overrides, handle, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def _validate_key(mcu_name: str) -> str:
    name = (mcu_name or "").strip()
    if not name or len(name) > _MAX_KEY_LEN:
        raise ValueError(f"Invalid mcu name {mcu_name!r}")
    return name


def set_override(data_dir: str, mcu_name: str, board_id: str) -> dict[str, dict[str, Any]]:
    """Record (or replace) the board the user assigned to an MCU. Returns the full override map."""
    name = _validate_key(mcu_name)
    if not (board_id or "").strip():
        raise ValueError("board_id is required")
    overrides = read_overrides(data_dir)
    overrides[name] = {"board_id": board_id, "at": datetime.now().isoformat(timespec="seconds")}
    _write(data_dir, overrides)
    return overrides


def clear_override(data_dir: str, mcu_name: str) -> dict[str, dict[str, Any]]:
    """Remove an MCU's override (revert to the auto suggestion). Returns the full override map."""
    name = _validate_key(mcu_name)
    overrides = read_overrides(data_dir)
    if overrides.pop(name, None) is not None:
        _write(data_dir, overrides)
    return overrides
