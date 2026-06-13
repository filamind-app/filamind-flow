"""Last Max-Flow run, persisted so the Machine Doctor (and a reopened widget) can read it.

A Max-Flow result otherwise lives only on the in-memory task and the browser's localStorage, so
nothing server-side can fold it into the health report. This mirrors :mod:`version_store`'s
atomic-write / graceful-read idiom: one small JSON under the data dir, best-effort (never raises
into a run).
"""

from __future__ import annotations

import contextlib
import json
import os
from datetime import datetime
from typing import Any


def _path(data_dir: str) -> str:
    return os.path.join(os.path.expanduser(data_dir), "max-flow-last.json")


def write_last(
    data_dir: str,
    result: dict[str, Any],
    hotend: str | None = None,
    expected_max_flow_mm3s: float | None = None,
) -> None:
    """Record the latest run's headline numbers (best-effort; never raises into a run)."""
    record: dict[str, Any] = {
        "at": datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S"),
        "max_flow_mm3s": result.get("max_flow_mm3s"),
        "slip_flow": result.get("slip_flow"),
        "recommend": result.get("recommend"),
        "driver": result.get("driver"),
        "method": result.get("method"),
    }
    if hotend:
        record["hotend"] = hotend
    if isinstance(expected_max_flow_mm3s, (int, float)) and not isinstance(
        expected_max_flow_mm3s, bool
    ):
        record["expected_max_flow_mm3s"] = float(expected_max_flow_mm3s)
    with contextlib.suppress(OSError):
        path = _path(data_dir)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = f"{path}.tmp"
        with open(tmp, "w") as handle:
            json.dump(record, handle, indent=2)
        os.replace(tmp, path)


def read_last(data_dir: str) -> dict[str, Any] | None:
    """The last recorded Max-Flow run, or None (missing / unreadable / corrupt)."""
    try:
        with open(_path(data_dir)) as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None
