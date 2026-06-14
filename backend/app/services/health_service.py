"""Install-integrity health checks.

Surfaces whether the host is set up for firmware flashing — the passwordless sudo
rule, the STM32 DFU udev rule, and the dfu-util tool — so the UI can show a clear
green / amber light and tell the user exactly what to run if something is missing
(``scripts/install.sh sudoers``). FilaMind never edits these privileged files itself;
it only reports on them.
"""

from __future__ import annotations

import os
import shutil
from typing import Any

from app.services.flash_service import _sudo_ready

_SUDOERS = "/etc/sudoers.d/filamind"
_UDEV_DFU = "/etc/udev/rules.d/99-stm32-dfu.rules"
_FIX = "run: sudo bash scripts/install.sh sudoers"


async def gather_health() -> dict[str, Any]:
    """Runs the install-integrity checks; returns a ``healthy`` flag + details."""
    # What matters is the CAPABILITY, not a specific filename: the NOPASSWD rules may be
    # provided by FilaMind's own file or an existing one (e.g. a co-installed panel). If the
    # backend can run the privileged commands, sudo is correctly set up wherever the rule lives.
    sudo_ok = await _sudo_ready()
    checks: list[dict[str, Any]] = [
        {"name": "sudoers", "ok": sudo_ok or os.path.isfile(_SUDOERS), "detail": _FIX},
        {"name": "sudo", "ok": sudo_ok, "detail": "backend can sudo non-interactively"},
        {"name": "udev-dfu", "ok": os.path.isfile(_UDEV_DFU), "detail": _FIX},
        {
            "name": "dfu-util",
            "ok": shutil.which("dfu-util") is not None,
            "detail": "install dfu-util",
        },
    ]
    return {"healthy": all(c["ok"] for c in checks), "checks": checks}
