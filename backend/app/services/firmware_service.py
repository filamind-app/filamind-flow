from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
from typing import Any

import httpx

from app.services.moonraker_client import MoonrakerClient

#: A Klipper 'Linux process' MCU connects over this host Unix socket.
_HOST_MCU_SOCKET = "klipper_host_mcu"


def _normalize(version: str | None) -> str:
    """Drops the ``-dirty`` suffix so a clean build matches a dirty checkout."""
    return (version or "").removesuffix("-dirty")


def _classify_mcu(settings: dict[str, Any], config_key: str) -> str:
    """Derives an MCU's connection kind from its parsed Klipper config section."""
    section = settings.get(config_key)
    section = section if isinstance(section, dict) else {}
    serial = str(section.get("serial") or "")
    if _HOST_MCU_SOCKET in serial.lower():
        return "host"
    if section.get("canbus_uuid"):
        return "canbus"
    if serial:
        return "usb"
    return "serial"


def _klipper_mcu_service_active() -> bool:
    """True if the host's ``klipper-mcu`` (Linux-process MCU) service is running.

    Returns False off systemd hosts (e.g. dev machines) instead of raising.
    """
    try:
        result = subprocess.run(
            ["systemctl", "is-active", "klipper-mcu"],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return result.stdout.strip() == "active"


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
        status = await client.query_objects([*mcu_names, "configfile"])

        configfile = status.get("configfile")
        configfile = configfile if isinstance(configfile, dict) else {}
        settings = configfile.get("settings")
        settings = settings if isinstance(settings, dict) else {}

        for name in mcu_names:
            obj = status.get(name)
            obj = obj if isinstance(obj, dict) else {}
            ver = obj.get("mcu_version")
            ver = ver if isinstance(ver, str) else None
            label = name[4:] if name.startswith("mcu ") else "mcu"
            in_sync = (
                _normalize(ver) == _normalize(host_version) if (ver and host_version) else None
            )
            mcus.append(
                {
                    "name": label,
                    "version": ver,
                    "in_sync": in_sync,
                    "kind": _classify_mcu(settings, name),
                }
            )
    except httpx.HTTPError:
        reachable = False

    # The Linux-process host MCU is independent of Moonraker reachability.
    service_active = await asyncio.to_thread(_klipper_mcu_service_active)
    return {
        "reachable": reachable,
        "host": {"version": host_version, "state": state},
        "mcus": mcus,
        "host_mcu": {
            "configured": any(m["kind"] == "host" for m in mcus),
            "service_active": service_active,
        },
        "tools": _scan_tools(klipper_dir, katapult_dir),
    }
