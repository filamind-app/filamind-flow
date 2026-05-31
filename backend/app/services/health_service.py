"""Install-integrity health checks.

Surfaces whether the host is set up for firmware flashing — the passwordless sudo
rule, the STM32 DFU udev rule, and the dfu-util tool — so the UI can show a clear
green / amber light and tell the user exactly what to run if something is missing
(``deploy/setup-sudoers.sh``). FilaMind never edits these privileged files itself;
it only reports on them.
"""

from __future__ import annotations

import os
import shutil
from typing import Any

from app.services.flash_service import _sudo_ready

_SUDOERS = "/etc/sudoers.d/filamind"
_UDEV_DFU = "/etc/udev/rules.d/99-stm32-dfu.rules"
_FIX = "run: sudo bash deploy/setup-sudoers.sh"


async def gather_health() -> dict[str, Any]:
    """Runs the install-integrity checks; returns a ``healthy`` flag + details."""
    checks: list[dict[str, Any]] = [
        {"name": "sudoers", "ok": os.path.isfile(_SUDOERS), "detail": _FIX},
        {"name": "sudo", "ok": await _sudo_ready(), "detail": "backend can sudo non-interactively"},
        {"name": "udev-dfu", "ok": os.path.isfile(_UDEV_DFU), "detail": _FIX},
        {
            "name": "dfu-util",
            "ok": shutil.which("dfu-util") is not None,
            "detail": "install dfu-util",
        },
    ]
    return {"healthy": all(c["ok"] for c in checks), "checks": checks}
