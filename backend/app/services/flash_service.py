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

# Methods that must stop services / use sudo to flash.
_NEEDS_SUDO = ("serial", "can", "dfu", "make", "linux")

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
    if method == "linux":
        return ["sudo", "-n", "cp", firmware, "/usr/local/bin/klipper_mcu"]
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
    needs_sudo = method in _NEEDS_SUDO

    warnings: list[str] = []
    if printing:
        warnings.append("A print is in progress — flashing is blocked.")
    if not artifact:
        warnings.append("No firmware has been built for this profile yet.")
    if needs_sudo and not sudo:
        warnings.append(
            "Passwordless sudo not configured — run deploy/setup-sudoers.sh on the host."
        )
    ready = bool(artifact) and not printing and (sudo or not needs_sudo)
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


async def _service_active(name: str) -> bool:
    """True if a systemd service is currently active (no sudo needed)."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "systemctl",
            "is-active",
            "--quiet",
            name,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
    except (OSError, NotImplementedError):
        return False
    return await proc.wait() == 0


async def _flash_linux(firmware: str) -> AsyncIterator[str]:
    """Installs a Linux-process host MCU as /usr/local/bin/klipper_mcu."""
    target = "/usr/local/bin/klipper_mcu"
    yield ">>> Stopping klipper-mcu…\n"
    async for line in _stream(["sudo", "-n", "systemctl", "stop", "klipper-mcu"]):
        yield line
    # Free the binary from any lingering process, then install it executable.
    async for line in _stream(["sudo", "-n", "fuser", "-k", target]):
        yield line
    await asyncio.sleep(1)
    async for line in _stream(["sudo", "-n", "cp", firmware, target]):
        yield line
    async for line in _stream(["sudo", "-n", "chmod", "0755", target]):
        yield line
    yield ">>> Starting klipper-mcu…\n"
    async for line in _stream(["sudo", "-n", "systemctl", "start", "klipper-mcu"]):
        yield line
    for _ in range(12):
        await asyncio.sleep(0.5)
        if await _service_active("klipper-mcu"):
            yield ">>> klipper-mcu is running.\n"
            return
    yield "!! klipper-mcu did not come up. If its journal shows 'sched_setscheduler',\n"
    yield "!! this kernel blocks realtime — drop the -r flag from the klipper-mcu unit.\n"


async def run_flash(
    profile: str, method: str, device: str, interface: str, settings: Settings
) -> AsyncIterator[str]:
    """Guarded flash sequence: stop services, reboot-to-bootloader, flash, restart."""
    if await _is_printing(settings.moonraker_url):
        yield "!! Refused: a print is in progress. Flashing is blocked for safety.\n"
        return
    artifact = artifact_path_for(settings.data_dir, profile) if profile else None
    if not artifact:
        yield f"!! No firmware built for profile '{profile}'. Build it first.\n"
        return
    if method in _NEEDS_SUDO and not await _sudo_ready():
        yield "!! Passwordless sudo is not configured — required to stop Klipper and flash.\n"
        yield "!! Run once on the host:  sudo bash deploy/setup-sudoers.sh\n"
        return

    yield f">>> Flashing {os.path.basename(artifact)} → {device} via {method}\n"

    # A Linux-process host MCU is installed as a binary, not flashed over a bus.
    if method == "linux":
        async for line in _flash_linux(artifact):
            yield line
        yield ">>> Flash sequence complete — host MCU reinstalled.\n"
        return

    offset = flash_offset(profile_path(settings.data_dir, profile))
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
