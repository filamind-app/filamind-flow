"""FilaMind Kiosk — run FilaMind Flow itself on the printer's touchscreen.

KlipperScreen has no plugin API and its panels are hardcoded, so the only way to put *arbitrary*
content on the physical screen is to turn it into a fullscreen browser pointed at FilaMind Flow.
This module owns the **reversible swap** between the two: a ``filamind-kiosk`` systemd service
(installed once by ``scripts/install.sh kiosk``) declares ``Conflicts=KlipperScreen.service``, so
starting one stops the other.

Switching is **temporary by default** — a plain ``start``, so a reboot restores whichever service
is boot-enabled (KlipperScreen, unless the user persists the kiosk). ``persist`` also flips the
boot default (``enable``/``disable``). All actuation goes through ``sudo -n systemctl`` (the same
passwordless-sudo rule the flasher uses); nothing here installs packages or writes unit files —
that's the one-time install script. If the kiosk fails to come up, KlipperScreen is brought back
so the screen never stays dark.
"""

from __future__ import annotations

import asyncio
from typing import Any

from app.config import get_settings

KIOSK_UNIT = "filamind-kiosk.service"
SCREEN_UNIT = "KlipperScreen.service"


class KioskNotInstalledError(RuntimeError):
    """Raised when asked to switch to a kiosk whose service isn't installed yet."""


async def _run(cmd: list[str]) -> tuple[int, str]:
    """Runs a command, returning (returncode, combined output)."""
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT
        )
        out, _ = await proc.communicate()
    except (OSError, NotImplementedError) as exc:
        return 1, str(exc)
    return proc.returncode or 0, out.decode(errors="replace")


async def _systemctl(*args: str) -> tuple[int, str]:
    """Runs a privileged ``systemctl`` (passwordless sudo, same rule as the flasher)."""
    return await _run(["sudo", "-n", "systemctl", *args])


async def _is_active(unit: str) -> bool:
    code, _ = await _run(["systemctl", "is-active", "--quiet", unit])
    return code == 0


async def _is_enabled(unit: str) -> bool:
    _, out = await _run(["systemctl", "is-enabled", unit])
    return out.strip() == "enabled"


async def _unit_installed(unit: str) -> bool:
    """Whether a unit file exists at all (regardless of active/enabled state)."""
    _, out = await _run(["systemctl", "list-unit-files", unit, "--no-legend", "--no-pager"])
    return unit in out


async def _do(action: str, unit: str) -> dict[str, Any]:
    """Runs one privileged systemctl action and reports its result."""
    code, out = await _systemctl(action, unit)
    return {"cmd": f"systemctl {action} {unit}", "ok": code == 0, "output": out.strip() or None}


async def status() -> dict[str, Any]:
    """The current screen mode + whether each side is installed / active / boot-enabled.

    ``mode`` is the live truth (which service is actually running); the install/enabled flags let
    the UI offer the right action and a setup hint when the kiosk isn't provisioned yet.
    """
    settings = get_settings()
    kiosk_installed = await _unit_installed(KIOSK_UNIT)
    screen_installed = await _unit_installed(SCREEN_UNIT)
    kiosk_active = await _is_active(KIOSK_UNIT) if kiosk_installed else False
    screen_active = await _is_active(SCREEN_UNIT) if screen_installed else False
    kiosk_enabled = await _is_enabled(KIOSK_UNIT) if kiosk_installed else False
    if kiosk_active:
        mode = "kiosk"
    elif screen_active:
        mode = "klipperscreen"
    else:
        mode = "none"
    return {
        "kiosk_installed": kiosk_installed,
        "kiosk_active": kiosk_active,
        "kiosk_enabled": kiosk_enabled,
        "screen_installed": screen_installed,
        "screen_active": screen_active,
        "mode": mode,
        "url": settings.kiosk_url,
    }


async def switch_to_kiosk(persist: bool = False) -> dict[str, Any]:
    """Put FilaMind on the touchscreen. ``Conflicts=`` stops KlipperScreen automatically.

    Temporary by default (a reboot restores KlipperScreen). ``persist`` also makes the kiosk the
    boot default. If the kiosk fails to start, KlipperScreen is restarted so the screen recovers.
    """
    if not await _unit_installed(KIOSK_UNIT):
        raise KioskNotInstalledError(
            "The FilaMind kiosk service isn't installed yet — "
            "run 'sudo bash scripts/install.sh kiosk' on the printer host first."
        )
    steps: list[dict[str, Any]] = []
    if persist:
        steps.append(await _do("disable", SCREEN_UNIT))
        steps.append(await _do("enable", KIOSK_UNIT))
    start_step = await _do("start", KIOSK_UNIT)
    steps.append(start_step)
    if not start_step["ok"]:
        # Kiosk didn't come up — never leave a dark screen; bring KlipperScreen back.
        steps.append(await _do("start", SCREEN_UNIT))
    return {"action": "kiosk", "persist": persist, "steps": steps, "status": await status()}


async def restore_screen(persist: bool = False) -> dict[str, Any]:
    """Hand the touchscreen back to KlipperScreen. ``persist`` also makes it the boot default."""
    steps: list[dict[str, Any]] = []
    if await _unit_installed(KIOSK_UNIT):
        steps.append(await _do("stop", KIOSK_UNIT))
        if persist:
            steps.append(await _do("disable", KIOSK_UNIT))
    if persist:
        steps.append(await _do("enable", SCREEN_UNIT))
    steps.append(await _do("start", SCREEN_UNIT))
    return {"action": "klipperscreen", "persist": persist, "steps": steps, "status": await status()}
