"""Closed-loop tuning wizards. First wizard: Pressure Advance (plan a TUNING_TOWER + apply PA)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.config import Settings, get_settings
from app.models.schemas import PaApplyRequest, PaApplyResult, PaTowerPlan, PaTowerRequest
from app.services import pa_tuning

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
