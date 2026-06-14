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


# ── Disk cleanup (Phase 3) ─────────────────────────────────────────────────────


class CleanupRun(BaseModel):
    ids: list[str]


@router.get("/cleanup")
async def host_cleanup_scan(settings: Settings = Depends(get_settings)) -> dict[str, Any]:
    """Dry-run: how much each cleanup target would free (no deletion)."""
    return {"targets": await host_control_service.cleanup_scan(settings.data_dir)}


@router.post("/cleanup/run")
async def host_cleanup_run(
    req: CleanupRun, settings: Settings = Depends(get_settings)
) -> dict[str, Any]:
    """Clean the requested targets and report the space reclaimed."""
    return await host_control_service.cleanup_run(req.ids, settings.data_dir)


# ── System settings (Phase 4) ──────────────────────────────────────────────────


class TimezoneReq(BaseModel):
    timezone: str


class NtpReq(BaseModel):
    enabled: bool


class TimeReq(BaseModel):
    value: str


class LocaleReq(BaseModel):
    lang: str


class KeymapReq(BaseModel):
    keymap: str


class HostnameReq(BaseModel):
    hostname: str


class PowerReq(BaseModel):
    action: str


class NetworkReq(BaseModel):
    method: str  # 'auto' | 'manual'
    address: str = ""
    cidr: int | None = None
    gateway: str = ""
    dns: str = ""  # comma/space-separated IPv4 list


async def _apply(coro: Any) -> dict[str, Any]:
    """Run a setter coroutine, mapping ValueError → 400 and a refusal → 403."""
    try:
        result = await coro
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if result.get("refused"):
        raise HTTPException(status_code=403, detail=result["output"])
    return result


@router.get("/system")
async def host_system_info() -> dict[str, Any]:
    """Current time/locale/hostname/network settings + the option lists for the System form."""
    return await host_control_service.system_info()


@router.post("/system/timezone")
async def host_set_timezone(req: TimezoneReq) -> dict[str, Any]:
    return await _apply(host_control_service.set_timezone(req.timezone))


@router.post("/system/ntp")
async def host_set_ntp(req: NtpReq) -> dict[str, Any]:
    return await _apply(host_control_service.set_ntp(req.enabled))


@router.post("/system/time")
async def host_set_time(req: TimeReq) -> dict[str, Any]:
    return await _apply(host_control_service.set_time(req.value))


@router.post("/system/locale")
async def host_set_locale(req: LocaleReq) -> dict[str, Any]:
    return await _apply(host_control_service.set_locale(req.lang))


@router.post("/system/keymap")
async def host_set_keymap(req: KeymapReq) -> dict[str, Any]:
    return await _apply(host_control_service.set_keymap(req.keymap))


@router.post("/system/hostname")
async def host_set_hostname(req: HostnameReq) -> dict[str, Any]:
    return await _apply(host_control_service.set_hostname(req.hostname))


@router.post("/system/power")
async def host_power(req: PowerReq, settings: Settings = Depends(get_settings)) -> dict[str, Any]:
    return await _apply(host_control_service.power(req.action, settings.moonraker_url))


@router.post("/system/network")
async def host_set_network(
    req: NetworkReq, settings: Settings = Depends(get_settings)
) -> dict[str, Any]:
    return await _apply(
        host_control_service.set_network(
            req.method, req.address, req.cidr, req.gateway, req.dns, settings.moonraker_url
        )
    )
