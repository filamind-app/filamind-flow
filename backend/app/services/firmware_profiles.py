"""Per-board firmware profiles — each profile is a saved Klipper ``.config``.

A printer has several MCUs (main board, toolhead, a Linux host MCU, …) and each
needs its *own* build configuration, so one shared ``klipper/.config`` is not
enough — Klipper overwrites it on every build. Profiles keep one ``.config`` per
board under the FilaMind data directory, ready to be applied for a build.
"""

from __future__ import annotations

import os
import re
from typing import Any

_PROFILE_NAME_RE = re.compile(r"^[A-Za-z0-9 _.\-]+$")


class ProfileNameError(ValueError):
    """Raised when a profile name is empty, malformed, or path-traversing."""


def validate_name(name: str) -> str:
    """Validates a profile name (guards against path traversal) and returns it."""
    if not name or ".." in name or not _PROFILE_NAME_RE.match(name):
        raise ProfileNameError(
            f"Invalid profile name {name!r}: use letters, digits, spaces, '_', '-', '.'"
        )
    return name


_ARTIFACT_EXTS = ("bin", "uf2", "elf")


def profiles_dir(data_dir: str) -> str:
    """Returns (creating if needed) the directory holding profile ``.config`` files."""
    path = os.path.join(os.path.expanduser(data_dir), "firmware-profiles")
    os.makedirs(path, exist_ok=True)
    return path


def artifacts_dir(data_dir: str) -> str:
    """Returns (creating if needed) the directory holding built firmware artifacts."""
    path = os.path.join(os.path.expanduser(data_dir), "artifacts")
    os.makedirs(path, exist_ok=True)
    return path


def artifact_path_for(data_dir: str, name: str) -> str | None:
    """Returns the path of the first built artifact for a profile, or None."""
    artifacts = artifacts_dir(data_dir)
    for ext in _ARTIFACT_EXTS:
        path = os.path.join(artifacts, f"{name}.{ext}")
        if os.path.isfile(path):
            return path
    return None


def profile_is_built(data_dir: str, name: str) -> bool:
    """True if a built firmware artifact exists for the profile."""
    return artifact_path_for(data_dir, name) is not None


def profile_path(data_dir: str, name: str) -> str:
    """Resolves a profile name to its ``.config`` path (validated)."""
    return os.path.join(profiles_dir(data_dir), f"{validate_name(name)}.config")


def _profile_flags(config_path: str) -> dict[str, bool]:
    """Reads the handful of ``.config`` flags that change how a board is flashed."""
    try:
        with open(config_path) as handle:
            content = handle.read()
    except OSError:
        content = ""
    return {
        "is_can_bridge": "CONFIG_USBCANBUS=y" in content,
        "is_linux": "CONFIG_MACH_LINUX=y" in content,
        "is_avr": "CONFIG_MACH_AVR=y" in content,
    }


def list_profiles(data_dir: str) -> list[dict[str, Any]]:
    """Lists saved profiles with the flags that drive build/flash behaviour."""
    directory = profiles_dir(data_dir)
    profiles: list[dict[str, Any]] = []
    for entry in sorted(os.listdir(directory)):
        if not entry.endswith(".config"):
            continue
        name = entry[: -len(".config")]
        profiles.append(
            {
                "name": name,
                "built": profile_is_built(data_dir, name),
                **_profile_flags(os.path.join(directory, entry)),
            }
        )
    return profiles


def delete_profile(data_dir: str, name: str) -> bool:
    """Deletes a profile's ``.config``. Returns False if it did not exist."""
    path = profile_path(data_dir, name)
    if not os.path.isfile(path):
        return False
    os.remove(path)
    return True
