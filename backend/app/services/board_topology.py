"""Board / MCU topology detection (Track A, read-only).

Pure analysis: given the printer's parsed config sections plus the reference board / MCU
pattern tables, identify each MCU (its connection type and a best-effort chip / board guess)
and assemble a host → MCU topology. No hardware access — the route feeds it the live
``configfile`` sections from Moonraker.
"""

from __future__ import annotations

import re
from typing import Any

from app.services import reference_data
from app.services.moonraker_client import MoonrakerClient

#: A ``[mcu]`` or ``[mcu <name>]`` section header.
_MCU_SECTION = re.compile(r"^mcu(?:\s+(?P<name>.+))?$")


def _sections(configfile: Any) -> dict[str, Any]:
    """Parsed config sections — prefer typed ``settings``, fall back to raw ``config``."""
    if not isinstance(configfile, dict):
        return {}
    for key in ("settings", "config"):
        section = configfile.get(key)
        if isinstance(section, dict):
            return section
    return {}


def _match(patterns: list[Any], text: str, key: str) -> tuple[str | None, float]:
    """First pattern whose (regex) ``pattern`` matches ``text`` (case-insensitive)."""
    low = text.lower()
    for entry in patterns:
        if not isinstance(entry, dict):
            continue
        pattern = str(entry.get("pattern", ""))
        if pattern and re.search(pattern, low):
            return (entry.get(key), float(entry.get("confidence", 1.0)))
    return (None, 0.0)


def _connection(cfg: dict[str, Any]) -> dict[str, Any]:
    """Classify how an MCU connects from its config (CAN bus / USB serial / UART)."""
    uuid = cfg.get("canbus_uuid")
    if isinstance(uuid, str) and uuid:
        return {"type": "canbus", "id": uuid}
    serial = cfg.get("serial")
    if isinstance(serial, str) and serial:
        low = serial.lower()
        ctype = "usb" if "usb-" in low or "by-id" in low else "uart"
        return {"type": ctype, "id": serial}
    if cfg.get("baud") is not None:
        return {"type": "uart", "id": str(cfg.get("baud"))}
    return {"type": "unknown", "id": None}


def analyze(
    sections: dict[str, Any], board_patterns: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Build the host → MCU topology from config ``sections`` (pure, no I/O)."""
    data = board_patterns if board_patterns is not None else reference_data.board_patterns()
    bpats = data.get("board_patterns", []) if isinstance(data, dict) else []
    mpats = data.get("mcu_patterns", []) if isinstance(data, dict) else []

    mcus: list[dict[str, Any]] = []
    if isinstance(sections, dict):
        for name, cfg in sections.items():
            match = _MCU_SECTION.match(str(name))
            if not match or not isinstance(cfg, dict):
                continue
            mcu_name = match.group("name") or "mcu"
            conn = _connection(cfg)
            signature = str(conn.get("id") or "")
            chip, _ = _match(mpats, signature, "mcu")
            board, confidence = _match(bpats, signature, "board")
            mcus.append(
                {
                    "name": mcu_name,
                    "connection": conn["type"],
                    "identifier": conn["id"],
                    "mcu": chip,
                    "board": board,
                    "confidence": confidence,
                }
            )
    # Primary [mcu] first, then the rest alphabetically.
    mcus.sort(key=lambda m: (m["name"] != "mcu", str(m["name"])))
    return {"host": {"name": "host", "role": "sbc"}, "mcus": mcus, "mcu_count": len(mcus)}


async def gather_topology(client: MoonrakerClient) -> dict[str, Any]:
    """Fetch the live ``configfile`` sections and build the topology.

    Raises:
        httpx.HTTPError: if Moonraker is unreachable.
    """
    configfile = await client.query_objects(["configfile"])
    sections = _sections(configfile.get("configfile"))
    result = analyze(sections)
    result["reachable"] = True
    return result
