"""Last successful driver-tuning action, persisted so the Machine Doctor can tell whether the
motor drivers have been tuned.

Live ``SET_TMC_*`` / ``AUTOTUNE_TMC`` writes are transient (``INIT_TMC`` / a restart reverts them)
and leave no host-side trace, so nothing server-side could otherwise know the user has tuned their
drivers. This records the fact - a small JSON under the data dir - when a live apply or autotune
succeeds. Mirrors :mod:`max_flow_store`'s atomic-write / graceful-read idiom: best-effort, never
raises into a request.
"""

from __future__ import annotations

import contextlib
import json
import os
from datetime import datetime
from typing import Any


def _path(data_dir: str) -> str:
    return os.path.join(os.path.expanduser(data_dir), "drivers-tuned.json")


def write_tuned(data_dir: str, stepper: str, method: str) -> None:
    """Record that a driver was tuned (best-effort; never raises into a request). ``method`` is
    ``apply`` (live current/field write) or ``autotune`` (klipper_tmc_autotune run)."""
    if not data_dir:
        return
    record = {
        "at": datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S"),
        "stepper": stepper,
        "method": method,
    }
    with contextlib.suppress(OSError):
        path = _path(data_dir)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = f"{path}.tmp"
        with open(tmp, "w") as handle:
            json.dump(record, handle, indent=2)
        os.replace(tmp, path)


def read_last(data_dir: str) -> dict[str, Any] | None:
    """The last recorded driver-tuning action, or None (missing / unreadable / corrupt)."""
    try:
        with open(_path(data_dir)) as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def is_tuned(data_dir: str) -> bool:
    """True once at least one driver has been tuned (a valid record with a stepper name exists)."""
    last = read_last(data_dir)
    return bool(last and last.get("stepper"))
