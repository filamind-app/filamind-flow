"""Macro Designer endpoints (Track A). Slice 1 = the offline G-code motion simulator.

``POST /api/macro/simulate`` takes a literal G-code program and returns the simulated toolhead
path, bounding box, totals, time estimate, and timeline — pure compute, no printer interaction.
"""

from __future__ import annotations

from typing import Any

import httpx
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.config import Settings, get_settings
from app.services import gcode_sim, live_state, macro_render
from app.services.moonraker_client import MoonrakerClient

router = APIRouter(prefix="/macro", tags=["macro"])


@router.get("/live")
async def macro_live(settings: Settings = Depends(get_settings)) -> dict[str, Any]:
    """The printer's OWN installed ``[gcode_macro]`` definitions (body + description + discovered
    params + variables), so they can be loaded into the editor and simulated. Degrades to
    ``reachable=false`` with an empty list when Moonraker is unreachable."""
    client = MoonrakerClient(settings.moonraker_url)
    try:
        configfile = await client.query_objects(["configfile"])
    except httpx.HTTPError:
        return {"reachable": False, "macros": []}
    macros = live_state.gcode_macros(live_state.settings_of(configfile))
    return {"reachable": True, "macros": macros}


@router.get("/limits")
async def macro_limits(settings: Settings = Depends(get_settings)) -> dict[str, Any]:
    """The printer's real build envelope + speed cap (from the live ``toolhead`` object), to ground
    the simulator's bounds / speed checks. ``reachable=false`` when the printer is down."""
    client = MoonrakerClient(settings.moonraker_url)
    try:
        objects = await client.query_objects(["toolhead"])
    except httpx.HTTPError:
        return {"reachable": False, "limits": None}
    return {"reachable": True, "limits": live_state.limits_of(objects.get("toolhead"))}


class SimulateRequest(BaseModel):
    """Body for ``POST /macro/simulate`` — the G-code, optional macro params, and optional machine
    limits to check moves against."""

    gcode: str = Field(
        ..., description="G-code program to simulate (may use { params.X } expressions)"
    )
    params: dict[str, str] = Field(
        default_factory=dict, description="Macro parameter values for { params.X } substitution"
    )
    limits: dict[str, Any] | None = Field(
        default=None, description="Printer envelope {min:[x,y,z], max:[x,y,z], max_velocity}"
    )


@router.post("/simulate")
async def macro_simulate(body: SimulateRequest) -> dict[str, Any]:
    """Substitute macro ``{ params.X }`` expressions, then simulate → path / bounds / totals (and,
    when ``limits`` are given, out-of-bounds / over-speed violations)."""
    rendered, warnings = macro_render.render(body.gcode, body.params)
    result = gcode_sim.simulate(rendered, body.limits)
    result["lint"] = gcode_sim.lint(rendered)
    result["warnings"] = warnings + result["warnings"]
    return result
