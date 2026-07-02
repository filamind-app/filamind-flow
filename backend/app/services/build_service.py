"""Firmware build - compiles a profile's ``.config`` into a flashable artifact.

The build mirrors what a user does by hand: stage the profile's ``.config`` as
``klipper/.config``, ``make clean`` + ``make olddefconfig`` (so the config is
valid for the installed Klipper), then ``make`` - streaming every line so the
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

from app.services.build_tools import build_env, make_available, missing_toolchain_lines
from app.services.firmware_profiles import artifacts_dir
from app.services.version_store import get_klipper_version, write_build_info

_ARTIFACT_EXTS = ("bin", "uf2", "elf")
_STALL_TIMEOUT_S = 120.0
_TOTAL_TIMEOUT_S = 600.0


def _diagnose_build_failure(tail: list[str]) -> list[str]:
    """Actionable ``!!`` hints for a failed build, inferred from the tail of make's output."""
    blob = "".join(tail).lower()
    if "no space left" in blob:
        return ["!! The host's disk is full - free some space, then build again.\n"]
    if "internal compiler error" in blob or "killed" in blob or "out of memory" in blob:
        return [
            "!! The compiler ran out of memory (common on small boards while printing).\n",
            "!! Retry while the printer is idle, or close other host tasks first.\n",
        ]
    return []


class BuildService:
    """Compiles a profile and streams the build log line by line."""

    def __init__(
        self, klipper_dir: str, data_dir: str, build_command: list[str] | None = None
    ) -> None:
        self.klipper_dir = os.path.abspath(os.path.expanduser(klipper_dir))
        self.data_dir = data_dir
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
        # Preflight: a host set up without the build dependencies has no `make`, which would
        # otherwise fail three times over as a cryptic "cannot run 'make'". Fail early + clearly.
        if self.build_command is None and not make_available():
            for line in missing_toolchain_lines():
                yield line
            yield ">>> BUILD FAILED - the host is missing the firmware build tools\n"
            return
        try:
            shutil.copy(config_path, os.path.join(self.klipper_dir, ".config"))
        except OSError as exc:
            yield f"!! Could not stage .config: {exc}\n"
            return

        yield f">>> Building firmware for profile '{profile_name}'\n"
        async for line in self._stream(["make", "clean"]):
            yield line
        cfg_result: dict[str, int] = {}
        async for line in self._stream(["make", "olddefconfig"], result=cfg_result):
            yield line
        # The real make path must not build from a config that failed to validate (the
        # test-override path runs a portable command instead of make, so it skips this gate).
        if self.build_command is None and cfg_result.get("rc", 0) != 0:
            yield ">>> BUILD FAILED - the profile's config could not be applied (olddefconfig)\n"
            return
        build_cmd = self.build_command or ["make", f"-j{os.cpu_count() or 1}"]
        yield f">>> {' '.join(build_cmd)}\n"
        tail: list[str] = []
        build_result: dict[str, int] = {}
        async for line in self._stream(build_cmd, result=build_result):
            tail.append(line)
            del tail[:-40]
            yield line
        # A non-zero make is a failed build even when a previous run left artifacts in out/ -
        # judging by artifact presence alone can save (and later flash) stale firmware.
        if build_result.get("rc", 0) != 0:
            for hint in _diagnose_build_failure(tail):
                yield hint
            yield f">>> BUILD FAILED - the build exited with code {build_result['rc']}\n"
            return

        saved = self._collect(profile_name)
        if saved:
            version = await get_klipper_version(self.klipper_dir)
            write_build_info(self.data_dir, profile_name, version)
            yield f">>> Built with Klipper {version['version']}\n"
            yield f">>> Saved artifact(s): {', '.join(saved)}\n>>> BUILD OK\n"
        else:
            yield ">>> BUILD FAILED - no firmware artifact was produced\n"

    def _collect(self, profile_name: str) -> list[str]:
        """Copies freshly built ``out/klipper.*`` into the artifacts directory.

        Stale sibling artifacts from a previous build (e.g. an old ``.bin`` after the profile was
        re-targeted to a platform that produces only ``.elf``) are purged first - the flash path
        picks the first extension it finds, and a leftover must never win over the fresh build.
        """
        saved: list[str] = []
        out_dir = os.path.join(self.klipper_dir, "out")
        fresh = {
            ext: os.path.join(out_dir, f"klipper.{ext}")
            for ext in _ARTIFACT_EXTS
            if os.path.isfile(os.path.join(out_dir, f"klipper.{ext}"))
        }
        if fresh:
            for ext in _ARTIFACT_EXTS:
                stale = os.path.join(self.artifacts, f"{profile_name}.{ext}")
                if ext not in fresh and os.path.isfile(stale):
                    os.remove(stale)
        for ext, src in fresh.items():
            shutil.copy(src, os.path.join(self.artifacts, f"{profile_name}.{ext}"))
            saved.append(f"{profile_name}.{ext}")
        return saved

    async def _stream(
        self, cmd: list[str], result: dict[str, int] | None = None
    ) -> AsyncIterator[str]:
        """Runs a command in the Klipper dir, yielding stdout+stderr lines. When ``result`` is
        given, its ``"rc"`` is set to the exit code (127 if the command couldn't start)."""
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=self.klipper_dir,
                env=build_env(),  # augmented PATH so make + the MCU compilers are found (#558)
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
        except (OSError, NotImplementedError) as exc:
            yield f"!! cannot run '{cmd[0]}': {exc}\n"
            if result is not None:
                result["rc"] = 127
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
        rc = await proc.wait()
        if result is not None:
            result["rc"] = rc
