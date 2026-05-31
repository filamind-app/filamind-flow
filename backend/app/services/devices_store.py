"""Devices — a saved registry of the printer's boards and how to flash each.

Board *discovery* (``board_service``) reports what is on the bus right now; the
registry remembers your *intent*: which build profile belongs to each board, how to
reach it (method, baudrate, CAN interface), and the separate bootloader identity
a board takes on when it drops into Katapult or DFU to be flashed (a board often
enumerates under a *different* id while in its bootloader, so we store both).

Persisted as a JSON list under ``<data_dir>/devices.json`` with atomic writes. The
firmware *version* of each device is deliberately not stored here — it is read
back from the flash records in ``version_store`` so there is one source of truth.
"""

from __future__ import annotations

import json
import os
from typing import Any

#: Every field a device carries, with its default. Unknown keys are
#: dropped on normalise so a stray ``old_id`` never lands in devices.json.
_DEVICE_DEFAULTS: dict[str, Any] = {
    "id": "",
    "name": "",
    "profile": None,
    #: serial / can / dfu / linux / beacon.
    "method": "serial",
    "interface": "can0",
    "baudrate": 250000,
    "notes": "",
    "is_katapult": True,
    "is_bridge": False,
    #: The board's Katapult serial / DFU bootloader identity, when distinct.
    "serial_id": None,
    "dfu_id": None,
    "exclude_from_batch": False,
    "custom_make_command": None,
}


def devices_path(data_dir: str) -> str:
    """The device registry file (``<data_dir>/devices.json``)."""
    return os.path.join(os.path.expanduser(data_dir), "devices.json")


def _normalise(device: dict[str, Any]) -> dict[str, Any]:
    """Returns the device with exactly the known fields, each defaulted."""
    merged = {**_DEVICE_DEFAULTS, **device}
    return {key: merged[key] for key in _DEVICE_DEFAULTS}


def read_devices(data_dir: str) -> list[dict[str, Any]]:
    """Returns the saved devices (empty if none / unreadable). Skips id-less rows."""
    try:
        with open(devices_path(data_dir)) as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(data, list):
        return []
    return [_normalise(d) for d in data if isinstance(d, dict) and d.get("id")]


def write_devices(data_dir: str, devices: list[dict[str, Any]]) -> None:
    """Atomically writes the device registry."""
    path = devices_path(data_dir)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.tmp"
    with open(tmp, "w") as handle:
        json.dump([_normalise(d) for d in devices], handle, indent=2)
    os.replace(tmp, path)


def get_device(data_dir: str, device_id: str) -> dict[str, Any] | None:
    """Returns a single device by id, or None."""
    for device in read_devices(data_dir):
        if device["id"] == device_id:
            return device
    return None


def save_device(data_dir: str, device: dict[str, Any], old_id: str | None = None) -> dict[str, Any]:
    """Inserts or updates a device, matched by ``old_id`` (for renames) or its id."""
    record = _normalise(device)
    key = old_id or record["id"]
    devices = read_devices(data_dir)
    for index, existing in enumerate(devices):
        if existing["id"] == key:
            devices[index] = record
            break
    else:
        devices.append(record)
    write_devices(data_dir, devices)
    return record


def remove_device(data_dir: str, device_id: str) -> bool:
    """Removes a device from the registry. Returns False if it was not present."""
    devices = read_devices(data_dir)
    kept = [d for d in devices if d["id"] != device_id]
    if len(kept) == len(devices):
        return False
    write_devices(data_dir, kept)
    return True


def rename_profile_refs(data_dir: str, old: str, new: str) -> int:
    """Rewrites every device whose ``profile`` is ``old`` to ``new``. Returns count."""
    devices = read_devices(data_dir)
    changed = [d for d in devices if d.get("profile") == old]
    for device in changed:
        device["profile"] = new
    if changed:
        write_devices(data_dir, devices)
    return len(changed)


def attach_identity(
    data_dir: str, device_id: str, hardware_id: str, kind: str
) -> dict[str, Any] | None:
    """Binds a discovered bootloader identity (``serial`` / ``dfu``) to a device.

    Returns the updated device, or None if no device has ``device_id``.
    """
    field = "dfu_id" if kind == "dfu" else "serial_id"
    devices = read_devices(data_dir)
    for device in devices:
        if device["id"] == device_id:
            device[field] = hardware_id
            write_devices(data_dir, devices)
            return device
    return None


def managed_identities(data_dir: str) -> set[str]:
    """Every identity the registry claims — runtime ids plus bootloader ids.

    Lets board discovery flag which scanned boards are already in the registry.
    """
    identities: set[str] = set()
    for device in read_devices(data_dir):
        for key in ("id", "serial_id", "dfu_id"):
            value = device.get(key)
            if value:
                identities.add(str(value))
    return identities
