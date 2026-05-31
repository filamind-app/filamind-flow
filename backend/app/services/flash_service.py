"""Firmware flash — pushes a built artifact onto a board. The hardware phase.

Safety first. A flash is only allowed when:
  * no print is running (refused otherwise),
  * a built artifact exists for the profile, and
  * passwordless sudo is configured (needed to stop Klipper + run the flasher).

The byte-pushing itself is delegated to the same standard tools a user would run
by hand — Katapult's ``flashtool.py`` (serial / CAN), ``dfu-util`` (DFU), or
Klipper's ``make flash`` (AVR) — and a Linux-process MCU is installed as the
``klipper-mcu`` binary. The plan endpoint reports exactly what *would* run
(read-only) so the UI can show it before anything touches the board.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator
from typing import Any

import httpx

from app.config import Settings
from app.services.firmware_profiles import artifact_path_for, profile_path
from app.services.moonraker_client import MoonrakerClient

# Board types FilaMind flashes. A Linux-process (host) MCU is intentionally
# excluded: its firmware is managed by Klipper/KIAUH, and rebuilding + installing
# it from here can leave the klipper-mcu service unable to start on some kernels.
_FLASHABLE = ("serial", "can", "dfu", "make")
# Flashing always stops Klipper and runs a privileged flasher, so it needs sudo.
_NEEDS_SUDO = _FLASHABLE

_DEFAULT_OFFSET = "0x08000000"
# CONFIG_*FLASH_START_<suffix> → application start address (Katapult/DFU bootloaders).
_OFFSETS = {
    "800": "0x08000800",
    "2000": "0x08002000",
    "4000": "0x08004000",
    "8000": "0x08008000",
    "10000": "0x08010000",
    "20000": "0x08020000",
}


def flash_offset(config_path: str) -> str:
    """Reads the bootloader offset from a profile's ``.config`` (default 0x08000000)."""
    try:
        with open(config_path) as handle:
            content = handle.read()
    except OSError:
        return _DEFAULT_OFFSET
    for suffix, address in _OFFSETS.items():
        if f"_FLASH_START_{suffix}=y" in content:
            return address
    return _DEFAULT_OFFSET


def _flashtool(katapult_dir: str) -> str:
    return os.path.join(os.path.expanduser(katapult_dir), "scripts", "flashtool.py")


def serial_command(katapult_dir: str, device: str, firmware: str, baud: int = 250000) -> list[str]:
    """Katapult serial flash."""
    return ["python3", _flashtool(katapult_dir), "-f", firmware, "-d", device, "-b", str(baud)]


def can_command(katapult_dir: str, interface: str, uuid: str, firmware: str) -> list[str]:
    """Katapult CAN flash."""
    return ["python3", _flashtool(katapult_dir), "-i", interface, "-u", uuid, "-f", firmware]


def dfu_command(firmware: str, offset: str, serial: str | None = None) -> list[str]:
    """dfu-util flash to the STM32 ROM bootloader."""
    cmd = ["sudo", "-n", "dfu-util", "-a", "0", "-d", "0483:df11", "-s", offset, "-D", firmware]
    if serial and len(serial) > 5 and not serial.startswith("/dev/"):
        cmd += ["-S", serial]
    return cmd


def make_flash_command(device: str) -> list[str]:
    """Klipper ``make flash`` (AVR / RP2040 / boards with their own flasher)."""
    return ["make", "flash", f"FLASH_DEVICE={device}"]


def method_for(connection: str, is_avr: bool) -> str:
    """Chooses a flash method from a board's connection kind."""
    if is_avr:
        return "make"
    return {"usb": "serial", "can": "can", "dfu": "dfu", "linux": "linux"}.get(connection, "serial")


def _build_command(
    method: str, settings: Settings, device: str, firmware: str, interface: str, offset: str
) -> list[str]:
    if method == "can":
        return can_command(settings.katapult_dir, interface, device, firmware)
    if method == "dfu":
        return dfu_command(firmware, offset, device)
    if method == "make":
        return make_flash_command(device)
    return serial_command(settings.katapult_dir, device, firmware)


async def _is_printing(moonraker_url: str) -> bool:
    """True if Moonraker reports an active or paused print."""
    try:
        data = await MoonrakerClient(moonraker_url).query_objects(["print_stats"])
    except httpx.HTTPError:
        return False
    stats = data.get("print_stats")
    state = stats.get("state") if isinstance(stats, dict) else None
    return state in ("printing", "paused")


async def _sudo_ready() -> bool:
    """True if the backend can sudo without a password.

    The sudoers rule only grants NOPASSWD for specific binaries, so we probe one
    of them (``systemctl --version``) rather than ``true`` — which would not match
    the rule and would always look unauthorised.
    """
    try:
        proc = await asyncio.create_subprocess_exec(
            "sudo",
            "-n",
            "systemctl",
            "--version",
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
    except (OSError, NotImplementedError):
        return False
    return await proc.wait() == 0


async def flash_plan(
    profile: str, method: str, device: str, interface: str, settings: Settings
) -> dict[str, Any]:
    """Read-only: reports the command + guards for flashing, without running it."""
    artifact = artifact_path_for(settings.data_dir, profile) if profile else None
    offset = flash_offset(profile_path(settings.data_dir, profile)) if profile else "0x08000000"
    command = _build_command(
        method, settings, device, artifact or "<firmware>", interface or "can0", offset
    )
    printing = await _is_printing(settings.moonraker_url)
    sudo = await _sudo_ready()
    flashable = method in _FLASHABLE
    needs_sudo = method in _NEEDS_SUDO

    warnings: list[str] = []
    if not flashable:
        warnings.append("Host MCU firmware is managed by Klipper/KIAUH, not flashed here.")
    if printing:
        warnings.append("A print is in progress — flashing is blocked.")
    if not artifact:
        warnings.append("No firmware has been built for this profile yet.")
    if needs_sudo and not sudo:
        warnings.append(
            "Passwordless sudo not configured — run deploy/setup-sudoers.sh on the host."
        )
    ready = flashable and bool(artifact) and not printing and (sudo or not needs_sudo)
    return {
        "method": method,
        "device": device,
        "artifact": os.path.basename(artifact) if artifact else None,
        "command": " ".join(command),
        "offset": offset,
        "printing": printing,
        "artifact_exists": bool(artifact),
        "sudo_ready": sudo,
        "ready": ready,
        "warnings": warnings,
    }


async def _stream(cmd: list[str], cwd: str | None = None) -> AsyncIterator[str]:
    """Runs a command, yielding stdout+stderr lines (tolerant of a missing binary)."""
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=cwd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
    except (OSError, NotImplementedError) as exc:
        yield f"!! cannot run '{cmd[0]}': {exc}\n"
        return
    assert proc.stdout is not None
    while True:
        raw = await proc.stdout.readline()
        if not raw:
            break
        yield raw.decode(errors="replace")
    await proc.wait()


async def _reboot_to_bootloader(
    method: str, device: str, interface: str, settings: Settings
) -> AsyncIterator[str]:
    """Asks a running device to drop into its Katapult/DFU bootloader."""
    yield f">>> Requesting {device} to enter its bootloader…\n"
    if method == "can":
        cmd = ["python3", _flashtool(settings.katapult_dir), "-i", interface, "-u", device, "-r"]
    else:
        cmd = ["python3", _flashtool(settings.katapult_dir), "-d", device, "-r"]
    async for line in _stream(cmd):
        yield line
    await asyncio.sleep(5)


async def run_flash(
    profile: str, method: str, device: str, interface: str, settings: Settings
) -> AsyncIterator[str]:
    """Guarded flash sequence: stop services, reboot-to-bootloader, flash, restart."""
    if method not in _FLASHABLE:
        yield "!! Host MCU firmware is managed by Klipper/KIAUH — FilaMind does not flash it.\n"
        return
    if await _is_printing(settings.moonraker_url):
        yield "!! Refused: a print is in progress. Flashing is blocked for safety.\n"
        return
    artifact = artifact_path_for(settings.data_dir, profile) if profile else None
    if not artifact:
        yield f"!! No firmware built for profile '{profile}'. Build it first.\n"
        return
    if not await _sudo_ready():
        yield "!! Passwordless sudo is not configured — required to stop Klipper and flash.\n"
        yield "!! Run once on the host:  sudo bash deploy/setup-sudoers.sh\n"
        return

    offset = flash_offset(profile_path(settings.data_dir, profile))
    yield f">>> Flashing {os.path.basename(artifact)} → {device} via {method}\n"

    yield ">>> Stopping Klipper to free the device…\n"
    async for line in _stream(["sudo", "-n", "systemctl", "stop", "klipper"]):
        yield line

    if method in ("serial", "can", "dfu"):
        async for line in _reboot_to_bootloader(method, device, interface, settings):
            yield line

    command = _build_command(method, settings, device, artifact, interface or "can0", offset)
    yield f">>> {' '.join(command)}\n"
    async for line in _stream(command, cwd=settings.klipper_dir if method == "make" else None):
        yield line

    yield ">>> Restarting Klipper…\n"
    async for line in _stream(["sudo", "-n", "systemctl", "start", "klipper"]):
        yield line
    yield ">>> Flash sequence complete — verify the board reconnects in Mainsail.\n"
