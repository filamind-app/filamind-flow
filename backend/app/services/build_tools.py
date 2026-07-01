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
    """Actionable log lines telling the user to install Klipper's build dependencies.

    Streamed into the build/flash log (``!!`` marks an error line), so it reads the
    same as the rest of the tool output. Covers the ARM (STM32/RP2040/SAM) and AVR
    compilers since the board's MCU family isn't known at this point."""
    return [
        "!! The firmware build tools are not installed on this host - 'make' was not found,\n",
        "!! so the firmware could not be built or flashed.\n",
        "!! Install Klipper's build dependencies on the host (over SSH), then try again:\n",
        "!!   sudo apt update && sudo apt install build-essential\n",
        "!! For 32-bit MCUs (STM32 / RP2040 / SAM, e.g. BigTreeTech Octopus) also install the "
        "ARM compiler:\n",
        "!!   sudo apt install gcc-arm-none-eabi binutils-arm-none-eabi libnewlib-arm-none-eabi\n",
        "!! For 8-bit AVR boards install instead:  sudo apt install avr-gcc avr-libc\n",
    ]
