from __future__ import annotations

import os

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from app.config import Settings, get_settings
from app.models.schemas import (
    BoardDiscovery,
    ConfigNode,
    ConfigTreeRequest,
    FirmwareProfile,
    FirmwareStatus,
    FlashPlan,
    FlashRequest,
    ProfileSaveRequest,
    ProfilesResponse,
)
from app.services import board_service, firmware_profiles, firmware_service, flash_service
from app.services.build_service import BuildService
from app.services.kconfig_service import KconfigError, get_kconfig_service

router = APIRouter(prefix="/firmware", tags=["firmware"])


@router.get("/status", response_model=FirmwareStatus)
async def firmware_status(settings: Settings = Depends(get_settings)) -> FirmwareStatus:
    """Read-only firmware status: host + per-MCU versions, sync check, tool readiness."""
    data = await firmware_service.gather_status(
        settings.moonraker_url, settings.klipper_dir, settings.katapult_dir
    )
    return FirmwareStatus.model_validate(data)


@router.get("/boards", response_model=BoardDiscovery)
async def firmware_boards(settings: Settings = Depends(get_settings)) -> BoardDiscovery:
    """Discovers every flashable board on the host (Moonraker + USB/CAN/DFU scans)."""
    data = await board_service.discover_boards(
        settings.moonraker_url, settings.klipper_dir, settings.katapult_dir
    )
    return BoardDiscovery.model_validate(data)


@router.post("/config/tree", response_model=list[ConfigNode])
async def firmware_config_tree(
    request: ConfigTreeRequest, settings: Settings = Depends(get_settings)
) -> list[ConfigNode]:
    """Klipper's Kconfig menu tree, optionally loaded with a profile and live edits."""
    config_file: str | None = None
    if request.profile:
        try:
            config_file = firmware_profiles.profile_path(settings.data_dir, request.profile)
        except firmware_profiles.ProfileNameError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    service = get_kconfig_service(settings.klipper_dir)
    try:
        tree = await service.menu_tree(
            config_file=config_file,
            values=[(v.name, v.value) for v in request.values],
            show_optional=request.show_optional,
        )
    except KconfigError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return [ConfigNode.model_validate(node) for node in tree]


@router.get("/config/profiles", response_model=ProfilesResponse)
async def firmware_list_profiles(
    settings: Settings = Depends(get_settings),
) -> ProfilesResponse:
    """Lists saved per-board firmware profiles and whether the editor is usable."""
    service = get_kconfig_service(settings.klipper_dir)
    profiles = [
        FirmwareProfile.model_validate(p)
        for p in firmware_profiles.list_profiles(settings.data_dir)
    ]
    return ProfilesResponse(kconfig_available=service.available, profiles=profiles)


@router.post("/config/profiles")
async def firmware_save_profile(
    request: ProfileSaveRequest, settings: Settings = Depends(get_settings)
) -> dict[str, str]:
    """Saves Kconfig edits (atop an optional base profile) as a named profile."""
    try:
        output = firmware_profiles.profile_path(settings.data_dir, request.name)
        base = (
            firmware_profiles.profile_path(settings.data_dir, request.base_profile)
            if request.base_profile
            else None
        )
    except firmware_profiles.ProfileNameError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    service = get_kconfig_service(settings.klipper_dir)
    try:
        await service.write_config(output, base, [(v.name, v.value) for v in request.values])
    except KconfigError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"message": f"Profile '{request.name}' saved"}


@router.delete("/config/profiles/{name}")
async def firmware_delete_profile(
    name: str, settings: Settings = Depends(get_settings)
) -> dict[str, str]:
    """Deletes a saved firmware profile."""
    try:
        removed = firmware_profiles.delete_profile(settings.data_dir, name)
    except firmware_profiles.ProfileNameError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not removed:
        raise HTTPException(status_code=404, detail=f"Profile '{name}' not found")
    return {"message": f"Profile '{name}' deleted"}


@router.get("/build/{profile}")
async def firmware_build(
    profile: str, settings: Settings = Depends(get_settings)
) -> StreamingResponse:
    """Compiles a profile's firmware, streaming the build log line by line."""
    try:
        config_path = firmware_profiles.profile_path(settings.data_dir, profile)
    except firmware_profiles.ProfileNameError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not os.path.isfile(config_path):
        raise HTTPException(status_code=404, detail=f"Profile '{profile}' not found")
    service = BuildService(settings.klipper_dir, settings.data_dir)
    return StreamingResponse(service.run_build(config_path, profile), media_type="text/plain")


@router.post("/flash-plan", response_model=FlashPlan)
async def firmware_flash_plan(
    request: FlashRequest, settings: Settings = Depends(get_settings)
) -> FlashPlan:
    """Read-only: reports the exact command + safety gates for a flash, running nothing."""
    data = await flash_service.flash_plan(
        request.profile or "", request.method, request.device, request.interface, settings
    )
    return FlashPlan.model_validate(data)


@router.post("/flash")
async def firmware_flash(
    request: FlashRequest, settings: Settings = Depends(get_settings)
) -> StreamingResponse:
    """Flashes a board, streaming the log. Refuses while printing or without sudo."""
    return StreamingResponse(
        flash_service.run_flash(
            request.profile or "", request.method, request.device, request.interface, settings
        ),
        media_type="text/plain",
    )
