"""Flash an external USB-CAN adapter (candleLight / BTT U2C) from the host via ``dfu-util``.

The adapter is NOT a Klipper MCU, so Klipper / Katapult never touch it (they flash the MCUs *behind*
it on the bus). Updating it = put the adapter's STM32 into its ROM **DFU bootloader** - which on a
U2C / CANable means a PHYSICAL action: hold the BOOT button while plugging the USB cable in (the
gs_usb protocol exposes no software bootloader-entry, so the host cannot trigger DFU remotely). Once
it is in DFU, the flash itself runs headless here via the panel's passwordless ``sudo -n dfu-util``
grant. We fetch the OFFICIAL BTT prebuilt candleLight binary for the chosen revision.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import tempfile
from typing import Any

import httpx

#: Official BTT prebuilt candleLight firmware per U2C revision (verified GitHub raw URLs). The chip
#: differs by revision, so the user picks the right one - the wrong binary can brick the adapter.
FIRMWARE: dict[str, dict[str, str]] = {
    "u2c-v1": {
        "label": "BTT U2C v1.0 / v1.1 (STM32F072)",
        "url": "https://raw.githubusercontent.com/bigtreetech/U2C/master/firmware/U2C_V1_STM32F072.bin",
    },
    "u2c-v2": {
        "label": "BTT U2C v2.0 / v2.1 (STM32G0B1)",
        "url": "https://raw.githubusercontent.com/bigtreetech/U2C/master/firmware/U2C_V2_STM32G0B1.bin",
    },
}

#: The flash target address of the STM32 ROM bootloader.
_FLASH_ADDR = "0x08000000:leave"


def revisions() -> list[dict[str, str]]:
    """The selectable adapter revisions (id + human label) for the flash picker."""
    return [{"id": key, "label": fw["label"]} for key, fw in FIRMWARE.items()]


async def _run(cmd: list[str], timeout: float = 120.0) -> tuple[int, str]:
    """Run a command, capturing combined stdout+stderr (C locale keeps messages parseable)."""
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            env={**os.environ, "LC_ALL": "C"},
        )
    except FileNotFoundError:
        return 127, f"{cmd[0]}: not found"
    try:
        out, _ = await asyncio.wait_for(proc.communicate(), timeout)
    except TimeoutError:
        proc.kill()
        return 124, f"{' '.join(cmd)}: timed out after {timeout:.0f}s"
    return proc.returncode or 0, out.decode("utf-8", "replace")


async def dfu_status() -> dict[str, Any]:
    """Whether an STM32 ROM-DFU device is currently attached (i.e. the BOOT-button entry worked).

    Detected from ``dfu-util -l`` (the ROM bootloader enumerates as ``0483:df11`` / "Found DFU")."""
    _rc, out = await _run(["sudo", "-n", "dfu-util", "-l"], 20)
    if "a password is required" in out or "sudo:" in out:
        return {"present": False, "detail": out.strip()[:2000], "sudo": False}
    present = "0483:df11" in out or "Found DFU" in out
    return {"present": present, "detail": out.strip()[:2000], "sudo": True}


async def flash(revision: str) -> dict[str, Any]:
    """Flash the chosen revision's official candleLight firmware to the adapter sitting in DFU mode.

    Requires the adapter to already be in DFU (hold BOOT while plugging USB) - we refuse otherwise,
    so a flash is never attempted against the live gs_usb adapter. Returns ``{ok, output}``."""
    fw = FIRMWARE.get(revision)
    if not fw:
        return {"ok": False, "output": f"Unknown adapter revision '{revision}'."}

    status = await dfu_status()
    if not status.get("sudo", True):
        return {
            "ok": False,
            "output": "Passwordless sudo for dfu-util is not active. Run once on the host:\n"
            "  sudo bash ~/filamind-flow/scripts/install.sh sudoers",
        }
    if not status["present"]:
        return {
            "ok": False,
            "output": "No DFU device found. Hold the adapter's BOOT button WHILE plugging its USB "
            "cable into the printer, release it, then try again.\n\n" + status["detail"],
        }

    try:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            resp = await client.get(fw["url"])
            resp.raise_for_status()
            data = resp.content
    except httpx.HTTPError as exc:
        return {"ok": False, "output": f"Could not download firmware from {fw['url']}: {exc}"}
    if len(data) < 1024:
        return {"ok": False, "output": f"Downloaded firmware is only {len(data)} bytes - aborting."}

    fd, path = tempfile.mkstemp(suffix=".bin", prefix="u2c-")
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
        rc, out = await _run(
            ["sudo", "-n", "dfu-util", "-a", "0", "-s", _FLASH_ADDR, "-D", path], 120
        )
    finally:
        with contextlib.suppress(OSError):
            os.unlink(path)

    # dfu-util with `:leave` often exits non-zero on the final get-status (the chip is already
    # rebooting out of DFU) - so treat the explicit success line as authoritative.
    ok = "File downloaded successfully" in out or "Download done" in out or rc == 0
    header = f"Firmware: {fw['label']} ({len(data)} bytes)\nSource: {fw['url']}\n\n"
    return {"ok": ok, "output": header + out.strip()}
