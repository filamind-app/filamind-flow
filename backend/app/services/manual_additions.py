"""User-supplied topology nodes the auto-detection can't see.

Some parts never show up in the live Klipper config or ``/machine/system_info`` - a board wired but
not yet configured, a USB-CAN adapter on a bus Moonraker doesn't report, a host display driven
purely by macros. This store lets the user add those by hand so the Machine Map is complete; the
entries are merged onto every topology read (see ``board_topology.apply_manual_additions``).

A single JSON file ``<data_dir>/manual-additions.json`` maps a generated id to the entry
``{kind, ...fields, at}``. Mirrors ``topology_overrides`` (atomic writes, graceful reads)."""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime
from typing import Any

_FILE = "manual-additions.json"
_KINDS = {"mcu", "canbus", "display"}
_MAX_LEN = 200


def _path(data_dir: str) -> str:
    return os.path.join(os.path.expanduser(data_dir), _FILE)


def read_additions(data_dir: str) -> dict[str, dict[str, Any]]:
    """The saved manual entries ``{id: {kind, ...}}`` (empty if missing / unreadable)."""
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
        if isinstance(val, dict) and val.get("kind") in _KINDS:
            out[str(key)] = val
    return out


def _write(data_dir: str, entries: dict[str, dict[str, Any]]) -> None:
    path = _path(data_dir)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(entries, handle, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def _clip(value: Any) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    if len(text) > _MAX_LEN:
        raise ValueError(f"Value too long: {text[:32]}…")
    return text


def _build_entry(req: dict[str, Any]) -> dict[str, Any]:
    """Validate + normalise an incoming manual entry into the stored shape (raises ValueError)."""
    kind = str(req.get("kind") or "")
    if kind not in _KINDS:
        raise ValueError(f"Unknown manual-addition kind {kind!r}")
    entry: dict[str, Any] = {"kind": kind}
    if kind == "mcu":
        name = _clip(req.get("name"))
        if not name:
            raise ValueError("An MCU name is required.")
        entry["name"] = name
        entry["board_id"] = _clip(req.get("board_id"))
        conn = _clip(req.get("connection")) or "unknown"
        entry["connection"] = conn if conn in {"usb", "canbus", "uart", "unknown"} else "unknown"
    elif kind == "canbus":
        iface = _clip(req.get("interface"))
        if not iface:
            raise ValueError("A CAN interface is required.")
        entry["interface"] = iface
        entry["board_id"] = _clip(req.get("board_id"))
    else:  # display
        name = _clip(req.get("name"))
        if not name:
            raise ValueError("A display name is required.")
        entry["name"] = name
        dk = _clip(req.get("display_kind")) or "other"
        entry["display_kind"] = dk if dk in {"touch", "knomi", "other"} else "other"
        entry["detail"] = _clip(req.get("detail"))
    return entry


def add_or_update(data_dir: str, req: dict[str, Any]) -> tuple[str, dict[str, dict[str, Any]]]:
    """Add a manual entry, or replace the one whose id is in ``req`` (edit). Returns (id, store)."""
    entry = _build_entry(req)
    entries = read_additions(data_dir)
    entry_id = _clip(req.get("id"))
    if not entry_id or entry_id not in entries:
        entry_id = "manual-" + uuid.uuid4().hex[:10]
    entry["at"] = datetime.now().isoformat(timespec="seconds")
    entries[entry_id] = entry
    _write(data_dir, entries)
    return entry_id, entries


def remove(data_dir: str, entry_id: str) -> dict[str, dict[str, Any]]:
    """Remove a manual entry by id (a no-op if it's already gone). Returns the full store."""
    key = _clip(entry_id)
    entries = read_additions(data_dir)
    if key and entries.pop(key, None) is not None:
        _write(data_dir, entries)
    return entries
