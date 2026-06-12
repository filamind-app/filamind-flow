"""Backup & restore.

Exports the app's user data as a single ZIP and restores it in one step: the device
registry, every Kconfig profile (+ its metadata), the small per-printer data files
(flash history, motor mapping, topology overrides + snapshot baseline) and the whole
input-shaper archive. Firmware binaries and build artifacts are deliberately left
out -- they rebuild from the profiles -- so a backup stays small and portable: move a
setup to a new host, or recover after a wipe.

Format 2 is a superset of format 1; format-1 archives still restore (they simply
carry fewer entries). Restore is hardened against zip path-traversal: every entry
is matched against a whitelist and rebuilt from validated parts -- nothing from the
archive is ever used as a raw filesystem path.
"""

from __future__ import annotations

import io
import json
import os
import zipfile
from typing import Any

from app.services import devices_store, shaper_archive
from app.services.firmware_profiles import ProfileNameError, profiles_dir, validate_name

_META = "filamind_backup.json"
_FORMAT = 2

#: Small per-printer data files at the data-dir root included in a backup (whitelist --
#: both directions: only these are exported, only these are ever restored).
_DATA_FILES = (
    "flashed.json",
    "motor-mapping.json",
    "topology-overrides.json",
    "topology-snapshot.json",
)


def export_backup(data_dir: str) -> bytes:
    """Builds a ZIP of all user data + a metadata header."""
    root = os.path.expanduser(data_dir)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(_META, json.dumps({"format": _FORMAT, "app": "filamind-flow"}))
        archive.writestr("devices.json", json.dumps(devices_store.read_devices(data_dir), indent=2))

        directory = profiles_dir(data_dir)
        for entry in sorted(os.listdir(directory)):
            if entry.endswith(".config") or entry.endswith(".meta.json"):
                with open(os.path.join(directory, entry), "rb") as handle:
                    archive.writestr(f"profiles/{entry}", handle.read())

        for name in _DATA_FILES:
            path = os.path.join(root, name)
            if os.path.isfile(path):
                with open(path, "rb") as handle:
                    archive.writestr(f"data/{name}", handle.read())

        # The input-shaper archive: the index + every run folder (summaries, CSVs, configs).
        runs = shaper_archive.read_index(data_dir)
        if runs:
            archive.writestr("input-shaper-archive/index.json", json.dumps(runs, indent=2))
        for run in runs:
            run_id = str(run.get("id", ""))
            for filename in run.get("files", []):
                src = shaper_archive.run_file_path(data_dir, run_id, str(filename))
                if src and os.path.isfile(src):
                    with open(src, "rb") as handle:
                        archive.writestr(f"input-shaper-archive/{run_id}/{filename}", handle.read())
    return buffer.getvalue()


def _restore_profiles(archive: zipfile.ZipFile, names: set[str], data_dir: str) -> list[str]:
    restored: set[str] = set()
    for name in sorted(names):
        if not name.startswith("profiles/"):
            continue
        base = os.path.basename(name)
        if base.endswith(".config"):
            stem, suffix = base[: -len(".config")], ".config"
        elif base.endswith(".meta.json"):
            stem, suffix = base[: -len(".meta.json")], ".meta.json"
        else:
            continue
        try:
            validate_name(stem)
        except ProfileNameError:
            continue  # skip anything with an unsafe profile name
        target = os.path.join(profiles_dir(data_dir), f"{stem}{suffix}")
        with open(target, "wb") as handle:
            handle.write(archive.read(name))
        if suffix == ".config":
            restored.add(stem)
    return sorted(restored)


def _restore_data_files(archive: zipfile.ZipFile, names: set[str], data_dir: str) -> list[str]:
    root = os.path.expanduser(data_dir)
    os.makedirs(root, exist_ok=True)
    restored: list[str] = []
    for filename in _DATA_FILES:
        entry = f"data/{filename}"
        if entry not in names:
            continue
        try:
            json.loads(archive.read(entry))
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue  # a corrupt entry must not clobber a good live file
        with open(os.path.join(root, filename), "wb") as handle:
            handle.write(archive.read(entry))
        restored.append(filename)
    return restored


def _restore_shaper_archive(archive: zipfile.ZipFile, names: set[str], data_dir: str) -> int:
    index_entry = "input-shaper-archive/index.json"
    if index_entry not in names:
        return 0
    try:
        runs = json.loads(archive.read(index_entry))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return 0
    if not isinstance(runs, list):
        return 0

    restored = 0
    valid_runs: list[dict[str, Any]] = []
    for run in runs:
        if not isinstance(run, dict):
            continue
        try:
            run_id = shaper_archive.validate_run_id(str(run.get("id", "")))
        except shaper_archive.ArchiveError:
            continue
        run_dir = os.path.join(shaper_archive.archive_dir(data_dir), run_id)
        os.makedirs(run_dir, exist_ok=True)
        for filename in run.get("files", []):
            try:
                safe = shaper_archive.validate_filename(str(filename))
            except shaper_archive.ArchiveError:
                continue
            entry = f"input-shaper-archive/{run_id}/{safe}"
            if entry not in names:
                continue
            with open(os.path.join(run_dir, safe), "wb") as handle:
                handle.write(archive.read(entry))
        valid_runs.append(run)
        restored += 1

    if valid_runs:
        # Merge with whatever the live index already lists (restored ids win).
        existing = {str(r.get("id")): r for r in shaper_archive.read_index(data_dir)}
        for run in valid_runs:
            existing[str(run.get("id"))] = run
        merged = sorted(existing.values(), key=lambda r: str(r.get("at", "")))
        shaper_archive._write_index(data_dir, merged)
    return restored


def import_backup(data_dir: str, blob: bytes) -> dict[str, Any]:
    """Restores everything a backup ZIP carries (format 1 or 2). Returns a summary."""
    try:
        archive = zipfile.ZipFile(io.BytesIO(blob))
    except zipfile.BadZipFile as exc:
        raise ValueError("Not a valid ZIP backup.") from exc

    with archive:
        names = set(archive.namelist())
        if _META not in names:
            raise ValueError("Not a FilaMind backup (metadata header missing).")

        restored_profiles = _restore_profiles(archive, names, data_dir)
        restored_data = _restore_data_files(archive, names, data_dir)
        restored_runs = _restore_shaper_archive(archive, names, data_dir)

        restored_devices = False
        if "devices.json" in names:
            try:
                data = json.loads(archive.read("devices.json"))
            except json.JSONDecodeError as exc:
                raise ValueError("Backup devices.json is corrupt.") from exc
            if isinstance(data, list):
                devices_store.write_devices(data_dir, data)
                restored_devices = True

    return {
        "restored_devices": restored_devices,
        "restored_profiles": restored_profiles,
        "restored_data": restored_data,
        "restored_runs": restored_runs,
    }
