from __future__ import annotations

from fastapi import APIRouter, Depends

from app.config import Settings, get_settings
from app.models.schemas import BoardDiscovery, FirmwareStatus
from app.services import board_service, firmware_service

router = APIRouter(prefix="/firmware", tags=["firmware"])


@router.get("/status", response_model=FirmwareStatus)
async def firmware_status(settings: Settings = Depends(get_settings)) -> FirmwareStatus:
    """Read-only firmware status: host + per-MCU versions, sync check, tool readiness."""
    data = await firmware_service.gather_status(
        settings.moonraker_url, settings.klipper_dir, settings.katapult_dir
    )
    return FirmwareStatus.model_validate(data)


@router.get("/boards", response_model=BoardDiscovery)
async def firmware_boards(settings: Settings = Depends(get_settings)) -> BoardDiscovery:
    """Discovers every flashable board on the host (Moonraker + USB/CAN/DFU scans)."""
    data = await board_service.discover_boards(
        settings.moonraker_url, settings.klipper_dir, settings.katapult_dir
    )
    return BoardDiscovery.model_validate(data)
