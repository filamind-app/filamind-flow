"""Board discovery — finds every flashable MCU on any printer.

Boards are discovered from four independent sources and merged by identity so a
single physical board appears once, enriched with whatever each source knows:

* **Moonraker** — the configured ``[mcu]`` sections (name, running firmware
  version, serial / CAN UUID identity). Tells us what is *in service*.
* **USB / serial** — ``/dev/serial/by-id`` + ``ttyACM``/``ttyUSB``. The by-id
  name reveals the mode: a ``klipper``/``kalico`` device is running firmware, a
  ``katapult``/``canboot`` device sits in its bootloader ready to flash.
* **CAN** — Katapult's ``flashtool.py -q`` on each ``can`` interface.
* **DFU** — ``dfu-util -l`` (boards sitting in the STM32 ROM bootloader).

Everything is read-only: discovery only *queries* buses, it never flashes.
"""

from __future__ import annotations

import asyncio
import glob
import os
import re
from typing import Any

import httpx

from app.services import fleet_store
from app.services.firmware_service import _klipper_mcu_service_active
from app.services.moonraker_client import MoonrakerClient
from app.services.version_store import flashed_version

_SERVICE_HINTS = ("klipper", "kalico")
_BOOTLOADER_HINTS = ("katapult", "canboot")
_HOST_MCU_SOCKET = "klipper_host_mcu"
_UUID_RE = re.compile(r"^[0-9a-f]{12}$")


def _classify_serial_mode(by_id_name: str) -> str:
    """Maps a /dev/serial/by-id name to a board mode."""
    low = by_id_name.lower()
    if any(h in low for h in _BOOTLOADER_HINTS):
        return "ready"
    if any(h in low for h in _SERVICE_HINTS):
        return "service"
    return "unknown"


def _parse_dfu_line(line: str) -> dict[str, str] | None:
    """Parses one ``dfu-util -l`` 'Found DFU:' line into a board dict."""
    if "Found DFU:" not in line:
        return None
    vid_pid = ""
    if "[" in line and "]" in line:
        vid_pid = line.split("[", 1)[1].split("]", 1)[0]
    serial = line.split('serial="', 1)[1].split('"', 1)[0] if 'serial="' in line else ""
    path = line.split('path="', 1)[1].split('"', 1)[0] if 'path="' in line else ""
    dev_id = serial if (serial and serial != "UNKNOWN") else path
    if not dev_id:
        return None
    name = f"DFU [{vid_pid}]" if vid_pid else "DFU device"
    if serial:
        name += f" · S/N {serial}"
    return {"id": dev_id, "name": name, "vid_pid": vid_pid}


def _serial_identity(serial: str) -> str:
    """A stable identity for a serial path (resolves by-id symlinks)."""
    return os.path.realpath(serial) if os.path.exists(serial) else serial


async def _moonraker_mcus(moonraker_url: str) -> dict[str, dict[str, Any]]:
    """Configured MCUs keyed by identity (serial realpath / CAN uuid / host)."""
    client = MoonrakerClient(moonraker_url)
    out: dict[str, dict[str, Any]] = {}
    try:
        names = await client.list_objects()
        mcu_names = [n for n in names if n == "mcu" or n.startswith("mcu ")]
        data = await client.query_objects([*mcu_names, "configfile"])
        configfile = data.get("configfile")
        settings = configfile.get("settings") if isinstance(configfile, dict) else None
        settings = settings if isinstance(settings, dict) else {}
        for name in mcu_names:
            label = name[4:] if name.startswith("mcu ") else "mcu"
            obj = data.get(name)
            obj = obj if isinstance(obj, dict) else {}
            version = obj.get("mcu_version")
            version = version if isinstance(version, str) else None
            section = settings.get(name)
            section = section if isinstance(section, dict) else {}
            serial = str(section.get("serial") or "")
            canbus = section.get("canbus_uuid")
            if canbus:
                identity, connection = str(canbus).lower(), "can"
            elif _HOST_MCU_SOCKET in serial.lower():
                identity, connection = "linux_process", "linux"
            elif serial:
                identity, connection = _serial_identity(serial), "usb"
            else:
                identity, connection = label, "serial"
            out[identity] = {
                "mcu_name": label,
                "version": version,
                "connection": connection,
                "serial": serial or None,
                "canbus_uuid": str(canbus) if canbus else None,
            }
    except httpx.HTTPError:
        pass
    return out


def _scan_serial() -> list[dict[str, str]]:
    """USB/serial boards from /dev/serial/by-id and raw ttyACM/ttyUSB nodes."""
    boards: list[dict[str, str]] = []
    seen: set[str] = set()
    by_id = [d for d in glob.glob("/dev/serial/by-id/*") if "Beacon_Beacon_Rev" not in d]
    for dev in by_id:
        real = os.path.realpath(dev)
        if real in seen:
            continue
        seen.add(real)
        boards.append(
            {
                "identity": real,
                "id": dev,
                "name": os.path.basename(dev),
                "connection": "usb",
                "mode": _classify_serial_mode(dev),
            }
        )
    for dev in sorted(glob.glob("/dev/ttyACM*") + glob.glob("/dev/ttyUSB*")):
        real = os.path.realpath(dev)
        if real in seen:
            continue
        seen.add(real)
        boards.append(
            {
                "identity": real,
                "id": dev,
                "name": os.path.basename(dev),
                "connection": "usb",
                "mode": "unknown",
            }
        )
    return boards


async def _run(cmd: list[str], timeout: float) -> str:
    """Runs a command, returning stdout (empty string on any failure)."""
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except (OSError, asyncio.TimeoutError, NotImplementedError):
        # Missing binary, timeout, or a loop without subprocess support (Windows tests).
        return ""
    return stdout.decode(errors="replace")


async def _scan_dfu() -> list[dict[str, str]]:
    """Boards sitting in DFU (STM32 ROM bootloader) mode."""
    boards: list[dict[str, str]] = []
    seen: set[str] = set()
    for line in (await _run(["dfu-util", "-l"], 5.0)).splitlines():
        parsed = _parse_dfu_line(line)
        if parsed and parsed["id"] not in seen:
            seen.add(parsed["id"])
            boards.append(
                {
                    "identity": f"dfu:{parsed['id']}",
                    "id": parsed["id"],
                    "name": parsed["name"],
                    "connection": "dfu",
                    "mode": "dfu",
                }
            )
    return boards


async def _list_can_interfaces() -> list[str]:
    """Lists CAN network interfaces via ``ip``."""
    interfaces: list[str] = []
    for line in (await _run(["ip", "-o", "link", "show", "type", "can"], 3.0)).splitlines():
        match = re.match(r"\d+:\s*([^:@\s]+)", line)
        if match:
            interfaces.append(match.group(1))
    return interfaces


async def _scan_can(klipper_dir: str, katapult_dir: str) -> list[dict[str, str]]:
    """CAN boards via Katapult's flashtool query on each CAN interface."""
    flashtool = os.path.join(os.path.expanduser(katapult_dir), "scripts", "flashtool.py")
    if not os.path.isfile(flashtool):
        return []
    boards: list[dict[str, str]] = []
    seen: set[str] = set()
    for iface in await _list_can_interfaces():
        out = await _run(["python3", flashtool, "-i", iface, "-q"], 6.0)
        for line in out.splitlines():
            if "UUID:" not in line:
                continue
            parts = line.replace("Detected UUID:", "UUID:").split(",")
            uuid = parts[0].split("UUID:", 1)[1].strip().lower()
            if not _UUID_RE.match(uuid) or uuid in seen:
                continue
            seen.add(uuid)
            app = "Unknown"
            for part in parts[1:]:
                if "Application:" in part:
                    app = part.split("Application:", 1)[1].strip()
            mode = "ready" if app.lower() in ("katapult", "canboot") else "service"
            boards.append(
                {
                    "identity": uuid,
                    "id": uuid,
                    "name": f"CAN {uuid}",
                    "connection": "can",
                    "mode": mode,
                    "application": app,
                    "interface": iface,
                }
            )
    return boards


def _board(**kwargs: Any) -> dict[str, Any]:
    """Builds a board record with all fields defaulted, then overridden."""
    base: dict[str, Any] = {
        "id": "",
        "name": "",
        "mcu_name": None,
        "connection": "serial",
        "mode": "unknown",
        "configured": False,
        "version": None,
        "application": None,
        "interface": None,
        "flashed_version": None,
        "managed": False,
    }
    base.update(kwargs)
    return base


async def discover_boards(
    moonraker_url: str, klipper_dir: str, katapult_dir: str, data_dir: str
) -> dict[str, Any]:
    """Discovers and merges every detectable board on the host."""
    configured = await _moonraker_mcus(moonraker_url)
    serial, dfu, can = await asyncio.gather(
        asyncio.to_thread(_scan_serial),
        _scan_dfu(),
        _scan_can(klipper_dir, katapult_dir),
    )

    boards: dict[str, dict[str, Any]] = {}

    # Seed with configured MCUs (these are running firmware = "service").
    for identity, meta in configured.items():
        boards[identity] = _board(
            id=meta["serial"] or meta["canbus_uuid"] or meta["mcu_name"],
            name=meta["mcu_name"],
            mcu_name=meta["mcu_name"],
            connection=meta["connection"],
            mode="service",
            configured=True,
            version=meta["version"],
        )

    # Fold in hardware scans, enriching configured boards or adding new ones.
    for found in (*serial, *dfu, *can):
        identity = found["identity"]
        existing = boards.get(identity)
        if existing is not None:
            # A configured board also seen in a bootloader = ready to flash.
            if found["mode"] in ("ready", "dfu"):
                existing["mode"] = found["mode"]
            existing["interface"] = found.get("interface") or existing["interface"]
            existing["application"] = found.get("application") or existing["application"]
            continue
        boards[identity] = _board(
            id=found["id"],
            name=found["name"],
            connection=found["connection"],
            mode=found["mode"],
            application=found.get("application"),
            interface=found.get("interface"),
        )

    # The Linux-process host MCU: present if configured or its service runs.
    if "linux_process" not in boards and await asyncio.to_thread(_klipper_mcu_service_active):
        boards["linux_process"] = _board(
            id="linux_process",
            name="Linux host MCU",
            connection="linux",
            mode="available",
        )

    # Annotate each board with its last-flashed version + fleet membership.
    managed = fleet_store.managed_identities(data_dir)
    for board in boards.values():
        board["flashed_version"] = flashed_version(data_dir, board["id"])
        board["managed"] = board["id"] in managed

    ordered = sorted(
        boards.values(), key=lambda b: (not b["configured"], b["connection"], b["name"])
    )
    return {
        "boards": ordered,
        "scanned": {
            "configured": len(configured),
            "serial": len(serial),
            "can": len(can),
            "dfu": len(dfu),
        },
    }
