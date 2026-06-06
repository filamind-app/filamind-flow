"""Max-Flow endpoints (Track B). Slice 1 is the dry-run planner only — no actuation.

``POST /api/maxflow/plan`` previews the flow ramp a run would execute (every step's flow,
feedrate, and filament pushed) plus the driver's StallGuard field — a pure compute the UI
shows before any live test. The actuating run (heat → extrude → sample) lands in a later slice.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services import max_flow_service
from app.services.max_flow_service import RampParams

router = APIRouter(prefix="/maxflow", tags=["maxflow"])


class MaxFlowPlanRequest(BaseModel):
    """Body for ``POST /maxflow/plan`` — the parameters a max-flow run would use."""

    temperature: float = Field(..., description="Hotend temperature for the test (°C)")
    start_flow: float = Field(5.0, description="First flow step (mm³/s)")
    end_flow: float = Field(25.0, description="Last flow step (mm³/s)")
    step_flow: float = Field(1.0, description="Flow increment per step (mm³/s)")
    filament_diameter: float = Field(1.75, description="Filament diameter (mm)")
    extrude_per_step: float = Field(5.0, description="Filament pushed per step (mm)")
    samples_per_step: int = Field(20, description="StallGuard samples captured per step")
    driver: str = Field("tmc2209", description="Extruder TMC driver model")


@router.post("/plan")
async def maxflow_plan(body: MaxFlowPlanRequest) -> dict[str, Any]:
    """Preview the flow ramp (pure compute; no printer interaction)."""
    params = RampParams(**body.model_dump())
    try:
        return max_flow_service.plan(params)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
