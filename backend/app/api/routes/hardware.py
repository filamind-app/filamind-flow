"""Hardware Browser endpoints (Track A, read-only).

A searchable curated 3D-printing hardware reference. All static data — no Moonraker, no writes.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.services import (
    board_search,
    catalog_search,
    driver_search,
    hardware_search,
    host_search,
    motor_search,
    reference_data,
)

router = APIRouter(prefix="/hardware", tags=["hardware"])


def _with_related(
    record: dict[str, Any], plural_type: str, entity_id: str, expand: str
) -> dict[str, Any]:
    """Optionally inline the cross-entity ``related`` block when ``expand`` requests it
    (``?expand=related``), so a caller can fetch an entity and its neighbours in one round-trip."""
    if "related" not in {part.strip() for part in expand.split(",")}:
        return record
    rel = reference_data.related(plural_type, entity_id)
    return {
        **record,
        "related": rel["groups"] if rel else {},
        "relatedCounts": rel["counts"] if rel else {},
    }


@router.get("")
async def hardware(
    q: str = Query("", description="Free-text search (manufacturer / name / category / specs)"),
    category: str = Query("", description="Exact category filter"),
    manufacturer: str = Query("", description="Manufacturer substring filter"),
    limit: int = Query(50, ge=1, le=200, description="Page size"),
    offset: int = Query(0, ge=0, description="Page offset"),
) -> dict[str, Any]:
    """Search the hardware component table (filtered + paginated)."""
    return hardware_search.search(
        reference_data.hardware_items(),
        q=q,
        category=category,
        manufacturer=manufacturer,
        limit=limit,
        offset=offset,
        haystacks=reference_data.item_haystacks(),
    )


@router.get("/categories")
async def hardware_categories() -> dict[str, Any]:
    """The hardware categories + per-category and total counts (for the browser's
    sectioned catalog + filters).

    ``counts`` are the **canonical** entity counts per category (deduped boards / drivers /
    motors / hosts / catalog), so a tile matches what its panel lists; ``rawCounts`` keeps the
    underlying flat-row counts; ``total`` is the flat-row total (the cross-category search scope).
    """
    from collections import Counter

    items = reference_data.hardware_items()
    raw = Counter(str(i.get("category", "")) for i in items)
    cats = reference_data.hardware_categories()
    return {
        "categories": cats,
        "counts": reference_data.canonical_category_counts(),
        "rawCounts": {c: raw.get(c, 0) for c in cats},
        "total": len(items),
    }


@router.get("/manufacturers")
async def hardware_manufacturers(
    q: str = Query("", description="Free-text search (name / alias)"),
) -> list[dict[str, Any]]:
    """The canonical manufacturer entities — each with a stable ``manufacturer_id``, auto-derived
    ``aliases`` and a ``memberCount`` (how many hardware entities link to it), sorted
    most-connected first. Use ``GET /manufacturers/{id}?expand=related`` to list its hardware."""
    rows = reference_data.manufacturers_canonical()
    ql = q.strip().lower()
    if not ql:
        return rows
    return [
        m
        for m in rows
        if ql in str(m.get("name", "")).lower()
        or any(ql in str(a).lower() for a in m.get("aliases", []))
    ]


@router.get("/manufacturers/{manufacturer_id}")
async def manufacturer_detail(
    manufacturer_id: str,
    expand: str = Query("", description="Comma list; ``related`` inlines linked entities"),
) -> dict[str, Any]:
    """A single canonical manufacturer entity (``?expand=related`` adds its linked hardware)."""
    man = reference_data.manufacturer_by_id(manufacturer_id)
    if man is None:
        raise HTTPException(status_code=404, detail=f"No manufacturer with id {manufacturer_id!r}")
    return _with_related(man, "manufacturers", manufacturer_id, expand)


@router.get("/mcus")
async def mcus(
    q: str = Query("", description="Free-text search (name / family)"),
    family: str = Query("", description="Family substring filter (e.g. STM32F4 / AVR / RP2xxx)"),
) -> dict[str, Any]:
    """The canonical MCU entities (parsed + normalised from board ``specs.MCU``), each with a
    ``family``, ``arch`` and ``boardCount``. Small set — returned unpaginated."""
    rows = reference_data.mcus()
    ql, fam = q.strip().lower(), family.strip().lower()
    if ql:
        rows = [
            m
            for m in rows
            if ql in str(m.get("name", "")).lower() or ql in str(m.get("family", "")).lower()
        ]
    if fam:
        rows = [m for m in rows if fam in str(m.get("family", "")).lower()]
    return {"total": len(rows), "count": len(rows), "items": rows}


@router.get("/mcus/{mcu_id}")
async def mcu_detail(
    mcu_id: str,
    expand: str = Query("", description="Comma list; ``related`` inlines the boards using it"),
) -> dict[str, Any]:
    """A single canonical MCU entity (``?expand=related`` adds the boards that use it)."""
    mcu = reference_data.mcu_by_id(mcu_id)
    if mcu is None:
        raise HTTPException(status_code=404, detail=f"No MCU with id {mcu_id!r}")
    return _with_related(mcu, "mcus", mcu_id, expand)


@router.get("/boards")
async def boards(
    q: str = Query("", description="Free-text search (manufacturer / model / specs / aliases)"),
    manufacturer: str = Query("", description="Manufacturer substring filter"),
    board_class: str = Query("", description="Exact boardClass filter (mainboard / toolhead / …)"),
    limit: int = Query(50, ge=1, le=200, description="Page size"),
    offset: int = Query(0, ge=0, description="Page offset"),
) -> dict[str, Any]:
    """Search the canonical board entities (lightweight summaries, paginated).

    Each board aggregates its connectors into a single ``ports[]`` list; the full
    per-port detail is served by ``GET /api/hardware/boards/{board_id}``.
    """
    return board_search.search(
        reference_data.boards(),
        q=q,
        manufacturer=manufacturer,
        board_class=board_class,
        limit=limit,
        offset=offset,
    )


@router.get("/boards/{board_id}")
async def board_detail(
    board_id: str,
    expand: str = Query("", description="Comma list; ``related`` inlines linked entities"),
) -> dict[str, Any]:
    """The full canonical board record (identity + specs + aggregated ``ports[]`` +
    detection ``matchPatterns``) for a single ``board_id`` (``?expand=related`` adds links)."""
    board = reference_data.board_by_id(board_id)
    if board is None:
        raise HTTPException(status_code=404, detail=f"No board with id {board_id!r}")
    return _with_related(board, "boards", board_id, expand)


@router.get("/drivers")
async def drivers(
    q: str = Query("", description="Free-text search (manufacturer / name / chip / specs)"),
    manufacturer: str = Query("", description="Manufacturer substring filter"),
    klipper_only: bool = Query(False, description="Only Klipper-managed (TMC) drivers"),
    limit: int = Query(50, ge=1, le=200, description="Page size"),
    offset: int = Query(0, ge=0, description="Page offset"),
) -> dict[str, Any]:
    """Search the canonical stepper-driver entities (lightweight summaries, paginated).

    The full record — including the copyable Klipper ``[tmcXXXX]`` config snippet — is
    served by ``GET /api/hardware/drivers/{driver_id}``.
    """
    return driver_search.search(
        reference_data.drivers(),
        q=q,
        manufacturer=manufacturer,
        klipper_only=klipper_only,
        limit=limit,
        offset=offset,
    )


@router.get("/drivers/{driver_id}")
async def driver_detail(
    driver_id: str,
    expand: str = Query("", description="Comma list; ``related`` inlines linked entities"),
) -> dict[str, Any]:
    """The full canonical driver record (specs + Klipper support + copyable config snippet);
    ``?expand=related`` adds the boards that carry/support it."""
    driver = reference_data.driver_by_id(driver_id)
    if driver is None:
        raise HTTPException(status_code=404, detail=f"No driver with id {driver_id!r}")
    return _with_related(driver, "drivers", driver_id, expand)


@router.get("/motors")
async def motors(
    q: str = Query("", description="Free-text search (manufacturer / name / NEMA / specs)"),
    manufacturer: str = Query("", description="Manufacturer substring filter"),
    nema: str = Query("", description="NEMA size substring filter (e.g. 17 / 23)"),
    limit: int = Query(50, ge=1, le=200, description="Page size"),
    offset: int = Query(0, ge=0, description="Page offset"),
) -> dict[str, Any]:
    """Search the canonical stepper-motor entities (lightweight summaries, paginated).

    The full record — including the recommended ``run_current`` and the copyable Klipper
    config snippet — is served by ``GET /api/hardware/motors/{motor_id}``.
    """
    return motor_search.search(
        reference_data.motors(),
        q=q,
        manufacturer=manufacturer,
        nema=nema,
        limit=limit,
        offset=offset,
    )


@router.get("/motors/{motor_id}")
async def motor_detail(
    motor_id: str,
    expand: str = Query("", description="Comma list; ``related`` inlines linked entities"),
) -> dict[str, Any]:
    """The full canonical motor record (specs + recommended run_current + presets + snippet);
    ``?expand=related`` adds its manufacturer link."""
    motor = reference_data.motor_by_id(motor_id)
    if motor is None:
        raise HTTPException(status_code=404, detail=f"No motor with id {motor_id!r}")
    return _with_related(motor, "motors", motor_id, expand)


@router.get("/hosts")
async def hosts(
    q: str = Query("", description="Free-text search (manufacturer / name / SoC / specs)"),
    manufacturer: str = Query("", description="Manufacturer substring filter"),
    kind: str = Query("", description="Exact kind filter (sbc / x86 / os / locked)"),
    limit: int = Query(50, ge=1, le=200, description="Page size"),
    offset: int = Query(0, ge=0, description="Page offset"),
) -> dict[str, Any]:
    """Search the canonical host-computer entities (lightweight summaries, paginated).

    The full record — including the copyable Klipper HOST config snippet — is served by
    ``GET /api/hardware/hosts/{host_id}``.
    """
    return host_search.search(
        reference_data.hosts(),
        q=q,
        manufacturer=manufacturer,
        kind=kind,
        limit=limit,
        offset=offset,
    )


@router.get("/hosts/{host_id}")
async def host_detail(
    host_id: str,
    expand: str = Query("", description="Comma list; ``related`` inlines linked entities"),
) -> dict[str, Any]:
    """The full canonical host record (specs + Klipper-open flag + copyable host config snippet);
    ``?expand=related`` adds its manufacturer link."""
    host = reference_data.host_by_id(host_id)
    if host is None:
        raise HTTPException(status_code=404, detail=f"No host with id {host_id!r}")
    return _with_related(host, "hosts", host_id, expand)


@router.get("/catalog")
async def catalog(
    category: str = Query(..., description="Category name (e.g. 'Sensors & Probes', 'Extruders')"),
    q: str = Query("", description="Free-text search (manufacturer / name / specs)"),
    manufacturer: str = Query("", description="Manufacturer substring filter"),
    limit: int = Query(50, ge=1, le=200, description="Page size"),
    offset: int = Query(0, ge=0, description="Page offset"),
) -> dict[str, Any]:
    """Search one category's canonical catalog entities (lightweight summaries, paginated).

    The full record — including the copyable Klipper config snippet — is served by
    ``GET /api/hardware/catalog/{catalog_id}``.
    """
    entities = reference_data.catalog_entities(category)
    if not entities and category not in reference_data.catalog_categories():
        raise HTTPException(status_code=404, detail=f"No catalog category {category!r}")
    return catalog_search.search(
        entities, q=q, manufacturer=manufacturer, limit=limit, offset=offset
    )


@router.get("/catalog/{catalog_id}")
async def catalog_detail(
    catalog_id: str,
    expand: str = Query("", description="Comma list; ``related`` inlines linked entities"),
) -> dict[str, Any]:
    """The full catalog entity (specs + copyable config snippet) for a single ``catalog_id``;
    ``?expand=related`` adds its manufacturer link."""
    entity = reference_data.catalog_entity_by_id(catalog_id)
    if entity is None:
        raise HTTPException(status_code=404, detail=f"No catalog entity with id {catalog_id!r}")
    return _with_related(entity, "catalog", catalog_id, expand)


@router.get("/{entity_type}/{entity_id}/related")
async def entity_related(entity_type: str, entity_id: str) -> dict[str, Any]:
    """Cross-entity relationships for any node, grouped by relation (O(1) adjacency walk).

    ``entity_type`` is the plural path segment (``boards`` / ``drivers`` / ``motors`` / ``hosts``
    / ``catalog`` / ``manufacturers`` / ``mcus``). Returns ``{type, id, groups, counts}`` where
    ``groups`` maps a relation (``manufacturer`` / ``mcus`` / ``onboardDrivers`` /
    ``supportedDrivers`` / ``boards`` / ``motors`` / ``hosts`` / ``catalog``) to entity summaries.
    """
    result = reference_data.related(entity_type, entity_id)
    if result is None:
        raise HTTPException(
            status_code=404, detail=f"No {entity_type!r} node with id {entity_id!r}"
        )
    return result
