"""Batch operations — build and/or flash every device in the registry as one
cancellable background task.

It reuses the single-board build and flash services unchanged, so a batch flash
behaves exactly like clicking *flash* on each board in turn — same bootloader
reboot, same print guard, same version recording. The orchestration on top adds:
de-duplicating builds by profile, skipping ``exclude_from_batch`` devices, an
optional *ready-only* filter (boards already sitting in a bootloader), and a
cancel checkpoint between every device and every streamed log line.
"""

from __future__ import annotations

from app.config import Settings
from app.services import board_service, devices_store, firmware_profiles, flash_service
from app.services.build_service import BuildService
from app.services.task_store import Task


async def _ready_ids(settings: Settings) -> set[str]:
    """Ids of boards currently sitting in a bootloader (ready / dfu)."""
    discovery = await board_service.discover_boards(
        settings.moonraker_url, settings.klipper_dir, settings.katapult_dir, settings.data_dir
    )
    return {b["id"] for b in discovery["boards"] if b["mode"] in ("ready", "dfu")}


async def _build_phase(devices: list[dict], settings: Settings, task: Task) -> None:
    built: set[str] = set()
    for device in devices:
        if task.cancelled:
            return
        profile = device.get("profile")
        if not profile:
            task.append(f">>> {device['name']}: no profile assigned — skipped.\n")
            continue
        if profile in built:
            task.append(f">>> {device['name']}: {profile} already built this run — skipped.\n")
            continue
        built.add(profile)
        try:
            config_path = firmware_profiles.profile_path(settings.data_dir, profile)
        except firmware_profiles.ProfileNameError as exc:
            task.append(f"!! {exc}\n")
            continue
        task.append(f">>> Building {profile} ({device['name']})…\n")
        service = BuildService(settings.klipper_dir, settings.data_dir)
        async for line in service.run_build(config_path, profile):
            task.append(line)
            if task.cancelled:
                return


async def _flash_phase(
    devices: list[dict], settings: Settings, task: Task, avr: dict[str, bool], ready_only: bool
) -> None:
    ready = await _ready_ids(settings) if ready_only else None
    for device in devices:
        if task.cancelled:
            return
        name = device["name"]
        if device.get("exclude_from_batch"):
            task.append(f">>> {name}: excluded from batch — skipped.\n")
            continue
        if device["method"] == "beacon":
            task.append(f">>> {name}: Beacon flashing is not supported yet — skipped.\n")
            continue
        profile = device.get("profile")
        if not profile:
            task.append(f">>> {name}: no profile assigned — skipped.\n")
            continue
        if ready is not None and device["id"] not in ready:
            task.append(f">>> {name}: not in a bootloader — skipped (Flash Ready).\n")
            continue
        method = "make" if avr.get(profile) else device["method"]
        task.append(f">>> Flashing {name} ({profile}) via {method}…\n")
        async for line in flash_service.run_flash(
            profile,
            method,
            device["id"],
            device.get("interface") or "can0",
            settings,
            device.get("is_katapult", True),
        ):
            task.append(line)
            if task.cancelled:
                return


async def run_batch(action: str, settings: Settings, task: Task) -> None:
    """Runs a build / flash batch over the registry, writing into ``task``.

    ``action`` is matched loosely: ``build`` → build, ``flash`` → flash,
    ``ready`` → only flash boards already in a bootloader. So ``build-flash-all``
    builds then flashes every device, ``flash-ready`` flashes only ready ones.
    """
    do_build = "build" in action
    do_flash = "flash" in action
    ready_only = "ready" in action

    devices = devices_store.read_devices(settings.data_dir)
    if not devices:
        task.append("!! No devices in the registry — add some first.\n")
        task.status = "done"
        return

    avr = {p["name"]: p["is_avr"] for p in firmware_profiles.list_profiles(settings.data_dir)}

    if do_build and not task.cancelled:
        task.append("===== BUILD ALL =====\n")
        await _build_phase(devices, settings, task)

    if do_flash and not task.cancelled:
        task.append(f"===== FLASH {'READY' if ready_only else 'ALL'} =====\n")
        await _flash_phase(devices, settings, task, avr, ready_only)

    task.append(
        "===== BATCH CANCELLED =====\n" if task.cancelled else "===== BATCH COMPLETE =====\n"
    )
    task.status = "cancelled" if task.cancelled else "done"
