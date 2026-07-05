"""FilaMind Setup endpoints - browse the component catalog, see what's installed, and (only when
the host opts in via FILAMIND_SETUP_WRITES) install / update / remove components.

Mutations funnel through setup_manager, which is gated + path-guarded; a disabled write returns 403.
"""

from __future__ import annotations

import asyncio
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.config import Settings, get_settings
from app.services import setup_manager, task_store
from app.services.moonraker_client import MoonrakerClient

router = APIRouter(prefix="/setup", tags=["setup"])

#: Hold background install tasks so they aren't garbage-collected mid-run.
_bg: set[asyncio.Task[None]] = set()


class ComponentRef(BaseModel):
    id: str
    #: Optional port for installing a first-party web app (e.g. FilaMind 3d) onto a chosen port.
    port: int | None = None
    #: Optional install action - ``"service"`` installs a first-party app's additional managed
    #: deployment (FilaMind 3d → the agent service), instead of its default install.
    action: str | None = None


class AutoUpdateRef(BaseModel):
    enabled: bool
    intervalHours: int = 24


class RemoveRef(BaseModel):
    id: str
    confirm: str


class PortRef(BaseModel):
    id: str
    port: int


class WritesRef(BaseModel):
    enabled: bool


class IncludeRef(BaseModel):
    id: str
    add: bool


async def _moonraker_full(
    settings: Settings,
) -> tuple[dict[str, Any], set[str], int | None]:
    """Best-effort (update-manager ``version_info``, managed services, remaining GitHub quota) from
    Moonraker; empty when unreachable. ``version_info`` carries each managed component's version /
    remote_version / commits_behind; the remaining-quota number gates best-effort GitHub lookups.
    On ANY failure callers fall back to the dir heuristic, so the status read never 500s.
    """
    client = MoonrakerClient(settings.moonraker_url)
    try:
        raw = await client.update_status_full()
        vi = raw.get("version_info")
        version_info = vi if isinstance(vi, dict) else {}
        remaining = raw.get("github_requests_remaining")
        services = {s.lower() for s in await client.available_services()}
        return version_info, services, (remaining if isinstance(remaining, int) else None)
    except (httpx.HTTPError, ValueError):
        return {}, set(), None


async def _moonraker_signals(settings: Settings) -> tuple[set[str], set[str]]:
    """(update-manager keys, managed services) for install detection - install/port paths only need
    the boolean signals, not versions, so this thin wrapper keeps their call sites unchanged."""
    version_info, services, _ = await _moonraker_full(settings)
    return {k.lower() for k in version_info}, services


@router.get("/catalog")
async def setup_catalog() -> dict[str, Any]:
    """The component catalog (groups → components)."""
    return setup_manager.catalog_payload()


@router.get("/status")
async def setup_status(settings: Settings = Depends(get_settings)) -> dict[str, Any]:
    """Per-component install state + version numbers + an update-available flag, plus whether GUI
    writes are enabled on this host."""
    version_info, services, github_remaining = await _moonraker_full(settings)
    return {
        "status": await setup_manager.probe_detailed(version_info, services, github_remaining),
        "writesEnabled": setup_manager.writes_enabled(),
        "autoUpdate": setup_manager.autoupdate_prefs(),
    }


def _apply(result: dict[str, Any]) -> dict[str, Any]:
    if result.get("refused"):
        raise HTTPException(status_code=403, detail=result["output"])
    return result


@router.post("/install")
async def setup_install(
    req: ComponentRef, settings: Settings = Depends(get_settings)
) -> dict[str, Any]:
    managed, services = await _moonraker_signals(settings)
    try:
        return _apply(
            await setup_manager.install(req.id, managed, services, port=req.port, action=req.action)
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/install/stream")
async def setup_install_stream(
    req: ComponentRef, settings: Settings = Depends(get_settings)
) -> dict[str, Any]:
    """Start an install as a background task and return its id; the widget polls /api/tasks/{id} for
    live progress. The refusal gates (writes-off / missing-deps) still raise a SYNCHRONOUS 403 here,
    before any task is created, so a refused install never looks like a started one."""
    managed, services = await _moonraker_signals(settings)
    try:
        refusal = await setup_manager.precheck_install(req.id, managed, services)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if refusal:
        _apply(refusal)  # raises 403
    task = task_store.create_task()
    bg = asyncio.create_task(
        setup_manager.install_task(
            req.id, task, managed, services, port=req.port, action=req.action
        )
    )
    _bg.add(bg)
    bg.add_done_callback(_bg.discard)
    return {"task_id": task.id}


@router.post("/update")
async def setup_update(
    req: ComponentRef, settings: Settings = Depends(get_settings)
) -> dict[str, Any]:
    """Update a component. Moonraker-managed ones (Mainsail, Fluidd, Klipper, Moonraker,
    KlipperScreen) go through Moonraker's update manager; an unmanaged git checkout gets a git pull.
    """
    managed, _ = await _moonraker_signals(settings)
    client = MoonrakerClient(settings.moonraker_url)

    async def mr_update(name: str) -> None:
        await client.update_client(name)

    try:
        return _apply(await setup_manager.update(req.id, managed, mr_update))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/remove")
async def setup_remove(
    req: RemoveRef, settings: Settings = Depends(get_settings)
) -> dict[str, Any]:
    # Pass the Moonraker signals so the dependency guard also detects managed/service-only
    # dependents (e.g. a Mainsail that Moonraker tracks but that isn't cloned under $HOME).
    managed, services = await _moonraker_signals(settings)
    try:
        return _apply(await setup_manager.remove(req.id, req.confirm, managed, services))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/restart")
async def setup_restart(req: ComponentRef) -> dict[str, Any]:
    """Restart a component's runtime - reload nginx for a first-party app (3d/screen), or restart a
    component's own systemd service. Shows whether 3d/screen are working and lets the user recover
    them without leaving the panel."""
    try:
        return _apply(await setup_manager.restart(req.id))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/logs")
async def setup_logs(req: ComponentRef) -> dict[str, Any]:
    """The last lines of a component's systemd journal (read-only) - debug a failed install/start
    without SSH. Always allowed (no writes gate)."""
    try:
        return _apply(await setup_manager.service_logs(req.id))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/register")
async def setup_register(req: ComponentRef) -> dict[str, Any]:
    """Register an installed unmanaged git checkout with Moonraker's update manager, so it gains
    reliable Moonraker-tracked updates."""
    try:
        return _apply(await setup_manager.register_component(req.id))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/include")
async def setup_include(req: IncludeRef) -> dict[str, Any]:
    """Wire an add-on into printer.cfg (or remove its ``[include]``) - so a cloned config add-on
    (KAMP, Nevermore…) is actually active, not just downloaded."""
    try:
        return _apply(await setup_manager.toggle_include(req.id, req.add))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/writes")
async def setup_writes(req: WritesRef) -> dict[str, Any]:
    """Enable/disable installing from the widget itself (no CLI / no env var needed)."""
    return {"writesEnabled": setup_manager.set_writes_enabled(req.enabled)}


@router.get("/autoupdate")
async def setup_autoupdate_get() -> dict[str, Any]:
    """Current auto-update preferences (enabled + interval in hours)."""
    return setup_manager.autoupdate_prefs()


@router.post("/autoupdate")
async def setup_autoupdate_set(req: AutoUpdateRef) -> dict[str, Any]:
    """Persist auto-update preferences. When enabled, a background loop applies available updates on
    the chosen interval - but only while the printer is idle, never mid-print."""
    return setup_manager.set_autoupdate_prefs(req.enabled, req.intervalHours)


@router.post("/port")
async def setup_port(req: PortRef, settings: Settings = Depends(get_settings)) -> dict[str, Any]:
    managed, services = await _moonraker_signals(settings)
    try:
        return _apply(await setup_manager.set_port(req.id, req.port, managed, services))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
