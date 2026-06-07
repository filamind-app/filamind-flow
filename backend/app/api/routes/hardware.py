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
    )


@router.get("/categories")
async def hardware_categories() -> dict[str, Any]:
    """The hardware categories + per-category and total counts (for the browser's
    sectioned catalog + filters)."""
    from collections import Counter

    items = reference_data.hardware_items()
    counts = Counter(str(i.get("category", "")) for i in items)
    cats = reference_data.hardware_categories()
    return {
        "categories": cats,
        "counts": {c: counts.get(c, 0) for c in cats},
        "total": len(items),
    }


@router.get("/manufacturers")
async def hardware_manufacturers() -> list[dict[str, Any]]:
    """The manufacturer directory (name / country / website / specialty / categories)."""
    return reference_data.hardware_manufacturers()


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
async def board_detail(board_id: str) -> dict[str, Any]:
    """The full canonical board record (identity + specs + aggregated ``ports[]`` +
    detection ``matchPatterns``) for a single ``board_id``."""
    board = reference_data.board_by_id(board_id)
    if board is None:
        raise HTTPException(status_code=404, detail=f"No board with id {board_id!r}")
    return board


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
async def driver_detail(driver_id: str) -> dict[str, Any]:
    """The full canonical driver record (specs + Klipper support + copyable config snippet)."""
    driver = reference_data.driver_by_id(driver_id)
    if driver is None:
        raise HTTPException(status_code=404, detail=f"No driver with id {driver_id!r}")
    return driver


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
async def motor_detail(motor_id: str) -> dict[str, Any]:
    """The full canonical motor record (specs + recommended run_current + presets + snippet)."""
    motor = reference_data.motor_by_id(motor_id)
    if motor is None:
        raise HTTPException(status_code=404, detail=f"No motor with id {motor_id!r}")
    return motor


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
async def host_detail(host_id: str) -> dict[str, Any]:
    """The full canonical host record (specs + Klipper-open flag + copyable host config snippet)."""
    host = reference_data.host_by_id(host_id)
    if host is None:
        raise HTTPException(status_code=404, detail=f"No host with id {host_id!r}")
    return host


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
async def catalog_detail(catalog_id: str) -> dict[str, Any]:
    """The full catalog entity (specs + copyable config snippet) for a single ``catalog_id``."""
    entity = reference_data.catalog_entity_by_id(catalog_id)
    if entity is None:
        raise HTTPException(status_code=404, detail=f"No catalog entity with id {catalog_id!r}")
    return entity
