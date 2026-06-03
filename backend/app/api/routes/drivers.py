from __future__ import annotations

from fastapi import APIRouter, Depends

from app.config import Settings, get_settings
from app.models.schemas import DriversStatus
from app.services import drivers_service

router = APIRouter(prefix="/drivers", tags=["drivers"])


@router.get("/status", response_model=DriversStatus)
async def drivers_status(settings: Settings = Depends(get_settings)) -> DriversStatus:
    """Read-only TMC driver inventory: every ``tmcXXXX <stepper>`` the printer has,
    with configured tuning + live telemetry. Generic across all Klipper printers."""
    data = await drivers_service.gather_drivers(settings.moonraker_url)
    return DriversStatus.model_validate(data)
