from __future__ import annotations

import os
from pathlib import Path

from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.main import create_app
from app.services import flash_service
from app.services.firmware_profiles import artifacts_dir, profiles_dir

_FLASHTOOL = os.path.join("/kat", "scripts", "flashtool.py")


def test_command_builders() -> None:
    assert flash_service.serial_command("/kat", "/dev/ttyACM0", "fw.bin", 250000) == [
        "python3",
        _FLASHTOOL,
        "-f",
        "fw.bin",
        "-d",
        "/dev/ttyACM0",
        "-b",
        "250000",
    ]
    assert flash_service.can_command("/kat", "can0", "aabbccddeeff", "fw.bin") == [
        "python3",
        _FLASHTOOL,
        "-i",
        "can0",
        "-u",
        "aabbccddeeff",
        "-f",
        "fw.bin",
    ]
    dfu = flash_service.dfu_command("fw.bin", "0x08002000", "357236543131")
    assert dfu[:3] == ["sudo", "-n", "dfu-util"]
    assert "0x08002000" in dfu and "357236543131" in dfu
    assert flash_service.make_flash_command("/dev/ttyUSB0") == [
        "make",
        "flash",
        "FLASH_DEVICE=/dev/ttyUSB0",
    ]


def test_method_for_and_offset(tmp_path: Path) -> None:
    assert flash_service.method_for("usb", False) == "serial"
    assert flash_service.method_for("can", False) == "can"
    assert flash_service.method_for("usb", True) == "make"
    cfg = tmp_path / "p.config"
    cfg.write_text("CONFIG_STM32_FLASH_START_8000=y\n")
    assert flash_service.flash_offset(str(cfg)) == "0x08008000"
    assert flash_service.flash_offset(str(tmp_path / "missing.config")) == "0x08000000"


def _client(tmp_path: Path) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: Settings(
        moonraker_url="http://127.0.0.1:1",
        katapult_dir="/kat",
        klipper_dir=str(tmp_path / "klipper"),
        data_dir=str(tmp_path / "data"),
    )
    return TestClient(app)


def test_flash_plan_needs_a_build(tmp_path: Path) -> None:
    plan = _client(tmp_path).post(
        "/api/firmware/flash-plan",
        json={"profile": "p", "method": "serial", "device": "/dev/ttyACM0"},
    )
    body = plan.json()
    assert body["artifact_exists"] is False
    assert body["ready"] is False
    assert any("built" in w for w in body["warnings"])


def test_flash_plan_with_artifact(tmp_path: Path) -> None:
    data = tmp_path / "data"
    Path(artifacts_dir(str(data)), "p.bin").write_bytes(b"\x00")
    Path(profiles_dir(str(data)), "p.config").write_text("CONFIG_X=y\n")

    body = (
        _client(tmp_path)
        .post(
            "/api/firmware/flash-plan",
            json={"profile": "p", "method": "serial", "device": "/dev/ttyACM0"},
        )
        .json()
    )
    assert body["artifact_exists"] is True
    assert body["artifact"] == "p.bin"
    assert "flashtool.py" in body["command"]
    assert body["printing"] is False


def test_flash_refused_without_artifact(tmp_path: Path) -> None:
    resp = _client(tmp_path).post(
        "/api/firmware/flash",
        json={"profile": "ghost", "method": "serial", "device": "/dev/ttyACM0"},
    )
    assert resp.status_code == 200
    assert "No firmware file to flash" in resp.text


async def test_flash_skips_reboot_when_not_katapult(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    data = tmp_path / "data"
    Path(artifacts_dir(str(data)), "p.bin").write_bytes(b"\x00")
    Path(profiles_dir(str(data)), "p.config").write_text("CONFIG_X=y\n")
    settings = Settings(
        moonraker_url="http://127.0.0.1:1",
        katapult_dir="/kat",
        klipper_dir=str(tmp_path / "klipper"),
        data_dir=str(data),
    )

    async def no_print(_url: str) -> bool:
        return False

    async def sudo_ok() -> bool:
        return True

    async def fast_sleep(*_a: object, **_k: object) -> None:
        return None

    monkeypatch.setattr(flash_service, "_is_printing", no_print)
    monkeypatch.setattr(flash_service, "_sudo_ready", sudo_ok)
    monkeypatch.setattr(flash_service.asyncio, "sleep", fast_sleep)

    async def run(is_katapult: bool) -> str:
        out = ""
        async for line in flash_service.run_flash(
            "p", "serial", "/dev/ttyACM0", "can0", settings, is_katapult
        ):
            out += line
        return out

    off = await run(is_katapult=False)
    assert "skipping reboot-to-bootloader" in off
    assert "enter its bootloader" not in off

    on = await run(is_katapult=True)
    assert "enter its bootloader" in on


def test_bootloader_serial_path(monkeypatch) -> None:
    """A board in the Katapult bootloader is found under usb-katapult_<id>, not usb-Klipper_<id>."""
    kl = "/dev/serial/by-id/usb-Klipper_stm32f103xe_36FFD8054755303931861457-if00"
    kat = "/dev/serial/by-id/usb-katapult_stm32f103xe_36FFD8054755303931861457-if00"
    # Board sitting in the bootloader: the katapult endpoint exists -> return it.
    monkeypatch.setattr(flash_service.os.path, "exists", lambda p: p == kat)
    monkeypatch.setattr(flash_service.glob, "glob", lambda pat: [kat])
    assert flash_service.bootloader_serial_path(kl) == kat
    # Board running normally: no katapult endpoint present -> None (flash uses the Klipper path).
    monkeypatch.setattr(flash_service.os.path, "exists", lambda p: False)
    monkeypatch.setattr(flash_service.glob, "glob", lambda pat: [])
    assert flash_service.bootloader_serial_path(kl) is None
    # Not a /dev/serial/by-id device.
    assert flash_service.bootloader_serial_path("/dev/ttyACM0") is None
