"""Macro Designer endpoints (Track A). Slice 1 = the offline G-code motion simulator.

``POST /api/macro/simulate`` takes a literal G-code program and returns the simulated toolhead
path, bounding box, totals, time estimate, and timeline — pure compute, no printer interaction.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.services import gcode_sim, macro_render

router = APIRouter(prefix="/macro", tags=["macro"])


class SimulateRequest(BaseModel):
    """Body for ``POST /macro/simulate`` — the G-code to simulate, with optional macro params."""

    gcode: str = Field(
        ..., description="G-code program to simulate (may use { params.X } expressions)"
    )
    params: dict[str, str] = Field(
        default_factory=dict, description="Macro parameter values for { params.X } substitution"
    )


@router.post("/simulate")
async def macro_simulate(body: SimulateRequest) -> dict[str, Any]:
    """Substitute macro ``{ params.X }`` expressions, then simulate → path / bounds / totals."""
    rendered, warnings = macro_render.render(body.gcode, body.params)
    result = gcode_sim.simulate(rendered)
    result["warnings"] = warnings + result["warnings"]
    return result
