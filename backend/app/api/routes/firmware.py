from __future__ import annotations

import asyncio
import os
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import FileResponse, StreamingResponse

from app.config import Settings, get_settings
from app.models.schemas import (
    AttachRequest,
    BackupImportResponse,
    BatchRequest,
    BeaconFlashRequest,
    BeaconResponse,
    BoardDiscovery,
    ConfigNode,
    ConfigTreeRequest,
    Device,
    DeviceSave,
    DevicesResponse,
    ExternalFirmware,
    ExternalFirmwareResponse,
    ExternalFlashRequest,
    ExternalMetaUpdate,
    FirmwareProfile,
    FirmwareStatus,
    FlashPlan,
    FlashRequest,
    HealthReport,
    ProfileRenameRequest,
    ProfileSaveRequest,
    ProfilesResponse,
    RebootRequest,
    ServiceActionResponse,
    ServicesResponse,
    TaskStatus,
)
from app.services import (
    backup_service,
    batch_service,
    beacon_service,
    board_service,
    devices_store,
    external_firmware,
    firmware_profiles,
    firmware_service,
    flash_service,
    health_service,
    printer_guard,
    services_service,
    task_store,
)
from app.services import firmware_identify as firmware_identify_service
from app.services.build_service import BuildService
from app.services.kconfig_service import KconfigError, get_kconfig_service
from app.services.moonraker_client import MoonrakerClient
from app.services.task_store import Task
from app.services.version_store import flash_records, read_build_info

router = APIRouter(prefix="/firmware", tags=["firmware"])

#: Strong references to in-flight batch tasks so the event loop doesn't drop them.
_background: set[asyncio.Task[None]] = set()


async def _run_batch(action: str, settings: Settings, task: Task) -> None:
    """Wraps the batch run so an unexpected error marks the task failed, not hung. Holds the
    printer's exclusive actuating slot for the whole run (flashing reboots MCUs)."""
    try:
        async with printer_guard.acquire("firmware_batch"):
            await batch_service.run_batch(action, settings, task)
    except printer_guard.GuardBusyError as exc:
        task.append(f"!! {exc}\n")
        task.status = "failed"
    except Exception as exc:
        task.append(f"!! Batch failed: {exc}\n")
        task.status = "failed"


@router.get("/status", response_model=FirmwareStatus)
async def firmware_status(settings: Settings = Depends(get_settings)) -> FirmwareStatus:
    """Read-only firmware status: host + per-MCU versions, sync check, tool readiness."""
    data = await firmware_service.gather_status(
        settings.moonraker_url, settings.klipper_dir, settings.katapult_dir, settings.data_dir
    )
    return FirmwareStatus.model_validate(data)


@router.get("/boards", response_model=BoardDiscovery)
async def firmware_boards(settings: Settings = Depends(get_settings)) -> BoardDiscovery:
    """Discovers every flashable board on the host (Moonraker + USB/CAN/DFU scans)."""
    data = await board_service.discover_boards(
        settings.moonraker_url, settings.klipper_dir, settings.katapult_dir, settings.data_dir
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
    profiles = []
    for entry in firmware_profiles.list_profiles(settings.data_dir):
        info = read_build_info(settings.data_dir, entry["name"])
        entry["built_version"] = info.get("version") if info else None
        profiles.append(FirmwareProfile.model_validate(entry))
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


@router.post("/config/profiles/{name}/rename")
async def firmware_rename_profile(
    name: str, request: ProfileRenameRequest, settings: Settings = Depends(get_settings)
) -> dict[str, str]:
    """Renames a profile (config + artifacts) and rewrites devices that used it."""
    try:
        firmware_profiles.validate_name(name)
        firmware_profiles.validate_name(request.new_name)
    except firmware_profiles.ProfileNameError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    try:
        firmware_profiles.rename_profile(settings.data_dir, name, request.new_name)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"Profile '{name}' not found") from exc
    except FileExistsError as exc:
        raise HTTPException(
            status_code=409, detail=f"Profile '{request.new_name}' already exists"
        ) from exc
    moved = devices_store.rename_profile_refs(settings.data_dir, name, request.new_name)
    return {"message": f"Renamed '{name}' → '{request.new_name}' ({moved} device(s) updated)"}


@router.post("/config/profiles/{name}/duplicate")
async def firmware_duplicate_profile(
    name: str, request: ProfileRenameRequest, settings: Settings = Depends(get_settings)
) -> dict[str, str]:
    """Duplicates a profile's config (and any built artifacts) under a new name."""
    try:
        firmware_profiles.validate_name(name)
        firmware_profiles.validate_name(request.new_name)
    except firmware_profiles.ProfileNameError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    try:
        firmware_profiles.duplicate_profile(settings.data_dir, name, request.new_name)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"Profile '{name}' not found") from exc
    except FileExistsError as exc:
        raise HTTPException(
            status_code=409, detail=f"Profile '{request.new_name}' already exists"
        ) from exc
    return {"message": f"Duplicated '{name}' → '{request.new_name}'"}


@router.get("/config/profiles/{name}/artifact")
async def firmware_download_artifact(
    name: str, settings: Settings = Depends(get_settings)
) -> FileResponse:
    """Downloads the built firmware binary (``.bin`` / ``.uf2`` / ``.elf``) for a profile."""
    try:
        firmware_profiles.validate_name(name)
    except firmware_profiles.ProfileNameError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    path = firmware_profiles.artifact_path_for(settings.data_dir, name)
    if path is None:
        raise HTTPException(status_code=404, detail=f"No built firmware for profile '{name}'")
    return FileResponse(
        path, media_type="application/octet-stream", filename=os.path.basename(path)
    )


@router.get("/external", response_model=ExternalFirmwareResponse)
async def firmware_external_list(
    settings: Settings = Depends(get_settings),
) -> ExternalFirmwareResponse:
    """Lists registered external firmware files (pre-built binaries flashed as-is)."""
    items = external_firmware.list_external(settings.data_dir)
    return ExternalFirmwareResponse(firmware=[ExternalFirmware.model_validate(f) for f in items])


@router.post("/external", response_model=ExternalFirmware)
async def firmware_external_upload(
    request: Request, name: str, ext: str, settings: Settings = Depends(get_settings)
) -> ExternalFirmware:
    """Uploads an external firmware file (raw body; ``name`` / ``ext`` are query params)."""
    try:
        saved = external_firmware.save_firmware(settings.data_dir, name, ext, await request.body())
    except external_firmware.ExternalNameError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ExternalFirmware.model_validate(saved)


@router.post("/external/{name}/meta", response_model=ExternalFirmware)
async def firmware_external_update(
    name: str, patch: ExternalMetaUpdate, settings: Settings = Depends(get_settings)
) -> ExternalFirmware:
    """Updates an external firmware's editable properties (label / method / offset / …)."""
    try:
        external_firmware.validate_name(name)
        updated = external_firmware.update_meta(
            settings.data_dir, name, patch.model_dump(exclude_none=True)
        )
    except external_firmware.ExternalNameError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=404, detail=f"External firmware '{name}' not found"
        ) from exc
    return ExternalFirmware.model_validate(updated)


@router.delete("/external/{name}")
async def firmware_external_delete(
    name: str, settings: Settings = Depends(get_settings)
) -> dict[str, str]:
    """Deletes an external firmware file and its metadata."""
    try:
        removed = external_firmware.delete_firmware(settings.data_dir, name)
    except external_firmware.ExternalNameError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not removed:
        raise HTTPException(status_code=404, detail=f"External firmware '{name}' not found")
    return {"message": f"Deleted external firmware '{name}'"}


@router.get("/external/{name}/download")
async def firmware_external_download(
    name: str, settings: Settings = Depends(get_settings)
) -> FileResponse:
    """Downloads a stored external firmware file."""
    try:
        external_firmware.validate_name(name)
    except external_firmware.ExternalNameError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    path = external_firmware.firmware_path(settings.data_dir, name)
    if path is None:
        raise HTTPException(status_code=404, detail=f"External firmware '{name}' not found")
    return FileResponse(
        path, media_type="application/octet-stream", filename=os.path.basename(path)
    )


@router.post("/external/{name}/flash")
async def firmware_external_flash(
    name: str, request: ExternalFlashRequest, settings: Settings = Depends(get_settings)
) -> StreamingResponse:
    """Flashes a stored external firmware file onto a board, streaming the log."""
    try:
        external_firmware.validate_name(name)
    except external_firmware.ExternalNameError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    path = external_firmware.firmware_path(settings.data_dir, name)
    if path is None:
        raise HTTPException(status_code=404, detail=f"External firmware '{name}' not found")
    meta = external_firmware.read_meta(settings.data_dir, name)
    return StreamingResponse(
        printer_guard.guarded_stream(
            "firmware_flash",
            flash_service.run_flash(
                name,
                meta["method"],
                request.device,
                meta.get("interface") or "can0",
                settings,
                request.is_katapult,
                firmware=path,
                offset_override=meta.get("offset") or None,
            ),
        ),
        media_type="text/plain",
    )


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
        printer_guard.guarded_stream(
            "firmware_flash",
            flash_service.run_flash(
                request.profile or "",
                request.method,
                request.device,
                request.interface,
                settings,
                request.is_katapult,
            ),
        ),
        media_type="text/plain",
    )


@router.get("/identify")
async def firmware_identify(settings: Settings = Depends(get_settings)) -> dict[str, Any]:
    """Joins each registered device to its board-map MCU and catalog board, with the Kconfig
    machine symbol its chip needs — powering the topology deep-link and the profile seed."""
    client = MoonrakerClient(settings.moonraker_url)
    service = get_kconfig_service(settings.klipper_dir)
    try:
        return await firmware_identify_service.identify_devices(client, settings.data_dir, service)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Moonraker unreachable: {exc}") from exc


@router.get("/devices", response_model=DevicesResponse)
async def firmware_devices(settings: Settings = Depends(get_settings)) -> DevicesResponse:
    """Returns the saved devices, each device enriched with its last-flashed version."""
    records = flash_records(settings.data_dir)
    devices: list[Device] = []
    for device in devices_store.read_devices(settings.data_dir):
        record = records.get(device["id"]) or {}
        device["flashed_version"] = record.get("version")
        device["flashed_commit"] = record.get("commit")
        device["last_flashed"] = record.get("flashed_at")
        devices.append(Device.model_validate(device))
    return DevicesResponse(devices=devices)


@router.post("/devices", response_model=Device)
async def firmware_save_device(
    request: DeviceSave, settings: Settings = Depends(get_settings)
) -> Device:
    """Adds or updates a board in the registry (matched by ``old_id`` on rename)."""
    if not request.id:
        raise HTTPException(status_code=400, detail="Device id is required")
    payload = request.model_dump(exclude={"old_id"})
    saved = devices_store.save_device(settings.data_dir, payload, old_id=request.old_id)
    return Device.model_validate(saved)


@router.delete("/devices")
async def firmware_remove_device(
    device_id: str, settings: Settings = Depends(get_settings)
) -> dict[str, str]:
    """Removes a board from the registry."""
    if not devices_store.remove_device(settings.data_dir, device_id):
        raise HTTPException(status_code=404, detail=f"Device '{device_id}' not in the registry")
    return {"message": f"Device '{device_id}' removed"}


@router.post("/devices/attach", response_model=Device)
async def firmware_attach_identity(
    request: AttachRequest, settings: Settings = Depends(get_settings)
) -> Device:
    """Binds a discovered bootloader identity (serial / dfu) to a device."""
    device = devices_store.attach_identity(
        settings.data_dir, request.device_id, request.hardware_id, request.kind
    )
    if device is None:
        raise HTTPException(
            status_code=404, detail=f"Device '{request.device_id}' not in the registry"
        )
    return Device.model_validate(device)


@router.post("/batch")
async def firmware_batch(
    request: BatchRequest, settings: Settings = Depends(get_settings)
) -> dict[str, str]:
    """Starts a background build / flash run over every device. Returns its task id."""
    task = task_store.create_task()
    background = asyncio.create_task(_run_batch(request.action, settings, task))
    _background.add(background)
    background.add_done_callback(_background.discard)
    return {"task_id": task.id}


@router.get("/task/{task_id}", response_model=TaskStatus)
async def firmware_task(task_id: str) -> TaskStatus:
    """Returns a batch task's accumulating log and status (for polling)."""
    task = task_store.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found")
    return TaskStatus.model_validate(task.as_dict())


@router.post("/task/{task_id}/cancel")
async def firmware_task_cancel(task_id: str) -> dict[str, str]:
    """Requests cancellation of a running batch task (stops at the next checkpoint)."""
    if not task_store.cancel_task(task_id):
        raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found")
    return {"message": "Cancellation requested"}


@router.get("/services", response_model=ServicesResponse)
async def firmware_services() -> ServicesResponse:
    """Lists the host's Klipper / Moonraker services and whether each is active."""
    return ServicesResponse.model_validate({"services": await services_service.list_services()})


@router.post("/services/{action}", response_model=ServiceActionResponse)
async def firmware_services_manage(action: str) -> ServiceActionResponse:
    """Starts / stops / restarts every Klipper / Moonraker service."""
    if action not in services_service.VALID_ACTIONS:
        raise HTTPException(status_code=400, detail="action must be start, stop, or restart")
    results = await services_service.manage_services(action)
    return ServiceActionResponse.model_validate({"results": results})


@router.post("/reboot")
async def firmware_reboot(
    request: RebootRequest, settings: Settings = Depends(get_settings)
) -> StreamingResponse:
    """Reboots a board into a bootloader (Katapult or DFU), streaming the log."""
    return StreamingResponse(
        flash_service.run_reboot(
            request.method, request.device, request.interface, settings, request.mode
        ),
        media_type="text/plain",
    )


@router.get("/beacon", response_model=BeaconResponse)
async def firmware_beacon(settings: Settings = Depends(get_settings)) -> BeaconResponse:
    """Lists connected Beacon probes plus the plugin path and available version."""
    data = await beacon_service.gather_beacons(settings.moonraker_url)
    return BeaconResponse.model_validate(data)


@router.post("/beacon/flash")
async def firmware_beacon_flash(
    request: BeaconFlashRequest, settings: Settings = Depends(get_settings)
) -> StreamingResponse:
    """Updates a Beacon probe's firmware through its plugin, streaming the log."""
    return StreamingResponse(
        beacon_service.flash_beacon(request.device, settings), media_type="text/plain"
    )


@router.get("/health", response_model=HealthReport)
async def firmware_health() -> HealthReport:
    """Reports whether the host is set up for flashing (sudoers, udev DFU, dfu-util)."""
    return HealthReport.model_validate(await health_service.gather_health())


@router.get("/backup/export")
async def firmware_backup_export(settings: Settings = Depends(get_settings)) -> Response:
    """Downloads a ZIP backup of the device registry + all Kconfig profiles."""
    blob = backup_service.export_backup(settings.data_dir)
    return Response(
        content=blob,
        media_type="application/zip",
        headers={"Content-Disposition": "attachment; filename=filamind-backup.zip"},
    )


@router.post("/backup/import", response_model=BackupImportResponse)
async def firmware_backup_import(
    request: Request, settings: Settings = Depends(get_settings)
) -> BackupImportResponse:
    """Restores a ZIP backup (raw body). Overwrites the registry + named profiles."""
    try:
        summary = backup_service.import_backup(settings.data_dir, await request.body())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return BackupImportResponse.model_validate(summary)
