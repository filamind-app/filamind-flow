"""KlipperScreen Studio endpoints — read/edit ``KlipperScreen.conf`` and restart it to apply.

Phase 1: a status probe (is KlipperScreen present + restartable, current theme/language), a gated
config read/save (reuses the Config Editor's backup + stale-write machinery), and a service
restart. Read-only except the explicit save/restart; the save is refused while the printer is busy.
"""

from __future__ import annotations

from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.config import Settings, get_settings
from app.services import config_service, screen_service
from app.services.moonraker_client import MoonrakerClient

router = APIRouter(prefix="/screen", tags=["screen"])


class ScreenConfSave(BaseModel):
    """Body for ``POST /screen/conf`` — the full file text plus the loaded fingerprint."""

    content: str = Field(..., description="Full KlipperScreen.conf text to write")
    expected_sha256: str | None = Field(
        None, description="SHA-256 of the loaded content — refuses a stale-overwrite when set."
    )


@router.get("/status")
async def screen_status(settings: Settings = Depends(get_settings)) -> dict[str, Any]:
    """Whether KlipperScreen is present/restartable and its current theme/language."""
    client = MoonrakerClient(settings.moonraker_url)
    return await screen_service.status(client)


@router.get("/conf")
async def screen_conf(settings: Settings = Depends(get_settings)) -> dict[str, Any]:
    """Read ``KlipperScreen.conf`` (raw + sha256 + parsed sections)."""
    client = MoonrakerClient(settings.moonraker_url)
    try:
        return await screen_service.read_conf(client)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            raise HTTPException(status_code=404, detail="KlipperScreen.conf not found") from exc
        raise HTTPException(status_code=502, detail=f"Moonraker error: {exc}") from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Moonraker error: {exc}") from exc


@router.post("/conf")
async def screen_conf_save(
    body: ScreenConfSave, settings: Settings = Depends(get_settings)
) -> dict[str, Any]:
    """Gated save of ``KlipperScreen.conf`` (backup + busy-refusal + stale-write guard)."""
    client = MoonrakerClient(settings.moonraker_url)
    try:
        return await screen_service.save_conf(client, body.content, body.expected_sha256)
    except config_service.ConfigBusyError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except config_service.ConfigConflictError as exc:
        raise HTTPException(status_code=412, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Moonraker error: {exc}") from exc


@router.post("/restart")
async def screen_restart(settings: Settings = Depends(get_settings)) -> dict[str, str]:
    """Restart the KlipperScreen service so an edited config takes effect."""
    client = MoonrakerClient(settings.moonraker_url)
    try:
        await screen_service.restart(client)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Moonraker error: {exc}") from exc
    return {"status": "restarting"}
