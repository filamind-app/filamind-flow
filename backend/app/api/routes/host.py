"""Linux host control endpoints - read (and, in later phases, change) the printer host's OS state.

Phase 1: a read-only health + OS-state monitor (CPU / temp / memory / disk / network / time /
locale). Phase 2: a systemd service manager (list / control / logs / delete). The remaining
system-changing actions (cleanup, time/locale/hostname/power) land in later phases behind
confirmations and the host's passwordless-sudo rule.
"""

from __future__ import annotations

import base64
import binascii
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.config import Settings, get_settings
from app.services import canbus_control, host_control_service

router = APIRouter(prefix="/host", tags=["host"])


@router.get("/monitor")
async def host_monitor(settings: Settings = Depends(get_settings)) -> dict[str, Any]:
    """Read-only snapshot of host health + OS state for the Host Control widget."""
    return await host_control_service.monitor(settings.data_dir)


@router.get("/advisor")
async def host_advisor(settings: Settings = Depends(get_settings)) -> dict[str, Any]:
    """Graded host-health cards (CPU / memory / disk / clock / services) + fix hints. Read-only."""
    return await host_control_service.advisory(settings.data_dir)


@router.get("/boot")
async def host_boot() -> dict[str, Any]:
    """Read-only boot configuration: default systemd target, active boot splash, plymouth theme."""
    return await host_control_service.boot_info()


@router.get("/boot/splash")
async def host_boot_splash() -> FileResponse:
    """Serve the active boot-splash image (restricted to the known splash locations) for preview."""
    path = host_control_service.splash_path()
    if not path:
        raise HTTPException(status_code=404, detail="No boot splash found on this host.")
    return FileResponse(path)


class SplashSet(BaseModel):
    image: str  # base64 PNG, optionally a "data:image/png;base64,…" data URL
    target: str | None = None


@router.post("/boot/splash")
async def host_set_boot_splash(req: SplashSet) -> dict[str, Any]:
    """Write a new boot-splash PNG to a known splash location (gated: validated + path-guarded +
    narrow privileged copy). Refuses (403) a non-PNG / oversize / out-of-bounds path."""
    raw = req.image.split(",", 1)[-1]
    try:
        data = base64.b64decode(raw, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise HTTPException(status_code=400, detail="Invalid image data.") from exc
    return await _apply(host_control_service.set_splash(data, req.target))


# -- Services (Phase 2) ---------------------------------------------------------


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


# -- Disk cleanup (Phase 3) -----------------------------------------------------


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


# -- CAN bus control (Phase 5) --------------------------------------------------
# View + manage the host's SocketCAN interfaces (link up/down, bitrate). Reads are unprivileged;
# changes go through the host's passwordless-sudo grant and are refused while a print is running.


class CanLinkReq(BaseModel):
    iface: str
    up: bool


class CanBitrateReq(BaseModel):
    iface: str
    bitrate: int


class CanParamsReq(BaseModel):
    iface: str
    params: dict[str, Any]  # any of bitrate/sample_point/sjw/restart_ms/dbitrate/flags/txqueuelen/…


class CanRestartReq(BaseModel):
    iface: str


@router.get("/canbus")
async def host_canbus(settings: Settings = Depends(get_settings)) -> dict[str, Any]:
    """Every host CAN interface with live status (link state, controller state, bitrate, error
    counters, tx queue length) + its best-effort bridging-adapter link. Read-only."""
    return {"buses": await canbus_control.list_can_buses(settings.moonraker_url, settings.data_dir)}


@router.post("/canbus/link")
async def host_canbus_link(
    req: CanLinkReq, settings: Settings = Depends(get_settings)
) -> dict[str, Any]:
    """Bring a CAN interface up or down (sudo ip link). Refused (403) while a print is running."""
    return await _apply(canbus_control.set_link(req.iface, req.up, settings.moonraker_url))


@router.post("/canbus/bitrate")
async def host_canbus_bitrate(
    req: CanBitrateReq, settings: Settings = Depends(get_settings)
) -> dict[str, Any]:
    """Set a CAN interface's bitrate (the interface must be down first). Refused while printing."""
    return await _apply(canbus_control.set_bitrate(req.iface, req.bitrate, settings.moonraker_url))


@router.post("/canbus/params")
async def host_canbus_params(
    req: CanParamsReq, settings: Settings = Depends(get_settings)
) -> dict[str, Any]:
    """Set any combination of CAN parameters (bit timing, control modes, recovery, CAN-FD,
    txqueuelen). All but txqueuelen need the interface down. 400 on a bad value; refused (403) while
    printing."""
    return await _apply(canbus_control.set_params(req.iface, req.params, settings.moonraker_url))


@router.post("/canbus/restart")
async def host_canbus_restart(
    req: CanRestartReq, settings: Settings = Depends(get_settings)
) -> dict[str, Any]:
    """Restart a BUS-OFF CAN controller to recover the bus. Refused while printing."""
    return await _apply(canbus_control.set_restart(req.iface, settings.moonraker_url))


# -- System settings (Phase 4) --------------------------------------------------


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
