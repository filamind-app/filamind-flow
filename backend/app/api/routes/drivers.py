from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.config import Settings, get_settings
from app.models.schemas import (
    DriverCatalog,
    DriverRecommendation,
    DriversStatus,
    MotorAssignRequest,
    MotorCatalog,
    MotorMapping,
    RecommendRequest,
)
from app.services import driver_catalog, drivers_service, motor_catalog, motor_mapping, recommender

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


@router.post("/recommend", response_model=DriverRecommendation)
async def recommend_tuning(request: RecommendRequest) -> DriverRecommendation:
    """Recommend a run current + StealthChop/SpreadCycle registers for a motor (compute-only;
    applying the values is a separate, gated step)."""
    motor = motor_catalog.lookup(request.motor_model)
    if motor is None:
        raise HTTPException(status_code=404, detail=f"Unknown motor '{request.motor_model}'")
    missing = recommender.missing_specs(motor)
    if missing:
        raise HTTPException(
            status_code=422,
            detail=f"Motor '{request.motor_model}' is missing specs: {', '.join(missing)}",
        )
    data = recommender.recommend(
        motor,
        volts=request.voltage,
        run_current=request.run_current,
        toff=request.toff,
        tbl=request.tbl,
        extra_hysteresis=request.extra_hysteresis,
        is_2240=request.is_2240,
    )
    return DriverRecommendation.model_validate(data)
