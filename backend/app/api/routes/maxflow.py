"""Max-Flow endpoints (Track B). Slice 1 is the dry-run planner only — no actuation.

``POST /api/maxflow/plan`` previews the flow ramp a run would execute (every step's flow,
feedrate, and filament pushed) plus the driver's StallGuard field — a pure compute the UI
shows before any live test. The actuating run (heat → extrude → sample) lands in a later slice.
"""

from __future__ import annotations

import asyncio
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.config import Settings, get_settings
from app.services import max_flow_service, printer_guard, task_store
from app.services.max_flow_service import RampParams
from app.services.moonraker_client import MoonrakerClient

router = APIRouter(prefix="/maxflow", tags=["maxflow"])

#: Heating + the extrusion ramp block for minutes — the run client needs a long timeout.
_RUN_TIMEOUT_S = 1200.0


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


@router.post("/run")
async def maxflow_run(
    body: MaxFlowPlanRequest, settings: Settings = Depends(get_settings)
) -> dict[str, Any]:
    """Run the live max-flow test (ACTUATING: heat + extrude + sample StallGuard).

    Refused while the printer is busy (409). The heater is always turned off when it finishes,
    and the ramp stops as soon as slip is detected.
    """
    client = MoonrakerClient(settings.moonraker_url, timeout=_RUN_TIMEOUT_S)
    params = RampParams(**body.model_dump())
    try:
        async with printer_guard.acquire("max_flow"):
            return await max_flow_service.run_max_flow(client, params)
    except printer_guard.GuardBusyError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except max_flow_service.MaxFlowBusyError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except max_flow_service.MaxFlowPreflightError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Moonraker error: {exc}") from exc


#: Strong refs so background supervised runs aren't garbage-collected mid-flight.
_background: set[asyncio.Task[None]] = set()


async def _run_maxflow_task(task: task_store.Task, params: RampParams, settings: Settings) -> None:
    """Body of a supervised max-flow run: holds the guard slot, reports per-step progress,
    holds the result on the task, and honours cancellation (the heater is always cut)."""

    def on_progress(step: int, total: int, detail: dict) -> None:
        task.progress = {"step": step, "total": total, "detail": detail}

    client = MoonrakerClient(settings.moonraker_url, timeout=_RUN_TIMEOUT_S)
    try:
        async with printer_guard.acquire("max_flow"):
            result = await max_flow_service.run_max_flow(
                client, params, progress_cb=on_progress, cancel_cb=lambda: task.cancelled
            )
        task.result = result
        task.status = "done"
    except task_store.TaskCancelled:
        task.status = "cancelled"
    except printer_guard.GuardBusyError as exc:
        task.append(f"!! {exc}\n")
        task.status = "failed"
    except (
        ValueError,
        max_flow_service.MaxFlowBusyError,
        max_flow_service.MaxFlowPreflightError,
    ) as exc:
        task.append(f"!! {exc}\n")
        task.status = "failed"
    except Exception as exc:  # a supervised task must never die silently
        task.append(f"!! Max-flow run failed: {exc}\n")
        task.status = "failed"


@router.post("/run/start")
async def maxflow_run_start(
    body: MaxFlowPlanRequest, settings: Settings = Depends(get_settings)
) -> dict[str, str]:
    """Start the max-flow test as a SUPERVISED background run: returns a task id to poll
    (``/api/tasks/{id}``) with per-step progress, a Cancel that always cuts the heater, and
    the result held server-side. Same ramp as ``/run``."""
    params = RampParams(**body.model_dump())
    try:
        max_flow_service.validate(params)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    task = task_store.create_task()
    background = asyncio.create_task(_run_maxflow_task(task, params, settings))
    _background.add(background)
    background.add_done_callback(_background.discard)
    return {"task_id": task.id}
