"""Firmware build — compiles a profile's ``.config`` into a flashable artifact.

The build mirrors what a user does by hand: stage the profile's ``.config`` as
``klipper/.config``, ``make clean`` + ``make olddefconfig`` (so the config is
valid for the installed Klipper), then ``make`` — streaming every line so the
browser shows a live log. The resulting ``out/klipper.{bin,uf2,elf}`` is copied
into the artifacts directory under the profile's name, ready to flash.

Building never touches the running firmware, so it is safe during a print
(though it does load the host CPU).
"""

from __future__ import annotations

import asyncio
import os
import shutil
from collections.abc import AsyncIterator

from app.services.firmware_profiles import artifacts_dir

_ARTIFACT_EXTS = ("bin", "uf2", "elf")
_STALL_TIMEOUT_S = 120.0
_TOTAL_TIMEOUT_S = 600.0


class BuildService:
    """Compiles a profile and streams the build log line by line."""

    def __init__(
        self, klipper_dir: str, data_dir: str, build_command: list[str] | None = None
    ) -> None:
        self.klipper_dir = os.path.abspath(os.path.expanduser(klipper_dir))
        self.artifacts = artifacts_dir(data_dir)
        # Overridable so tests can drive a portable command instead of `make`.
        self.build_command = build_command

    async def run_build(self, config_path: str, profile_name: str) -> AsyncIterator[str]:
        """Yields the build log; the final lines report BUILD OK / FAILED."""
        if not os.path.isfile(os.path.join(self.klipper_dir, "Makefile")):
            yield f"!! Klipper Makefile not found under {self.klipper_dir}\n"
            return
        if not os.path.isfile(config_path):
            yield f"!! Profile config not found: {config_path}\n"
            return
        try:
            shutil.copy(config_path, os.path.join(self.klipper_dir, ".config"))
        except OSError as exc:
            yield f"!! Could not stage .config: {exc}\n"
            return

        yield f">>> Building firmware for profile '{profile_name}'\n"
        async for line in self._stream(["make", "clean"]):
            yield line
        async for line in self._stream(["make", "olddefconfig"]):
            yield line
        build_cmd = self.build_command or ["make", f"-j{os.cpu_count() or 1}"]
        yield f">>> {' '.join(build_cmd)}\n"
        async for line in self._stream(build_cmd):
            yield line

        saved = self._collect(profile_name)
        if saved:
            yield f">>> Saved artifact(s): {', '.join(saved)}\n>>> BUILD OK\n"
        else:
            yield ">>> BUILD FAILED — no firmware artifact was produced\n"

    def _collect(self, profile_name: str) -> list[str]:
        """Copies freshly built ``out/klipper.*`` into the artifacts directory."""
        saved: list[str] = []
        out_dir = os.path.join(self.klipper_dir, "out")
        for ext in _ARTIFACT_EXTS:
            src = os.path.join(out_dir, f"klipper.{ext}")
            if os.path.isfile(src):
                shutil.copy(src, os.path.join(self.artifacts, f"{profile_name}.{ext}"))
                saved.append(f"{profile_name}.{ext}")
        return saved

    async def _stream(self, cmd: list[str]) -> AsyncIterator[str]:
        """Runs a command in the Klipper dir, yielding stdout+stderr lines."""
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=self.klipper_dir,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
        except (OSError, NotImplementedError) as exc:
            yield f"!! cannot run '{cmd[0]}': {exc}\n"
            return
        assert proc.stdout is not None

        loop = asyncio.get_running_loop()
        start = loop.time()
        while True:
            if loop.time() - start > _TOTAL_TIMEOUT_S:
                yield f"!! aborted: exceeded {int(_TOTAL_TIMEOUT_S)}s\n"
                proc.kill()
                break
            try:
                raw = await asyncio.wait_for(proc.stdout.readline(), timeout=_STALL_TIMEOUT_S)
            except asyncio.TimeoutError:
                yield f"!! aborted: no output for {int(_STALL_TIMEOUT_S)}s\n"
                proc.kill()
                break
            if not raw:
                break
            yield raw.decode(errors="replace")
        await proc.wait()
