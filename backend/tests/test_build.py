from __future__ import annotations

import asyncio
import sys
from pathlib import Path

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


def test_build_missing_makefile_reports_error(tmp_path: Path) -> None:
    service = BuildService(str(tmp_path / "no-klipper"), str(tmp_path / "data"))

    async def collect() -> str:
        return "".join([line async for line in service.run_build(str(tmp_path / "x.config"), "x")])

    assert "Makefile not found" in asyncio.run(collect())


def test_build_endpoint_unknown_profile_404(tmp_path: Path) -> None:
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: Settings(
        klipper_dir=str(tmp_path / "klipper"),
        data_dir=str(tmp_path / "data"),
    )
    client = TestClient(app)

    assert client.get("/api/firmware/build/ghost").status_code == 404
