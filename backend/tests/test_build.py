from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.main import create_app
from app.services import firmware_profiles
from app.services.build_service import BuildService

# A portable stand-in for `make`: creates out/klipper.bin and prints a line,
# so the build pipeline can be exercised without a cross-compiler toolchain.
_FAKE_MAKE = [
    sys.executable,
    "-c",
    "import os; os.makedirs('out', exist_ok=True); "
    "open(os.path.join('out', 'klipper.bin'), 'wb').close(); print('compiling firmware...')",
]


def test_build_streams_and_collects_artifact(tmp_path: Path) -> None:
    klipper = tmp_path / "klipper"
    klipper.mkdir()
    (klipper / "Makefile").write_text("# fake makefile\n")
    profile_cfg = tmp_path / "p.config"
    profile_cfg.write_text("CONFIG_DEMO=y\n")
    data = tmp_path / "data"

    service = BuildService(str(klipper), str(data), build_command=_FAKE_MAKE)

    async def collect() -> str:
        return "".join([line async for line in service.run_build(str(profile_cfg), "p")])

    log = asyncio.run(collect())

    assert "compiling firmware..." in log
    assert "BUILD OK" in log
    assert (Path(firmware_profiles.artifacts_dir(str(data))) / "p.bin").is_file()
    # The artifact now marks the profile as built.
    assert firmware_profiles.profile_is_built(str(data), "p") is True


def test_build_env_augments_path_with_standard_dirs(monkeypatch: Any) -> None:
    """The build/flash subprocess PATH must include the standard toolchain dirs even when the
    service started with a minimal PATH - the real cause of #558 (make installed in /usr/bin but
    /usr/bin absent from the backend's PATH)."""
    from app.services import build_tools

    monkeypatch.setenv("PATH", "/opt/custom/bin")
    parts = build_tools.build_env()["PATH"].split(os.pathsep)
    assert "/opt/custom/bin" in parts  # keeps the existing PATH entries
    for d in ("/usr/local/bin", "/usr/bin", "/usr/sbin", "/bin", "/sbin"):
        assert d in parts  # adds every standard toolchain dir
    assert parts.count("/usr/bin") == 1  # de-duplicated

    # Even a wholly empty PATH still yields the standard dirs.
    monkeypatch.setenv("PATH", "")
    assert "/usr/bin" in build_tools.build_env()["PATH"].split(os.pathsep)


class _FakeStdout:
    def __init__(self, lines: list[bytes]) -> None:
        self._lines = list(lines)

    async def readline(self) -> bytes:
        return self._lines.pop(0) if self._lines else b""


class _FakeProc:
    def __init__(self) -> None:
        self.stdout = _FakeStdout([b"ok\n"])

    async def wait(self) -> int:
        return 0

    def kill(self) -> None:  # pragma: no cover - only hit on a timeout
        pass


def test_build_stream_spawns_with_augmented_path(tmp_path: Path, monkeypatch: Any) -> None:
    """build_service runs its commands with the augmented PATH, so `make` (and the compilers it
    invokes) resolve regardless of the service's own PATH."""
    service = BuildService(str(tmp_path), str(tmp_path / "data"))
    seen: dict[str, Any] = {}

    async def fake_exec(*_args: Any, **kwargs: Any) -> _FakeProc:
        seen["env"] = kwargs.get("env")
        return _FakeProc()

    monkeypatch.setattr("app.services.build_service.asyncio.create_subprocess_exec", fake_exec)

    async def run() -> None:
        async for _ in service._stream(["make", "clean"]):
            pass

    asyncio.run(run())
    assert seen["env"] is not None
    assert "/usr/bin" in seen["env"]["PATH"].split(os.pathsep)


def test_build_missing_makefile_reports_error(tmp_path: Path) -> None:
    service = BuildService(str(tmp_path / "no-klipper"), str(tmp_path / "data"))

    async def collect() -> str:
        return "".join([line async for line in service.run_build(str(tmp_path / "x.config"), "x")])

    assert "Makefile not found" in asyncio.run(collect())


def test_build_without_make_fails_early_with_actionable_message(
    tmp_path: Path, monkeypatch: Any
) -> None:
    """A host set up without the build tools has no `make`; the build must fail early with an
    install-these message, not run three doomed `make` commands (issue #558)."""
    klipper = tmp_path / "klipper"
    klipper.mkdir()
    (klipper / "Makefile").write_text("# fake makefile\n")
    profile_cfg = tmp_path / "p.config"
    profile_cfg.write_text("CONFIG_DEMO=y\n")
    # build_command=None -> the real `make` path; pretend `make` is absent from PATH.
    monkeypatch.setattr("app.services.build_service.make_available", lambda: False)
    service = BuildService(str(klipper), str(tmp_path / "data"))

    async def collect() -> str:
        return "".join([line async for line in service.run_build(str(profile_cfg), "p")])

    log = asyncio.run(collect())
    assert "build tools aren't installed" in log
    # points the user at the auto-update flow, not at manual shell commands
    assert "Update FilaMind" in log
    assert "sudo apt" not in log
    assert "BUILD FAILED" in log
    # no artifact was produced / staged, and it did not claim success
    assert "BUILD OK" not in log


def test_build_endpoint_unknown_profile_404(tmp_path: Path) -> None:
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: Settings(
        klipper_dir=str(tmp_path / "klipper"),
        data_dir=str(tmp_path / "data"),
    )
    client = TestClient(app)

    assert client.get("/api/firmware/build/ghost").status_code == 404
