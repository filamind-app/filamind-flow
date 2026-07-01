"""Host build-toolchain checks for the Firmware Manager.

Building or ``make flash``-ing Klipper firmware needs the host's build tools
(``make`` + a C compiler for the target MCU). A fresh Klipper host that was set
up without the build dependencies has no ``make`` at all, which otherwise surfaces
as a cryptic ``cannot run 'make': [Errno 2]`` / ``exited with code 127``. This
module centralises the check + an actionable "install these" message so both the
build and the flash paths fail early and clearly.
"""

from __future__ import annotations

import os
import shutil

# Standard locations for the build toolchain (make, gcc, arm-none-eabi-gcc, avr-gcc, dfu-util).
# A systemd service can start with a PATH that omits these even when the tools ARE installed - #558
# was exactly this: build-essential + the Arm compiler were present in /usr/bin, but the backend's
# `make` subprocess still failed with `[Errno 2]` because /usr/bin wasn't on the service's PATH. So
# build/flash always run with an augmented PATH covering these dirs.
_TOOLCHAIN_DIRS = ("/usr/local/bin", "/usr/bin", "/usr/sbin", "/bin", "/sbin")


def _augmented_path() -> str:
    """The current PATH plus the standard system bin dirs, order-preserving + de-duplicated, so
    build/flash subprocesses find ``make`` + the MCU compilers even under a minimal service PATH."""
    seen: list[str] = []
    for d in os.environ.get("PATH", "").split(os.pathsep) + list(_TOOLCHAIN_DIRS):
        if d and d not in seen:
            seen.append(d)
    return os.pathsep.join(seen)


def build_env() -> dict[str, str]:
    """``os.environ`` with PATH augmented to include the standard toolchain dirs. Pass as the
    ``env=`` of the build / ``make flash`` subprocess so ``make`` AND the compilers it invokes are
    found regardless of the (possibly minimal) PATH the backend service was started with."""
    env = dict(os.environ)
    env["PATH"] = _augmented_path()
    return env


def make_available() -> bool:
    """True if ``make`` is resolvable via the augmented PATH (the minimum to build / flash)."""
    return shutil.which("make", path=_augmented_path()) is not None


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
