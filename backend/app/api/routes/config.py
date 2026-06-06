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

from app.config import Settings, get_settings
from app.services import config_service
from app.services.moonraker_client import MoonrakerClient

router = APIRouter(prefix="/config", tags=["config"])


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
