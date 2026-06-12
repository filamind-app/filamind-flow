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
from app.services import board_topology, config_service
from app.services.moonraker_client import MoonrakerClient

router = APIRouter(prefix="/config", tags=["config"])


class ConfigSaveRequest(BaseModel):
    """Body for ``POST /config/save`` — overwrite one config file with new text."""

    filename: str = Field(..., description="Config path within the config root")
    content: str = Field(..., description="The full new file content")
    expected_sha256: str | None = Field(
        default=None,
        description="Fingerprint of the content the editor loaded; the save is refused (412) "
        "when the on-disk file no longer matches, so a parallel change isn't clobbered",
    )


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


@router.get("/graph")
async def config_graph(settings: Settings = Depends(get_settings)) -> dict[str, Any]:
    """The project's `[include]` dependency graph + cross-file lint (broken include / duplicate
    section / orphan TMC driver) across every config file. ``reachable=false`` when down."""
    return await config_service.gather_project(_client(settings))


@router.get("/search")
async def config_search(
    q: str = Query("", description="Case-insensitive substring to find across all config files"),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    """Project-wide search: every line (file + line number + text) that contains ``q``, capped."""
    return await config_service.search_project(_client(settings), q)


@router.get("/backups")
async def config_backups(
    filename: str = Query("", description="Limit to one file's snapshots (empty = all)"),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    """List timestamped backup snapshots under ``filamind-backups/`` (newest first)."""
    return await config_service.list_backups(_client(settings), filename or None)


@router.get("/backup")
async def config_backup(
    path: str = Query(..., description="A filamind-backups/*.bak snapshot path"),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    """Fetch one backup snapshot's content (read-only) for diff / restore-into-editor."""
    try:
        return {"path": path, "content": await config_service.read_backup(_client(settings), path)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            raise HTTPException(status_code=404, detail=f"Not found: {path}") from exc
        raise HTTPException(status_code=502, detail=f"Moonraker error: {exc}") from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Moonraker unreachable: {exc}") from exc


@router.get("/pin-map")
async def config_pin_map(settings: Settings = Depends(get_settings)) -> dict[str, Any]:
    """Per-MCU board pins (name + owners + caveat) so a ``*_pin`` field can suggest valid pins and
    flag a non-existent / double-assigned / caveated pin inline. ``reachable=false`` when down."""
    try:
        return await board_topology.gather_pin_map(_client(settings), settings.data_dir)
    except httpx.HTTPError:
        return {"reachable": False, "mcus": []}


@router.get("/sanity")
async def config_sanity(settings: Settings = Depends(get_settings)) -> dict[str, Any]:
    """Cross-check each TMC driver's run_current / microsteps against the driver's full-scale
    ceiling and the mapped motor's rating (honest when no reference exists). Down → reachable=false.
    """
    return await config_service.gather_sanity(_client(settings), settings.data_dir)


@router.get("/pin-doctor")
async def config_pin_doctor(settings: Settings = Depends(get_settings)) -> dict[str, Any]:
    """A whole-config pin-conflict scan (every MCU): double-assigned pins + board electronics
    caveats on a used pin — caught before a FIRMWARE_RESTART. ``reachable=false`` when down."""
    try:
        return await board_topology.gather_pin_doctor(_client(settings), settings.data_dir)
    except httpx.HTTPError:
        return {"reachable": False, "mcus": [], "total": 0}


@router.post("/save")
async def config_save(
    body: ConfigSaveRequest, settings: Settings = Depends(get_settings)
) -> dict[str, Any]:
    """Back up then overwrite one config file. Refused while the printer is busy (409) and when
    the file changed on disk since it was loaded (412 — reload instead of clobbering).

    Does not restart — call ``/config/restart`` to apply.
    """
    try:
        return await config_service.save_config_file(
            _client(settings),
            body.filename,
            body.content,
            body.expected_sha256,
            keep_n=settings.config_backup_keep_n,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except config_service.ConfigBusyError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except config_service.ConfigConflictError as exc:
        raise HTTPException(status_code=412, detail=str(exc)) from exc
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
