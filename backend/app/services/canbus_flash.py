"""Flash an external USB-CAN adapter (candleLight / BTT U2C) from the host via ``dfu-util``.

The adapter is NOT a Klipper MCU, so Klipper / Katapult never touch it (they flash the MCUs *behind*
it on the bus). Updating it = put the adapter's STM32 into its ROM **DFU bootloader**, then run
``dfu-util``. candleLight / budgetcan firmware exposes a **USB DFU runtime interface**, so the host
can put a running adapter into DFU on its own with a ``dfu-util -e`` detach - no button press. We
try that first (stopping Klipper, since the detach drops the CAN bus) and only fall back to the
manual **BOOT-button** entry (hold BOOT while plugging the USB cable in) when the adapter can't be
detached in software - a corrupt adapter, or a build without the DFU runtime interface. Once it is
in DFU, the flash runs headless via the panel's passwordless ``sudo -n dfu-util`` grant. We fetch
the OFFICIAL BTT prebuilt candleLight binary for the chosen revision.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import re
import subprocess
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

#: The gs_usb runtime USB id of a candleLight / budgetcan adapter (BTT U2C v1/v2, CANable). When
#: ``dfu-util -l`` lists this, the adapter is running and advertising its DFU runtime interface, so
#: ``dfu-util -e`` can detach it into ROM DFU without the BOOT button.
_ADAPTER_ID = "1d50:606f"

#: Seconds to let the chip reset and re-enumerate as 0483:df11 after a detach.
_DETACH_SETTLE_S = 4.0

#: Signatures of "sudo isn't granted" (needs a password / not allowed / no tty). Matched precisely
#: so a benign warning like "sudo: unable to resolve host <name>" (common on SBC hosts, merged in
#: from stderr) is never misread as a denial - which would refuse the flash on a set-up host.
_SUDO_NOT_GRANTED = re.compile(
    r"a password is required|not allowed to execute|must have a tty|sudo:.*(askpass|required)",
    re.IGNORECASE,
)


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
    """Whether the adapter is in ROM DFU, or a running adapter we can auto-detach into DFU.

    From ``dfu-util -l``: ``0483:df11`` / "Found DFU" = already in the STM32 ROM bootloader;
    the gs_usb runtime id (:data:`_ADAPTER_ID`) = running and detachable in software."""
    _rc, out = await _run(["sudo", "-n", "dfu-util", "-l"], 20)
    if _SUDO_NOT_GRANTED.search(out):
        return {"present": False, "runtime": False, "detail": out.strip()[:2000], "sudo": False}
    present = "0483:df11" in out or "Found DFU" in out
    runtime = (not present) and _ADAPTER_ID in out
    return {"present": present, "runtime": runtime, "detail": out.strip()[:2000], "sudo": True}


async def _dfu_detach() -> str:
    """Ask a running gs_usb adapter to reboot into ROM DFU via a USB DFU_DETACH (``dfu-util -e``).

    candleLight / budgetcan implement the DFU runtime interface, so this replaces the manual
    BOOT-button entry. Returns dfu-util's output; the caller re-checks :func:`dfu_status`."""
    _rc, out = await _run(["sudo", "-n", "dfu-util", "-e", "-d", _ADAPTER_ID], 30)
    await asyncio.sleep(_DETACH_SETTLE_S)  # let the chip reset and re-enumerate as 0483:df11
    return out.strip()


async def _klipper(action: str) -> None:
    """Best-effort ``systemctl <action> klipper`` (stop before a detach; start is the finally)."""
    with contextlib.suppress(Exception):
        await _run(["sudo", "-n", "systemctl", action, "klipper"], 20)


def _start_klipper_detached() -> None:
    """Fire-and-forget ``systemctl start klipper`` that survives request teardown.

    A client disconnect can cancel this request mid-flash; Klipper must never be left stopped, so
    the restart uses a plain ``Popen`` that needs no event-loop cooperation during the unwind."""
    with contextlib.suppress(OSError):
        subprocess.Popen(
            ["sudo", "-n", "systemctl", "start", "klipper"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )


async def flash(revision: str) -> dict[str, Any]:
    """Flash the chosen revision's official candleLight firmware to the adapter.

    If the adapter is already in DFU (BOOT-button entry, or a prior detach) we flash it directly.
    Otherwise, when it is running and detachable, we stop Klipper (the detach drops the CAN bus),
    put it into DFU with ``dfu-util -e``, then flash - no manual step. We refuse only when the
    adapter is neither in DFU nor auto-detachable, so a flash never hits the live gs_usb interface.
    Klipper is always restarted afterwards. Returns ``{ok, output}``."""
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

    prelog: list[str] = []
    klipper_stopped = False
    try:
        if not status["present"]:
            if not status["runtime"]:
                return {
                    "ok": False,
                    "output": "No DFU device, and no running gs_usb adapter to put into DFU, was "
                    "found on USB. Plug the adapter in (or hold its BOOT button while plugging the "
                    "USB cable into the printer), then try again.\n\n" + status["detail"],
                }
            # The detach drops the adapter off the CAN bus, so stop Klipper first - it must not
            # thrash on a vanishing bus. Set the flag BEFORE the stop so the finally restarts it
            # even if the await is cancelled mid-stop - the printer must never be left headless.
            klipper_stopped = True
            await _klipper("stop")
            prelog.append(">>> Adapter is running - entering DFU in software (USB detach)…")
            prelog.append(await _dfu_detach())
            status = await dfu_status()
            if not status["present"]:
                return {
                    "ok": False,
                    "output": "Could not put the adapter into DFU automatically. Hold its BOOT "
                    "button while plugging the USB cable into the printer, release, then flash "
                    "again.\n\n" + "\n".join(prelog) + "\n\n" + status["detail"],
                }

        try:
            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                resp = await client.get(fw["url"])
                resp.raise_for_status()
                data = resp.content
        except httpx.HTTPError as exc:
            return {"ok": False, "output": f"Could not download firmware from {fw['url']}: {exc}"}
        if len(data) < 1024:
            return {
                "ok": False,
                "output": f"Downloaded firmware is only {len(data)} bytes - aborting.",
            }

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
        body = ("\n".join(prelog) + "\n\n" if prelog else "") + out.strip()
        if klipper_stopped:
            body += (
                "\n\n>>> Klipper is being restarted. If the adapter doesn't come back on the CAN "
                "bus, unplug and replug it once to power-cycle it, then Klipper will reconnect."
            )
        return {"ok": ok, "output": header + body}
    finally:
        if klipper_stopped:
            _start_klipper_detached()
