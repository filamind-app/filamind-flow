"""Linux host control endpoints — read (and, in later phases, change) the printer host's OS state.

Phase 1: a read-only health + OS-state monitor (CPU / temp / memory / disk / network / time /
locale). Phase 2: a systemd service manager (list / control / logs / delete). The remaining
system-changing actions (cleanup, time/locale/hostname/power) land in later phases behind
confirmations and the host's passwordless-sudo rule.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.config import Settings, get_settings
from app.services import host_control_service

router = APIRouter(prefix="/host", tags=["host"])


@router.get("/monitor")
async def host_monitor(settings: Settings = Depends(get_settings)) -> dict[str, Any]:
    """Read-only snapshot of host health + OS state for the Host Control widget."""
    return await host_control_service.monitor(settings.data_dir)


# ── Services (Phase 2) ─────────────────────────────────────────────────────────


class ServiceAction(BaseModel):
    name: str
    action: str


class ServiceDelete(BaseModel):
    name: str
    confirm: str


@router.get("/services")
async def host_services() -> dict[str, Any]:
    """All systemd .service units with their state (read-only)."""
    return {"services": await host_control_service.list_units()}


@router.get("/services/detail")
async def host_service_detail(name: str = Query(...)) -> dict[str, Any]:
    """Per-unit detail + whether its unit file is safe to delete."""
    try:
        return await host_control_service.unit_detail(name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/services/logs")
async def host_service_logs(name: str = Query(...), lines: int = Query(200)) -> dict[str, Any]:
    """Recent journal lines for a unit (read-only)."""
    try:
        return {"name": name, "logs": await host_control_service.unit_logs(name, lines)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/services/action")
async def host_service_action(req: ServiceAction) -> dict[str, Any]:
    """Run a systemctl action (start/stop/restart/enable/disable/mask/unmask) on a unit."""
    try:
        result = await host_control_service.manage_unit(req.name, req.action)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if result.get("refused"):
        raise HTTPException(status_code=403, detail=result["output"])
    return result


@router.post("/services/delete")
async def host_service_delete(req: ServiceDelete) -> dict[str, Any]:
    """Remove a user-installed unit file (typed-confirm + path-guarded to /etc/systemd/system)."""
    try:
        result = await host_control_service.delete_unit(req.name, req.confirm)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if result.get("refused"):
        raise HTTPException(status_code=403, detail=result["output"])
    return result
