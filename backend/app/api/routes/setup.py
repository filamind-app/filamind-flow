"""FilaMind Setup endpoints — browse the component catalog, see what's installed, and (only when
the host opts in via FILAMIND_SETUP_WRITES) install / update / remove components.

Mutations funnel through setup_manager, which is gated + path-guarded; a disabled write returns 403.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services import setup_manager

router = APIRouter(prefix="/setup", tags=["setup"])


class ComponentRef(BaseModel):
    id: str


class RemoveRef(BaseModel):
    id: str
    confirm: str


@router.get("/catalog")
async def setup_catalog() -> dict[str, Any]:
    """The component catalog (groups → components)."""
    return setup_manager.catalog_payload()


@router.get("/status")
async def setup_status() -> dict[str, Any]:
    """Installed status per component + whether GUI writes are enabled on this host."""
    return {
        "status": await setup_manager.probe_status(),
        "writesEnabled": setup_manager.writes_enabled(),
    }


def _apply(result: dict[str, Any]) -> dict[str, Any]:
    if result.get("refused"):
        raise HTTPException(status_code=403, detail=result["output"])
    return result


@router.post("/install")
async def setup_install(req: ComponentRef) -> dict[str, Any]:
    try:
        return _apply(await setup_manager.install(req.id))
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
