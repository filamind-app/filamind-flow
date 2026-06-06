"""Read-only reference-data endpoints (Phase 0 foundation).

Serve the curated Klipper datasets (StallGuard tuning, hotend table, board/MCU patterns,
built-in macros) to the frontend. Pure static reads — no Moonraker, no writes, no gating.
Payloads are returned verbatim (no response_model) so no extracted field is ever dropped.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from app.services import reference_data

router = APIRouter(prefix="/reference", tags=["reference"])


@router.get("/stallguard")
async def stallguard() -> dict[str, Any]:
    """Per-driver StallGuard slip-detection tuning constants (base + overrides + field map)."""
    return reference_data.stallguard_profiles()


@router.get("/stallguard/{driver}")
async def stallguard_for_driver(driver: str) -> dict[str, Any]:
    """The effective StallGuard constants for one driver model (base merged with its overrides)."""
    return reference_data.resolved_profile(driver)


@router.get("/hotends")
async def hotends() -> list[dict[str, Any]]:
    """Hotend melt-zone / expected max-flow / suggested test presets."""
    return reference_data.hotends()


@router.get("/boards")
async def boards() -> dict[str, Any]:
    """Board + MCU identification patterns."""
    return reference_data.board_patterns()


@router.get("/macros")
async def macros() -> list[dict[str, Any]]:
    """Built-in Klipper calibration macro definitions."""
    return reference_data.macros()
