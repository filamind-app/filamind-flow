from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from app.config import Settings, get_settings
from app.models.schemas import (
    ApplyRequest,
    ApplyResponse,
    ConfigBlockRequest,
    ConfigBlockResponse,
    CoolstepRequest,
    DriverCatalog,
    DriverLive,
    DriverRecommendation,
    DriversStatus,
    EndstopStates,
    FieldPolicyResponse,
    HomeRequest,
    MotorAssignRequest,
    MotorCatalog,
    MotorMapping,
    MotorsSyncRequest,
    MotorsSyncStatus,
    RecommendRequest,
    SetFieldRequest,
    StallguardRequest,
    StepperRequest,
)
from app.services import (
    drivers_apply,
    drivers_service,
    field_policy,
    motor_mapping,
    printer_guard,
    recommender,
    reference_data,
)

router = APIRouter(prefix="/drivers", tags=["drivers"])


async def _guarded(operation: str, call: Any, /, *args: Any, **kwargs: Any) -> dict[str, Any]:
    """Run an actuating drivers_apply call while holding the printer's exclusive slot.

    A taken slot becomes the widget's soft-error result shape (code ``guardLocked``) rather
    than an HTTP error, matching how every other apply refusal reaches the UI.
    """
    try:
        async with printer_guard.acquire(operation):
            result: dict[str, Any] = await call(*args, **kwargs)
            return result
    except printer_guard.GuardBusyError as exc:
        return {
            "ok": False,
            "applied": [],
            "message": str(exc),
            "code": "guardLocked",
            "params": {"operation": exc.operation},
        }


@router.get("/status", response_model=DriversStatus)
async def drivers_status(settings: Settings = Depends(get_settings)) -> DriversStatus:
    """Read-only TMC driver inventory: every ``tmcXXXX <stepper>`` the printer has,
    with configured tuning + live telemetry + reference capabilities + the assigned motor.
    Generic across all Klipper printers."""
    data = await drivers_service.gather_drivers(settings.moonraker_url, settings.data_dir)
    return DriversStatus.model_validate(data)


@router.get("/endstops", response_model=EndstopStates)
async def endstops(settings: Settings = Depends(get_settings)) -> EndstopStates:
    """Live endstop trigger state (open / TRIGGERED), actively queried on demand. Useful for
    physical-switch axes; a sensorless axis only reads meaningfully during a homing move."""
    data = await drivers_service.gather_endstops(settings.moonraker_url)
    return EndstopStates.model_validate(data)


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
        {"source": "Curated TMC driver reference", "drivers": reference_data.driver_infos()}
    )


@router.get("/motors", response_model=MotorCatalog)
async def drivers_motors() -> MotorCatalog:
    """The stepper-motor catalog (datasheet parameters) backing the motor picker — served from
    the unified hardware catalog (the single source of truth)."""
    motors = reference_data.motor_specs()
    return MotorCatalog.model_validate(
        {
            "source": "Hardware reference catalog",
            "count": len(motors),
            "manufacturers": reference_data.motor_spec_manufacturers(),
            "motors": motors,
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
    motor = reference_data.motor_spec_lookup(request.motor_model)
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
    data = await _guarded(
        "driver_write",
        drivers_apply.apply_live,
        settings.moonraker_url,
        request.stepper,
        request.run_current,
        request.hold_current,
        request.fields,
        data_dir=settings.data_dir,
    )
    return ApplyResponse.model_validate(data)


@router.post("/init", response_model=ApplyResponse)
async def init_driver(
    request: StepperRequest, settings: Settings = Depends(get_settings)
) -> ApplyResponse:
    """INIT_TMC — re-apply the stepper's configured registers (undo a live apply)."""
    data = await _guarded(
        "driver_write", drivers_apply.revert, settings.moonraker_url, request.stepper
    )
    return ApplyResponse.model_validate(data)


@router.post("/autotune", response_model=ApplyResponse)
async def autotune(
    request: StepperRequest, settings: Settings = Depends(get_settings)
) -> ApplyResponse:
    """Drive AUTOTUNE_TMC if a TMC autotune host extra is installed for this stepper."""
    data = await _guarded(
        "driver_write", drivers_apply.run_autotune, settings.moonraker_url, request.stepper
    )
    return ApplyResponse.model_validate(data)


@router.post("/stallguard", response_model=ApplyResponse)
async def set_stallguard(
    request: StallguardRequest, settings: Settings = Depends(get_settings)
) -> ApplyResponse:
    """Set a StallGuard threshold (sensorless-homing sensitivity). Gated; refused while printing."""
    data = await _guarded(
        "driver_write",
        drivers_apply.set_stallguard,
        settings.moonraker_url,
        request.stepper,
        request.field,
        request.value,
    )
    return ApplyResponse.model_validate(data)


@router.get("/field-policy/{model}", response_model=FieldPolicyResponse)
async def field_policy_for_model(model: str) -> FieldPolicyResponse:
    """The editable-register policy for one TMC model — which fields the editor may expose, with
    each one's control type + clamp range. Blocked and non-applicable fields are omitted."""
    return FieldPolicyResponse(model=model, fields=field_policy.policy_for(model))


@router.post("/field", response_model=ApplyResponse)
async def set_field(
    request: SetFieldRequest, settings: Settings = Depends(get_settings)
) -> ApplyResponse:
    """Write one editable TMC register field live via SET_TMC_FIELD. Gated (refused while
    printing / paused / error) and clamped server-side by the field_policy allowlist; raw
    current-scaling and protection-defeat fields are blocked. Reversible with /init."""
    data = await _guarded(
        "driver_write",
        drivers_apply.set_field,
        settings.moonraker_url,
        request.stepper,
        request.field,
        request.value,
        model=request.model,
    )
    return ApplyResponse.model_validate(data)


@router.post("/coolstep", response_model=ApplyResponse)
async def coolstep(
    request: CoolstepRequest, settings: Settings = Depends(get_settings)
) -> ApplyResponse:
    """Enable CoolStep with a single vetted register set (semin/semax/seup/sedn/seimin), or
    disable it. Gated + clamped like any register write; reversible with /init."""
    data = await _guarded(
        "driver_write",
        drivers_apply.set_coolstep,
        settings.moonraker_url,
        request.stepper,
        request.enable,
        model=request.model,
    )
    return ApplyResponse.model_validate(data)


@router.post("/home", response_model=ApplyResponse)
async def home(request: HomeRequest, settings: Settings = Depends(get_settings)) -> ApplyResponse:
    """Home one axis (G28) as a sensorless test — moves the toolhead. Gated; the UI warns
    about crash risk and requires a confirm."""
    data = await _guarded("homing", drivers_apply.home_axis, settings.moonraker_url, request.axis)
    return ApplyResponse.model_validate(data)


@router.get("/motors-sync", response_model=MotorsSyncStatus)
async def motors_sync_status(settings: Settings = Depends(get_settings)) -> MotorsSyncStatus:
    """Whether the motors_sync add-on is installed (for the motor-sync panel)."""
    available = await drivers_apply.motors_sync_available(settings.moonraker_url)
    return MotorsSyncStatus(available=available)


@router.post("/motors-sync", response_model=ApplyResponse)
async def motors_sync(
    request: MotorsSyncRequest, settings: Settings = Depends(get_settings)
) -> ApplyResponse:
    """Run motor synchronization (dual/quad-Z, dual-X) via the motors_sync add-on — moves the
    toolhead. Gated; refused while printing and when the add-on isn't installed."""
    data = await _guarded(
        "motors_sync",
        drivers_apply.run_motors_sync,
        settings.moonraker_url,
        calibrate=request.calibrate,
    )
    return ApplyResponse.model_validate(data)
