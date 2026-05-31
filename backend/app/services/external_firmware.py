"""External firmware — register pre-built firmware files (``.bin`` / ``.uf2`` /
``.elf`` / ``.hex``) that were produced *elsewhere* and flash them directly,
each with its own editable flash properties.

Unlike a *profile* (which FilaMind builds from Kconfig), an external firmware is
a binary the user brings in. We store the bytes under ``<data_dir>/external-firmware/``
next to a ``<name>.meta.json`` sidecar holding the editable properties (a display
label, flash method, bootloader offset, CAN interface, notes). No build step is
involved — the file is flashed as-is.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any

_NAME_RE = re.compile(r"^[A-Za-z0-9 _.\-]+$")
#: Firmware binary extensions we accept (lowercase, no dot).
ALLOWED_EXTS = ("bin", "uf2", "elf", "hex")


class ExternalNameError(ValueError):
    """Raised when an external-firmware name is empty, malformed, or traversing."""


def validate_name(name: str) -> str:
    """Validates a firmware name (guards path traversal) and returns it."""
    if not name or ".." in name or not _NAME_RE.match(name):
        raise ExternalNameError(
            f"Invalid name {name!r}: use letters, digits, spaces, '_', '-', '.'"
        )
    return name


def external_dir(data_dir: str) -> str:
    """Returns (creating if needed) the directory holding external firmware."""
    path = os.path.join(os.path.expanduser(data_dir), "external-firmware")
    os.makedirs(path, exist_ok=True)
    return path


def _meta_path(data_dir: str, name: str) -> str:
    return os.path.join(external_dir(data_dir), f"{validate_name(name)}.meta.json")


def firmware_path(data_dir: str, name: str) -> str | None:
    """Resolves a name to its stored firmware file (any allowed extension), or None."""
    directory = external_dir(data_dir)
    for ext in ALLOWED_EXTS:
        path = os.path.join(directory, f"{validate_name(name)}.{ext}")
        if os.path.isfile(path):
            return path
    return None


#: Klipper stamps its git version into the firmware, e.g. ``v0.12.0-345-gabcd123``.
_VERSION_RE = re.compile(rb"v\d+\.\d+\.\d+(?:-\d+-g[0-9a-f]{6,})?(?:-dirty)?")
#: MCU family tokens that may appear in the binary's strings (best-effort).
_MCU_TOKENS = (
    b"stm32",
    b"rp2040",
    b"atmega",
    b"sam3",
    b"samd",
    b"same5",
    b"lpc176",
    b"hc32",
    b"ar100",
)


def inspect_firmware(path: str) -> dict[str, Any]:
    """Best-effort read of properties embedded in a firmware binary by scanning its
    printable strings — the Klipper git version and an MCU-family hint."""
    info: dict[str, Any] = {"detected_version": None, "detected_mcu": None}
    try:
        with open(path, "rb") as handle:
            data = handle.read(8_000_000)
    except OSError:
        return info
    version = _VERSION_RE.search(data)
    if version:
        info["detected_version"] = version.group(0).decode("ascii", "replace")
    low = data.lower()
    for token in _MCU_TOKENS:
        idx = low.find(token)
        if idx == -1:
            continue
        end = idx
        while end < len(low) and end < idx + 14 and chr(low[end]).isalnum():
            end += 1
        info["detected_mcu"] = data[idx:end].decode("ascii", "replace")
        break
    return info


def _default_meta(name: str) -> dict[str, Any]:
    return {
        "name": name,
        "label": name,
        "method": "serial",
        "offset": "",
        "interface": "can0",
        "notes": "",
        "detected_version": None,
        "detected_mcu": None,
        "inspected": False,
    }


def read_meta(data_dir: str, name: str) -> dict[str, Any]:
    """Reads a firmware's metadata sidecar, falling back to sensible defaults."""
    try:
        with open(_meta_path(data_dir, name)) as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError):
        data = {}
    return {**_default_meta(name), **(data if isinstance(data, dict) else {}), "name": name}


def _write_meta(data_dir: str, name: str, meta: dict[str, Any]) -> None:
    path = _meta_path(data_dir, name)
    tmp = f"{path}.tmp"
    with open(tmp, "w") as handle:
        json.dump(meta, handle, indent=2)
    os.replace(tmp, path)


#: Properties the user may edit; everything else is ignored on update.
_EDITABLE = ("label", "method", "offset", "interface", "notes")


def save_firmware(
    data_dir: str, name: str, ext: str, blob: bytes, meta: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Stores uploaded firmware bytes as ``<name>.<ext>`` plus a metadata sidecar."""
    validate_name(name)
    ext = ext.lower().lstrip(".")
    if ext not in ALLOWED_EXTS:
        raise ExternalNameError(
            f"Unsupported firmware type '.{ext}' (use {', '.join(ALLOWED_EXTS)})"
        )
    directory = external_dir(data_dir)
    # Drop any prior file for this name under a different extension.
    for other in ALLOWED_EXTS:
        prior = os.path.join(directory, f"{name}.{other}")
        if other != ext and os.path.isfile(prior):
            os.remove(prior)
    with open(os.path.join(directory, f"{name}.{ext}"), "wb") as handle:
        handle.write(blob)
    merged = {**_default_meta(name), **{k: v for k, v in (meta or {}).items() if k in _EDITABLE}}
    _write_meta(data_dir, name, merged)
    return list_one(data_dir, name)


def update_meta(data_dir: str, name: str, patch: dict[str, Any]) -> dict[str, Any]:
    """Updates a firmware's editable properties. Raises FileNotFoundError if absent."""
    if firmware_path(data_dir, name) is None:
        raise FileNotFoundError(name)
    meta = read_meta(data_dir, name)
    meta.update({k: v for k, v in patch.items() if k in _EDITABLE})
    _write_meta(data_dir, name, meta)
    return list_one(data_dir, name)


def delete_firmware(data_dir: str, name: str) -> bool:
    """Deletes a firmware file and its metadata. False if it did not exist."""
    path = firmware_path(data_dir, name)
    if path is None:
        return False
    os.remove(path)
    meta = _meta_path(data_dir, name)
    if os.path.isfile(meta):
        os.remove(meta)
    return True


def list_one(data_dir: str, name: str) -> dict[str, Any]:
    """One firmware's metadata enriched with its file name + size + read properties.

    Embedded properties are inspected once (best-effort) and cached in the sidecar.
    """
    path = firmware_path(data_dir, name)
    meta = read_meta(data_dir, name)
    if path and not meta.get("inspected"):
        meta.update(inspect_firmware(path))
        meta["inspected"] = True
        _write_meta(data_dir, name, meta)
    meta["filename"] = os.path.basename(path) if path else None
    meta["size"] = os.path.getsize(path) if path else 0
    return meta


def list_external(data_dir: str) -> list[dict[str, Any]]:
    """Lists every registered external firmware (metadata + filename + size)."""
    directory = external_dir(data_dir)
    names: set[str] = set()
    for entry in os.listdir(directory):
        for ext in ALLOWED_EXTS:
            if entry.endswith(f".{ext}"):
                names.add(entry[: -len(ext) - 1])
    return [list_one(data_dir, n) for n in sorted(names)]
