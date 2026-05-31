"""Backup & restore.

Exports the device registry + every Kconfig profile as a single ZIP, and restores
them. Firmware binaries are deliberately left out — they rebuild from the profiles
— so a backup is small and portable: move a setup to a new host, or recover after
a wipe. Restore is hardened against zip path-traversal: only ``devices.json`` and
validated ``profiles/<name>.config`` entries are ever written.
"""

from __future__ import annotations

import io
import json
import os
import zipfile
from typing import Any

from app.services import devices_store
from app.services.firmware_profiles import ProfileNameError, profiles_dir, validate_name

_META = "filamind_backup.json"
_FORMAT = 1


def export_backup(data_dir: str) -> bytes:
    """Builds a ZIP of devices.json + all profiles + a metadata header."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(_META, json.dumps({"format": _FORMAT, "app": "filamind-flow"}))
        archive.writestr("devices.json", json.dumps(devices_store.read_devices(data_dir), indent=2))
        directory = profiles_dir(data_dir)
        for entry in sorted(os.listdir(directory)):
            if entry.endswith(".config"):
                with open(os.path.join(directory, entry)) as handle:
                    archive.writestr(f"profiles/{entry}", handle.read())
    return buffer.getvalue()


def import_backup(data_dir: str, blob: bytes) -> dict[str, Any]:
    """Restores devices.json + profiles from a backup ZIP. Returns a summary."""
    try:
        archive = zipfile.ZipFile(io.BytesIO(blob))
    except zipfile.BadZipFile as exc:
        raise ValueError("Not a valid ZIP backup.") from exc

    restored_profiles: list[str] = []
    restored_devices = False
    with archive:
        names = set(archive.namelist())
        if _META not in names:
            raise ValueError("Not a FilaMind backup (metadata header missing).")

        for name in sorted(names):
            if not name.startswith("profiles/") or not name.endswith(".config"):
                continue
            base = os.path.basename(name)[: -len(".config")]
            try:
                validate_name(base)
            except ProfileNameError:
                continue  # skip anything with an unsafe profile name
            target = os.path.join(profiles_dir(data_dir), f"{base}.config")
            with open(target, "wb") as handle:
                handle.write(archive.read(name))
            restored_profiles.append(base)

        if "devices.json" in names:
            try:
                data = json.loads(archive.read("devices.json"))
            except json.JSONDecodeError as exc:
                raise ValueError("Backup devices.json is corrupt.") from exc
            if isinstance(data, list):
                devices_store.write_devices(data_dir, data)
                restored_devices = True

    return {"restored_devices": restored_devices, "restored_profiles": sorted(restored_profiles)}
