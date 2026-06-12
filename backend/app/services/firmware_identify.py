"""Identify registered flash devices against the live board map and the hardware catalog.

A registered device (the flash registry) and a detected MCU (the board map) describe the
same physical board from two sides — this joins them on the connection identifier, then
resolves the board's catalog entity and the Kconfig machine symbol its chip needs, so the
firmware widget can deep-link a device to its place on the board map and seed a build
profile with the right MCU preselected.

Everything degrades honestly: no topology match → no link, chip without a Kconfig symbol
(or Klipper sources absent) → no seed offer. Nothing is guessed beyond what the board map
already established.
"""

from __future__ import annotations

from typing import Any

from app.services import board_topology, devices_store, reference_data
from app.services.kconfig_service import KconfigService
from app.services.moonraker_client import MoonrakerClient


def _ids_of(device: dict[str, Any]) -> list[str]:
    out = [str(device.get("id", ""))]
    serial_id = device.get("serial_id")
    if isinstance(serial_id, str) and serial_id:
        out.append(serial_id)
    return [i for i in out if i]


def match_devices(
    devices: list[dict[str, Any]], mcus: list[dict[str, Any]]
) -> dict[str, dict[str, Any]]:
    """Join devices to topology MCUs on the connection identifier (exact, then substring
    either way — a Katapult id carries the same usb serial inside a longer path).
    Returns ``{device_id: mcu}`` for the matches."""
    matched: dict[str, dict[str, Any]] = {}
    for device in devices:
        ids = _ids_of(device)
        for mcu in mcus:
            identifier = str(mcu.get("identifier") or "")
            if not identifier:
                continue
            if any(i == identifier or i in identifier or identifier in i for i in ids):
                matched[str(device.get("id"))] = mcu
                break
    return matched


async def identify_devices(
    client: MoonrakerClient, data_dir: str, kconfig: KconfigService
) -> dict[str, Any]:
    """The identification report for every registered device (see module docstring)."""
    topo = await board_topology.gather_topology(client, data_dir)
    devices = devices_store.read_devices(data_dir)
    matched = match_devices(devices, topo.get("mcus", []))

    kconfig_available = kconfig.available
    symbol_cache: dict[str, str | None] = {}

    async def symbol_for(chip: str) -> str | None:
        if not chip or not kconfig_available:
            return None
        if chip not in symbol_cache:
            symbol_cache[chip] = await kconfig.find_symbol(f"MACH_{chip}")
        return symbol_cache[chip]

    out: list[dict[str, Any]] = []
    for device in devices:
        device_id = str(device.get("id"))
        mcu = matched.get(device_id)
        entry: dict[str, Any] = {
            "device_id": device_id,
            "mcu_section": None,
            "board_id": None,
            "board_name": None,
            "manufacturer": None,
            "mcu": None,
            "kconfig_symbol": None,
        }
        if mcu:
            entry["mcu_section"] = mcu.get("name")
            entry["mcu"] = mcu.get("mcu")
            board_id = mcu.get("board_id")
            if isinstance(board_id, str) and board_id:
                entry["board_id"] = board_id
                board = reference_data.board_by_id(board_id)
                if board:
                    entry["board_name"] = board.get("display_name") or board.get("model")
                    entry["manufacturer"] = board.get("manufacturer")
            entry["kconfig_symbol"] = await symbol_for(str(mcu.get("mcu") or ""))
        out.append(entry)
    return {"devices": out, "kconfig_available": kconfig_available}
