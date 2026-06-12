"""Mission-control overview endpoint — every home tile in one call."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from app.config import Settings, get_settings
from app.services import overview

router = APIRouter(prefix="/overview", tags=["overview"])


@router.get("")
async def get_overview(settings: Settings = Depends(get_settings)) -> dict[str, Any]:
    """Print state, per-MCU firmware sync, latest tuning per axis, hardware-change status —
    one concurrent read-only call; each block degrades independently when something is down."""
    return await overview.gather_overview(settings)
