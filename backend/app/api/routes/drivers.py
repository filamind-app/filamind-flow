from __future__ import annotations

from fastapi import APIRouter, Depends

from app.config import Settings, get_settings
from app.models.schemas import (
    DriverCatalog,
    DriversStatus,
    MotorAssignRequest,
    MotorCatalog,
    MotorMapping,
)
from app.services import driver_catalog, drivers_service, motor_catalog, motor_mapping

router = APIRouter(prefix="/drivers", tags=["drivers"])


@router.get("/status", response_model=DriversStatus)
async def drivers_status(settings: Settings = Depends(get_settings)) -> DriversStatus:
    """Read-only TMC driver inventory: every ``tmcXXXX <stepper>`` the printer has,
    with configured tuning + live telemetry + reference capabilities + the assigned motor.
    Generic across all Klipper printers."""
    data = await drivers_service.gather_drivers(settings.moonraker_url, settings.data_dir)
    return DriversStatus.model_validate(data)


@router.get("/catalog", response_model=DriverCatalog)
async def drivers_catalog() -> DriverCatalog:
    """The curated TMC driver capability map — interface, current cap, chopper modes,
    StallGuard field, sensorless / temperature support — keyed by Klipper model."""
    return DriverCatalog.model_validate(
        {"source": driver_catalog.source(), "drivers": driver_catalog.all_drivers()}
    )


@router.get("/motors", response_model=MotorCatalog)
async def drivers_motors() -> MotorCatalog:
    """The stepper-motor catalog (datasheet parameters) backing the motor picker."""
    return MotorCatalog.model_validate(
        {
            "source": motor_catalog.source(),
            "count": len(motor_catalog.all_motors()),
            "manufacturers": motor_catalog.manufacturers(),
            "motors": motor_catalog.all_motors(),
        }
    )


@router.get("/mapping", response_model=MotorMapping)
async def get_mapping(settings: Settings = Depends(get_settings)) -> MotorMapping:
    """The saved stepper -> motor assignments."""
    return MotorMapping(mapping=motor_mapping.read_mapping(settings.data_dir))


@router.post("/mapping", response_model=MotorMapping)
async def assign_motor(
    request: MotorAssignRequest, settings: Settings = Depends(get_settings)
) -> MotorMapping:
    """Assign a catalogued motor to a stepper (empty ``motor_model`` clears it)."""
    mapping = motor_mapping.assign(settings.data_dir, request.stepper, request.motor_model)
    return MotorMapping(mapping=mapping)
