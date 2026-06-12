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
import glob
import os
import re
import shutil
from collections.abc import AsyncIterator
from typing import Any

import httpx

from app.config import Settings
from app.services import devices_store, printer_guard
from app.services.firmware_profiles import artifact_path_for, profile_path
from app.services.moonraker_client import MoonrakerClient
from app.services.version_store import read_build_info, record_flash

# Methods that must stop services / use sudo to flash.
_NEEDS_SUDO = ("serial", "can", "dfu", "make", "linux")

#: Machine-readable phase markers emitted alongside the human flash log. The UI consumes
#: these to drive a progress bar and hides them from the shown output; the readable ">>> …"
#: lines stay for the details view. Order: start → stop → boot → write → restart → done.
_PHASE = "::phase::"


def _phase(code: str) -> str:
    return f"{_PHASE}{code}\n"


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


def dfu_leave_command(offset: str, serial: str | None = None) -> list[str]:
    """dfu-util exit — returns a board from DFU back to firmware (``:leave``)."""
    cmd = ["sudo", "-n", "dfu-util", "-a", "0", "-d", "0483:df11", "-s", f"{offset}:leave"]
    if serial and len(serial) > 5 and not serial.startswith("/dev/"):
        cmd += ["-S", serial]
    return cmd


def resolve_method(method: str, device: str) -> str:
    """Corrects a USB-to-CAN bridge: it is configured as CAN but enumerates as a
    serial ``/dev/`` path, so a ``/dev/`` device given for CAN is flashed over serial.
    """
    if method == "can" and device.startswith("/dev/"):
        return "serial"
    return method


def reenumerated_id(old_id: str, before: set[str], after: set[str]) -> str | None:
    """A board can re-appear under a new ``/dev`` id after a flash. If the old id
    is gone and exactly one new id appeared, that new id is the same board.
    """
    if old_id in after:
        return None
    fresh = after - before
    return next(iter(fresh)) if len(fresh) == 1 else None


def make_flash_command(device: str) -> list[str]:
    """Klipper ``make flash`` (AVR / RP2040 / boards with their own flasher)."""
    return ["make", "flash", f"FLASH_DEVICE={device}"]


def method_for(connection: str, is_avr: bool) -> str:
    """Chooses a flash method from a board's connection kind."""
    if is_avr:
        return "make"
    return {"usb": "serial", "can": "can", "dfu": "dfu", "linux": "linux"}.get(connection, "serial")


def _saved_baudrate(settings: Settings, device: str) -> int:
    """The baudrate stored on the saved device matching this serial path (default 250000).

    The Devices panel lets users edit a baudrate per board; serial flashes must actually use it
    (a 115200 board flashed at the 250000 default just times out).
    """
    for saved in devices_store.read_devices(settings.data_dir):
        if saved.get("device") == device:
            raw = saved.get("baudrate")
            if isinstance(raw, int) and raw > 0:
                return raw
            break
    return 250000


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
    return serial_command(
        settings.katapult_dir, device, firmware, _saved_baudrate(settings, device)
    )


async def _is_printing(moonraker_url: str) -> bool:
    """True if Moonraker reports the printer busy (printing / paused / error) — the shared
    :mod:`printer_guard` definition. Fail-open when Moonraker is unreachable (a dead Moonraker
    must not block flashing the very MCU that might fix it)."""
    try:
        return await printer_guard.is_busy(MoonrakerClient(moonraker_url))
    except httpx.HTTPError:
        return False


#: A Klipper canbus UUID is exactly 12 lowercase hex digits — what Katapult's flashtool
#: expects after ``-u``. A friendly device name ("Toolhead") is not one.
_CAN_UUID_RE = re.compile(r"^[0-9a-f]{12}$")


async def _live_config(moonraker_url: str) -> dict[str, Any]:
    """The live ``configfile.config`` mapping, or ``{}`` when Moonraker is unreachable."""
    try:
        data = await MoonrakerClient(moonraker_url).query_objects(["configfile"])
    except httpx.HTTPError:
        return {}
    config = data.get("configfile", {}).get("config", {})
    return config if isinstance(config, dict) else {}


async def _can_node_runs_version(
    uuid: str, expected: str, moonraker_url: str, *, attempts: int = 12, delay: float = 2.5
) -> bool:
    """True if the CAN node with ``uuid`` reports ``expected`` as its firmware version.

    Polls Klipper (which we just restarted) until it connects and exposes the node's
    ``mcu_version`` — up to ~30 s. Finds the node's ``[mcu …]`` section by matching its
    ``canbus_uuid`` in the live config, then reads that object's version.
    """
    client = MoonrakerClient(moonraker_url)
    for _ in range(attempts):
        await asyncio.sleep(delay)
        try:
            config = (await client.query_objects(["configfile"])).get("configfile", {})
            sections = config.get("config", {})
            section = next(
                (
                    name
                    for name, cfg in sections.items()
                    if isinstance(cfg, dict) and str(cfg.get("canbus_uuid", "")).strip() == uuid
                ),
                None,
            )
            if not section:
                continue
            status_ = await client.query_objects([section])
            version = str((status_.get(section) or {}).get("mcu_version") or "")
            if version:
                return version == expected or version.startswith(expected)
        except httpx.HTTPError:
            continue
    return False


async def resolve_can_uuid(device: str, moonraker_url: str) -> tuple[str | None, str | None]:
    """Resolve the CAN node UUID to flash. CAN flashing needs the 12-hex ``canbus_uuid``, but a
    device may be registered under a friendly id ("Toolhead"). Returns ``(uuid, error)``:

    * the id itself if it already is a UUID;
    * the ``canbus_uuid`` of the live ``[mcu <id>]`` section (name match);
    * the only ``canbus_uuid`` in the config if there is exactly one (unambiguous);
    * ``(None, message)`` when it can't be resolved — better to refuse than flash the wrong node.
    """
    if _CAN_UUID_RE.match(device):
        return device, None
    config = await _live_config(moonraker_url)
    uuids: dict[str, str] = {}
    for section, cfg in config.items():
        if not isinstance(cfg, dict):
            continue
        uuid = cfg.get("canbus_uuid")
        if isinstance(uuid, str) and _CAN_UUID_RE.match(uuid.strip()):
            # section is "mcu" or "mcu <name>"
            name = section.split(" ", 1)[1] if section.startswith("mcu ") else section
            uuids[name] = uuid.strip()
    if device in uuids:
        return uuids[device], None
    if len(set(uuids.values())) == 1:
        return next(iter(uuids.values())), None
    if not uuids:
        return None, (
            f"!! Could not find a canbus_uuid for '{device}' in the live config — "
            "set this device's id to its 12-hex CAN UUID in the Manager, then flash.\n"
        )
    return None, (
        f"!! '{device}' did not match a unique CAN node ({len(uuids)} found) — set this "
        "device's id to its 12-hex canbus_uuid in the Manager so the right board is flashed.\n"
    )


async def _sudo_ready() -> bool:
    """True if the backend can run the flash's privileged commands without a password.

    Probes ``sudo -n -l systemctl stop klipper`` — ``sudo -l <cmd>`` reports whether the
    command is *authorised* (exit 0) WITHOUT running it, and ``-n`` never prompts. This
    matches an actual flash command, so it is correct regardless of which sudoers file
    grants it. (The old probe ran ``systemctl --version``, which the NOPASSWD rules don't
    cover — so it false-failed whenever sudo's credential cache was cold.)
    """
    systemctl = shutil.which("systemctl") or "/usr/bin/systemctl"
    try:
        proc = await asyncio.create_subprocess_exec(
            "sudo",
            "-n",
            "-l",
            systemctl,
            "stop",
            "klipper",
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


async def _stream(
    cmd: list[str], cwd: str | None = None, result: dict[str, int] | None = None
) -> AsyncIterator[str]:
    """Runs a command, yielding stdout+stderr lines (tolerant of a missing binary). When
    ``result`` is given, its ``"rc"`` is set to the process exit code (127 if it couldn't
    start) so a caller can tell a failed flash from a successful one."""
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=cwd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
    except (OSError, NotImplementedError) as exc:
        yield f"!! cannot run '{cmd[0]}': {exc}\n"
        if result is not None:
            result["rc"] = 127
        return
    assert proc.stdout is not None
    while True:
        raw = await proc.stdout.readline()
        if not raw:
            break
        yield raw.decode(errors="replace")
    rc = await proc.wait()
    if result is not None:
        result["rc"] = rc


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


def _serial_by_id() -> set[str]:
    """The current set of /dev/serial/by-id endpoints (used to spot re-enumeration)."""
    return set(glob.glob("/dev/serial/by-id/*"))


async def _magic_baud(device: str) -> None:
    """1200-baud 'touch' — a native-USB STM32 resets into DFU on a 1200 open/close.

    Done with stdlib termios (Unix only; this only ever runs on the Linux host) so
    no extra dependency is needed.
    """
    import termios

    fd = os.open(device, os.O_RDWR | os.O_NOCTTY)
    try:
        attrs = termios.tcgetattr(fd)
        attrs[4] = termios.B1200  # input speed
        attrs[5] = termios.B1200  # output speed
        termios.tcsetattr(fd, termios.TCSANOW, attrs)
    finally:
        os.close(fd)
    await asyncio.sleep(2)


async def reboot_to_dfu(device: str) -> AsyncIterator[str]:
    """Resets a running native-USB board into its STM32 DFU bootloader."""
    yield f">>> 1200-baud touch on {device} to enter DFU…\n"
    try:
        await _magic_baud(device)
    except (OSError, ImportError) as exc:
        yield f"!! magic-baud touch failed: {exc}\n"
        yield "!! Enter DFU manually (hold BOOT0, tap RESET) and retry.\n"
        return
    await asyncio.sleep(1)
    yield ">>> Touch sent — the board should now enumerate as a DFU device.\n"


async def _flash_dfu(
    device: str, firmware: str, offset: str, attempts: int = 3
) -> AsyncIterator[str]:
    """DFU download with retries, then ``:leave`` to return the board to firmware."""
    cmd = dfu_command(firmware, offset, device)
    for attempt in range(1, attempts + 1):
        yield f">>> DFU attempt {attempt}/{attempts}: {' '.join(cmd)}\n"
        ok = False
        async for line in _stream(cmd):
            yield line
            if "success" in line.lower() or "download done" in line.lower():
                ok = True
        if ok:
            break
        if attempt < attempts:
            yield ">>> DFU failed — retrying…\n"
            await asyncio.sleep(2)
    yield ">>> Exiting DFU (:leave) to return to firmware…\n"
    async for line in _stream(dfu_leave_command(offset, device)):
        yield line


async def run_flash(
    profile: str,
    method: str,
    device: str,
    interface: str,
    settings: Settings,
    is_katapult: bool = True,
    firmware: str | None = None,
    offset_override: str | None = None,
) -> AsyncIterator[str]:
    """Guarded flash sequence: stop services, reboot-to-bootloader, flash, restart.

    ``is_katapult=False`` skips the Katapult reboot-to-bootloader step for serial /
    CAN boards (boards without Katapult are flashed directly / via ``make flash``).
    ``firmware`` flashes a direct file path (external firmware) instead of a built
    profile artifact; ``offset_override`` sets the DFU/bootloader offset for it.
    """
    if await _is_printing(settings.moonraker_url):
        yield "!! Refused: a print is in progress. Flashing is blocked for safety.\n"
        return
    artifact = firmware or (artifact_path_for(settings.data_dir, profile) if profile else None)
    if not artifact or not os.path.isfile(artifact):
        yield f"!! No firmware file to flash for '{profile or firmware}'.\n"
        return
    if method in _NEEDS_SUDO and not await _sudo_ready():
        yield "!! Passwordless sudo is not configured — required to stop Klipper and flash.\n"
        yield "!! Run once on the host:  sudo bash deploy/setup-sudoers.sh\n"
        return

    method = resolve_method(method, device)
    yield _phase("start")
    yield f">>> Flashing {os.path.basename(artifact)} → {device} via {method}\n"

    # A Linux-process host MCU is installed as a binary, not flashed over a bus.
    if method == "linux":
        yield _phase("write")
        async for line in _flash_linux(artifact):
            yield line
        record_flash(
            settings.data_dir, device, profile, read_build_info(settings.data_dir, profile) or {}
        )
        yield _phase("done")
        yield ">>> Flash sequence complete — host MCU reinstalled.\n"
        return

    offset = offset_override or (
        flash_offset(profile_path(settings.data_dir, profile)) if profile else _DEFAULT_OFFSET
    )
    # CAN flashing addresses the node by its 12-hex canbus_uuid, not a friendly name —
    # resolve it from the live config so a device registered as "Toolhead" still flashes.
    target = device
    if method == "can":
        resolved, uuid_err = await resolve_can_uuid(device, settings.moonraker_url)
        if resolved is None:
            yield uuid_err or "!! Could not resolve the CAN node to flash.\n"
            return
        target = resolved

    yield _phase("stop")
    yield ">>> Stopping Klipper to free the device…\n"
    async for line in _stream(["sudo", "-n", "systemctl", "stop", "klipper"]):
        yield line

    # A board can re-appear under a new /dev id after a serial flash — snapshot first.
    before = _serial_by_id() if method == "serial" else set()

    # A DFU device is already in its bootloader; only running Katapult boards need
    # a reboot. Boards not marked Katapult are flashed directly (skip the reboot).
    if method in ("serial", "can") and is_katapult:
        yield _phase("boot")
        async for line in _reboot_to_bootloader(method, target, interface or "can0", settings):
            yield line
    elif method in ("serial", "can"):
        yield ">>> Device is not marked Katapult — skipping reboot-to-bootloader.\n"

    yield _phase("write")
    flash_result: dict[str, int] = {}
    flash_tool = ""
    if method == "dfu":
        async for line in _flash_dfu(device, artifact, offset):
            yield line
    else:
        command = _build_command(method, settings, target, artifact, interface or "can0", offset)
        flash_tool = os.path.basename(command[0])
        yield f">>> {' '.join(command)}\n"
        async for line in _stream(
            command, cwd=settings.klipper_dir if method == "make" else None, result=flash_result
        ):
            yield line

    yield _phase("restart")
    yield ">>> Restarting Klipper…\n"
    async for line in _stream(["sudo", "-n", "systemctl", "start", "klipper"]):
        yield line

    # The flash tool failed (non-zero exit). For CAN this is often the read-back VERIFY
    # phase dying on the USB-CAN adapter (sustained node→host flood) AFTER the write
    # completed — the board actually runs the new firmware. Check the real outcome via
    # Klipper before declaring failure: if the node now reports the built version, the
    # flash took.
    rc = flash_result.get("rc", 0)
    if rc != 0:
        expected = str((read_build_info(settings.data_dir, profile) or {}).get("version") or "")
        if method == "can" and expected:
            yield (
                ">>> Flash tool reported an error — checking via Klipper whether the "
                "board took the new firmware anyway…\n"
            )
            if await _can_node_runs_version(target, expected, settings.moonraker_url):
                yield f">>> Verified: the board reports {expected} — the flash DID succeed.\n"
                yield (
                    ">>> (The tool's error was in its read-back verify, a known limitation "
                    "of some USB-CAN adapters under sustained load.)\n"
                )
                record_flash(
                    settings.data_dir,
                    device,
                    profile,
                    read_build_info(settings.data_dir, profile) or {},
                )
                yield _phase("done")
                yield ">>> Flash sequence complete — verified through Klipper.\n"
                return
        yield (
            f"!! Flash failed — {flash_tool or 'the flash tool'} exited with code {rc}. "
            "The board was not flashed; see the output above.\n"
        )
        return

    # Pick up a serial board's new id (re-enumeration) and carry it into the registry.
    flashed_id = device
    if method == "serial":
        await asyncio.sleep(3)
        new_id = reenumerated_id(device, before, _serial_by_id())
        if new_id:
            yield f">>> Board re-appeared as {new_id} — updating the registry.\n"
            existing = devices_store.get_device(settings.data_dir, device)
            if existing:
                devices_store.save_device(
                    settings.data_dir, {**existing, "id": new_id}, old_id=device
                )
            flashed_id = new_id

    record_flash(
        settings.data_dir, flashed_id, profile, read_build_info(settings.data_dir, profile) or {}
    )
    yield _phase("done")
    yield ">>> Flash sequence complete — verify the board reconnects in Mainsail.\n"


async def run_reboot(
    method: str, device: str, interface: str, settings: Settings, mode: str = "katapult"
) -> AsyncIterator[str]:
    """Reboots a running board into a bootloader (no flashing).

    ``mode='katapult'`` uses ``flashtool.py -r`` (serial / CAN); ``mode='dfu'``
    does the 1200-baud touch to drop a native-USB board into STM32 DFU. Refused
    mid print. Useful to stage a board for a manual flash, or to recover one.
    """
    if await _is_printing(settings.moonraker_url):
        yield "!! Refused: a print is in progress.\n"
        return
    if mode == "dfu":
        async for line in reboot_to_dfu(device):
            yield line
        return
    method = resolve_method(method, device)
    async for line in _reboot_to_bootloader(method, device, interface or "can0", settings):
        yield line
    yield ">>> Reboot requested — the board should re-appear in its bootloader.\n"
