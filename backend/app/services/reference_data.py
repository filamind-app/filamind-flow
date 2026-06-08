"""Phase 0 reference-data layer — curated Klipper datasets reused across upcoming widgets.

Static JSON datasets baked under ``app/data/reference/``:

* ``stallguard_profiles.json`` — per-driver StallGuard slip-detection tuning constants
  (base + per-driver overrides + the StallGuard field name per model). Backs the planned
  Max-Flow widget and the Motor Drivers auto-SGT / slip-detection enhancement.
* ``hotend_table.json`` — hotend melt-zone + expected max-flow + suggested test presets.
* ``board_patterns.json`` — board / MCU identification patterns.
* ``macros.json`` — built-in Klipper calibration macro definitions.

Read once at import — small, static reference data (mirrors ``motor_catalog`` / ``driver_catalog``).
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from app.services import hardware_links as _hwlinks  # pure (no reference_data import) — no cycle
from app.services import hardware_search as _hwsearch  # pure (no reference_data import) — no cycle

_DIR = Path(__file__).resolve().parent.parent / "data" / "reference"


def _load(name: str) -> dict[str, Any]:
    try:
        with (_DIR / name).open(encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


_STALLGUARD = _load("stallguard_profiles.json")
_HOTENDS = _load("hotend_table.json")
_BOARDS = _load("board_patterns.json")
_MACROS = _load("macros.json")
_HARDWARE = _load("hardware.json")
_TEMPLATES = _load("templates.json")


# ── StallGuard ───────────────────────────────────────────────────────────────
def stallguard_profiles() -> dict[str, Any]:
    """The full StallGuard dataset (``base`` + per-driver ``overrides`` + ``field_by_driver``)."""
    return _STALLGUARD


def stallguard_field(driver: str) -> str | None:
    """The StallGuard threshold field for a driver model (e.g. tmc2209 -> ``sgthrs``)."""
    fields = _STALLGUARD.get("field_by_driver", {})
    return fields.get(driver.lower()) if isinstance(fields, dict) else None


def resolved_profile(driver: str) -> dict[str, Any]:
    """The effective slip-detection constants for a driver = ``base`` merged with its overrides.

    Always returns the base set (so an unknown driver falls back to the validated SG2 defaults).
    """
    base = _STALLGUARD.get("base", {})
    merged: dict[str, Any] = dict(base) if isinstance(base, dict) else {}
    overrides = _STALLGUARD.get("overrides", {})
    driver_ov = overrides.get(driver.lower()) if isinstance(overrides, dict) else None
    if isinstance(driver_ov, dict):
        merged.update(driver_ov)
    return {"driver": driver.lower(), "field": stallguard_field(driver), "constants": merged}


# ── Hotends / boards / macros ────────────────────────────────────────────────
def hotends() -> list[dict[str, Any]]:
    """Hotend melt-zone / expected-flow / test-preset table."""
    rows = _HOTENDS.get("hotends", [])
    return [r for r in rows if isinstance(r, dict)] if isinstance(rows, list) else []


def board_patterns() -> dict[str, Any]:
    """Board + MCU identification patterns (``board_patterns`` + ``mcu_patterns``)."""
    return _BOARDS


def macros() -> list[dict[str, Any]]:
    """Built-in Klipper calibration macro definitions."""
    rows = _MACROS.get("builtin_macros", [])
    return [r for r in rows if isinstance(r, dict)] if isinstance(rows, list) else []


# ── Hardware reference DB (loaded once at import; cached + indexed for O(1) reads) ─────
def _rows(key: str) -> list[dict[str, Any]]:
    rows = _HARDWARE.get(key, [])
    return [r for r in rows if isinstance(r, dict)] if isinstance(rows, list) else []


_HW_ITEMS = _rows("items")
_HW_BOARDS = _rows("boards")
_HW_DRIVERS = _rows("drivers")
_HW_MOTORS = _rows("motors")
_HW_HOSTS = _rows("hosts")
_HW_MANUFACTURERS = _rows("manufacturers")
_HW_CATEGORIES = [str(c) for c in _HARDWARE.get("categories", []) if isinstance(c, (str, int))]
_HW_CATALOG: dict[str, list[dict[str, Any]]] = {
    str(k): [e for e in v if isinstance(e, dict)]
    for k, v in (_HARDWARE.get("catalog") or {}).items()
    if isinstance(v, list)
}


def _index(rows: list[dict[str, Any]], key: str) -> dict[str, dict[str, Any]]:
    return {str(r[key]): r for r in rows if r.get(key)}


_BOARD_IDX = _index(_HW_BOARDS, "board_id")
_DRIVER_IDX = _index(_HW_DRIVERS, "driver_id")
_MOTOR_IDX = _index(_HW_MOTORS, "motor_id")
_HOST_IDX = _index(_HW_HOSTS, "host_id")
_CATALOG_IDX: dict[str, dict[str, Any]] = {
    str(e["catalog_id"]): e for rows in _HW_CATALOG.values() for e in rows if e.get("catalog_id")
}

# Precomputed lowercased search haystacks for the flat-item search (the hot path), built once.
# Kept as a parallel list aligned to _HW_ITEMS (NOT stored on the entities) so nothing leaks
# into API responses.
_ITEM_HAY: list[str] = [_hwsearch._haystack(it) for it in _HW_ITEMS]

# DB-2 linking backbone: the cross-entity graph (canonical manufacturers + MCU entities +
# composite-key adjacency), built once at load for O(1) `related()` lookups.
_LINKS: _hwlinks.LinkGraph = _hwlinks.build_links(
    boards=_HW_BOARDS,
    drivers=_HW_DRIVERS,
    motors=_HW_MOTORS,
    hosts=_HW_HOSTS,
    catalog=_HW_CATALOG,
    manufacturers=_HW_MANUFACTURERS,
)


def _dataset_etag() -> str:
    meta = _HARDWARE.get("_meta") or {}
    basis = "|".join(
        str(x)
        for x in (
            meta.get("version", ""),
            len(_HW_ITEMS),
            len(_HW_BOARDS),
            len(_HW_DRIVERS),
            len(_HW_MOTORS),
            len(_HW_HOSTS),
            sum(len(v) for v in _HW_CATALOG.values()),
            len(_LINKS.manufacturers),
            len(_LINKS.mcus),
        )
    )
    return 'W/"hw-' + hashlib.md5(basis.encode()).hexdigest()[:16] + '"'


_HW_ETAG = _dataset_etag()


def dataset_etag() -> str:
    """A stable weak ETag for the (immutable-after-load) hardware dataset; changes on redeploy."""
    return _HW_ETAG


def hardware_items() -> list[dict[str, Any]]:
    """Every hardware component row (category / manufacturer / name / specs)."""
    return _HW_ITEMS


def item_haystacks() -> list[str]:
    """Precomputed lowercased search strings aligned to :func:`hardware_items` by index."""
    return _ITEM_HAY


def hardware_categories() -> list[str]:
    """The hardware component categories, in dataset order."""
    return _HW_CATEGORIES


def hardware_manufacturers() -> list[dict[str, Any]]:
    """The raw manufacturer directory (name / country / website / specialty / categories)."""
    return _HW_MANUFACTURERS


# ── DB-2 linking backbone (canonical manufacturers / MCUs + cross-entity graph) ───────
def manufacturers_canonical() -> list[dict[str, Any]]:
    """The canonical manufacturer entities — directory entries (deduped, each with a stable
    ``manufacturer_id``, auto-derived ``aliases`` and a ``memberCount``) plus a few recurring
    real brands derived from entity usage. Sorted most-connected first."""
    return _LINKS.manufacturers


def manufacturer_by_id(manufacturer_id: str) -> dict[str, Any] | None:
    """A single canonical manufacturer entity by its ``manufacturer_id`` slug (O(1))."""
    return _LINKS.manufacturer_by_id.get(manufacturer_id)


def mcus() -> list[dict[str, Any]]:
    """The canonical MCU entities parsed from board ``specs.MCU`` (normalised to a canonical
    part, e.g. ``stm32f407``), each with a ``family``, an ``arch`` and a ``boardCount``.
    Sorted by board usage."""
    return _LINKS.mcus


def mcu_by_id(mcu_id: str) -> dict[str, Any] | None:
    """A single canonical MCU entity by its ``mcu_id`` slug (O(1))."""
    return _LINKS.mcu_by_id.get(mcu_id)


def related(plural_type: str, entity_id: str) -> dict[str, Any] | None:
    """Grouped related entities for one node (O(1) adjacency walk), or ``None`` if unknown.

    ``plural_type`` is the route path segment (``boards`` / ``drivers`` / ``motors`` / ``hosts``
    / ``catalog`` / ``manufacturers`` / ``mcus``)."""
    return _hwlinks.related(_LINKS, plural_type, entity_id)


def link_graph() -> _hwlinks.LinkGraph:
    """The full in-memory link graph (used by the CI edge-validator test)."""
    return _LINKS


def _facets() -> dict[str, list[str]]:
    board_class = sorted({str(b["boardClass"]) for b in _HW_BOARDS if b.get("boardClass")})
    # the raw nema field is inconsistent ("17", "17 (42mm)", "23 (57)") — facet on the size number
    nema_sizes: set[str] = set()
    for m in _HW_MOTORS:
        hit = re.match(r"\d+", str(m.get("nema", "")))
        if hit:
            nema_sizes.add(hit.group(0))
    nema = sorted(nema_sizes, key=int)
    kind = sorted({str(h["kind"]) for h in _HW_HOSTS if h.get("kind")})
    return {"boardClass": board_class, "nema": nema, "kind": kind}


def _catalog_subsections() -> dict[str, list[str]]:
    """Per-category distinct sub-types (e.g. Fans / Power supplies / Heated beds) for the catalog
    sub-type facet — the catalog equivalent of a board's class."""
    out: dict[str, list[str]] = {}
    for cat, rows in _HW_CATALOG.items():
        subs = sorted({str(e["subsection"]) for e in rows if e.get("subsection")})
        if len(subs) > 1:  # only categories that actually mix sub-types get a facet
            out[cat] = subs
    return out


_HW_FACETS = _facets()
_HW_CATALOG_SUBSECTIONS = _catalog_subsections()


def hardware_facets() -> dict[str, Any]:
    """Distinct filter values for the catalog facet dropdowns: ``boardClass`` (boards),
    ``nema`` size (motors, normalised to the leading number), ``kind`` (hosts), and
    ``catalogSubsections`` (per mixed catalog category, its sub-types)."""
    return {**_HW_FACETS, "catalogSubsections": _HW_CATALOG_SUBSECTIONS}


def canonical_category_counts() -> dict[str, int]:
    """Per-category counts using the CANONICAL deduped entity sets where one exists
    (boards / drivers / motors / hosts / the 9 catalog categories), else the raw item count —
    so the browser's category tiles match what each panel actually lists."""
    from collections import Counter

    raw = Counter(str(i.get("category", "")) for i in _HW_ITEMS)
    out: dict[str, int] = {}
    for c in _HW_CATEGORIES:
        cl = c.lower()
        if "mcu" in cl and "board" in cl:
            out[c] = len(_HW_BOARDS)
        elif "driver" in cl:
            out[c] = len(_HW_DRIVERS)
        elif "stepper" in cl and "motor" in cl:
            out[c] = len(_HW_MOTORS)
        elif "host" in cl:
            out[c] = len(_HW_HOSTS)
        elif c in _HW_CATALOG:
            out[c] = len(_HW_CATALOG[c])
        else:
            out[c] = raw.get(c, 0)
    return out


def boards() -> list[dict[str, Any]]:
    """The canonical control-board entities — each board's connectors aggregated into
    a single ``ports[]`` list (instead of one flat row per pin), joined to its spec
    row, with detection ``matchPatterns``. Built from the ``MCU & Boards`` category."""
    return _HW_BOARDS


def board_by_id(board_id: str) -> dict[str, Any] | None:
    """A single canonical board record by its stable ``board_id`` slug (O(1))."""
    return _BOARD_IDX.get(board_id)


def drivers() -> list[dict[str, Any]]:
    """The canonical stepper-driver entities — one per chip (deduped from the flat
    ``Stepper Drivers`` rows), with a copyable Klipper ``[tmcXXXX]`` config snippet
    (or an honest note for standalone step/dir and closed-loop parts)."""
    return _HW_DRIVERS


def driver_by_id(driver_id: str) -> dict[str, Any] | None:
    """A single canonical driver record by its stable ``driver_id`` slug (O(1))."""
    return _DRIVER_IDX.get(driver_id)


def motors() -> list[dict[str, Any]]:
    """The canonical stepper-motor entities — one per model (lightly deduped), with a
    recommended Klipper ``run_current`` (~0.7 x rated), any community per-axis current
    presets, and a copyable config snippet."""
    return _HW_MOTORS


def motor_by_id(motor_id: str) -> dict[str, Any] | None:
    """A single canonical motor record by its stable ``motor_id`` slug (O(1))."""
    return _MOTOR_IDX.get(motor_id)


def hosts() -> list[dict[str, Any]]:
    """The canonical host-computer entities — SBCs / x86 hosts / Klipper OS images (deduped),
    each with a copyable Klipper HOST config (the ``[mcu host]`` Linux-process-MCU block + setup
    note for open Linux hosts; an honest note for locked-proprietary hosts and OS images)."""
    return _HW_HOSTS


def host_by_id(host_id: str) -> dict[str, Any] | None:
    """A single canonical host record by its stable ``host_id`` slug (O(1))."""
    return _HOST_IDX.get(host_id)


def catalog() -> dict[str, Any]:
    """Generic canonical catalog for the remaining categories (sensors, hotends, extruders,
    fans/power/bed, displays/cameras, motion, nozzles, filament, electronics) — each a deduped
    entity with a copyable Klipper config snippet. Keyed by category name."""
    return _HW_CATALOG


def catalog_categories() -> list[str]:
    """The category names that have a canonical catalog (in dataset order)."""
    return list(_HW_CATALOG.keys())


def catalog_entities(category: str) -> list[dict[str, Any]]:
    """The canonical entities for one catalog category."""
    return _HW_CATALOG.get(category, [])


def catalog_entity_by_id(catalog_id: str) -> dict[str, Any] | None:
    """A single catalog entity by its stable ``catalog_id`` slug (O(1) across categories)."""
    return _CATALOG_IDX.get(catalog_id)


# ── Config / macro templates ──────────────────────────────────────────────────
def templates() -> list[dict[str, Any]]:
    """Insertable Klipper config / macro templates (id / name / category / description / body)."""
    rows = _TEMPLATES.get("templates", [])
    return [r for r in rows if isinstance(r, dict)] if isinstance(rows, list) else []
