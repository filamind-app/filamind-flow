"""Board / MCU topology detection (Track A, read-only).

Pure analysis: given the printer's parsed config sections plus the reference board / MCU
pattern tables, identify each MCU (its connection type and a best-effort chip / board guess)
and assemble a host → MCU topology. No hardware access — the route feeds it the live
``configfile`` sections from Moonraker.
"""

from __future__ import annotations

import re
from typing import Any

import httpx

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


def _split_pin(value: Any) -> tuple[str, str]:
    """``(chip, pin)`` for a Klipper pin value: split ``chip:pin`` on the first colon, strip pin
    modifiers ``^ ~ !``; a bare pin lives on the primary ``mcu``."""
    pin = str(value).strip()
    if ":" in pin:
        chip, pin = (s.strip() for s in pin.split(":", 1))
        chip = chip.lstrip("^~!").strip() or "mcu"
    else:
        chip = "mcu"
    return chip, pin.lstrip("^~!").strip().upper()


def _used_pins(sections: dict[str, Any], mcu_name: str) -> set[str]:
    """The set of pin names the live config uses on a given MCU (chip-prefix == ``mcu_name``)."""
    used: set[str] = set()
    for cfg in sections.values():
        if not isinstance(cfg, dict):
            continue
        for key, value in cfg.items():
            if not isinstance(value, str) or not (key.endswith("_pin") or key == "pin"):
                continue
            chip, pin = _split_pin(value)
            if chip == mcu_name and pin:
                used.add(pin)
    return used


def _board_pin_set(board: dict[str, Any]) -> set[str]:
    """Every pin name in a catalog board's verbatim Klipper pin-maps."""
    pins: set[str] = set()
    for port in board.get("ports") or []:
        if not isinstance(port, dict):
            continue
        for pm in port.get("pinMap") or []:
            p = str(pm.get("pin") or "").strip().upper() if isinstance(pm, dict) else ""
            if p:
                pins.add(p)
    return pins


#: Pin-fingerprint acceptance thresholds. A match needs strong containment AND must be
#: *unambiguous* — the winner either agrees by Jaccard (its pin-map size fits the used set) or
#: clearly beats the next distinct board. This stops a handful of generic MCU pins shared by many
#: small boards (e.g. a CAN toolhead with no catalog entry) from producing a confident wrong match.
_FINGERPRINT_MIN_CONTAINMENT = 0.6
_FINGERPRINT_MIN_JACCARD = 0.45
_FINGERPRINT_MIN_MARGIN = 0.15


def _fingerprint_board(used: set[str], boards: list[dict[str, Any]]) -> tuple[str | None, float]:
    """Match the printer's used pin set to a catalog board by containment (how many of the used
    pins exist in the board's pin-map), guarded against ambiguous matches. A strong, board-specific
    signal — unlike a serial id, which reveals only the chip. Returns ``(board_id, confidence)`` or
    ``(None, 0)`` when no board is a confident, unambiguous match.

    Containment alone favours *large* boards (more pins → more likely to contain any given pin), so
    a toolhead's few generic pins can tie across many small boards. The guard accepts the top board
    only when it also clears a Jaccard floor (its pin-map size fits) *or* beats the next distinct
    board's containment by a margin — otherwise the match is ``None`` (no confident board).
    """
    if len(used) < 5:
        return None, 0.0  # too few pins to discriminate
    scored: list[tuple[float, float, str | None]] = []
    for b in boards:
        bp = _board_pin_set(b)
        if len(bp) < 10:
            continue  # board has too sparse a pin-map to fingerprint against
        inter = len(used & bp)
        containment = inter / len(used)
        union = len(used | bp)
        jaccard = inter / union if union else 0.0
        scored.append((containment, jaccard, b.get("board_id")))
    if not scored:
        return None, 0.0
    scored.sort(key=lambda s: (s[0], s[1]), reverse=True)
    best_containment, best_jaccard, best_id = scored[0]
    if best_containment < _FINGERPRINT_MIN_CONTAINMENT:
        return None, 0.0
    # Containment margin over the next *distinct* board (~0 when several boards tie at the top).
    runner = next((s for s in scored[1:] if s[2] != best_id), None)
    margin = best_containment - runner[0] if runner else best_containment
    if best_jaccard < _FINGERPRINT_MIN_JACCARD and margin < _FINGERPRINT_MIN_MARGIN:
        return None, 0.0  # weak overlap AND ambiguous → not a real board match
    return best_id, round(best_containment, 2)


def _resolve_host_id(model: str, hosts: list[dict[str, Any]]) -> tuple[str | None, float]:
    """Best-effort link of the host's CPU/SoC string to a catalog ``host_id`` (a normalized
    substring match against each host's name / soc / cpu). Low-confidence *suggested* link —
    SBC SoC strings are generic, so ``(None, 0)`` is common."""
    nm = _norm(model)
    if len(nm) < 4:
        return None, 0.0
    best: tuple[str | None, float] = (None, 0.0)
    for h in hosts:
        for field, weight in (("soc", 0.6), ("name", 0.5), ("cpu", 0.5)):
            nc = _norm(h.get(field))
            if nc and len(nc) > 3 and (nc in nm or nm in nc) and weight > best[1]:
                best = (h.get("host_id"), weight)
    return best


def host_node(
    system_info: dict[str, Any], hosts: list[dict[str, Any]] | None = None
) -> dict[str, Any]:
    """Build the host node from ``/machine/system_info`` with a best-effort link to a DB host."""
    catalog = hosts if hosts is not None else reference_data.hosts()
    info = system_info if isinstance(system_info, dict) else {}
    raw_cpu = info.get("cpu_info")
    cpu: dict[str, Any] = raw_cpu if isinstance(raw_cpu, dict) else {}
    raw_distro = info.get("distribution")
    distro: dict[str, Any] = raw_distro if isinstance(raw_distro, dict) else {}
    # Many SBCs leave cpu_info.model empty and put the board/OS string in distribution.name
    # (e.g. a BTT CB1 reports "BIGTREETECH-CB1 …" there), so fall through to it for both the
    # display name and the catalog match.
    ident = (
        str(cpu.get("model") or cpu.get("cpu_desc") or cpu.get("hardware_desc") or "").strip()
        or str(distro.get("name") or "").strip()
    )
    name = ident or "host"
    host_id, conf = _resolve_host_id(ident, catalog)
    return {
        "name": name,
        "role": "sbc",
        "host_id": host_id,
        "host_match": "suggested" if host_id else None,
        "host_match_confidence": conf,
    }


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
            # Pin-fingerprint: match the printer's used pin set on this MCU against each board's
            # verbatim pin-map — a board-specific signal a serial id can't give. Use it when it
            # beats (or fills in for) the signature-based guess.
            fp_id, fp_conf = _fingerprint_board(_used_pins(sections, mcu_name), catalog)
            if fp_id and (board_id is None or fp_conf > board_id_conf):
                board_id, board_id_conf = fp_id, fp_conf
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
    # Identify the host SBC (optional — older Moonraker may lack /machine/system_info; degrade
    # gracefully so the topology still returns).
    try:
        system_info = await client.machine_system_info()
        result["host"] = host_node(system_info)
    except httpx.HTTPError:
        pass
    result["reachable"] = True
    return result
