"""Board topology endpoint (Track A).

``GET /api/topology`` returns the host → MCU topology built from the live ``configfile``: each
MCU's connection type (CAN bus / USB / UART) and a best-effort chip / board guess. The board guess
can be *confirmed* or *overridden* per MCU (``POST /api/topology/override`` and
``…/override/clear``) — a persisted user choice applied to every subsequent read (the only write
path here).
"""

from __future__ import annotations

import httpx
from fastapi import APIRouter, Depends, HTTPException

from app.config import Settings, get_settings
from app.models.schemas import BoardOverrideRequest, McuKeyRequest, PinAtlas, Topology
from app.services import board_topology, reference_data, topology_overrides
from app.services.moonraker_client import MoonrakerClient

router = APIRouter(prefix="/topology", tags=["topology"])


async def _build(settings: Settings) -> Topology:
    """Build the topology from the live config, applying any saved per-MCU board overrides."""
    client = MoonrakerClient(settings.moonraker_url)
    try:
        data = await board_topology.gather_topology(client, settings.data_dir)
        return Topology.model_validate(data)
    except httpx.HTTPError as exc:
        return Topology(reachable=False, host=None, mcus=[], mcu_count=0, detail=str(exc))


@router.get("", response_model=Topology)
async def topology(settings: Settings = Depends(get_settings)) -> Topology:
    """Host → MCU topology from the live config (``reachable=False`` if Moonraker is down)."""
    return await _build(settings)


@router.post("/override", response_model=Topology)
async def set_board_override(
    request: BoardOverrideRequest, settings: Settings = Depends(get_settings)
) -> Topology:
    """Confirm / override the catalog board for an MCU. Persisted (per MCU section name) and applied
    to every future read. 404 if the ``board_id`` isn't a known catalog board."""
    if reference_data.board_by_id(request.board_id) is None:
        raise HTTPException(status_code=404, detail=f"Unknown board '{request.board_id}'")
    topology_overrides.set_override(settings.data_dir, request.mcu_name, request.board_id)
    return await _build(settings)


@router.post("/override/clear", response_model=Topology)
async def clear_board_override(
    request: McuKeyRequest, settings: Settings = Depends(get_settings)
) -> Topology:
    """Remove an MCU's board override (revert to the auto suggestion)."""
    topology_overrides.clear_override(settings.data_dir, request.mcu_name)
    return await _build(settings)


@router.get("/pin-atlas/{mcu_name}", response_model=PinAtlas)
async def pin_atlas(mcu_name: str, settings: Settings = Depends(get_settings)) -> PinAtlas:
    """The used-vs-free pin map of one MCU's resolved board + wiring-health findings (double-assign,
    electronics caveats on a used pin). ``available=false`` when the board has no pin-map."""
    client = MoonrakerClient(settings.moonraker_url)
    try:
        data = await board_topology.gather_pin_atlas(client, mcu_name, settings.data_dir)
        return PinAtlas.model_validate(data)
    except httpx.HTTPError:
        return PinAtlas(mcu_name=mcu_name, available=False)
