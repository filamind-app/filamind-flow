"""FilaMind Setup endpoints — browse the component catalog, see what's installed, and (only when
the host opts in via FILAMIND_SETUP_WRITES) install / update / remove components.

Mutations funnel through setup_manager, which is gated + path-guarded; a disabled write returns 403.
"""

from __future__ import annotations

from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.config import Settings, get_settings
from app.services import setup_manager
from app.services.moonraker_client import MoonrakerClient

router = APIRouter(prefix="/setup", tags=["setup"])


class ComponentRef(BaseModel):
    id: str


class RemoveRef(BaseModel):
    id: str
    confirm: str


async def _moonraker_signals(settings: Settings) -> tuple[set[str], set[str]]:
    """Best-effort (update-manager keys, managed services) from Moonraker; empty when unreachable.

    These refine install detection; on ANY failure the manager falls back to the dir heuristic, so
    the widget's status read never 500s. ``ValueError`` covers a non-JSON 200 body (json decode);
    ``httpx.HTTPError`` covers unreachable/refused/bad-status (matches beacon_service's pattern).
    """
    client = MoonrakerClient(settings.moonraker_url)
    try:
        managed = {k.lower() for k in await client.update_status()}
        services = {s.lower() for s in await client.available_services()}
        return managed, services
    except (httpx.HTTPError, ValueError):
        return set(), set()


@router.get("/catalog")
async def setup_catalog() -> dict[str, Any]:
    """The component catalog (groups → components)."""
    return setup_manager.catalog_payload()


@router.get("/status")
async def setup_status(settings: Settings = Depends(get_settings)) -> dict[str, Any]:
    """Installed status per component + whether GUI writes are enabled on this host."""
    managed, services = await _moonraker_signals(settings)
    return {
        "status": await setup_manager.probe_status(managed, services),
        "writesEnabled": setup_manager.writes_enabled(),
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
        return _apply(await setup_manager.install(req.id, managed, services))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/update")
async def setup_update(req: ComponentRef) -> dict[str, Any]:
    try:
        return _apply(await setup_manager.update(req.id))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/remove")
async def setup_remove(req: RemoveRef) -> dict[str, Any]:
    try:
        return _apply(await setup_manager.remove(req.id, req.confirm))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
