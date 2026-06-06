"""Hardware Browser endpoints (Track A, read-only).

A searchable curated 3D-printing hardware reference. All static data — no Moonraker, no writes.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.services import board_search, hardware_search, reference_data

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
    """The hardware categories + total component count (for the browser's filters)."""
    return {
        "categories": reference_data.hardware_categories(),
        "total": len(reference_data.hardware_items()),
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
