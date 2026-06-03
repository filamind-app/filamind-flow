from __future__ import annotations

from fastapi import APIRouter, Depends

from app.config import Settings, get_settings
from app.models.schemas import DriverCatalog, DriversStatus
from app.services import driver_catalog, drivers_service

router = APIRouter(prefix="/drivers", tags=["drivers"])


@router.get("/status", response_model=DriversStatus)
async def drivers_status(settings: Settings = Depends(get_settings)) -> DriversStatus:
    """Read-only TMC driver inventory: every ``tmcXXXX <stepper>`` the printer has,
    with configured tuning + live telemetry + reference capabilities. Generic across all
    Klipper printers."""
    data = await drivers_service.gather_drivers(settings.moonraker_url)
    return DriversStatus.model_validate(data)


@router.get("/catalog", response_model=DriverCatalog)
async def drivers_catalog() -> DriverCatalog:
    """The curated TMC driver capability map — interface, current cap, chopper modes,
    StallGuard field, sensorless / temperature support — keyed by Klipper model."""
    return DriverCatalog.model_validate(
        {"source": driver_catalog.source(), "drivers": driver_catalog.all_drivers()}
    )
