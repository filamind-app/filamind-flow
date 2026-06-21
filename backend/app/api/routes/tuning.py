"""Closed-loop tuning wizards. First wizard: Pressure Advance (plan a TUNING_TOWER + apply PA)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.config import Settings, get_settings
from app.models.schemas import (
    PaApplyRequest,
    PaApplyResult,
    PaTowerPlan,
    PaTowerRequest,
    RetractionApplyRequest,
    RetractionApplyResult,
    RetractionTowerPlan,
    RetractionTowerRequest,
    TempApplyRequest,
    TempApplyResult,
    TempTowerPlan,
    TempTowerRequest,
)
from app.services import pa_tuning, retraction_tuning, temp_tuning

router = APIRouter(prefix="/tuning", tags=["tuning"])


@router.post("/pa/plan", response_model=PaTowerPlan)
async def pa_plan(req: PaTowerRequest) -> PaTowerPlan:
    """The TUNING_TOWER command + height->PA table for a PA tower (read-only)."""
    try:
        plan = pa_tuning.plan_tower(
            pa_tuning.PaTowerParams(start=req.start, factor=req.factor, height=req.height)
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return PaTowerPlan(**plan)


@router.post("/pa/apply", response_model=PaApplyResult)
async def pa_apply(
    req: PaApplyRequest, settings: Settings = Depends(get_settings)
) -> PaApplyResult:
    """Apply the chosen PA value live (gated; refuses while the printer is busy)."""
    result = await pa_tuning.apply_pa(settings.moonraker_url, req.value)
    return PaApplyResult(**result)


@router.post("/retraction/plan", response_model=RetractionTowerPlan)
async def retraction_plan(req: RetractionTowerRequest) -> RetractionTowerPlan:
    """The TUNING_TOWER command + height->retraction-length table for a tower (read-only)."""
    try:
        plan = retraction_tuning.plan_tower(
            retraction_tuning.RetractionTowerParams(
                start=req.start, factor=req.factor, height=req.height
            )
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return RetractionTowerPlan(**plan)


@router.post("/retraction/apply", response_model=RetractionApplyResult)
async def retraction_apply(
    req: RetractionApplyRequest, settings: Settings = Depends(get_settings)
) -> RetractionApplyResult:
    """Apply the chosen retraction length live (gated; needs ``[firmware_retraction]``)."""
    result = await retraction_tuning.apply_retraction(settings.moonraker_url, req.value)
    return RetractionApplyResult(**result)


@router.post("/temp/plan", response_model=TempTowerPlan)
async def temp_plan(req: TempTowerRequest) -> TempTowerPlan:
    """The TUNING_TOWER (BAND) command + per-band temperature table for a tower (read-only)."""
    try:
        plan = temp_tuning.plan_tower(
            temp_tuning.TempTowerParams(
                start=req.start,
                factor=req.factor,
                band=req.band,
                height=req.height,
                heater=req.heater,
            )
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return TempTowerPlan(**plan)


@router.post("/temp/apply", response_model=TempApplyResult)
async def temp_apply(
    req: TempApplyRequest, settings: Settings = Depends(get_settings)
) -> TempApplyResult:
    """Set the chosen temperature live (gated; allowlisted heater + bounded target)."""
    result = await temp_tuning.apply_temp(settings.moonraker_url, req.heater, req.value)
    return TempApplyResult(**result)
