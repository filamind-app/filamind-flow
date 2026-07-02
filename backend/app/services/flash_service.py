"""Firmware flash - pushes a built artifact onto a board. The hardware phase.

Safety first. A flash is only allowed when:
  * no print is running (refused otherwise),
  * a built artifact exists for the profile, and
  * passwordless sudo is configured (needed to stop Klipper + run the flasher).

The byte-pushing itself is delegated to the same standard tools a user would run
by hand - Katapult's ``flashtool.py`` (serial / CAN), ``dfu-util`` (DFU), or
Klipper's ``make flash`` (AVR) - and a Linux-process MCU is installed as the
``klipper-mcu`` binary. The plan endpoint reports exactly what *would* run
(read-only) so the UI can show it before anything touches the board.
"""

from __future__ import annotations

import asyncio
import contextlib
import glob
import os
import re
import shutil
import subprocess
import tempfile
from collections.abc import AsyncIterator
from typing import Any

import httpx

from app.config import Settings
from app.services import devices_store, external_firmware, printer_guard
from app.services.build_tools import (
    build_env,
    flash_python,
    make_available,
    missing_toolchain_lines,
)
from app.services.firmware_profiles import (
    artifact_path_for,
    is_avr_profile,
    is_linux_profile,
    profile_path,
)
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
    """Katapult serial flash (run under a pyserial-capable interpreter - #569)."""
    return [flash_python(), _flashtool(katapult_dir), "-f", firmware, "-d", device, "-b", str(baud)]


def can_command(katapult_dir: str, interface: str, uuid: str, firmware: str) -> list[str]:
    """Katapult CAN flash (run under the same interpreter for determinism - #569)."""
    return [flash_python(), _flashtool(katapult_dir), "-i", interface, "-u", uuid, "-f", firmware]


def dfu_command(firmware: str, offset: str, serial: str | None = None) -> list[str]:
    """dfu-util flash to the STM32 ROM bootloader."""
    cmd = ["sudo", "-n", "dfu-util", "-a", "0", "-d", "0483:df11", "-s", offset, "-D", firmware]
    if serial and len(serial) > 5 and not serial.startswith("/dev/"):
        cmd += ["-S", serial]
    return cmd


def dfu_leave_command(offset: str, serial: str | None = None) -> list[str]:
    """dfu-util exit - returns a board from DFU back to firmware (``:leave``)."""
    cmd = ["sudo", "-n", "dfu-util", "-a", "0", "-d", "0483:df11", "-s", f"{offset}:leave"]
    if serial and len(serial) > 5 and not serial.startswith("/dev/"):
        cmd += ["-S", serial]
    return cmd


def resolve_method(method: str, device: str, is_linux: bool = False) -> str:
    """Normalises the flash method to what the device actually needs.

    * The Linux host-process MCU is installed as a binary, never flashed over a bus - force
      ``linux`` when the profile builds the Linux target (``is_linux``) or the device is the host
      MCU (``linux_process`` / the ``klipper_host_mcu`` socket). Its "serial" is that socket, so a
      serial flash otherwise fails with "No Serial Device found" (the ``[mcu PI2]`` host case).
    * A USB-to-CAN bridge is configured as CAN but enumerates as a serial ``/dev/`` path, so a
      ``/dev/`` device given for CAN is flashed over serial.
    """
    if is_linux or device == "linux_process" or device.endswith("klipper_host_mcu"):
        return "linux"
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


# Non-AVR MCU tokens that appear in a /dev/serial/by-id name (usb-Klipper_<chip>_...). Used ONLY to
# refuse the certain conflict we can prove: AVR firmware aimed at a non-AVR board (#567). A positive
# allowlist, so an unknown / token-less device never blocks a genuine flash.
_NON_AVR_DEVICE_TOKENS = (
    "rp2040",
    "stm32",
    "samd51",
    "samd21",
    "samd",
    "same5",
    "sam3",
    "gd32",
    "lpc176",
    "hc32",
    "ch32",
    "ar100",
)


def device_chip_token(device: str) -> str | None:
    """The non-AVR MCU family named in a ``/dev/serial/by-id`` device, or None.

    Klipper names a USB board ``usb-Klipper_<chip>_<id>-if00``; reading <chip> lets us detect the
    one conflict we can prove - an AVR build aimed at a non-AVR board. Returns None for a raw
    ``/dev/ttyACM*`` / ``ttyUSB*`` (a genuine ATmega enumerates there), a CAN uuid, a DFU vid:pid,
    the Linux socket, or any name without a recognised token - so the arch guard fails OPEN.
    """
    if "/serial/by-id/" not in device:
        return None
    name = os.path.basename(device).lower()
    # Anchor the token to Klipper's ``usb-Klipper_<chip>_<id>`` prefix, so a third-party USB-serial
    # bridge name (FTDI / CH340 / CP2102) can never collide with a token substring - keeps the guard
    # airtight-fail-open. Every real Klipper by-id name is ``usb-Klipper_<chip>...``, so this still
    # catches all genuine chips (klipper_stm32h723xx, klipper_rp2040, klipper_samd21g18, ...).
    return next((token for token in _NON_AVR_DEVICE_TOKENS if f"klipper_{token}" in name), None)


def arch_mismatch(is_avr: bool, device: str, method: str) -> tuple[str, str] | None:
    """The one certain firmware-vs-board conflict, or None.

    Fires only for an AVR ``make`` flash whose target device names a non-AVR chip (e.g. an AVR
    profile aimed at an ``rp2040`` board - #567), where Klipper's ``make flash`` would run avrdude
    against a board it cannot program. Fails OPEN on any unknown / token-less / non-serial target,
    so it never blocks a real flash. Returns ``(firmware_arch, device_chip)``.
    """
    if method != "make" or not is_avr:
        return None
    chip = device_chip_token(device)
    return ("AVR", chip) if chip else None


def _diagnose_make_failure(tail: list[str], device: str) -> list[str]:
    """Actionable ``!!`` hints for a failed ``make flash``, inferred from the tail of its output.

    Turns a bare "make exited with code N" into something the user can act on - covering cases the
    pre-flash arch guard cannot classify (external firmware, unusual device names).
    """
    blob = "".join(tail).lower()
    if any(
        t in blob
        for t in ("avrdude", "device signature", "not in sync", "programmer is not responding")
    ):
        return [
            "!! 'make flash' ran avrdude (the AVR/ATmega programmer). If your board isn't an\n",
            "!! ATmega (e.g. an rp2040/stm32), the profile's MCU doesn't match the board -\n",
            "!! rebuild the profile for your actual board in the Config step, then flash again.\n",
        ]
    if "no such file" in blob or "no such device" in blob or "cannot open" in blob:
        return [
            f"!! The flash device {device} was not found - is the board plugged in and did it\n",
            "!! re-enumerate? Re-plug it (or re-run discovery), then flash again.\n",
        ]
    if "permission denied" in blob:
        return ["!! Permission denied talking to the board - a udev / sudo rule may be missing.\n"]
    return []


def _diagnose_serial_failure(tail: list[str], device: str) -> list[str]:
    """Actionable ``!!`` hints for a failed serial / CAN flash, from the tail of flashtool's output.

    The serial/CAN path can exit non-zero for reasons the bare exit code hides (#569). Never echoes
    Katapult's own ``apt install python3-serial`` line - FilaMind installs pyserial on update.
    """
    blob = "".join(tail).lower()
    if any(t in blob for t in ("no module named 'serial'", "no module named serial", "pyserial")):
        return [
            "!! The flasher's Python is missing serial support (pyserial).\n",
            "!! Update FilaMind - it installs it automatically - then flash again.\n",
        ]
    if any(
        t in blob for t in ("could not open port", "permission denied", "resource busy", "in use")
    ):
        return [
            f"!! Could not open the serial port {device}.\n",
            "!! It may be in use or missing a udev rule - re-plug the board and retry.\n",
        ]
    if any(t in blob for t in ("no serial device found", "no such file", "no such device")):
        return [
            f"!! The flash device {device} was not found.\n",
            "!! The board may not be in its bootloader, or it re-enumerated - re-plug and retry.\n",
        ]
    if any(t in blob for t in ("checksum mismatch", "block request error", "got eof", "timeout")):
        return [
            "!! The transfer failed mid-flash (verify/timeout) - often a bad USB cable or port.\n",
            "!! Try a different (rear) USB port and cable, then flash again.\n",
        ]
    return []


def _saved_baudrate(settings: Settings, device: str) -> int:
    """The baudrate stored on the saved device matching this serial path (default 250000).

    The Devices panel lets users edit a baudrate per board; serial flashes must actually use it
    (a 115200 board flashed at the 250000 default just times out). Registry records are keyed by
    ``id`` (with optional ``serial_id``), and the path handed here may already be retargeted to the
    board's bootloader-renamed port (usb-Klipper_<id> -> usb-katapult_<id>) - match all three.
    """
    for saved in devices_store.read_devices(settings.data_dir):
        candidates = {saved.get("id"), saved.get("serial_id")}
        saved_id = str(saved.get("id") or "")
        if saved_id:
            candidates.add(re.sub(r"(?i)(usb-)Klipper(_)", r"\1katapult\2", saved_id))
        if device in candidates:
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
    """True if Moonraker reports the printer busy (printing / paused / error) - the shared
    :mod:`printer_guard` definition. Fail-open when Moonraker is unreachable (a dead Moonraker
    must not block flashing the very MCU that might fix it)."""
    try:
        return await printer_guard.is_busy(MoonrakerClient(moonraker_url))
    except httpx.HTTPError:
        return False


#: A Klipper canbus UUID is exactly 12 lowercase hex digits - what Katapult's flashtool
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


async def _can_node_version(uuid: str, moonraker_url: str) -> str:
    """The firmware version a CAN node currently reports (via its live ``[mcu]`` object), or ""."""
    client = MoonrakerClient(moonraker_url)
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
            return ""
        status_ = await client.query_objects([section])
        return str((status_.get(section) or {}).get("mcu_version") or "")
    except httpx.HTTPError:
        return ""


async def _can_node_runs_version(
    uuid: str, expected: str, moonraker_url: str, *, attempts: int = 12, delay: float = 2.5
) -> bool:
    """True if the CAN node with ``uuid`` reports ``expected`` as its firmware version.

    Polls Klipper (which we just restarted) until it connects and exposes the node's
    ``mcu_version`` - up to ~30 s. Finds the node's ``[mcu …]`` section by matching its
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
    * ``(None, message)`` when it can't be resolved - better to refuse than flash the wrong node.
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
            f"!! Could not find a canbus_uuid for '{device}' in the live config - "
            "set this device's id to its 12-hex CAN UUID in the Manager, then flash.\n"
        )
    return None, (
        f"!! '{device}' did not match a unique CAN node ({len(uuids)} found) - set this "
        "device's id to its 12-hex canbus_uuid in the Manager so the right board is flashed.\n"
    )


async def _sudo_ready() -> bool:
    """True if the backend can run the flash's privileged commands without a password.

    Probes ``sudo -n -l systemctl stop klipper`` - ``sudo -l <cmd>`` reports whether the
    command is *authorised* (exit 0) WITHOUT running it, and ``-n`` never prompts. This
    matches an actual flash command, so it is correct regardless of which sudoers file
    grants it. (The old probe ran ``systemctl --version``, which the NOPASSWD rules don't
    cover - so it false-failed whenever sudo's credential cache was cold.)
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
    is_linux = is_linux_profile(settings.data_dir, profile) if profile else False
    method = resolve_method(method, device, is_linux)
    is_avr = is_avr_profile(settings.data_dir, profile) if profile else False
    mismatch = arch_mismatch(is_avr, device, method)
    artifact = artifact_path_for(settings.data_dir, profile) if profile else None
    offset = flash_offset(profile_path(settings.data_dir, profile)) if profile else "0x08000000"
    command = _build_command(
        method, settings, device, artifact or "<firmware>", interface or "can0", offset
    )
    printing = await _is_printing(settings.moonraker_url)
    sudo = await _sudo_ready()
    needs_sudo = method in _NEEDS_SUDO

    # Coded warnings: frontend renders firmware.flashConfirm.warn.<code> from {code, params}.
    warnings: list[dict[str, object]] = []
    if printing:
        warnings.append({"code": "printing", "params": {}})
    if not artifact:
        warnings.append({"code": "no_artifact", "params": {}})
    if needs_sudo and not sudo:
        warnings.append({"code": "no_sudo", "params": {}})
    # `make flash` needs the host build tools; warn (and block) if `make` is absent.
    make_missing = method == "make" and not make_available()
    if make_missing:
        warnings.append({"code": "build_tools", "params": {}})
    # AVR firmware can't be flashed to a non-AVR board (avrdude vs the chip) - block it (#567).
    if mismatch:
        warnings.append(
            {"code": "arch_mismatch", "params": {"firmware": mismatch[0], "chip": mismatch[1]}}
        )
    ready = (
        bool(artifact)
        and not printing
        and (sudo or not needs_sudo)
        and not make_missing
        and not mismatch
    )
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
            env=build_env(),  # augmented PATH so make / flash tools resolve (#558)
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
    except (OSError, NotImplementedError) as exc:
        yield f"!! cannot run '{cmd[0]}': {exc}\n"
        if result is not None:
            result["rc"] = 127
        return
    assert proc.stdout is not None
    try:
        while True:
            raw = await proc.stdout.readline()
            if not raw:
                break
            yield raw.decode(errors="replace")
        rc = await proc.wait()
        if result is not None:
            result["rc"] = rc
    finally:
        # The consumer can vanish mid-run (client disconnect closes the generator at a yield).
        # Never leave the child (flashtool / dfu-util / make) running orphaned against the board.
        if proc.returncode is None:
            with contextlib.suppress(ProcessLookupError, OSError):
                proc.kill()


def _restart_klipper_detached() -> None:
    """Best-effort fire-and-forget ``systemctl start klipper`` that survives generator teardown.

    A client disconnect (closed tab / dropped proxy) closes the flash stream at a yield, mid
    stop→write→restart - Klipper must never be left stopped. Plain ``subprocess.Popen`` needs no
    event-loop cooperation during the unwind, so it works even while the request is being torn down.
    """
    with contextlib.suppress(OSError):
        subprocess.Popen(
            ["sudo", "-n", "systemctl", "start", "klipper"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=build_env(),
        )


async def _dfu_device_present() -> bool:
    """True if an STM32 ROM-DFU device (0483:df11) is enumerated on USB right now."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "sudo",
            "-n",
            "dfu-util",
            "-l",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            env=build_env(),
        )
        try:
            out, _ = await asyncio.wait_for(proc.communicate(), timeout=10)
        except asyncio.TimeoutError:
            with contextlib.suppress(ProcessLookupError, OSError):
                proc.kill()
            return False
    except (OSError, NotImplementedError):
        return False
    return b"0483:df11" in out


async def _reboot_to_bootloader(
    method: str, device: str, interface: str, settings: Settings
) -> AsyncIterator[str]:
    """Asks a running device to drop into its Katapult/DFU bootloader."""
    yield f">>> Requesting {device} to enter its bootloader…\n"
    if method == "can":
        cmd = [
            flash_python(),
            _flashtool(settings.katapult_dir),
            "-i",
            interface,
            "-u",
            device,
            "-r",
        ]
    else:
        cmd = [flash_python(), _flashtool(settings.katapult_dir), "-d", device, "-r"]
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


_MCU_DROPIN_DIR = "/etc/systemd/system/klipper-mcu.service.d"
_MCU_DROPIN = f"{_MCU_DROPIN_DIR}/filamind-norealtime.conf"
# Drop-in that runs klipper-mcu WITHOUT -r. Some ARM SBC kernels deny realtime scheduling to a
# service cgroup (CONFIG_RT_GROUP_SCHED, cpu.rt_runtime_us=0), so `klipper_mcu -r` fails with
# `sched_setscheduler: Operation not permitted` and crash-loops. The host MCU runs fine without it.
_MCU_NOREALTIME = (
    "# Managed by FilaMind Flow. This kernel denies realtime scheduling to the service cgroup,\n"
    "# so 'klipper_mcu -r' fails (sched_setscheduler EPERM) and crash-loops. Run without -r.\n"
    "[Service]\n"
    "ExecStart=\n"
    "ExecStart=/usr/local/bin/klipper_mcu -I ${KLIPPER_HOST_MCU_SERIAL}\n"
)


async def _mcu_realtime_blocked() -> bool:
    """True if klipper-mcu's current-boot journal shows the realtime-scheduling denial (-r crash).

    Runs via the granted ``sudo -n journalctl`` (like the rest of the codebase) so it reads the
    root-run service's own lines - an unprivileged journalctl would only see the caller's messages
    and miss the crash. Scoped to the current boot (``-b``) so a stale prior-boot crash can't fire a
    needless fix.
    """
    try:
        proc = await asyncio.create_subprocess_exec(
            "sudo",
            "-n",
            "journalctl",
            "-u",
            "klipper-mcu",
            "-b",
            "-n",
            "30",
            "--no-pager",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
            env=build_env(),
        )
        out, _ = await proc.communicate()
    except (OSError, NotImplementedError):
        return False
    return "sched_setscheduler" in out.decode(errors="replace")


async def _drop_mcu_realtime() -> AsyncIterator[str]:
    """Install a drop-in that runs klipper-mcu without -r, then reload + restart it.

    Uses only the panel's granted sudo (mkdir / cp / systemctl) so the fix is automatic - the user
    never edits a systemd unit by hand.
    """
    yield ">>> This kernel blocks realtime scheduling - reconfiguring klipper-mcu without -r…\n"
    fd, tmp = tempfile.mkstemp(suffix=".conf")
    try:
        with os.fdopen(fd, "w") as handle:
            handle.write(_MCU_NOREALTIME)
        async for line in _stream(["sudo", "-n", "mkdir", "-p", _MCU_DROPIN_DIR]):
            yield line
        async for line in _stream(["sudo", "-n", "cp", tmp, _MCU_DROPIN]):
            yield line
    finally:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
    async for line in _stream(["sudo", "-n", "systemctl", "daemon-reload"]):
        yield line
    async for line in _stream(["sudo", "-n", "systemctl", "reset-failed", "klipper-mcu"]):
        yield line
    async for line in _stream(["sudo", "-n", "systemctl", "restart", "klipper-mcu"]):
        yield line


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
    # Didn't come up. On kernels that deny realtime scheduling, `klipper_mcu -r` crash-loops with
    # sched_setscheduler EPERM - auto-fix by dropping -r (no manual step) and retry.
    if await _mcu_realtime_blocked():
        async for line in _drop_mcu_realtime():
            yield line
        for _ in range(12):
            await asyncio.sleep(0.5)
            if await _service_active("klipper-mcu"):
                yield ">>> klipper-mcu is running (realtime disabled - this kernel blocks it).\n"
                return
    yield "!! klipper-mcu did not come up - see its journal in Host Control -> Services.\n"
    yield "!! If this persists, update FilaMind so the latest host fixes reach your printer.\n"


def _serial_by_id() -> set[str]:
    """The current set of /dev/serial/by-id endpoints (used to spot re-enumeration)."""
    return set(glob.glob("/dev/serial/by-id/*"))


def bootloader_serial_path(device: str) -> str | None:
    """If the board whose *running-firmware* path is ``device`` is currently sitting in its Katapult
    bootloader, return the bootloader's ``/dev/serial/by-id`` path, else ``None``.

    A USB STM32 enumerates under a different name in each mode - ``usb-Klipper_<chip-id>-if00``
    when running Klipper, ``usb-katapult_<chip-id>-if00`` when in the Katapult bootloader. Once a
    board is in the bootloader the Klipper path disappears, so a flash must target the katapult
    path, not the stored running-firmware path. Matched by the trailing chip id (prefix-robust).
    """
    if "/serial/by-id/" not in device:
        return None
    base = os.path.basename(device)
    swapped = re.sub(r"(?i)(usb-)Klipper(_)", r"\1katapult\2", base)
    if swapped != base:
        candidate = "/dev/serial/by-id/" + swapped
        if os.path.exists(candidate):
            return candidate
    # Fallback: any present *katapult* endpoint carrying the same trailing chip id.
    hit = re.search(r"_([0-9A-Za-z]{8,})-if\d", base)
    if hit:
        for path in glob.glob("/dev/serial/by-id/*katapult*"):
            if hit.group(1) in path:
                return path
    return None


async def _magic_baud(device: str) -> None:
    """1200-baud 'touch' - a native-USB STM32 resets into DFU on a 1200 open/close.

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
    yield ">>> Touch sent - the board should now enumerate as a DFU device.\n"


def _diagnose_dfu_failure(tail: list[str], device: str) -> list[str]:
    """Actionable ``!!`` hints for a failed dfu-util run, from the tail of its output."""
    blob = "".join(tail).lower()
    if "no dfu capable usb device" in blob:
        return [
            "!! No board in DFU mode was found on USB. Put the board into DFU (or use the\n",
            "!! 'reboot to DFU' action) and flash again.\n",
        ]
    if "not writeable" in blob or "last page" in blob:
        return [
            "!! dfu-util refused the write range - the firmware's start offset doesn't fit this\n",
            "!! chip's flash layout. Rebuild the profile for this exact board, then flash again.\n",
        ]
    if "cannot open dfu device" in blob or "permission" in blob or "password is required" in blob:
        return [
            "!! Could not open the DFU device (permissions). Update FilaMind - it refreshes the\n",
            "!! needed access automatically - then flash again.\n",
        ]
    return []


async def _flash_dfu(
    device: str,
    firmware: str,
    offset: str,
    result: dict[str, int] | None = None,
    attempts: int = 3,
) -> AsyncIterator[str]:
    """DFU download with retries; ``:leave`` (boot the app) only after a successful write.

    Reports the real outcome via ``result["rc"]`` (0 only when dfu-util's success marker was seen) -
    a fully failed download must never be recorded as a flash. On failure the board is deliberately
    left parked in DFU (rebooting a half-written app is worse), and the log says so.
    """
    cmd = dfu_command(firmware, offset, device)
    ok = False
    tail: list[str] = []
    for attempt in range(1, attempts + 1):
        yield f">>> DFU attempt {attempt}/{attempts}: {' '.join(cmd)}\n"
        async for line in _stream(cmd):
            tail.append(line)
            del tail[:-60]
            yield line
            if "success" in line.lower() or "download done" in line.lower():
                ok = True
        if ok:
            break
        if attempt < attempts:
            yield ">>> DFU failed - retrying…\n"
            await asyncio.sleep(2)
    if result is not None:
        result["rc"] = 0 if ok else 1
    if not ok:
        for hint in _diagnose_dfu_failure(tail, device):
            yield hint
        yield "!! DFU write failed - leaving the board in DFU so it can be flashed again.\n"
        return
    yield ">>> Exiting DFU (:leave) to return to firmware…\n"
    async for line in _stream(dfu_leave_command(offset, device)):
        yield line


#: Klipper's documented CAN txqueuelen (klipper3d.org). The BTT default of 1024 bufferbloats the
#: sustained block write during a CAN flash, so Katapult aborts with SEND_BLOCK - we lower it for
#: the flash and restore it after.
_CAN_QLEN = "128"
_CAN_FLASH_ATTEMPTS = 3


async def _can_txqueuelen(interface: str) -> str | None:
    """The CAN interface's current txqueuelen, or None if it can't be read."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "ip",
            "-o",
            "link",
            "show",
            interface,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
            env=build_env(),
        )
        out, _ = await proc.communicate()
    except (OSError, NotImplementedError):
        return None
    match = re.search(r"qlen (\d+)", out.decode(errors="replace"))
    return match.group(1) if match else None


async def _set_txqueuelen(interface: str, value: str) -> None:
    """Best-effort set of a CAN interface's txqueuelen (uses the panel's ``ip`` sudo grant)."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "sudo",
            "-n",
            "ip",
            "link",
            "set",
            interface,
            "txqueuelen",
            value,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
            env=build_env(),
        )
        await proc.wait()
    except (OSError, NotImplementedError):
        pass


async def _flash_can(
    uuid: str, firmware: str, interface: str, settings: Settings, result: dict[str, int]
) -> AsyncIterator[str]:
    """Katapult CAN flash, hardened for the two failure modes seen on real buses.

    * A large txqueuelen (the BTT default 1024) bufferbloats the sustained block write, so Katapult
      aborts with ``SEND_BLOCK``; we lower it to Klipper's documented 128 for the flash + restore.
    * A single attempt can still drop a CAN frame under load. Katapult re-erases the app region
      before every write, so a retry is safe - we try a few times before giving up.

    ``result["rc"]`` is set to the last attempt's exit code (0 = flashed).
    """
    command = can_command(settings.katapult_dir, interface, uuid, firmware)
    original = await _can_txqueuelen(interface)
    lowered = bool(original and original != _CAN_QLEN)
    if lowered:
        yield f">>> Lowering {interface} txqueuelen {original} -> {_CAN_QLEN} for the flash.\n"
        await _set_txqueuelen(interface, _CAN_QLEN)
    rc = 127
    restored = ""
    try:
        for attempt in range(1, _CAN_FLASH_ATTEMPTS + 1):
            if attempt > 1:
                yield f">>> CAN flash attempt {attempt}/{_CAN_FLASH_ATTEMPTS}…\n"
            yield f">>> {' '.join(command)}\n"
            attempt_result: dict[str, int] = {}
            async for line in _stream(command, result=attempt_result):
                yield line
            rc = attempt_result.get("rc", 127)
            if rc == 0:
                break
            if attempt < _CAN_FLASH_ATTEMPTS:
                yield ">>> CAN write failed - retrying (Katapult re-erases before each write)…\n"
                await asyncio.sleep(2)
    finally:
        # Restore on every exit path - success, failure, or a client-disconnect cancellation - so a
        # tab closed mid-flash can't leave the interface stuck at 128. No yield in finally (that
        # raises during GeneratorExit); the log line is emitted after, on the normal path.
        if lowered and original is not None:
            await _set_txqueuelen(interface, original)
            restored = f">>> Restored {interface} txqueuelen to {original}.\n"
    if restored:
        yield restored
    result["rc"] = rc


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
        yield "!! Passwordless sudo is not configured - required to stop Klipper and flash.\n"
        yield "!! Run once on the host:  sudo bash scripts/install.sh sudoers\n"
        return

    is_linux = is_linux_profile(settings.data_dir, profile) if profile else False
    method = resolve_method(method, device, is_linux)
    # External firmware (a direct file, no profile .config) gets its own guards FIRST - they are
    # the most specific refusals, and the generic method guards below can't see inside the file.
    if firmware:
        if method == "make":
            # `make flash` builds+pushes klipper/out - whatever profile was built LAST - never
            # this file. Silently flashing the wrong firmware is the worst possible outcome.
            yield "!! External firmware can't be flashed with 'make' - that would push the last\n"
            yield "!! BUILT firmware, not this file. Set the method to serial / can / dfu in the\n"
            yield "!! firmware's properties, then flash again.\n"
            return
        if method == "dfu" and not offset_override:
            # Without the file's true start offset a DFU write lands at 0x08000000 and can wipe
            # the board's bootloader.
            yield "!! A DFU flash of an external file needs its start offset (it depends on the\n"
            yield "!! board's bootloader). Set the offset in the firmware's properties, then\n"
            yield "!! flash again.\n"
            return
        # Read the MCU from the FILE being flashed (best-effort binary inspection) - the meta
        # sidecar only stores the editable fields, never the detected properties.
        detected = str(
            external_firmware.inspect_firmware(firmware).get("detected_mcu") or ""
        ).lower()
        chip = device_chip_token(device)
        if detected and chip and not (detected.startswith(chip) or chip.startswith(detected)):
            # Same contract as the profile arch guard: refuse only a PROVABLE mismatch between
            # the binary's embedded MCU and the chip named in the board's serial id; fail open
            # when either side is unknown.
            yield (
                f"!! This firmware was built for '{detected}', but the target board is a "
                f"{chip}\n"
                f"!! ({device}). Flashing it would leave the board unbootable. Pick a firmware\n"
                "!! built for this board, then flash again.\n"
            )
            return
    # `make flash` needs the host build tools; check before stopping Klipper so a host without
    # `make` fails early and clearly instead of after a needless service stop + cryptic code 127.
    if method == "make" and not make_available():
        for line in missing_toolchain_lines():
            yield line
        yield "!! Flash aborted - the host is missing the firmware build tools.\n"
        return
    # An AVR profile aimed at a non-AVR board would run avrdude against a chip it can't program
    # (e.g. an rp2040), failing with a cryptic "make exited with code 2" (#567). Refuse up front,
    # before touching the board - the fix is to build a profile that matches the board.
    is_avr = is_avr_profile(settings.data_dir, profile) if profile else False
    mismatch = arch_mismatch(is_avr, device, method)
    if mismatch:
        _fw, chip = mismatch
        yield (
            f"!! This profile builds AVR / ATmega firmware, but the target board is an {chip}\n"
            f"!! ({device}). Klipper's 'make flash' runs avrdude, which cannot program an {chip}.\n"
            "!! Build or select a profile whose MCU matches this board (in the Config step), then\n"
            "!! flash again - the board was not touched.\n"
        )
        return
    # A make flash to a /dev path: fail early if the device vanished (unplugged / re-enumerated),
    # rather than after a needless Klipper stop + a cryptic make error.
    if method == "make" and device.startswith("/dev/") and not os.path.exists(device):
        yield f"!! The flash device {device} was not found - is the board plugged in?\n"
        return
    # A DFU flash needs a board that is actually sitting in ROM DFU - fail early and clearly
    # (before stopping Klipper) instead of letting dfu-util fail three times.
    if method == "dfu" and not await _dfu_device_present():
        yield "!! No board in DFU mode was found on USB. Put the board into DFU first (or use\n"
        yield "!! the 'reboot to DFU' action), then flash again.\n"
        return
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
        yield ">>> Flash sequence complete - host MCU reinstalled.\n"
        return

    offset = offset_override or (
        flash_offset(profile_path(settings.data_dir, profile)) if profile else _DEFAULT_OFFSET
    )
    # CAN flashing addresses the node by its 12-hex canbus_uuid, not a friendly name -
    # resolve it from the live config so a device registered as "Toolhead" still flashes.
    target = device
    pre_version = ""
    if method == "can":
        resolved, uuid_err = await resolve_can_uuid(device, settings.moonraker_url)
        if resolved is None:
            yield uuid_err or "!! Could not resolve the CAN node to flash.\n"
            return
        target = resolved
        # Snapshot the node's CURRENT firmware version (Klipper is still up here). The
        # verify-via-Klipper rescue below is only trustworthy when the built version DIFFERS -
        # on a same-version reflash the old firmware answers with the same string.
        pre_version = await _can_node_version(target, settings.moonraker_url)

    # From here Klipper goes down: whatever happens (including the client closing the stream at a
    # yield - even during the stop itself), it must come back up. The finally fires a detached
    # restart on any abnormal exit.
    flash_result: dict[str, int] = {}
    flash_tool = ""
    tail: list[str] = []
    klipper_restarted = False
    try:
        yield _phase("stop")
        yield ">>> Stopping Klipper to free the device…\n"
        async for line in _stream(["sudo", "-n", "systemctl", "stop", "klipper"]):
            yield line

        # A board can re-appear under a new /dev id after a serial flash - snapshot first.
        before = _serial_by_id() if method == "serial" else set()

        # A DFU device is already in its bootloader; only running Katapult boards need
        # a reboot. Boards not marked Katapult are flashed directly (skip the reboot).
        if method == "serial" and is_katapult:
            yield _phase("boot")
            # A USB serial board renames itself once it's in the bootloader (usb-Klipper_<id> →
            # usb-katapult_<id>), so the stored running-firmware path is gone. If it's already in
            # the bootloader (e.g. a previous flash didn't finish), flash it directly; otherwise
            # reboot it and then retarget to whatever the board actually became.
            already = bootloader_serial_path(target)
            if already:
                yield (
                    f">>> Board is already in the Katapult bootloader ({os.path.basename(already)})"
                    " - flashing it directly.\n"
                )
                target = already
            else:
                # Snapshot DFU presence BEFORE the reboot: the fallback below must only fire on a
                # DFU device that NEWLY appeared (i.e. this board), never on some other STM32
                # already parked in DFU on the same host - that one must not receive this firmware.
                dfu_before = await _dfu_device_present()
                async for line in _reboot_to_bootloader(
                    method, target, interface or "can0", settings
                ):
                    yield line
                # Probe what the board became - giving the Katapult port the FULL budget first
                # (a slow udev symlink must not lose a race to the DFU check).
                booted = bootloader_serial_path(target)
                for _ in range(4):
                    if booted or os.path.exists(target):
                        break
                    await asyncio.sleep(2)
                    booted = bootloader_serial_path(target)
                if booted:
                    yield f">>> Board entered the bootloader as {os.path.basename(booted)}.\n"
                    target = booted
                elif not os.path.exists(target) and not dfu_before and await _dfu_device_present():
                    # No Katapult on this board: the bootloader request dropped it into ROM DFU
                    # (the DFU device appeared only after OUR reboot request, so it is this board).
                    if offset != _DEFAULT_OFFSET:
                        # The profile is linked for a bootloader offset, but the board just proved
                        # it has no Katapult - flashing at that offset would "succeed" and never
                        # boot. Refuse honestly instead.
                        yield (
                            f"!! This profile expects a bootloader (firmware linked at {offset}), "
                            "but the board has no Katapult -\n"
                            "!! it rebooted into ROM DFU instead. Rebuild the profile without a "
                            "bootloader offset, then flash again.\n"
                        )
                        yield _phase("restart")
                        yield ">>> Restarting Klipper…\n"
                        async for line in _stream(["sudo", "-n", "systemctl", "start", "klipper"]):
                            yield line
                        klipper_restarted = True
                        yield "!! Flash aborted - nothing was written to the board.\n"
                        return
                    yield (
                        ">>> The board rebooted into ROM DFU instead of Katapult - continuing as "
                        f"a DFU flash at offset {offset}.\n"
                    )
                    method = "dfu"
                elif not os.path.exists(target):
                    yield (
                        "!! After the bootloader request the board's port did not come back (no "
                        "Katapult port appeared).\n"
                        "!! Power-cycle the printer to boot the board back into its firmware, "
                        "then flash again.\n"
                    )
                    yield _phase("restart")
                    yield ">>> Restarting Klipper…\n"
                    async for line in _stream(["sudo", "-n", "systemctl", "start", "klipper"]):
                        yield line
                    klipper_restarted = True
                    yield "!! Flash aborted - nothing was written to the board.\n"
                    return
        elif method == "can" and is_katapult:
            # Katapult's flashtool enters the node's bootloader itself: `flashtool.py -u <uuid> -f`
            # always issues its own jump. A separate pre-jump (`-r`) double-jumps the node - it
            # churns it app↔Katapult and leaves the flasher's CONNECT failing - so we do NOT
            # pre-reboot for CAN; the one flash command handles it (a CAN node keeps its UUID in
            # both modes, so unlike serial there is no renamed path to retarget).
            yield _phase("boot")
            yield ">>> The CAN flasher enters the bootloader itself - no pre-reboot needed.\n"
        elif method in ("serial", "can"):
            yield ">>> Device is not marked Katapult - skipping reboot-to-bootloader.\n"

        yield _phase("write")
        if method == "dfu":
            flash_tool = "dfu-util"
            async for line in _flash_dfu(device, artifact, offset, flash_result):
                yield line
        elif method == "can":
            flash_tool = "flashtool.py"
            async for line in _flash_can(
                target, artifact, interface or "can0", settings, flash_result
            ):
                tail.append(line)
                del tail[:-60]
                yield line
        else:
            if method == "make" and profile and not firmware:
                # `make flash` builds + pushes from klipper/.config, which may still hold the
                # LAST-built profile (e.g. after a batch build) - re-stage this profile's config
                # so the flashed bytes always match the board being flashed.
                try:
                    shutil.copy(
                        profile_path(settings.data_dir, profile),
                        os.path.join(settings.klipper_dir, ".config"),
                    )
                except OSError as exc:
                    yield f"!! Could not stage the profile's build config: {exc}\n"
                    yield _phase("restart")
                    yield ">>> Restarting Klipper…\n"
                    async for line in _stream(["sudo", "-n", "systemctl", "start", "klipper"]):
                        yield line
                    klipper_restarted = True
                    yield "!! Flash aborted - nothing was written to the board.\n"
                    return
                yield ">>> Staged this profile's build config for make flash.\n"
                async for line in _stream(["make", "olddefconfig"], cwd=settings.klipper_dir):
                    yield line
            command = _build_command(
                method, settings, target, artifact, interface or "can0", offset
            )
            flash_tool = os.path.basename(command[0])
            yield f">>> {' '.join(command)}\n"
            async for line in _stream(
                command, cwd=settings.klipper_dir if method == "make" else None, result=flash_result
            ):
                tail.append(line)
                del tail[:-60]  # keep the last ~60 lines to diagnose a flash failure
                yield line

        yield _phase("restart")
        yield ">>> Restarting Klipper…\n"
        async for line in _stream(["sudo", "-n", "systemctl", "start", "klipper"]):
            yield line
        klipper_restarted = True
    finally:
        # Abnormal exit (client disconnect / cancel / unexpected error) before the restart ran:
        # bring Klipper back detached - the printer must never be left headless by a dead stream.
        if not klipper_restarted:
            _restart_klipper_detached()

    # The flash tool failed (non-zero exit). For CAN this is often the read-back VERIFY
    # phase dying on the USB-CAN adapter (sustained node→host flood) AFTER the write
    # completed - the board actually runs the new firmware. Check the real outcome via
    # Klipper before declaring failure: if the node now reports the built version, the
    # flash took.
    rc = flash_result.get("rc", 0)
    if rc != 0:
        expected = str((read_build_info(settings.data_dir, profile) or {}).get("version") or "")
        # Same-version reflash: the node reporting `expected` proves nothing (the OLD firmware
        # answers with the identical string), so the tool's exit code stays authoritative. The
        # sameness test mirrors the rescue's own startswith tolerance (suffixed version strings).
        same_version = bool(pre_version) and (
            pre_version == expected or pre_version.startswith(expected)
        )
        if method == "can" and expected and not same_version:
            yield (
                ">>> Flash tool reported an error - checking via Klipper whether the "
                "board took the new firmware anyway…\n"
            )
            if await _can_node_runs_version(target, expected, settings.moonraker_url):
                yield f">>> Verified: the board reports {expected} - the flash DID succeed.\n"
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
                yield ">>> Flash sequence complete - verified through Klipper.\n"
                return
        if method == "make":
            for hint in _diagnose_make_failure(tail, device):
                yield hint
        elif method in ("serial", "can"):
            for hint in _diagnose_serial_failure(tail, device):
                yield hint
        yield (
            f"!! Flash failed - {flash_tool or 'the flash tool'} exited with code {rc}. "
            "The board was not flashed; see the output above.\n"
        )
        return

    # Pick up a serial board's new id (re-enumeration) and carry it into the registry.
    flashed_id = device
    if method == "serial":
        await asyncio.sleep(3)
        new_id = reenumerated_id(device, before, _serial_by_id())
        if new_id:
            yield f">>> Board re-appeared as {new_id} - updating the registry.\n"
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
    yield ">>> Flash sequence complete - verify the board reconnects in Mainsail.\n"


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
    yield ">>> Reboot requested - the board should re-appear in its bootloader.\n"
