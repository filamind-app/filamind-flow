"""Persistent motor↔stepper mapping for the Motor Drivers picker.

Stores which catalogued motor the user assigned to each stepper, in
``<data_dir>/motor-mapping.json`` (``{stepper_name: motor_model}``). The live config
keeps owning currents/registers; this is purely the user's "this stepper runs this
motor" annotation — used to surface the motor's datasheet specs and (later) drive
current/register recommendations.
"""

from __future__ import annotations

import json
import os


def _path(data_dir: str) -> str:
    return os.path.join(os.path.expanduser(data_dir), "motor-mapping.json")


def read_mapping(data_dir: str) -> dict[str, str]:
    """The saved ``{stepper: motor_model}`` map (empty if none / unreadable)."""
    try:
        with open(_path(data_dir)) as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(k): str(v) for k, v in data.items() if isinstance(v, str) and v}


def assign(data_dir: str, stepper: str, motor_model: str | None) -> dict[str, str]:
    """Assigns a motor to ``stepper`` — or clears it when ``motor_model`` is falsy.

    Returns the updated mapping. Writes atomically (tmp + replace).
    """
    mapping = read_mapping(data_dir)
    if motor_model:
        mapping[stepper] = motor_model
    else:
        mapping.pop(stepper, None)

    path = _path(data_dir)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.tmp"
    with open(tmp, "w") as handle:
        json.dump(mapping, handle, indent=2)
    os.replace(tmp, path)
    return mapping
