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

from app.services import hardware_links, reference_data, topology_overrides
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


def _pin_owners(sections: dict[str, Any], mcu_name: str) -> dict[str, list[dict[str, str]]]:
    """Every pin the live config uses on a given MCU, mapped to the config sections that drive it —
    ``{PIN: [{section, key}]}``. A pin owned by >1 distinct section is a real double-assignment."""
    owners: dict[str, list[dict[str, str]]] = {}
    for section, cfg in sections.items():
        if not isinstance(cfg, dict):
            continue
        for key, value in cfg.items():
            if not isinstance(value, str) or not (key.endswith("_pin") or key == "pin"):
                continue
            chip, pin = _split_pin(value)
            if chip == mcu_name and pin:
                owners.setdefault(pin, []).append({"section": str(section), "key": str(key)})
    return owners


def _caveat_for(pin: str, electronics: dict[str, Any]) -> str | None:
    """A board electronics caveat that explicitly names this pin (e.g. the SSR/mains warning on the
    SV08's ``PA0``), so it can be surfaced right on the pin the user is wiring."""
    for value in electronics.values():
        if re.search(rf"\b{re.escape(pin)}\b", str(value), re.IGNORECASE):
            return str(value)
    return None


def build_pin_atlas(
    sections: dict[str, Any], mcu_name: str, board: dict[str, Any] | None
) -> dict[str, Any]:
    """The used-vs-free pin map of ``mcu_name``'s resolved board plus wiring-health findings.

    Pins come from the board's verbatim ``ports[].pinMap``; each is marked used (and by which config
    section) by intersecting with the live config. Findings: a pin assigned by >1 section
    (``double_assign``), and a board electronics ``caveat`` that names a used pin."""
    owners = _pin_owners(sections, mcu_name)
    findings: list[dict[str, Any]] = []
    for pin, used_by in owners.items():
        distinct = sorted({o["section"] for o in used_by})
        if len(distinct) > 1:
            findings.append(
                {
                    "kind": "double_assign",
                    "pin": pin,
                    "message": f"{pin} is assigned in {', '.join(distinct)}",
                    "sections": distinct,
                }
            )

    if not isinstance(board, dict):
        return {
            "mcu_name": mcu_name,
            "board_id": None,
            "board_name": None,
            "available": False,
            "total": 0,
            "used": 0,
            "free": 0,
            "pins": [],
            "findings": findings,
        }

    electronics = board.get("electronics")
    electronics = electronics if isinstance(electronics, dict) else {}
    pins: list[dict[str, Any]] = []
    seen: set[str] = set()
    for port in board.get("ports") or []:
        if not isinstance(port, dict):
            continue
        for pm in port.get("pinMap") or []:
            if not isinstance(pm, dict):
                continue
            _, pin = _split_pin(pm.get("pin") or "")  # bare pin (drop any MCU-name prefix)
            if not pin or pin in seen:
                continue
            seen.add(pin)
            used_by = owners.get(pin, [])
            caveat = _caveat_for(pin, electronics)
            pins.append(
                {
                    "pin": pin,
                    "signal": pm.get("signal"),
                    "config_key": pm.get("configKey"),
                    "hint": pm.get("hint"),
                    "category": port.get("category"),
                    "port": port.get("label"),
                    "used": bool(used_by),
                    "owners": [f"{o['section']}.{o['key']}" for o in used_by],
                    "caveat": caveat,
                }
            )
            if caveat and used_by:
                findings.append(
                    {
                        "kind": "caveat",
                        "pin": pin,
                        "message": caveat,
                        "sections": sorted({o["section"] for o in used_by}),
                    }
                )

    used = sum(1 for p in pins if p["used"])
    return {
        "mcu_name": mcu_name,
        "board_id": board.get("board_id"),
        "board_name": board.get("display_name") or board.get("model"),
        "available": bool(pins),
        "total": len(pins),
        "used": used,
        "free": len(pins) - used,
        "pins": pins,
        "findings": findings,
    }


def _board_pin_set(board: dict[str, Any]) -> set[str]:
    """Every physical pin name in a catalog board's pin-maps, normalised the SAME way the live
    config's used pins are (``_split_pin``) — so a pin-map entry that still carries a config
    MCU-name prefix (e.g. ``TOOLHEAD_MCU:PA1`` on a toolhead board) is compared as its bare pin
    ``PA1`` and still fingerprints. Without this, prefixed toolhead pin-maps never match."""
    pins: set[str] = set()
    for port in board.get("ports") or []:
        if not isinstance(port, dict):
            continue
        for pm in port.get("pinMap") or []:
            if not isinstance(pm, dict):
                continue
            _, p = _split_pin(pm.get("pin") or "")
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


def _integrated_sbc(host_soc: str, board: dict[str, Any] | None) -> bool:
    """True when a mainboard declares an onboard / socketed SBC whose SoC matches the host's — i.e.
    the host computer is physically *on* this board (a Sovol SV07/SV08, a BTT Manta carrying a CB1 /
    CM4, …) rather than a separate Pi. Read from the board's catalog ``specs`` (``Class`` /
    ``Host``); the host's SoC must match when known, so an external Pi on the same board still reads
    as a separate host. Casing differs by source (host ``soc`` lower, board ``Host``/``Class``
    title) so both are normalised first."""
    if not isinstance(board, dict):
        return False
    specs = board.get("specs")
    specs = specs if isinstance(specs, dict) else {}
    host_field = _norm(specs.get("Host"))
    board_class = _norm(specs.get("Class"))
    declares = "integrated" in board_class or "sbc" in host_field or "onboard" in host_field
    if not declares:
        return False
    soc = _norm(host_soc)
    return soc in host_field if soc else True


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


def apply_overrides(result: dict[str, Any], overrides: dict[str, dict[str, Any]]) -> None:
    """Apply the user's saved per-MCU board choices onto a built topology, keyed by MCU name.

    A confirmed override replaces the auto suggestion: the chosen ``board_id`` wins, ``board_match``
    becomes ``"confirmed"`` and the confidence is 1.0 (it's the user's call, not a guess). Mutates
    ``result`` in place; a no-op when there are no overrides."""
    if not overrides:
        return
    for mcu in result.get("mcus", []):
        override = overrides.get(str(mcu.get("name", "")))
        if override and override.get("board_id"):
            mcu["board_id"] = override["board_id"]
            mcu["board_match"] = "confirmed"
            mcu["board_match_confidence"] = 1.0


async def gather_topology(client: MoonrakerClient, data_dir: str = "") -> dict[str, Any]:
    """Fetch the live ``configfile`` sections and build the topology, applying any saved per-MCU
    board overrides from ``data_dir``.

    Raises:
        httpx.HTTPError: if Moonraker is unreachable.
    """
    configfile = await client.query_objects(["configfile"])
    sections = _sections(configfile.get("configfile"))
    result = analyze(sections)
    apply_overrides(result, topology_overrides.read_overrides(data_dir))
    # Identify the host SBC (optional — older Moonraker may lack /machine/system_info; degrade
    # gracefully so the topology still returns).
    try:
        system_info = await client.machine_system_info()
        result["host"] = host_node(system_info)
    except httpx.HTTPError:
        pass
    _mark_integrated_host(result)
    result["reachable"] = True
    return result


async def gather_pin_atlas(
    client: MoonrakerClient, mcu_name: str, data_dir: str = ""
) -> dict[str, Any]:
    """The used-vs-free pin atlas for one MCU, using its override-resolved board.

    Raises:
        httpx.HTTPError: if Moonraker is unreachable.
    """
    configfile = await client.query_objects(["configfile"])
    sections = _sections(configfile.get("configfile"))
    result = analyze(sections)
    apply_overrides(result, topology_overrides.read_overrides(data_dir))
    mcu = next((m for m in result.get("mcus", []) if m.get("name") == mcu_name), None)
    board_id = mcu.get("board_id") if mcu else None
    board = reference_data.board_by_id(str(board_id)) if board_id else None
    return build_pin_atlas(sections, mcu_name, board)


async def gather_pin_doctor(client: MoonrakerClient, data_dir: str = "") -> dict[str, Any]:
    """Run the pin-conflict scanner over the WHOLE live config (every MCU), so the Config Editor can
    catch double-assigned pins + mains-on-logic-pin caveats — the #1 restart-bricking errors —
    before a ``FIRMWARE_RESTART``. Aggregates each MCU's :func:`build_pin_atlas` findings.

    Raises:
        httpx.HTTPError: if Moonraker is unreachable.
    """
    configfile = await client.query_objects(["configfile"])
    sections = _sections(configfile.get("configfile"))
    result = analyze(sections)
    apply_overrides(result, topology_overrides.read_overrides(data_dir))
    mcus: list[dict[str, Any]] = []
    total = 0
    for mcu in result.get("mcus", []):
        board_id = mcu.get("board_id")
        board = reference_data.board_by_id(str(board_id)) if board_id else None
        atlas = build_pin_atlas(sections, str(mcu.get("name", "")), board)
        if atlas["findings"]:
            mcus.append(
                {
                    "name": atlas["mcu_name"],
                    "board_id": atlas["board_id"],
                    "board_name": atlas["board_name"],
                    "findings": atlas["findings"],
                }
            )
            total += len(atlas["findings"])
    return {"reachable": True, "mcus": mcus, "total": total}


def _mark_integrated_host(result: dict[str, Any]) -> None:
    """Flag when the host SBC is physically integrated onto the primary mainboard (e.g. an SV08 or
    Manta carrying a CB1), so the UI can draw the host *inside* that board instead of as a separate
    node. Sets ``host.integrated_into_board_id`` to the mainboard id, or leaves it unset."""
    host = result.get("host")
    if not isinstance(host, dict) or not host.get("host_id"):
        return
    mcus = result.get("mcus") or []
    primary = next((m for m in mcus if m.get("name") == "mcu" and m.get("board_id")), None) or next(
        (m for m in mcus if m.get("board_id")), None
    )
    if not primary:
        return
    host_entity = reference_data.host_by_id(str(host["host_id"]))
    board = reference_data.board_by_id(str(primary["board_id"]))
    soc = str(host_entity.get("soc", "")) if isinstance(host_entity, dict) else ""
    if _integrated_sbc(soc, board):
        host["integrated_into_board_id"] = primary["board_id"]
