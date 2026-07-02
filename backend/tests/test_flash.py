from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.main import create_app
from app.services import build_tools, flash_service
from app.services.firmware_profiles import artifacts_dir, profiles_dir

_FLASHTOOL = os.path.join("/kat", "scripts", "flashtool.py")


@pytest.fixture(autouse=True)
def _pin_flash_python(monkeypatch):  # type: ignore[no-untyped-def]
    """Pin the flasher interpreter to 'python3' for deterministic command tests + no real probing.
    (The real flash_python() picker is covered by its own unit test, which uses build_tools.)"""
    build_tools._FLASH_PYTHON = None
    monkeypatch.setattr(flash_service, "flash_python", lambda: "python3")


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
    # offsets are parsed generically - an uncommon bootloader offset must not silently fall back
    # to the flash base (a DFU write there would overwrite the resident bootloader)
    cfg.write_text("CONFIG_STM32_FLASH_START_C000=y\n")
    assert flash_service.flash_offset(str(cfg)) == "0x0800c000"
    cfg.write_text("CONFIG_FLASH_APPLICATION_ADDRESS=0x08020200\n")
    assert flash_service.flash_offset(str(cfg)) == "0x08020200"
    # Klipper's kconfig writes hex defaults UNPADDED (0x8000000) - the address must canonicalise
    # so the "has a bootloader offset" string comparison can't false-fire on a no-bootloader board
    cfg.write_text("CONFIG_FLASH_APPLICATION_ADDRESS=0x8000000\n")
    assert flash_service.flash_offset(str(cfg)) == "0x08000000"
    cfg.write_text("CONFIG_FLASH_APPLICATION_ADDRESS=0x2000\n")  # short SAMD-style address
    assert flash_service.flash_offset(str(cfg)) == "0x00002000"


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
    assert any(w["code"] == "no_artifact" for w in body["warnings"])


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


async def test_flash_plan_warns_when_make_missing(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """A `make flash` on a host without the build tools is pre-warned + blocked (issue #558)."""
    data = tmp_path / "data"
    Path(artifacts_dir(str(data)), "p.bin").write_bytes(b"\x00")
    Path(profiles_dir(str(data)), "p.config").write_text("CONFIG_X=y\n")

    async def no_print(_url: str) -> bool:
        return False

    async def sudo_ok() -> bool:
        return True

    monkeypatch.setattr(flash_service, "_is_printing", no_print)
    monkeypatch.setattr(flash_service, "_sudo_ready", sudo_ok)
    monkeypatch.setattr(flash_service, "make_available", lambda: False)
    settings = Settings(
        moonraker_url="http://127.0.0.1:1",
        katapult_dir=str(tmp_path / "kat"),
        klipper_dir=str(tmp_path / "klipper"),
        data_dir=str(data),
    )
    plan = await flash_service.flash_plan("p", "make", "usb0", "can0", settings)
    assert any(w["code"] == "build_tools" for w in plan["warnings"])
    assert plan["ready"] is False


async def test_flash_run_aborts_before_stopping_klipper_when_make_missing(
    tmp_path: Path,
    monkeypatch,  # type: ignore[no-untyped-def]
) -> None:
    """The make-flash run must fail early (no systemctl stop klipper) when `make` is absent."""
    data = tmp_path / "data"
    Path(artifacts_dir(str(data)), "p.bin").write_bytes(b"\x00")
    Path(profiles_dir(str(data)), "p.config").write_text("CONFIG_X=y\n")
    calls: list[list[str]] = []

    async def no_print(_url: str) -> bool:
        return False

    async def sudo_ok() -> bool:
        return True

    async def record_stream(cmd, cwd=None, result=None):  # type: ignore[no-untyped-def]
        calls.append(list(cmd))
        if result is not None:
            result["rc"] = 0
        return
        yield ""  # pragma: no cover - makes this an async generator

    monkeypatch.setattr(flash_service, "_is_printing", no_print)
    monkeypatch.setattr(flash_service, "_sudo_ready", sudo_ok)
    monkeypatch.setattr(flash_service, "make_available", lambda: False)
    monkeypatch.setattr(flash_service, "_stream", record_stream)
    settings = Settings(
        moonraker_url="http://127.0.0.1:1",
        katapult_dir=str(tmp_path / "kat"),
        klipper_dir=str(tmp_path / "klipper"),
        data_dir=str(data),
    )
    log = "".join(
        [line async for line in flash_service.run_flash("p", "make", "usb0", "can0", settings)]
    )
    assert "build tools" in log and "Flash aborted" in log
    # crucially, Klipper was never stopped for a doomed flash
    assert not any("stop" in c and "klipper" in c for c in calls)


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

    async def ok_stream(cmd, cwd=None, result=None):  # type: ignore[no-untyped-def]
        if result is not None:
            result["rc"] = 0
        return
        yield ""  # pragma: no cover

    monkeypatch.setattr(flash_service, "_is_printing", no_print)
    monkeypatch.setattr(flash_service, "_sudo_ready", sudo_ok)
    monkeypatch.setattr(flash_service.asyncio, "sleep", fast_sleep)
    monkeypatch.setattr(flash_service, "_stream", ok_stream)
    monkeypatch.setattr(flash_service, "bootloader_serial_path", lambda _d: None)
    monkeypatch.setattr(flash_service.os.path, "exists", lambda _p: True)

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


def test_resolve_method_linux() -> None:
    """A Linux-target profile / the host MCU is installed as a binary, never bus-flashed."""
    # profile builds the Linux target -> force linux regardless of the stored bus method
    assert flash_service.resolve_method("serial", "PI2", is_linux=True) == "linux"
    assert flash_service.resolve_method("can", "PI2", is_linux=True) == "linux"
    # host MCU recognised by discovery id / the klipper_host_mcu socket path
    assert flash_service.resolve_method("serial", "linux_process") == "linux"
    assert flash_service.resolve_method("serial", "/tmp/klipper_host_mcu") == "linux"
    # unchanged: a real serial board, and a USB-CAN bridge given as a /dev path
    assert flash_service.resolve_method("serial", "/dev/ttyACM0") == "serial"
    assert flash_service.resolve_method("can", "/dev/ttyACM0") == "serial"
    assert flash_service.resolve_method("can", "aabbccddeeff") == "can"


async def test_flash_can_does_not_prejump(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """CAN flash lets flashtool ``-f`` enter the node's bootloader itself - no redundant ``-r``
    pre-jump (the double-jump churns the node so the flasher's CONNECT fails)."""
    data = tmp_path / "data"
    Path(artifacts_dir(str(data)), "p.bin").write_bytes(b"\x00")
    Path(profiles_dir(str(data)), "p.config").write_text("CONFIG_X=y\n")
    calls: list[list[str]] = []

    async def no_print(_url: str) -> bool:
        return False

    async def sudo_ok() -> bool:
        return True

    async def fast_sleep(*_a: object, **_k: object) -> None:
        return None

    async def record_stream(cmd, cwd=None, result=None):  # type: ignore[no-untyped-def]
        calls.append(list(cmd))
        if result is not None:
            result["rc"] = 0
        return
        yield ""  # pragma: no cover - makes this an async generator

    monkeypatch.setattr(flash_service, "_is_printing", no_print)
    monkeypatch.setattr(flash_service, "_sudo_ready", sudo_ok)
    monkeypatch.setattr(flash_service.asyncio, "sleep", fast_sleep)
    monkeypatch.setattr(flash_service, "_stream", record_stream)
    settings = Settings(
        moonraker_url="http://127.0.0.1:1",
        katapult_dir="/kat",
        klipper_dir=str(tmp_path / "klipper"),
        data_dir=str(data),
    )
    log = "".join(
        [
            line
            async for line in flash_service.run_flash(
                "p", "can", "aabbccddeeff", "can0", settings, is_katapult=True
            )
        ]
    )
    assert "no pre-reboot needed" in log
    assert "enter its bootloader" not in log
    # the flash itself is the single flashtool -u <uuid> -f invocation ...
    assert any("-u" in c and "aabbccddeeff" in c and "-f" in c for c in calls)
    # ... and no separate -r pre-jump command ran
    assert not any("-r" in c for c in calls)


async def test_flash_linux_profile_installs_binary(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """A profile building the Linux target is installed as the klipper_mcu binary even when the
    device was registered with a serial method (the ``[mcu PI2]`` host-process case)."""
    data = tmp_path / "data"
    Path(artifacts_dir(str(data)), "PI2.elf").write_bytes(b"\x7fELF")
    Path(profiles_dir(str(data)), "PI2.config").write_text("CONFIG_MACH_LINUX=y\n")
    calls: list[list[str]] = []

    async def no_print(_url: str) -> bool:
        return False

    async def sudo_ok() -> bool:
        return True

    async def fast_sleep(*_a: object, **_k: object) -> None:
        return None

    async def record_stream(cmd, cwd=None, result=None):  # type: ignore[no-untyped-def]
        calls.append(list(cmd))
        if result is not None:
            result["rc"] = 0
        return
        yield ""  # pragma: no cover - makes this an async generator

    async def service_up(_name: str) -> bool:
        return True

    monkeypatch.setattr(flash_service, "_is_printing", no_print)
    monkeypatch.setattr(flash_service, "_sudo_ready", sudo_ok)
    monkeypatch.setattr(flash_service.asyncio, "sleep", fast_sleep)
    monkeypatch.setattr(flash_service, "_stream", record_stream)
    monkeypatch.setattr(flash_service, "_service_active", service_up)
    settings = Settings(
        moonraker_url="http://127.0.0.1:1",
        katapult_dir="/kat",
        klipper_dir=str(tmp_path / "klipper"),
        data_dir=str(data),
    )
    log = "".join(
        [line async for line in flash_service.run_flash("PI2", "serial", "PI2", "can0", settings)]
    )
    assert "host MCU reinstalled" in log
    # installed as the klipper_mcu binary, never handed to a serial flashtool
    assert any("/usr/local/bin/klipper_mcu" in c for c in calls)
    assert not any("flashtool.py" in " ".join(c) for c in calls)


async def test_flash_can_retries_and_lowers_txqueuelen(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """CAN flash lowers txqueuelen to 128 for the write, retries a transient failure, then restores
    the original txqueuelen (the SEND_BLOCK-under-bufferbloat fix)."""
    data = tmp_path / "data"
    Path(artifacts_dir(str(data)), "p.bin").write_bytes(b"\x00")
    Path(profiles_dir(str(data)), "p.config").write_text("CONFIG_X=y\n")
    calls: list[list[str]] = []
    set_calls: list[str] = []
    flash_n = {"n": 0}

    async def no_print(_url: str) -> bool:
        return False

    async def sudo_ok() -> bool:
        return True

    async def fast_sleep(*_a: object, **_k: object) -> None:
        return None

    async def qlen(_iface: str) -> str:
        return "1024"

    async def set_q(_iface: str, value: str) -> None:
        set_calls.append(value)

    async def record_stream(cmd, cwd=None, result=None):  # type: ignore[no-untyped-def]
        calls.append(list(cmd))
        if result is not None:
            if any("flashtool.py" in c for c in cmd):
                flash_n["n"] += 1
                result["rc"] = 0 if flash_n["n"] >= 2 else 1
            else:
                result["rc"] = 0
        return
        yield ""  # pragma: no cover

    monkeypatch.setattr(flash_service, "_is_printing", no_print)
    monkeypatch.setattr(flash_service, "_sudo_ready", sudo_ok)
    monkeypatch.setattr(flash_service.asyncio, "sleep", fast_sleep)
    monkeypatch.setattr(flash_service, "_stream", record_stream)
    monkeypatch.setattr(flash_service, "_can_txqueuelen", qlen)
    monkeypatch.setattr(flash_service, "_set_txqueuelen", set_q)
    settings = Settings(
        moonraker_url="http://127.0.0.1:1",
        katapult_dir="/kat",
        klipper_dir=str(tmp_path / "klipper"),
        data_dir=str(data),
    )
    log = "".join(
        [
            line
            async for line in flash_service.run_flash(
                "p", "can", "aabbccddeeff", "can0", settings, is_katapult=True
            )
        ]
    )
    assert set_calls == ["128", "1024"]  # lowered for the flash, restored after
    flash_runs = [c for c in calls if any("flashtool.py" in x for x in c)]
    assert len(flash_runs) == 2  # transient first failure retried, second succeeded
    assert "retrying" in log
    assert "Flash sequence complete" in log


async def test_flash_can_fails_after_retry_budget(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """Every CAN attempt failing gives up after the retry budget and reports failure."""
    data = tmp_path / "data"
    Path(artifacts_dir(str(data)), "p.bin").write_bytes(b"\x00")
    Path(profiles_dir(str(data)), "p.config").write_text("CONFIG_X=y\n")
    calls: list[list[str]] = []

    async def no_print(_url: str) -> bool:
        return False

    async def sudo_ok() -> bool:
        return True

    async def fast_sleep(*_a: object, **_k: object) -> None:
        return None

    async def qlen(_iface: str) -> str:
        return "128"  # already 128 -> no lower/restore

    async def record_stream(cmd, cwd=None, result=None):  # type: ignore[no-untyped-def]
        calls.append(list(cmd))
        if result is not None:
            result["rc"] = 1 if any("flashtool.py" in c for c in cmd) else 0
        return
        yield ""  # pragma: no cover

    monkeypatch.setattr(flash_service, "_is_printing", no_print)
    monkeypatch.setattr(flash_service, "_sudo_ready", sudo_ok)
    monkeypatch.setattr(flash_service.asyncio, "sleep", fast_sleep)
    monkeypatch.setattr(flash_service, "_stream", record_stream)
    monkeypatch.setattr(flash_service, "_can_txqueuelen", qlen)
    settings = Settings(
        moonraker_url="http://127.0.0.1:1",
        katapult_dir="/kat",
        klipper_dir=str(tmp_path / "klipper"),
        data_dir=str(data),
    )
    log = "".join(
        [
            line
            async for line in flash_service.run_flash(
                "p", "can", "aabbccddeeff", "can0", settings, is_katapult=True
            )
        ]
    )
    flash_runs = [c for c in calls if any("flashtool.py" in x for x in c)]
    assert len(flash_runs) == flash_service._CAN_FLASH_ATTEMPTS
    assert "Flash failed" in log


async def test_flash_linux_autofixes_blocked_realtime(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """When klipper-mcu can't start because the kernel blocks realtime (-r crash-loop), the flash
    drops -r via a drop-in automatically - no manual unit edit - and brings the service up."""
    data = tmp_path / "data"
    Path(artifacts_dir(str(data)), "PI2.elf").write_bytes(b"\x7fELF")
    Path(profiles_dir(str(data)), "PI2.config").write_text("CONFIG_MACH_LINUX=y\n")
    calls: list[list[str]] = []
    state = {"restarted": False}

    async def no_print(_url: str) -> bool:
        return False

    async def sudo_ok() -> bool:
        return True

    async def fast_sleep(*_a: object, **_k: object) -> None:
        return None

    async def record_stream(cmd, cwd=None, result=None):  # type: ignore[no-untyped-def]
        calls.append(list(cmd))
        if "restart" in cmd and "klipper-mcu" in cmd:
            state["restarted"] = True
        if result is not None:
            result["rc"] = 0
        return
        yield ""  # pragma: no cover

    async def blocked() -> bool:
        return True

    async def active(_name: str) -> bool:
        return state["restarted"]

    monkeypatch.setattr(flash_service, "_is_printing", no_print)
    monkeypatch.setattr(flash_service, "_sudo_ready", sudo_ok)
    monkeypatch.setattr(flash_service.asyncio, "sleep", fast_sleep)
    monkeypatch.setattr(flash_service, "_stream", record_stream)
    monkeypatch.setattr(flash_service, "_mcu_realtime_blocked", blocked)
    monkeypatch.setattr(flash_service, "_service_active", active)
    settings = Settings(
        moonraker_url="http://127.0.0.1:1",
        katapult_dir="/kat",
        klipper_dir=str(tmp_path / "klipper"),
        data_dir=str(data),
    )
    log = "".join(
        [line async for line in flash_service.run_flash("PI2", "serial", "PI2", "can0", settings)]
    )
    assert "without -r" in log
    assert "realtime disabled" in log
    # a drop-in was created + the service restarted, all via granted sudo
    assert any("mkdir" in c and flash_service._MCU_DROPIN_DIR in c for c in calls)
    assert any("cp" in c and flash_service._MCU_DROPIN in c for c in calls)
    assert any(
        c[:4] == ["sudo", "-n", "systemctl", "restart"] and "klipper-mcu" in c for c in calls
    )


async def test_make_flash_cwd_is_resolved(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """`make flash` runs in the RESOLVED (absolute) klipper dir, never a literal '~/klipper' that a
    subprocess cwd can't chdir into - the cause of the cryptic 'cannot run make' on AVR (#565)."""
    data = tmp_path / "data"
    Path(artifacts_dir(str(data)), "p.bin").write_bytes(b"\x00")
    Path(profiles_dir(str(data)), "p.config").write_text("CONFIG_MACH_AVR=y\n")
    seen: dict[str, object] = {}

    async def no_print(_url: str) -> bool:
        return False

    async def sudo_ok() -> bool:
        return True

    async def fast_sleep(*_a: object, **_k: object) -> None:
        return None

    async def record_stream(cmd, cwd=None, result=None):  # type: ignore[no-untyped-def]
        if cmd and cmd[0] == "make" and "flash" in cmd:
            seen["cwd"] = cwd
        if result is not None:
            result["rc"] = 0
        return
        yield ""  # pragma: no cover

    monkeypatch.setattr(flash_service, "_is_printing", no_print)
    monkeypatch.setattr(flash_service, "_sudo_ready", sudo_ok)
    monkeypatch.setattr(flash_service, "make_available", lambda: True)
    monkeypatch.setattr(flash_service.asyncio, "sleep", fast_sleep)
    monkeypatch.setattr(flash_service, "_stream", record_stream)
    monkeypatch.setattr(flash_service.os.path, "exists", lambda _p: True)  # device is present
    monkeypatch.setattr(flash_service.shutil, "copy", lambda *_a, **_k: None)  # staging no-op
    settings = Settings(
        moonraker_url="http://127.0.0.1:1",
        katapult_dir="/kat",
        klipper_dir="~/klipper",  # tilde form - must be resolved before it reaches the subprocess
        data_dir=str(data),
    )
    # klipper_dir is resolved at the config layer, so no '~' survives to any consumer
    assert os.path.isabs(settings.klipper_dir) and "~" not in settings.klipper_dir
    async for _line in flash_service.run_flash("p", "make", "/dev/ttyUSB0", "can0", settings):
        pass
    assert seen.get("cwd") is not None
    assert os.path.isabs(str(seen["cwd"])) and "~" not in str(seen["cwd"])


def test_arch_mismatch_guard() -> None:
    """The AVR-vs-non-AVR-board guard fires only on a certain conflict + fails open (#567)."""
    rp = "/dev/serial/by-id/usb-Klipper_rp2040_34343433391347D6-if00"
    stm = "/dev/serial/by-id/usb-Klipper_stm32h723xx_12001F00-if00"
    # AVR firmware aimed at a non-AVR board -> certain conflict
    assert flash_service.arch_mismatch(True, rp, "make") == ("AVR", "rp2040")
    assert flash_service.arch_mismatch(True, stm, "make") == ("AVR", "stm32")
    # genuine ATmega boards enumerate token-less (ttyUSB/ttyACM) -> MUST NOT block
    assert flash_service.arch_mismatch(True, "/dev/ttyUSB0", "make") is None
    assert flash_service.arch_mismatch(True, "/dev/ttyACM0", "make") is None
    # not a make flash / not an AVR build -> never fires
    assert flash_service.arch_mismatch(False, rp, "make") is None
    assert flash_service.arch_mismatch(True, rp, "serial") is None
    # CAN uuid / DFU vid:pid / linux socket carry no by-id chip token -> fail open
    assert flash_service.arch_mismatch(True, "aabbccddeeff", "make") is None
    assert flash_service.arch_mismatch(True, "0483:df11", "make") is None
    assert flash_service.arch_mismatch(True, "linux_process", "make") is None
    assert flash_service.device_chip_token(rp) == "rp2040"
    assert flash_service.device_chip_token("/dev/ttyUSB0") is None
    # real ATmega boards enumerate through a USB-serial bridge (no Klipper chip token) -> fail open,
    # and the token is anchored to the Klipper prefix so a bridge name can't collide
    by_id = "/dev/serial/by-id/"
    assert flash_service.device_chip_token(by_id + "usb-1a86_USB_Serial-if00-port0") is None
    assert flash_service.device_chip_token(by_id + "usb-FTDI_FT232R_USB_UART_A5-if00-port0") is None


async def test_flash_refuses_avr_firmware_on_non_avr_board(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """An AVR profile aimed at an rp2040 is refused up front with an actionable message, and the
    board is never touched (Klipper is not stopped) - the #567 fix."""
    data = tmp_path / "data"
    Path(artifacts_dir(str(data)), "nite.bin").write_bytes(b"\x00")
    Path(profiles_dir(str(data)), "nite.config").write_text("CONFIG_MACH_AVR=y\n")
    calls: list[list[str]] = []

    async def no_print(_url: str) -> bool:
        return False

    async def sudo_ok() -> bool:
        return True

    async def record_stream(cmd, cwd=None, result=None):  # type: ignore[no-untyped-def]
        calls.append(list(cmd))
        if result is not None:
            result["rc"] = 0
        return
        yield ""  # pragma: no cover

    monkeypatch.setattr(flash_service, "_is_printing", no_print)
    monkeypatch.setattr(flash_service, "_sudo_ready", sudo_ok)
    monkeypatch.setattr(flash_service, "make_available", lambda: True)
    monkeypatch.setattr(flash_service, "_stream", record_stream)
    settings = Settings(
        moonraker_url="http://127.0.0.1:1",
        katapult_dir="/kat",
        klipper_dir=str(tmp_path / "klipper"),
        data_dir=str(data),
    )
    dev = "/dev/serial/by-id/usb-Klipper_rp2040_34343433391347D6-if00"
    log = "".join(
        [line async for line in flash_service.run_flash("nite", "make", dev, "can0", settings)]
    )
    assert "rp2040" in log and "avrdude" in log
    # refused BEFORE touching the board: Klipper was never stopped
    assert not any("stop" in c and "klipper" in c for c in calls)


async def test_flash_plan_blocks_arch_mismatch(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """flash_plan flags the mismatch as a blocking coded warning that survives the FlashPlan
    response_model round-trip (per the response-model-strips-undeclared-fields lesson)."""
    from app.models.schemas import FlashPlan

    data = tmp_path / "data"
    Path(artifacts_dir(str(data)), "nite.bin").write_bytes(b"\x00")
    Path(profiles_dir(str(data)), "nite.config").write_text("CONFIG_MACH_AVR=y\n")

    async def no_print(_url: str) -> bool:
        return False

    async def sudo_ok() -> bool:
        return True

    monkeypatch.setattr(flash_service, "_is_printing", no_print)
    monkeypatch.setattr(flash_service, "_sudo_ready", sudo_ok)
    monkeypatch.setattr(flash_service, "make_available", lambda: True)
    settings = Settings(
        moonraker_url="http://127.0.0.1:1",
        katapult_dir="/kat",
        klipper_dir=str(tmp_path / "klipper"),
        data_dir=str(data),
    )
    dev = "/dev/serial/by-id/usb-Klipper_rp2040_34343433391347D6-if00"
    plan = await flash_service.flash_plan("nite", "make", dev, "can0", settings)
    warn = next(w for w in plan["warnings"] if w["code"] == "arch_mismatch")
    assert warn["params"] == {"firmware": "AVR", "chip": "rp2040"}
    assert plan["ready"] is False
    round_trip = FlashPlan.model_validate(plan).model_dump()
    assert any(w["code"] == "arch_mismatch" for w in round_trip["warnings"])


def test_flash_python_prefers_first_pyserial_capable(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """flash_python() picks the first interpreter that has pyserial, caches it, and falls back to
    'python3' when none qualify - so the flasher never runs under a serial-less python (#569)."""
    monkeypatch.delenv("FILAMIND_FLASH_PYTHON", raising=False)
    build_tools._FLASH_PYTHON = None
    klippy = os.path.expanduser("~/klippy-env/bin/python")
    # only klippy-env has pyserial in this scenario (sys.executable is probed first, fails)
    monkeypatch.setattr(build_tools, "_has_pyserial", lambda p: p == klippy)
    assert build_tools.flash_python() == klippy
    # cached: a later probe flip does not change the resolved interpreter
    monkeypatch.setattr(build_tools, "_has_pyserial", lambda _p: False)
    assert build_tools.flash_python() == klippy
    # fresh probe, nothing capable -> fall back to 'python3' WITHOUT caching, so a transient probe
    # timeout on a busy host is retried on the next flash rather than frozen for the process life.
    build_tools._FLASH_PYTHON = None
    assert build_tools.flash_python() == "python3"
    assert build_tools._FLASH_PYTHON is None


def test_diagnose_serial_failure() -> None:
    """A failed serial/CAN flash is explained from its output tail, not a bare exit code (#569)."""
    d = flash_service._diagnose_serial_failure
    assert any("pyserial" in ln.lower() for ln in d(["No module named 'serial'"], "/dev/x"))
    assert any(
        "port" in ln.lower() for ln in d(["Could not open port /dev/ttyACM0"], "/dev/ttyACM0")
    )
    assert any("bootloader" in ln.lower() for ln in d(["No Serial Device found"], "/dev/x"))
    assert any("cable" in ln.lower() for ln in d(["Checksum mismatch at 0x1000"], "/dev/x"))
    # never invents a diagnosis on a clean/unknown tail
    assert d(["Programming Complete", "success"], "/dev/x") == []


async def test_flash_serial_surfaces_pyserial_error(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """When flashtool fails because its python lacks pyserial, the real cause is surfaced (not just
    'python3 exited with code 1'). The interpreter-picker fix + this diagnosis close #569."""
    data = tmp_path / "data"
    Path(artifacts_dir(str(data)), "p.bin").write_bytes(b"\x00")
    Path(profiles_dir(str(data)), "p.config").write_text("CONFIG_X=y\n")

    async def no_print(_url: str) -> bool:
        return False

    async def sudo_ok() -> bool:
        return True

    async def fast_sleep(*_a: object, **_k: object) -> None:
        return None

    async def rec(cmd, cwd=None, result=None):  # type: ignore[no-untyped-def]
        if "-f" in cmd:  # the flashtool flash command fails on a missing pyserial
            yield "ModuleNotFoundError: No module named 'serial'\n"
            if result is not None:
                result["rc"] = 1
            return
        if result is not None:
            result["rc"] = 0
        return

    monkeypatch.setattr(flash_service, "_is_printing", no_print)
    monkeypatch.setattr(flash_service, "_sudo_ready", sudo_ok)
    monkeypatch.setattr(flash_service.asyncio, "sleep", fast_sleep)
    monkeypatch.setattr(flash_service, "_stream", rec)
    monkeypatch.setattr(flash_service, "bootloader_serial_path", lambda _d: None)
    monkeypatch.setattr(flash_service.os.path, "exists", lambda _p: True)
    settings = Settings(
        moonraker_url="http://127.0.0.1:1",
        katapult_dir="/kat",
        klipper_dir=str(tmp_path / "klipper"),
        data_dir=str(data),
    )
    log = "".join(
        [
            line
            async for line in flash_service.run_flash(
                "p", "serial", "/dev/ttyACM0", "can0", settings, is_katapult=True
            )
        ]
    )
    assert "pyserial" in log.lower()  # the real cause is surfaced
    assert "exited with code 1" in log  # the generic line still follows


def _flash_env(tmp_path: Path, monkeypatch, profile: str = "p", config: str = "CONFIG_X=y\n"):  # type: ignore[no-untyped-def]
    """Shared run_flash test scaffolding: artifact+profile on disk, guards mocked, call recorder."""
    data = tmp_path / "data"
    Path(artifacts_dir(str(data)), f"{profile}.bin").write_bytes(b"\x00")
    Path(profiles_dir(str(data)), f"{profile}.config").write_text(config)
    calls: list[list[str]] = []

    async def no_print(_url: str) -> bool:
        return False

    async def sudo_ok() -> bool:
        return True

    async def fast_sleep(*_a: object, **_k: object) -> None:
        return None

    monkeypatch.setattr(flash_service, "_is_printing", no_print)
    monkeypatch.setattr(flash_service, "_sudo_ready", sudo_ok)
    monkeypatch.setattr(flash_service.asyncio, "sleep", fast_sleep)
    settings = Settings(
        moonraker_url="http://127.0.0.1:1",
        katapult_dir="/kat",
        klipper_dir=str(tmp_path / "klipper"),
        data_dir=str(data),
    )
    return settings, calls


async def test_flash_dfu_failure_is_reported(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """A DFU flash whose every dfu-util attempt fails is reported as FAILED (not recorded as a
    success), no ':leave' runs (the board stays parked in DFU), and a diagnosis is shown."""
    settings, calls = _flash_env(tmp_path, monkeypatch)

    async def dfu_present() -> bool:
        return True

    async def rec(cmd, cwd=None, result=None):  # type: ignore[no-untyped-def]
        calls.append(list(cmd))
        if "dfu-util" in cmd and "-D" in cmd:
            yield "dfu-util: No DFU capable USB device available\n"
            if result is not None:
                result["rc"] = 74
            return
        if result is not None:
            result["rc"] = 0
        return

    monkeypatch.setattr(flash_service, "_dfu_device_present", dfu_present)
    monkeypatch.setattr(flash_service, "_stream", rec)
    recorded: list[str] = []
    monkeypatch.setattr(flash_service, "record_flash", lambda *a, **k: recorded.append("x"))
    log = "".join(
        [line async for line in flash_service.run_flash("p", "dfu", "0483:df11", "", settings)]
    )
    assert "Flash failed - dfu-util exited" in log
    assert "leaving the board in DFU" in log
    # the early guard passed (Klipper was stopped for a real attempt); the WRITE failed
    assert any("stop" in c and "klipper" in c for c in calls)
    assert "Flash sequence complete" not in log
    assert recorded == []  # a failed flash must never be recorded
    assert not any(":leave" in " ".join(c) for c in calls)  # no boot of a half-written app


async def test_flash_dfu_refused_when_no_device(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """A DFU flash with no 0483:df11 device on USB is refused before Klipper is stopped."""
    settings, calls = _flash_env(tmp_path, monkeypatch)

    async def dfu_absent() -> bool:
        return False

    async def rec(cmd, cwd=None, result=None):  # type: ignore[no-untyped-def]
        calls.append(list(cmd))
        if result is not None:
            result["rc"] = 0
        return
        yield ""  # pragma: no cover

    monkeypatch.setattr(flash_service, "_dfu_device_present", dfu_absent)
    monkeypatch.setattr(flash_service, "_stream", rec)
    log = "".join(
        [line async for line in flash_service.run_flash("p", "dfu", "0483:df11", "", settings)]
    )
    assert "No board in DFU mode" in log
    assert not any("stop" in c and "klipper" in c for c in calls)


def _dfu_appears_after_reboot():  # type: ignore[no-untyped-def]
    """A DFU-presence mock that is False before the reboot (the already-in-DFU pre-check and the
    pre-reboot snapshot), True afterwards - i.e. the DFU device NEWLY appeared because of our
    reboot request (it is our board)."""
    state = {"n": 0}

    async def dfu_present() -> bool:
        state["n"] += 1
        return state["n"] > 2

    return dfu_present


async def test_serial_reboot_falls_back_to_dfu(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """A non-Katapult native-USB board that lands in ROM DFU after the bootloader request is
    flashed via DFU at the profile offset instead of failing against the vanished serial path."""
    settings, calls = _flash_env(tmp_path, monkeypatch)

    async def rec(cmd, cwd=None, result=None):  # type: ignore[no-untyped-def]
        calls.append(list(cmd))
        if "dfu-util" in cmd and "-D" in cmd:
            yield "File downloaded successfully\n"
        if result is not None:
            result["rc"] = 0
        return

    monkeypatch.setattr(flash_service, "_dfu_device_present", _dfu_appears_after_reboot())
    monkeypatch.setattr(flash_service, "_stream", rec)
    monkeypatch.setattr(flash_service, "bootloader_serial_path", lambda _d: None)
    monkeypatch.setattr(flash_service.os.path, "exists", lambda _p: False)  # serial path vanished
    dev = "/dev/serial/by-id/usb-Klipper_stm32h723xx_12001F00-if00"
    log = "".join(
        [
            line
            async for line in flash_service.run_flash(
                "p", "serial", dev, "can0", settings, is_katapult=True
            )
        ]
    )
    assert "ROM DFU instead of Katapult" in log
    assert "Flash sequence complete" in log
    assert any("dfu-util" in c and "-D" in c for c in calls)  # the write really went via DFU


async def test_no_dfu_fallback_for_stray_dfu_device(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """A HEALTHY board is flashed while some other STM32 sits parked in DFU on the same host: the
    stray was present BEFORE our reboot request, so it must never receive this firmware - the
    fallback fires only on a newly-appeared DFU device."""
    settings, calls = _flash_env(tmp_path, monkeypatch)
    state = {"rebooted": False}

    async def dfu_always_there() -> bool:  # a stray STM32 parked in DFU the whole time
        return True

    async def rec(cmd, cwd=None, result=None):  # type: ignore[no-untyped-def]
        calls.append(list(cmd))
        if "-r" in cmd:  # the reboot-to-bootloader request: the healthy board's port now renames
            state["rebooted"] = True
        if result is not None:
            result["rc"] = 0
        return
        yield ""  # pragma: no cover

    monkeypatch.setattr(flash_service, "_dfu_device_present", dfu_always_there)
    monkeypatch.setattr(flash_service, "_stream", rec)
    monkeypatch.setattr(flash_service, "bootloader_serial_path", lambda _d: None)
    # the target's port is alive until the reboot request, then vanishes (normal transition)
    monkeypatch.setattr(flash_service.os.path, "exists", lambda _p: not state["rebooted"])
    dev = "/dev/serial/by-id/usb-Klipper_stm32h723xx_12001F00-if00"
    log = "".join(
        [
            line
            async for line in flash_service.run_flash(
                "p", "serial", dev, "can0", settings, is_katapult=True
            )
        ]
    )
    assert "Flash aborted - nothing was written" in log
    # crucially: no DFU download ever ran against the stray device
    assert not any("dfu-util" in c and "-D" in c for c in calls)


async def test_dfu_fallback_flashes_at_the_profile_offset(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """A stock-bootloader board (e.g. an Octopus: app linked at 0x08008000, vendor bootloader at
    the base) that lands in ROM DFU is flashed at its linked offset - the standard way such boards
    are flashed - with the bootloader region left untouched and a boots-check note."""
    settings, calls = _flash_env(tmp_path, monkeypatch, config="CONFIG_STM32_FLASH_START_8000=y\n")

    async def rec(cmd, cwd=None, result=None):  # type: ignore[no-untyped-def]
        calls.append(list(cmd))
        if "dfu-util" in cmd and "-D" in cmd:
            yield "File downloaded successfully\n"
        if result is not None:
            result["rc"] = 0
        return

    monkeypatch.setattr(flash_service, "_dfu_device_present", _dfu_appears_after_reboot())
    monkeypatch.setattr(flash_service, "_stream", rec)
    monkeypatch.setattr(flash_service, "bootloader_serial_path", lambda _d: None)
    monkeypatch.setattr(flash_service.os.path, "exists", lambda _p: False)
    dev = "/dev/serial/by-id/usb-Klipper_stm32f446xx_38002F00-if00"
    log = "".join(
        [
            line
            async for line in flash_service.run_flash(
                "p", "serial", dev, "can0", settings, is_katapult=True
            )
        ]
    )
    assert "continuing as a DFU flash at 0x08008000" in log
    assert "bootloader region" in log  # the informational note for offset profiles
    assert "Flash sequence complete" in log
    dfu_cmd = next(c for c in calls if "dfu-util" in c and "-D" in c)
    assert "0x08008000" in dfu_cmd  # written at the linked address, not the flash base


async def test_serial_flash_of_board_already_in_dfu(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """A board a previous attempt left parked in ROM DFU (port gone, DFU present at flash start)
    is flashed over DFU directly instead of failing the serial path again."""
    settings, calls = _flash_env(tmp_path, monkeypatch)

    async def dfu_always() -> bool:
        return True

    async def rec(cmd, cwd=None, result=None):  # type: ignore[no-untyped-def]
        calls.append(list(cmd))
        if "dfu-util" in cmd and "-D" in cmd:
            yield "File downloaded successfully\n"
        if result is not None:
            result["rc"] = 0
        return

    monkeypatch.setattr(flash_service, "_dfu_device_present", dfu_always)
    monkeypatch.setattr(flash_service, "_stream", rec)
    monkeypatch.setattr(flash_service, "bootloader_serial_path", lambda _d: None)
    monkeypatch.setattr(flash_service.os.path, "exists", lambda _p: False)  # port gone
    dev = "/dev/serial/by-id/usb-Klipper_stm32f446xx_38002F00-if00"
    log = "".join(
        [
            line
            async for line in flash_service.run_flash(
                "p", "serial", dev, "can0", settings, is_katapult=True
            )
        ]
    )
    assert "waiting in ROM DFU" in log
    assert "Flash sequence complete" in log
    # no reboot-to-bootloader ran (the board is already in a bootloader)
    assert not any("-r" in c for c in calls)
    assert any("dfu-util" in c and "-D" in c for c in calls)


async def test_cancel_mid_flash_restarts_klipper(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """Closing the stream mid-write (client disconnect / cancel) still brings Klipper back."""
    settings, _calls = _flash_env(tmp_path, monkeypatch)

    async def rec(cmd, cwd=None, result=None):  # type: ignore[no-untyped-def]
        if result is not None:
            result["rc"] = 0
        yield "line\n"

    restarted: list[str] = []
    monkeypatch.setattr(flash_service, "_stream", rec)
    monkeypatch.setattr(flash_service, "bootloader_serial_path", lambda _d: None)
    monkeypatch.setattr(flash_service.os.path, "exists", lambda _p: True)
    monkeypatch.setattr(flash_service, "_restart_klipper_detached", lambda: restarted.append("x"))
    gen = flash_service.run_flash(
        "p", "serial", "/dev/ttyACM0", "can0", settings, is_katapult=False
    )
    async for line in gen:
        if "flashtool.py" in line:  # parked inside the write phase
            break
    await gen.aclose()
    assert restarted == ["x"]  # the detached restart fired on the abnormal close

    # ... and a NORMAL completion does not double-restart
    restarted.clear()
    log = "".join(
        [
            line
            async for line in flash_service.run_flash(
                "p", "serial", "/dev/ttyACM0", "can0", settings, is_katapult=False
            )
        ]
    )
    assert "Flash sequence complete" in log
    assert restarted == []


def test_saved_baudrate_matches_registry_id(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """The per-device baudrate is honoured: registry records are keyed by 'id' (not 'device'),
    and the flash path may hand in the bootloader-renamed port - all must match."""
    dev = "/dev/serial/by-id/usb-Klipper_stm32f103xe_ABCD-if00"
    kat = "/dev/serial/by-id/usb-katapult_stm32f103xe_ABCD-if00"
    settings = Settings(moonraker_url="http://x", katapult_dir="/kat", data_dir=str(tmp_path))
    monkeypatch.setattr(
        flash_service.devices_store,
        "read_devices",
        lambda _d: [{"id": dev, "serial_id": None, "baudrate": 115200}],
    )
    assert flash_service._saved_baudrate(settings, dev) == 115200
    assert flash_service._saved_baudrate(settings, kat) == 115200  # bootloader-renamed port
    assert flash_service._saved_baudrate(settings, "/dev/ttyACM9") == 250000  # unknown -> default


async def test_external_firmware_guards(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """External files: 'make' is refused (it would flash the last-built profile), DFU without an
    offset is refused (0x08000000 could wipe the bootloader), and a provable MCU mismatch between
    the binary and the board is refused - all before Klipper is stopped."""
    settings, calls = _flash_env(tmp_path, monkeypatch)
    fw = tmp_path / "ext.bin"
    fw.write_bytes(b"\x00")

    async def rec(cmd, cwd=None, result=None):  # type: ignore[no-untyped-def]
        calls.append(list(cmd))
        if result is not None:
            result["rc"] = 0
        return
        yield ""  # pragma: no cover

    monkeypatch.setattr(flash_service, "_stream", rec)
    # Mock the REAL source the guard reads (binary inspection of the flashed file) - the meta
    # sidecar never carries detected_mcu, which is exactly why the guard must not read it.
    monkeypatch.setattr(
        flash_service.external_firmware,
        "inspect_firmware",
        lambda _p: {"detected_mcu": "rp2040"},
    )

    async def run(method: str, device: str, offset=None) -> str:  # type: ignore[no-untyped-def]
        return "".join(
            [
                line
                async for line in flash_service.run_flash(
                    "ext",
                    method,
                    device,
                    "can0",
                    settings,
                    firmware=str(fw),
                    offset_override=offset,
                )
            ]
        )

    assert "can't be flashed with 'make'" in await run("make", "/dev/ttyUSB0")
    log = await run("dfu", "0483:df11")
    assert "needs its start offset" in log
    stm = "/dev/serial/by-id/usb-Klipper_stm32h723xx_12001F00-if00"
    log = await run("serial", stm)  # rp2040 binary aimed at an stm32 board
    assert "built for 'rp2040'" in log and "unbootable" in log
    assert not any("stop" in c and "klipper" in c for c in calls)  # all refused pre-stop


def test_external_meta_validators() -> None:
    """External meta: method 'make' and malformed offsets are rejected at the schema."""
    from app.models.schemas import ExternalMetaUpdate

    assert ExternalMetaUpdate(method="Serial").method == "serial"
    assert ExternalMetaUpdate(offset="0x08002000").offset == "0x08002000"
    with pytest.raises(ValueError):
        ExternalMetaUpdate(method="make")
    with pytest.raises(ValueError):
        ExternalMetaUpdate(offset="bootloader")


async def test_make_flash_stages_the_profile_config(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """`make flash` re-stages the SELECTED profile's .config first, so a batch that built another
    profile last can never push the wrong firmware."""
    settings, calls = _flash_env(tmp_path, monkeypatch, config="CONFIG_MACH_AVR=y\n")
    staged: list[tuple[str, str]] = []

    async def rec(cmd, cwd=None, result=None):  # type: ignore[no-untyped-def]
        calls.append(list(cmd))
        if result is not None:
            result["rc"] = 0
        return
        yield ""  # pragma: no cover

    monkeypatch.setattr(flash_service, "_stream", rec)
    monkeypatch.setattr(flash_service, "make_available", lambda: True)
    monkeypatch.setattr(flash_service.os.path, "exists", lambda _p: True)
    monkeypatch.setattr(flash_service.shutil, "copy", lambda s, d: staged.append((str(s), str(d))))
    log = "".join(
        [
            line
            async for line in flash_service.run_flash("p", "make", "/dev/ttyUSB0", "can0", settings)
        ]
    )
    assert "Staged this profile's build config" in log
    assert staged and staged[0][0].endswith("p.config") and staged[0][1].endswith(".config")
    assert any(c[:2] == ["make", "olddefconfig"] for c in calls)
    # the olddefconfig runs BEFORE the make flash command
    idx_cfg = next(i for i, c in enumerate(calls) if c[:2] == ["make", "olddefconfig"])
    idx_flash = next(i for i, c in enumerate(calls) if c[:2] == ["make", "flash"])
    assert idx_cfg < idx_flash


async def test_can_verify_skipped_on_same_version_reflash(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """A failed CAN write is NOT rescued by the version check when the node already ran the same
    version before the flash - the old firmware answering proves nothing."""
    settings, calls = _flash_env(tmp_path, monkeypatch)

    async def rec(cmd, cwd=None, result=None):  # type: ignore[no-untyped-def]
        calls.append(list(cmd))
        if result is not None:
            result["rc"] = 1 if any("flashtool.py" in x for x in cmd) else 0
        return
        yield ""  # pragma: no cover

    async def pre_version(_u: str, _m: str) -> str:
        return "v0.13.0-1"

    monkeypatch.setattr(flash_service, "_stream", rec)
    monkeypatch.setattr(flash_service, "_can_txqueuelen", lambda _i: _none())
    monkeypatch.setattr(flash_service, "_can_node_version", pre_version)
    monkeypatch.setattr(flash_service, "read_build_info", lambda _d, _p: {"version": "v0.13.0-1"})

    async def _resolve(_d: str, _m: str):  # type: ignore[no-untyped-def]
        return "aabbccddeeff", None

    monkeypatch.setattr(flash_service, "resolve_can_uuid", _resolve)
    log = "".join(
        [
            line
            async for line in flash_service.run_flash(
                "p", "can", "aabbccddeeff", "can0", settings, is_katapult=True
            )
        ]
    )
    # the same-version rescue is skipped: straight to the honest failure
    assert "checking via Klipper" not in log
    assert "Flash failed" in log


async def _none():  # type: ignore[no-untyped-def]
    return None


async def test_flash_aborts_when_klipper_stop_fails(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """A failed 'systemctl stop klipper' aborts before touching the board (nothing to restart)."""
    settings, calls = _flash_env(tmp_path, monkeypatch)

    async def rec(cmd, cwd=None, result=None):  # type: ignore[no-untyped-def]
        calls.append(list(cmd))
        if result is not None:
            result["rc"] = 1 if ("stop" in cmd and "klipper" in cmd) else 0
        return
        yield ""  # pragma: no cover

    restarted: list[str] = []
    monkeypatch.setattr(flash_service, "_stream", rec)
    monkeypatch.setattr(flash_service, "_restart_klipper_detached", lambda: restarted.append("x"))
    log = "".join(
        [
            line
            async for line in flash_service.run_flash(
                "p", "serial", "/dev/ttyACM0", "can0", settings, is_katapult=False
            )
        ]
    )
    assert "Could not stop the Klipper service" in log
    assert "Flash aborted" in log
    # no write ran; the detached restart fires as a safety net (systemctl start is idempotent -
    # a no-op if Klipper never stopped, a recovery if the stop half-landed)
    assert not any("flashtool.py" in " ".join(c) for c in calls)
    assert restarted == ["x"]


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
