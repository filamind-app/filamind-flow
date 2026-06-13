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
from app.services import config_service, screen_service, screen_theme_service
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


# ── Theme builder ────────────────────────────────────────────────────────────
class ScreenThemeBody(BaseModel):
    """A theme to preview or generate: a name, a palette of token→#RRGGBB, a corner radius."""

    name: str = Field(..., description="Theme folder name (letters/numbers/space/-/_)")
    palette: dict[str, str] = Field(
        default_factory=dict, description="Palette token → #RRGGBB overrides (unknown keys ignored)"
    )
    radius: int = Field(8, description="Button corner radius, px")


class ScreenThemeActivate(BaseModel):
    name: str = Field(..., description="Theme to set as [main] theme in KlipperScreen.conf")


@router.get("/themes")
async def screen_themes(settings: Settings = Depends(get_settings)) -> dict[str, Any]:
    """Installed themes (each flagged ``generated`` if FilaMind made it) + the palette schema."""
    return {
        "themes": screen_theme_service.list_themes(settings.klipperscreen_dir),
        "tokens": list(screen_theme_service.PALETTE_TOKENS),
        "defaults": screen_theme_service.DEFAULT_PALETTE,
    }


@router.post("/themes/preview")
async def screen_theme_preview(body: ScreenThemeBody) -> dict[str, str]:
    """Render the style.css / style.conf for a palette without writing anything."""
    return {
        "style_css": screen_theme_service.render_style_css(
            body.name or "preview", body.palette, body.radius
        ),
        "style_conf": screen_theme_service.render_style_conf(body.palette),
    }


@router.post("/themes")
async def screen_theme_create(
    body: ScreenThemeBody, settings: Settings = Depends(get_settings)
) -> dict[str, Any]:
    """Generate + write the theme folder (host-side). Refuses to overwrite a stock theme."""
    try:
        return screen_theme_service.generate_theme(
            settings.klipperscreen_dir, body.name, body.palette, body.radius
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Could not write theme: {exc}") from exc


@router.post("/themes/activate")
async def screen_theme_activate(
    body: ScreenThemeActivate, settings: Settings = Depends(get_settings)
) -> dict[str, Any]:
    """Set ``[main] theme`` to this theme (gated conf save). Restart applies it on the screen."""
    client = MoonrakerClient(settings.moonraker_url)
    try:
        return await screen_theme_service.activate_theme(client, body.name)
    except config_service.ConfigBusyError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except config_service.ConfigConflictError as exc:
        raise HTTPException(status_code=412, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Moonraker error: {exc}") from exc


@router.delete("/themes/{name}")
async def screen_theme_delete(
    name: str, settings: Settings = Depends(get_settings)
) -> dict[str, str]:
    """Delete a FilaMind-generated theme (refuses to delete a stock one)."""
    try:
        screen_theme_service.delete_theme(settings.klipperscreen_dir, name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Could not delete theme: {exc}") from exc
    return {"status": "deleted"}
