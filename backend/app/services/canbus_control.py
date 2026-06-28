"""Full CAN-bus control for the printer host - view link state + bring interfaces up/down + set
bitrate, all from the panel.

A SocketCAN interface (``can0`` …) is a kernel netdev, not a Klipper MCU, so it's managed with
``ip`` rather than Klipper/Moonraker. Reading status is unprivileged (``ip … link show``); changing
it (``ip link set``) goes through the host's narrow passwordless-sudo grant (scripts/install.sh
sudoers). Every change is refused while a print is running - taking the bus down mid-print drops
every CAN MCU - and only ever targets a discovered CAN interface (never an arbitrary netdev).

This is the *control* side of CAN; flashing the USB-CAN *adapter's* firmware is a separate concern
(see ``canbus_flash.py`` / the Firmware Manager).
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import re
from typing import Any

import httpx

from app.services import board_topology, topology_overrides
from app.services.moonraker_client import MoonrakerClient

#: A SocketCAN interface name we will act on. Restricting ``ip link set`` to this shape (and to an
#: interface we actually discovered as CAN) keeps the privileged grant from touching other netdevs.
_IFACE_RE = re.compile(r"^can[0-9]{1,2}$")

#: Sane SocketCAN bitrate bounds (bit/s). Common values: 1000000 / 500000 / 250000 / 125000.
_MIN_BITRATE = 10_000
_MAX_BITRATE = 1_000_000

_BUSY_MSG = "A print is running. Stop the print before changing the CAN bus."

#: Sudo refused / not granted - same signatures host_control_service watches for, so the UI can tell
#: "passwordless sudo isn't set up" from a genuine failure.
_SUDO_NOT_GRANTED_RE = re.compile(
    r"a password is required|not allowed to execute|must have a tty|sudo:.*(askpass|required)",
    re.IGNORECASE,
)


def _needs_setup(out: str) -> bool:
    return bool(_SUDO_NOT_GRANTED_RE.search(out))


async def _run(cmd: list[str], timeout: float = 10.0) -> tuple[int, str]:
    """Run a command, returning (returncode, combined stdout+stderr). C locale keeps sudo/ip
    messages parseable (and the sudo-not-granted signature detectable) on a non-English host."""
    env = {**os.environ, "LC_ALL": "C", "LANG": "C"}
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT, env=env
        )
        out, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except (FileNotFoundError, NotImplementedError):
        return 127, f"{cmd[0]}: not found"
    except (OSError, asyncio.TimeoutError) as exc:
        return 1, str(exc)
    return proc.returncode or 0, out.decode("utf-8", "replace")


def _parse_live(entry: dict[str, Any]) -> dict[str, Any]:
    """Pull the fields we surface from one ``ip -details -statistics -json link show`` record."""
    flags = entry.get("flags")
    link_up = "UP" in flags if isinstance(flags, list) else None
    txqlen = entry.get("txqlen")
    info = (entry.get("linkinfo") or {}).get("info_data") or {}
    berr = info.get("berr_counter") or {}
    bittiming = info.get("bittiming") or {}
    state = info.get("state")
    bitrate = bittiming.get("bitrate")
    return {
        "link_up": bool(link_up) if link_up is not None else None,
        # CAN controller state: ERROR-ACTIVE (healthy) / ERROR-PASSIVE / BUS-OFF / STOPPED.
        "state": str(state) if state else None,
        "errors_rx": berr["rx"] if isinstance(berr.get("rx"), int) else None,
        "errors_tx": berr["tx"] if isinstance(berr.get("tx"), int) else None,
        "txqueuelen": txqlen if isinstance(txqlen, int) else None,
        "bitrate": bitrate if isinstance(bitrate, int) else None,
    }


async def _all_live_status() -> dict[str, dict[str, Any]]:
    """Live status of every CAN interface, keyed by name, from a single ``ip`` call. ``{}`` if
    ``ip`` is missing or its JSON can't be parsed (older iproute2); the caller degrades."""
    rc, out = await _run(["ip", "-details", "-statistics", "-json", "link", "show", "type", "can"])
    if rc != 0 or not out.strip():
        return {}
    try:
        data = json.loads(out)
    except (json.JSONDecodeError, ValueError):
        return {}
    result: dict[str, dict[str, Any]] = {}
    for entry in data if isinstance(data, list) else []:
        if isinstance(entry, dict) and entry.get("ifname"):
            result[str(entry["ifname"])] = _parse_live(entry)
    return result


async def _printer_busy(moonraker_url: str) -> bool:
    """True while a print is running/paused (Moonraker down → treated as not busy)."""
    client = MoonrakerClient(moonraker_url)
    try:
        status = await client.query_objects(["print_stats"])
    except httpx.HTTPError:
        return False
    state = str((status.get("print_stats") or {}).get("state") or "").lower()
    return state in {"printing", "paused"}


async def list_can_buses(moonraker_url: str, data_dir: str) -> list[dict[str, Any]]:
    """Every host CAN interface with its live status (link up/down, controller state, bitrate, bus
    error counters, tx queue length) plus its best-effort bridging-adapter link from the catalog.

    Sources: Moonraker ``/machine/system_info`` ``canbus`` (driver + configured bitrate + adapter
    match) merged with live ``ip`` data. Either source can be absent and the list still builds."""
    buses: list[dict[str, Any]] = []
    overrides = topology_overrides.read_overrides(data_dir)
    client = MoonrakerClient(moonraker_url)
    with contextlib.suppress(httpx.HTTPError):
        system_info = await client.machine_system_info()
        buses = board_topology._can_buses(system_info, overrides)

    live = await _all_live_status()
    known = {b["interface"] for b in buses}
    # CAN interfaces the kernel reports but Moonraker's system_info didn't (older Moonraker).
    for iface in live:
        if iface not in known:
            buses.append(
                {
                    "interface": iface,
                    "driver": None,
                    "bitrate": None,
                    "board_id": None,
                    "board_match": None,
                    "board_match_confidence": 0.0,
                }
            )

    for bus in buses:
        status = live.get(bus["interface"]) or {}
        bus["link_up"] = status.get("link_up")
        bus["state"] = status.get("state")
        bus["errors_rx"] = status.get("errors_rx")
        bus["errors_tx"] = status.get("errors_tx")
        bus["txqueuelen"] = status.get("txqueuelen")
        if status.get("bitrate"):
            bus["bitrate"] = status["bitrate"]  # live value wins over the configured one
    return buses


def _refused(message: str, iface: str = "") -> dict[str, Any]:
    return {"interface": iface, "ok": False, "refused": True, "output": message}


def _result(iface: str, rc: int, out: str) -> dict[str, Any]:
    return {
        "interface": iface,
        "ok": rc == 0,
        "refused": False,
        "output": out.strip(),
        "needs_setup": rc != 0 and _needs_setup(out),
    }


async def _require_can_iface(iface: str) -> None:
    """Reject anything that isn't a real, discovered CAN interface (raises ValueError → 400)."""
    if not _IFACE_RE.match(iface):
        raise ValueError(f"Invalid CAN interface name '{iface}'.")
    live = await _all_live_status()
    # Only enforce membership when we could actually enumerate (ip present); else trust the regex.
    if live and iface not in live:
        raise ValueError(f"'{iface}' is not a CAN interface on this host.")


async def set_link(iface: str, up: bool, moonraker_url: str) -> dict[str, Any]:
    """Bring a CAN interface up or down. Refused while printing. Bringing it up needs a bitrate to
    already be configured (the kernel rejects ``up`` otherwise - surfaced in the output)."""
    await _require_can_iface(iface)
    if await _printer_busy(moonraker_url):
        return _refused(_BUSY_MSG, iface)
    rc, out = await _run(["sudo", "-n", "ip", "link", "set", iface, "up" if up else "down"])
    return _result(iface, rc, out)


async def set_bitrate(iface: str, bitrate: int, moonraker_url: str) -> dict[str, Any]:
    """Set a CAN interface's bitrate. The interface must be DOWN first (SocketCAN can't retime a
    running controller). Refused while printing."""
    await _require_can_iface(iface)
    if not _MIN_BITRATE <= bitrate <= _MAX_BITRATE:
        raise ValueError(f"Bitrate must be between {_MIN_BITRATE} and {_MAX_BITRATE} bit/s.")
    if await _printer_busy(moonraker_url):
        return _refused(_BUSY_MSG, iface)
    status = (await _all_live_status()).get(iface) or {}
    if status.get("link_up"):
        return _refused("Bring the interface down before changing its bitrate.", iface)
    rc, out = await _run(
        ["sudo", "-n", "ip", "link", "set", iface, "type", "can", "bitrate", str(bitrate)]
    )
    return _result(iface, rc, out)
