"""Board / MCU topology detection (Track A, read-only).

Pure analysis: given the printer's parsed config sections plus the reference board / MCU
pattern tables, identify each MCU (its connection type and a best-effort chip / board guess)
and assemble a host → MCU topology. No hardware access - the route feeds it the live
``configfile`` sections from Moonraker.
"""

from __future__ import annotations

import contextlib
import re
from typing import Any

import httpx

from app.services import hardware_links, reference_data, topology_overrides
from app.services.moonraker_client import MoonrakerClient

#: A ``[mcu]`` or ``[mcu <name>]`` section header.
_MCU_SECTION = re.compile(r"^mcu(?:\s+(?P<name>.+))?$")


def _sections(configfile: Any) -> dict[str, Any]:
    """Parsed config sections - prefer typed ``settings``, fall back to raw ``config``."""
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
    board_name: str | None,
    signature: str,
    boards: list[dict[str, Any]],
    section: str = "",
) -> tuple[str | None, float]:
    """Map a detected MCU to a catalog ``board_id``.

    Tries each board's folded ``matchPatterns`` against the connection signature (serial / canbus
    id) and, as a weaker signal, the MCU's config section name (e.g. ``[mcu eddy]`` -> ``eddy``) -
    how standalone accessory boards such as eddy scanners are usually named, since their serial id
    reveals only the chip. Falls back to a normalized-name match against the ``board_patterns``
    guess. Returns ``(board_id, confidence)`` - often ``(None, 0)``, as a serial / canbus id
    usually reveals only the chip, not the board.
    """
    sig = signature.lower()
    sec = (section or "").lower()
    best: tuple[str | None, float] = (None, 0.0)
    for b in boards:
        for mp in b.get("matchPatterns", []) or []:
            pat = str(mp.get("pattern", "")) if isinstance(mp, dict) else ""
            if not pat:
                continue
            conf = float(mp.get("confidence", 0.5))
            if re.search(pat, sig):
                if conf > best[1]:
                    best = (b.get("board_id"), conf)
            elif sec and re.search(pat, sec):
                # The section name is a weaker signal than the connection id, so discount it.
                sconf = round(conf * 0.8, 3)
                if sconf > best[1]:
                    best = (b.get("board_id"), sconf)
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


# -- Component → MCU edges (which steppers / drivers / heaters / fans / sensors live on each MCU) --
# A component is attached to the MCU named by the chip prefix of its primary pin (a bare pin lives
# on the primary ``mcu``). MCU NODES come only from ``[mcu]`` sections - components merely attach to
# them - so a stray pin can never invent a phantom MCU.
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

#: Config keys whose pins name a SHARED bus, not an exclusive assignment. Klipper lets the
#: same software-SPI / software-I2C / UART pins recur across many sections - a stack of TMC51xx
#: drivers sharing one software-SPI bus, several TMC2209s on one UART line addressed by
#: ``uart_address``, an accelerometer sharing the toolhead's SPI. Repetition of these is valid
#: wiring, NOT a double-assignment (which only an exclusive pin - step/heater/cs/… - is).
#:
#: TMC UART comes in two wirings, both legitimately shared across every driver section:
#:   * one-wire: ``uart_pin`` only (RX/TX on one line);
#:   * two-wire: ``uart_pin`` (RX) + ``tx_pin`` (TX) - e.g. the BTT SKR mini E3 V3.0 shares
#:     ``uart_pin: PC11`` and ``tx_pin: PC10`` across stepper_x/y/z/e, distinguished only by
#:     ``uart_address``. ``rx_pin`` is the same line for boards that name it explicitly.
_SHARED_BUS_PIN_KEYS: frozenset[str] = frozenset(
    {
        "spi_software_miso_pin",
        "spi_software_mosi_pin",
        "spi_software_sclk_pin",
        "i2c_software_scl_pin",
        "i2c_software_sda_pin",
        "uart_pin",
        "tx_pin",
        "rx_pin",
    }
)

#: Primary-pin candidate keys per kind - the pin whose chip prefix names the owning MCU.
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
    # MCU node names come from Moonraker's lowercased settings, but a pin's chip-prefix keeps its
    # declared case (e.g. "EBBCan:gpio7") - match case-insensitively or a mixed-case CAN MCU's
    # components (extruder / driver / fan / accel on the toolhead) never attach.
    by_name = {str(m["name"]).lower(): m for m in mcus}
    for name, cfg in sections.items():
        if not isinstance(cfg, dict):
            continue
        kind = _component_kind(str(name))
        if not kind:
            continue
        owner = _owning_mcu(kind, cfg)
        if owner is None:
            continue
        target = by_name.get(owner.lower())
        if target is None:
            continue  # pin references an MCU with no [mcu] section - skip (never invent a node)
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
            if chip.lower() == mcu_name.lower() and pin:
                used.add(pin)
    return used


def _pin_owners(sections: dict[str, Any], mcu_name: str) -> dict[str, list[dict[str, str]]]:
    """Every pin the live config uses on a given MCU, mapped to the config sections that drive it -
    ``{PIN: [{section, key}]}``. A pin owned by >1 distinct section is a real double-assignment."""
    owners: dict[str, list[dict[str, str]]] = {}
    for section, cfg in sections.items():
        if not isinstance(cfg, dict):
            continue
        for key, value in cfg.items():
            if not isinstance(value, str) or not (key.endswith("_pin") or key == "pin"):
                continue
            chip, pin = _split_pin(value)
            if chip.lower() == mcu_name.lower() and pin:
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
        if len(distinct) <= 1:
            continue
        # A shared bus (software SPI/I2C, single-wire UART) legitimately repeats a pin across
        # sections. It's a real conflict only when an EXCLUSIVE pin (step/heater/cs/…) is among
        # the owners - an exclusive output can't be shared. All-shared owners = valid wiring.
        if not any(o["key"] not in _SHARED_BUS_PIN_KEYS for o in used_by):
            continue
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
    config's used pins are (``_split_pin``) - so a pin-map entry that still carries a config
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
#: *unambiguous* - the winner either agrees by Jaccard (its pin-map size fits the used set) or
#: clearly beats the next distinct board. This stops a handful of generic MCU pins shared by many
#: small boards (e.g. a CAN toolhead with no catalog entry) from producing a confident wrong match.
_FINGERPRINT_MIN_CONTAINMENT = 0.6
_FINGERPRINT_MIN_JACCARD = 0.45
_FINGERPRINT_MIN_MARGIN = 0.15


def _fingerprint_board(used: set[str], boards: list[dict[str, Any]]) -> tuple[str | None, float]:
    """Match the printer's used pin set to a catalog board by containment (how many of the used
    pins exist in the board's pin-map), guarded against ambiguous matches. A strong, board-specific
    signal - unlike a serial id, which reveals only the chip. Returns ``(board_id, confidence)`` or
    ``(None, 0)`` when no board is a confident, unambiguous match.

    Containment alone favours *large* boards (more pins → more likely to contain any given pin), so
    a toolhead's few generic pins can tie across many small boards. The guard accepts the top board
    only when it also clears a Jaccard floor (its pin-map size fits) *or* beats the next distinct
    board's containment by a margin - otherwise the match is ``None`` (no confident board).
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
    substring match against each host's name / soc / cpu). Low-confidence *suggested* link -
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
    """True when a mainboard declares an onboard / socketed SBC whose SoC matches the host's - i.e.
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
            board_id, board_id_conf = _resolve_board_id(board, signature, catalog, mcu_name)
            # Pin-fingerprint: match the printer's used pin set on this MCU against each board's
            # verbatim pin-map - a board-specific signal a serial id can't give. Use it when it
            # beats (or fills in for) the signature-based guess.
            fp_id, fp_conf = _fingerprint_board(_used_pins(sections, mcu_name), catalog)
            if fp_id and (board_id is None or fp_conf > board_id_conf):
                board_id, board_id_conf = fp_id, fp_conf
            # Join the detected chip to a canonical DB MCU entity (one of the first-class MCUs) -
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
                    # null - a serial/canbus id usually reveals only the chip. Surfaced as
                    # a *suggested* match the user can override.
                    "board_id": board_id,
                    "board_match": "suggested" if board_id else None,
                    "board_match_confidence": board_id_conf,
                    # Running firmware version (e.g. "v0.13.0-628-g…"); filled from the live MCU
                    # object by gather_topology - null on a config-only (offline) analyze.
                    "firmware": None,
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


async def _enrich_live_mcus(
    client: MoonrakerClient, result: dict[str, Any], sections: dict[str, Any]
) -> None:
    """Enrich each MCU node with its LIVE chip + firmware from the running MCU object.

    The config/serial reveals a chip only for USB MCUs; a CAN MCU's signature is just a uuid, so
    ``analyze`` leaves CAN chips unknown. Querying the live ``mcu`` / ``mcu <name>`` objects yields
    the authoritative ``mcu_constants.MCU`` (chip) + ``mcu_version`` (firmware) for EVERY MCU,
    including CAN ones. With the real chip known we also re-fingerprint the board against ONLY the
    catalog boards that carry that chip - far less ambiguous than the whole catalog - but never
    override a user-confirmed board. Mutates ``result`` in place; best-effort (the caller guards the
    HTTP error so an older / offline Moonraker just keeps the config-only guess)."""
    mcus = result.get("mcus", [])
    if not mcus:
        return
    # The live mcu OBJECT names keep the config's declared case (e.g. "mcu EBBCan"), but the
    # topology names come from Moonraker's lowercased `settings` ("ebbcan") - so map the object
    # names case-insensitively, or a mixed-case CAN toolhead would never enrich.
    obj_names = await client.list_objects()
    live = {o.lower(): o for o in obj_names if o == "mcu" or o.lower().startswith("mcu ")}
    want: dict[str, dict[str, Any]] = {}
    for m in mcus:
        n = str(m.get("name") or "")
        obj = live.get(("mcu" if n == "mcu" else f"mcu {n}").lower())
        if obj:
            want[obj] = m
    if not want:
        return
    status = await client.query_objects(list(want.keys()))
    if not status:
        return
    boards = reference_data.boards()
    for key, m in want.items():
        info = status.get(key)
        if not isinstance(info, dict):
            continue
        version = info.get("mcu_version")
        if isinstance(version, str) and version:
            m["firmware"] = version
        consts = info.get("mcu_constants")
        chip = consts.get("MCU") if isinstance(consts, dict) else None
        if not (isinstance(chip, str) and chip):
            continue
        m["mcu"] = chip
        norm = hardware_links.normalize_mcu(chip)
        if norm and reference_data.mcu_by_id(norm[0]):
            m["mcu_id"], _, m["mcu_family"] = norm
        # Chip-narrowed pin-fingerprint - a confident, board-specific guess the config alone can't
        # give. Skip a user-confirmed board and an unrecognised chip.
        if m.get("board_match") == "confirmed" or not norm:
            continue
        candidates = [
            b for b in boards if norm[0] in {mid for mid, _, _ in hardware_links.board_mcu_ids(b)}
        ]
        if not candidates:
            continue
        fp_id, fp_conf = _fingerprint_board(
            _used_pins(sections, str(m.get("name") or "")), candidates
        )
        if fp_id and (
            m.get("board_id") is None or fp_conf > float(m.get("board_match_confidence") or 0.0)
        ):
            m["board_id"], m["board_match"], m["board_match_confidence"] = (
                fp_id,
                "suggested",
                fp_conf,
            )


#: External USB-CAN dongles all present as the candleLight ``gs_usb`` driver - a BTT U2C, a Canable
#: or a clone are indistinguishable in software, so the catalog link is the generic "u2c-all",
#: surfaced as a low-confidence *suggested* match the user can confirm.
_USB_CAN_DRIVERS = {"gs_usb"}
_USB_CAN_BOARD_ID = "u2c-all"


def _can_buses(system_info: dict[str, Any]) -> list[dict[str, Any]]:
    """The host's CAN buses from ``/machine/system_info`` ``canbus``, each with a best-effort
    link to its bridging adapter. An external USB-CAN dongle (``gs_usb``) is not a Klipper MCU, so
    it has no node - this is the only place it surfaces. An onboard transceiver gets no adapter."""
    canbus = system_info.get("canbus") if isinstance(system_info, dict) else None
    if not isinstance(canbus, dict):
        return []
    out: list[dict[str, Any]] = []
    for iface, info in canbus.items():
        if not isinstance(info, dict):
            continue
        driver = str(info.get("driver") or "") or None
        raw_bitrate = info.get("bitrate")
        bus: dict[str, Any] = {
            "interface": str(iface),
            "driver": driver,
            "bitrate": raw_bitrate if isinstance(raw_bitrate, int) else None,
            "board_id": None,
            "board_match": None,
            "board_match_confidence": 0.0,
        }
        if driver in _USB_CAN_DRIVERS and reference_data.board_by_id(_USB_CAN_BOARD_ID):
            bus["board_id"] = _USB_CAN_BOARD_ID
            bus["board_match"] = "suggested"
            bus["board_match_confidence"] = 0.4
        out.append(bus)
    return out


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
    # Enrich each MCU with its live chip + firmware (and a chip-narrowed board fingerprint) - the
    # only way to identify a CAN MCU's chip + every MCU's running firmware. Best-effort.
    with contextlib.suppress(httpx.HTTPError):
        await _enrich_live_mcus(client, result, sections)
    # Identify the host SBC (optional - older Moonraker may lack /machine/system_info; degrade
    # gracefully so the topology still returns).
    try:
        system_info = await client.machine_system_info()
        result["host"] = host_node(system_info)
        result["can_buses"] = _can_buses(system_info)
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


async def gather_pin_map(client: MoonrakerClient, data_dir: str = "") -> dict[str, Any]:
    """Per-MCU pin data for the Config Editor's pin-aware editing: each resolved board's named pins
    (with what config section uses them + any electronics caveat), so a ``*_pin`` field can offer
    valid-pin suggestions and flag a non-existent / double-assigned / caveated pin inline.

    Raises:
        httpx.HTTPError: if Moonraker is unreachable.
    """
    configfile = await client.query_objects(["configfile"])
    sections = _sections(configfile.get("configfile"))
    result = analyze(sections)
    apply_overrides(result, topology_overrides.read_overrides(data_dir))
    mcus: list[dict[str, Any]] = []
    for mcu in result.get("mcus", []):
        board_id = mcu.get("board_id")
        board = reference_data.board_by_id(str(board_id)) if board_id else None
        atlas = build_pin_atlas(sections, str(mcu.get("name", "")), board)
        mcus.append(
            {
                "name": atlas["mcu_name"],
                "board_name": atlas["board_name"],
                "pins": [
                    {"pin": p["pin"], "owners": p["owners"], "caveat": p["caveat"]}
                    for p in atlas["pins"]
                ],
            }
        )
    return {"reachable": True, "mcus": mcus}


async def gather_pin_doctor(client: MoonrakerClient, data_dir: str = "") -> dict[str, Any]:
    """Run the pin-conflict scanner over the WHOLE live config (every MCU), so the Config Editor can
    catch double-assigned pins + mains-on-logic-pin caveats - the #1 restart-bricking errors -
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
