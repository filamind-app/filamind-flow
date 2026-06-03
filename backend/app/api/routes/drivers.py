from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.config import Settings, get_settings
from app.models.schemas import (
    ApplyRequest,
    ApplyResponse,
    ConfigBlockRequest,
    ConfigBlockResponse,
    DriverCatalog,
    DriverLive,
    DriverRecommendation,
    DriversStatus,
    HomeRequest,
    MotorAssignRequest,
    MotorCatalog,
    MotorMapping,
    RecommendRequest,
    StallguardRequest,
    StepperRequest,
)
from app.services import (
    driver_catalog,
    drivers_apply,
    drivers_service,
    motor_catalog,
    motor_mapping,
    recommender,
)

router = APIRouter(prefix="/drivers", tags=["drivers"])


@router.get("/status", response_model=DriversStatus)
async def drivers_status(settings: Settings = Depends(get_settings)) -> DriversStatus:
    """Read-only TMC driver inventory: every ``tmcXXXX <stepper>`` the printer has,
    with configured tuning + live telemetry + reference capabilities + the assigned motor.
    Generic across all Klipper printers."""
    data = await drivers_service.gather_drivers(settings.moonraker_url, settings.data_dir)
    return DriversStatus.model_validate(data)


@router.get("/live/{stepper}", response_model=DriverLive)
async def driver_live(stepper: str, settings: Settings = Depends(get_settings)) -> DriverLive:
    """Fast live telemetry for one driver (temperature / SG_RESULT / CS_ACTUAL / faults) —
    for the live monitor's quick polling. ``drv_status`` is null while the motor is disabled."""
    data = await drivers_service.gather_live(settings.moonraker_url, stepper)
    return DriverLive.model_validate(data)


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


@router.post("/config-block", response_model=ConfigBlockResponse)
async def config_block(request: ConfigBlockRequest) -> ConfigBlockResponse:
    """Render a printer.cfg override block to copy — no write, always safe."""
    text = drivers_apply.config_block(
        request.stepper, request.model, request.run_current, request.fields
    )
    return ConfigBlockResponse(text=text)


@router.post("/apply", response_model=ApplyResponse)
async def apply_tuning(
    request: ApplyRequest, settings: Settings = Depends(get_settings)
) -> ApplyResponse:
    """Write tuning to a driver now via SET_TMC_CURRENT / SET_TMC_FIELD. Refuses while
    printing; reversible with /init. The UI also requires an explicit confirm."""
    data = await drivers_apply.apply_live(
        settings.moonraker_url,
        request.stepper,
        request.run_current,
        request.hold_current,
        request.fields,
    )
    return ApplyResponse.model_validate(data)


@router.post("/init", response_model=ApplyResponse)
async def init_driver(
    request: StepperRequest, settings: Settings = Depends(get_settings)
) -> ApplyResponse:
    """INIT_TMC — re-apply the stepper's configured registers (undo a live apply)."""
    data = await drivers_apply.revert(settings.moonraker_url, request.stepper)
    return ApplyResponse.model_validate(data)


@router.post("/autotune", response_model=ApplyResponse)
async def autotune(
    request: StepperRequest, settings: Settings = Depends(get_settings)
) -> ApplyResponse:
    """Drive AUTOTUNE_TMC if the klipper_tmc_autotune extra is installed for this stepper."""
    data = await drivers_apply.run_autotune(settings.moonraker_url, request.stepper)
    return ApplyResponse.model_validate(data)


@router.post("/stallguard", response_model=ApplyResponse)
async def set_stallguard(
    request: StallguardRequest, settings: Settings = Depends(get_settings)
) -> ApplyResponse:
    """Set a StallGuard threshold (sensorless-homing sensitivity). Gated; refused while printing."""
    data = await drivers_apply.set_stallguard(
        settings.moonraker_url, request.stepper, request.field, request.value
    )
    return ApplyResponse.model_validate(data)


@router.post("/home", response_model=ApplyResponse)
async def home(request: HomeRequest, settings: Settings = Depends(get_settings)) -> ApplyResponse:
    """Home one axis (G28) as a sensorless test — moves the toolhead. Gated; the UI warns
    about crash risk and requires a confirm."""
    data = await drivers_apply.home_axis(settings.moonraker_url, request.axis)
    return ApplyResponse.model_validate(data)
