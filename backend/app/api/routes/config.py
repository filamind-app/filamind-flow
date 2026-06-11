"""Config Editor endpoints — read the live Klipper config (Track A keystone).

List the files under Moonraker's ``config`` root and return a structured, parsed view of
any one of them (sections → params + validation issues), built on the round-trip
:mod:`klipper_config` engine. Read-only: the gated save path lands in a later phase.

Payloads are returned as plain dicts (no ``response_model``) so no parsed field — including
optional issue keys and multi-line values — is ever dropped.
"""

from __future__ import annotations

from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.config import Settings, get_settings
from app.services import config_service
from app.services.moonraker_client import MoonrakerClient

router = APIRouter(prefix="/config", tags=["config"])


class ConfigSaveRequest(BaseModel):
    """Body for ``POST /config/save`` — overwrite one config file with new text."""

    filename: str = Field(..., description="Config path within the config root")
    content: str = Field(..., description="The full new file content")


class AdoptParamRequest(BaseModel):
    """Body for ``POST /config/adopt`` — set one param to the live value (pure text transform)."""

    content: str = Field(..., description="The current file text to mutate")
    section: str = Field(..., description="Section header, e.g. 'tmc2209 stepper_x'")
    key: str = Field(..., description="Param key to set")
    value: str = Field(..., description="The new (live) value to adopt")


def _client(settings: Settings) -> MoonrakerClient:
    return MoonrakerClient(settings.moonraker_url)


@router.get("/files")
async def config_files(settings: Settings = Depends(get_settings)) -> dict[str, Any]:
    """List the editable config files (``.cfg`` / ``.conf``) under the ``config`` root."""
    try:
        files = await config_service.list_config_files(_client(settings))
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Moonraker unreachable: {exc}") from exc
    return {"files": files}


@router.get("/file")
async def config_file(
    filename: str = Query("printer.cfg", description="Config path within the config root"),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    """Fetch and parse one config file into the structured editor view (sections + issues)."""
    try:
        return await config_service.read_config_file(_client(settings), filename)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code
        if status == 404:
            raise HTTPException(status_code=404, detail=f"Not found: {filename}") from exc
        raise HTTPException(status_code=502, detail=f"Moonraker error: {exc}") from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Moonraker unreachable: {exc}") from exc


@router.get("/drift")
async def config_drift(
    filename: str = Query("printer.cfg", description="Config path within the config root"),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    """Compare the on-disk file to the live running config: a pending-SAVE_CONFIG flag, Klipper's
    own parse warnings, and per-param drift (disk vs live). ``reachable=false`` when down."""
    try:
        return await config_service.gather_drift(_client(settings), filename)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/adopt")
async def config_adopt(body: AdoptParamRequest) -> dict[str, Any]:
    """Set one param to the live value via the round-trip engine and return the new text — a pure,
    surgical transform (no write). The result lands in the editor for review + the gated save."""
    return {"content": config_service.adopt_param(body.content, body.section, body.key, body.value)}


@router.post("/save")
async def config_save(
    body: ConfigSaveRequest, settings: Settings = Depends(get_settings)
) -> dict[str, Any]:
    """Back up then overwrite one config file. Refused while the printer is busy (409).

    Does not restart — call ``/config/restart`` to apply.
    """
    try:
        return await config_service.save_config_file(_client(settings), body.filename, body.content)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except config_service.ConfigBusyError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Moonraker error: {exc}") from exc


@router.post("/restart")
async def config_restart(settings: Settings = Depends(get_settings)) -> dict[str, Any]:
    """Trigger ``FIRMWARE_RESTART`` to apply a saved config. Refused while busy (409)."""
    try:
        return await config_service.restart_firmware(_client(settings))
    except config_service.ConfigBusyError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Moonraker error: {exc}") from exc
