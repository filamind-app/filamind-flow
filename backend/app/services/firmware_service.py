from __future__ import annotations

import os
import shutil
from typing import Any

import httpx

from app.services.moonraker_client import MoonrakerClient


def _normalize(version: str | None) -> str:
    """Drops the ``-dirty`` suffix so a clean build matches a dirty checkout."""
    return (version or "").removesuffix("-dirty")


def _scan_tools(klipper_dir: str, katapult_dir: str) -> dict[str, bool]:
    """Checks the local firmware toolchain (read-only)."""
    klipper = os.path.expanduser(klipper_dir)
    katapult = os.path.expanduser(katapult_dir)
    return {
        "klipper": os.path.isdir(klipper),
        "katapult": os.path.isdir(katapult),
        "flashtool": os.path.isfile(os.path.join(katapult, "scripts", "flashtool.py")),
        "dfu_util": shutil.which("dfu-util") is not None,
        "avrdude": shutil.which("avrdude") is not None,
        "can_utils": shutil.which("cansend") is not None,
    }


async def gather_status(moonraker_url: str, klipper_dir: str, katapult_dir: str) -> dict[str, Any]:
    """Read-only firmware status: host + per-MCU versions, sync check, tool readiness."""
    client = MoonrakerClient(moonraker_url)
    host_version: str | None = None
    state: str | None = None
    mcus: list[dict[str, Any]] = []
    reachable = True

    try:
        info = await client.get_printer_info()
        sw = info.get("software_version")
        host_version = sw if isinstance(sw, str) else None
        st = info.get("state")
        state = st if isinstance(st, str) else None

        names = await client.list_objects()
        mcu_names = [n for n in names if n == "mcu" or n.startswith("mcu ")]
        status = await client.query_objects(mcu_names)

        for name in mcu_names:
            obj = status.get(name)
            obj = obj if isinstance(obj, dict) else {}
            ver = obj.get("mcu_version")
            ver = ver if isinstance(ver, str) else None
            label = name[4:] if name.startswith("mcu ") else "mcu"
            in_sync = (
                _normalize(ver) == _normalize(host_version) if (ver and host_version) else None
            )
            mcus.append({"name": label, "version": ver, "in_sync": in_sync})
    except httpx.HTTPError:
        reachable = False

    return {
        "reachable": reachable,
        "host": {"version": host_version, "state": state},
        "mcus": mcus,
        "tools": _scan_tools(klipper_dir, katapult_dir),
    }
