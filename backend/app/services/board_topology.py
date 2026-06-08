"""Board / MCU topology detection (Track A, read-only).

Pure analysis: given the printer's parsed config sections plus the reference board / MCU
pattern tables, identify each MCU (its connection type and a best-effort chip / board guess)
and assemble a host → MCU topology. No hardware access — the route feeds it the live
``configfile`` sections from Moonraker.
"""

from __future__ import annotations

import re
from typing import Any

from app.services import hardware_links, reference_data
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


def _norm(s: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(s or "").lower())


def _resolve_board_id(
    board_name: str | None, signature: str, boards: list[dict[str, Any]]
) -> tuple[str | None, float]:
    """Map a detected MCU to a catalog ``board_id``.

    First tries each board's folded ``matchPatterns`` against the connection signature
    (the unified detection path); falls back to a normalized-name match against the
    board guess from ``board_patterns``. Returns ``(board_id, confidence)`` — often
    ``(None, 0)`` because a serial/canbus id usually reveals only the chip, not the board.
    """
    sig = signature.lower()
    best: tuple[str | None, float] = (None, 0.0)
    for b in boards:
        for mp in b.get("matchPatterns", []) or []:
            pat = str(mp.get("pattern", "")) if isinstance(mp, dict) else ""
            if pat and re.search(pat, sig):
                conf = float(mp.get("confidence", 0.5))
                if conf > best[1]:
                    best = (b.get("board_id"), conf)
    if best[0]:
        return best
    if board_name:
        nb = _norm(board_name)
        for b in boards:
            for cand in (b.get("model"), b.get("display_name"), *(b.get("aliases") or [])):
                nc = _norm(cand)
                if nc and len(nc) > 4 and (nc in nb or nb in nc):
                    return (b.get("board_id"), 0.5)
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


# ── Component → MCU edges (which steppers / drivers / heaters / fans / sensors live on each MCU) ──
# A component is attached to the MCU named by the chip prefix of its primary pin (a bare pin lives
# on the primary ``mcu``). MCU NODES come only from ``[mcu]`` sections — components merely attach to
# them — so a stray pin can never invent a phantom MCU.
_COMPONENT_KINDS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"^stepper_\S+$"), "motor"),
    (re.compile(r"^manual_stepper\s+\S"), "motor"),
    (re.compile(r"^extruder\d*$"), "motor"),
    (re.compile(r"^tmc\d\w*\s+\S"), "driver"),
    (re.compile(r"^heater_bed$"), "heater"),
    (re.compile(r"^heater_generic\s+\S"), "heater"),
    (
        re.compile(
            r"^(?:fan|fan_generic\s+\S+|heater_fan\s+\S+|controller_fan\s+\S+|temperature_fan\s+\S+)$"
        ),
        "fan",
    ),
    (re.compile(r"^(?:adxl345|lis2dw|mpu9250|icm20948)(?:\s+\S+)?$"), "sensor"),
    (re.compile(r"^(?:probe|bltouch|smart_effector)$"), "sensor"),
    (re.compile(r"^probe_eddy_current\s+\S"), "sensor"),
]

#: Primary-pin candidate keys per kind — the pin whose chip prefix names the owning MCU.
_PRIMARY_PIN: dict[str, tuple[str, ...]] = {
    "motor": ("step_pin", "dir_pin", "enable_pin"),
    "driver": ("uart_pin", "cs_pin", "step_pin"),
    "heater": ("heater_pin", "pin"),
    "fan": ("pin",),
    "sensor": ("cs_pin", "sensor_pin", "data_pin", "pin"),
}


def _chip_of(value: Any) -> str | None:
    """The MCU chip prefix of a Klipper pin value: ``chip:pin`` split on the first colon, pin
    modifiers ``^ ~ !`` stripped; a bare pin lives on the primary ``mcu``. ``None`` if not a pin."""
    if not isinstance(value, str) or not value.strip():
        return None
    pin = value.strip()
    chip = pin.split(":", 1)[0].strip().lstrip("^~!").strip() if ":" in pin else "mcu"
    return chip or "mcu"


def _component_kind(name: str) -> str | None:
    low = name.strip().lower()
    for pattern, kind in _COMPONENT_KINDS:
        if pattern.match(low):
            return kind
    return None


def _owning_mcu(kind: str, cfg: dict[str, Any]) -> str | None:
    """The chip prefix of the component's primary pin = the MCU it lives on."""
    for key in _PRIMARY_PIN.get(kind, ()):
        chip = _chip_of(cfg.get(key))
        if chip:
            return chip
    return None


def _attach_components(sections: dict[str, Any], mcus: list[dict[str, Any]]) -> None:
    """Attach each component section (stepper / driver / heater / fan / sensor) to the MCU node it
    lives on, by the chip prefix of its primary pin. Mutates each MCU's ``components`` list."""
    by_name = {m["name"]: m for m in mcus}
    for name, cfg in sections.items():
        if not isinstance(cfg, dict):
            continue
        kind = _component_kind(str(name))
        if not kind:
            continue
        owner = _owning_mcu(kind, cfg)
        if owner is None:
            continue
        target = by_name.get(owner) or (by_name.get("mcu") if owner == "mcu" else None)
        if target is None:
            continue  # pin references an MCU with no [mcu] section — skip (never invent a node)
        target["components"].append({"section": str(name), "kind": kind})


def analyze(
    sections: dict[str, Any],
    board_patterns: dict[str, Any] | None = None,
    boards: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build the host → MCU topology from config ``sections`` (pure, no I/O)."""
    data = board_patterns if board_patterns is not None else reference_data.board_patterns()
    bpats = data.get("board_patterns", []) if isinstance(data, dict) else []
    mpats = data.get("mcu_patterns", []) if isinstance(data, dict) else []
    catalog = boards if boards is not None else reference_data.boards()

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
            board_id, board_id_conf = _resolve_board_id(board, signature, catalog)
            # Join the detected chip to a canonical DB MCU entity (one of the first-class MCUs) —
            # a reliable DB anchor even when no board_id resolves. null for unrecognised chips.
            norm = hardware_links.normalize_mcu(chip or signature or "")
            mcu_id: str | None = None
            mcu_family: str | None = None
            if norm and reference_data.mcu_by_id(norm[0]):
                mcu_id, _, mcu_family = norm
            mcus.append(
                {
                    "name": mcu_name,
                    "connection": conn["type"],
                    "identifier": conn["id"],
                    "mcu": chip,
                    "board": board,
                    "confidence": confidence,
                    # Canonical DB MCU entity (GET /api/hardware/mcus/{id}); null if unrecognised.
                    "mcu_id": mcu_id,
                    "mcu_family": mcu_family,
                    # Link into the board catalog (GET /api/hardware/boards/{id}); may be
                    # null — a serial/canbus id usually reveals only the chip. Surfaced as
                    # a *suggested* match the user can override.
                    "board_id": board_id,
                    "board_match": "suggested" if board_id else None,
                    "board_match_confidence": board_id_conf,
                    # Components (steppers / drivers / heaters / fans / sensors) on this MCU,
                    # attached below by the chip prefix of each component's primary pin.
                    "components": [],
                }
            )
    _attach_components(sections if isinstance(sections, dict) else {}, mcus)
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
