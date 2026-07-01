"""Host build-toolchain checks for the Firmware Manager.

Building or ``make flash``-ing Klipper firmware needs the host's build tools
(``make`` + a C compiler for the target MCU). A fresh Klipper host that was set
up without the build dependencies has no ``make`` at all, which otherwise surfaces
as a cryptic ``cannot run 'make': [Errno 2]`` / ``exited with code 127``. This
module centralises the check + an actionable "install these" message so both the
build and the flash paths fail early and clearly.
"""

from __future__ import annotations

import shutil


def make_available() -> bool:
    """True if ``make`` is on the host PATH (the minimum to build / ``make flash``)."""
    return shutil.which("make") is not None


def missing_toolchain_lines() -> list[str]:
    """Log lines shown when ``make`` is absent. FilaMind installs the build toolchain automatically
    on update (``scripts/install.sh`` ``ensure_build_toolchain``), so the user is pointed at the
    update flow rather than handed shell commands. Streamed into the build/flash log (``!!`` marks
    an error line), so it reads the same as the rest of the tool output."""
    return [
        "!! The firmware build tools aren't installed on this host yet, so the firmware couldn't\n",
        "!! be built or flashed. FilaMind installs them for you automatically when it updates.\n",
        "!! Update FilaMind from your printer's update manager (Mainsail / Fluidd -> Machine ->\n",
        "!! Update), then try Build & Flash again - no commands to run by hand.\n",
        "!! (If you just updated and still see this, the host may have been offline during the\n",
        "!! update; it retries automatically on the next one.)\n",
    ]
