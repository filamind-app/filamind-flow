"""Board topology endpoint (Track A, read-only).

``GET /api/topology`` returns the host → MCU topology built from the live ``configfile``:
each MCU's connection type (CAN bus / USB / UART) and a best-effort chip / board guess.
"""

from __future__ import annotations

from typing import Any

import httpx
from fastapi import APIRouter, Depends

from app.config import Settings, get_settings
from app.services import board_topology
from app.services.moonraker_client import MoonrakerClient

router = APIRouter(prefix="/topology", tags=["topology"])


@router.get("")
async def topology(settings: Settings = Depends(get_settings)) -> dict[str, Any]:
    """Host → MCU topology from the live config (``reachable=False`` if Moonraker is down)."""
    client = MoonrakerClient(settings.moonraker_url)
    try:
        return await board_topology.gather_topology(client)
    except httpx.HTTPError as exc:
        return {"reachable": False, "host": None, "mcus": [], "mcu_count": 0, "detail": str(exc)}
