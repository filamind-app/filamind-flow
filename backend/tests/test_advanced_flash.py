from __future__ import annotations

import pytest

from app.services import flash_service


def test_dfu_leave_command() -> None:
    cmd = flash_service.dfu_leave_command("0x08000000", "357236543131")
    assert "0x08000000:leave" in cmd
    assert cmd[:6] == ["sudo", "-n", "dfu-util", "-a", "0", "-d"]
    assert "-S" in cmd and "357236543131" in cmd
    # A /dev path is not a DFU serial, so it is not passed with -S.
    assert "-S" not in flash_service.dfu_leave_command("0x08000000", "/dev/ttyACM0")


def test_resolve_method_redirects_can_bridge_to_serial() -> None:
    # A USB-to-CAN bridge enumerates as a /dev path even though it is "CAN".
    assert flash_service.resolve_method("can", "/dev/ttyACM0") == "serial"
    # A real CAN UUID stays on CAN; serial stays serial.
    assert flash_service.resolve_method("can", "aabbccddeeff") == "can"
    assert flash_service.resolve_method("serial", "/dev/ttyACM0") == "serial"


def test_reenumerated_id_detects_a_single_new_endpoint() -> None:
    before = {"/dev/serial/by-id/usb-katapult_x-if00"}
    after = {"/dev/serial/by-id/usb-Klipper_x-if00"}
    assert (
        flash_service.reenumerated_id("/dev/serial/by-id/usb-katapult_x-if00", before, after)
        == "/dev/serial/by-id/usb-Klipper_x-if00"
    )
    # Still present → no change.
    assert flash_service.reenumerated_id("a", {"a"}, {"a", "b"}) is None
    # Ambiguous (two new) → don't guess.
    assert flash_service.reenumerated_id("a", {"a"}, {"b", "c"}) is None


class _ConfigClient:
    """Stub MoonrakerClient returning a fixed configfile.config."""

    def __init__(self, config: dict) -> None:
        self._config = config

    async def query_objects(self, objects: list[str]) -> dict:
        return {"configfile": {"config": self._config}}


def _patch_client(monkeypatch: pytest.MonkeyPatch, config: dict) -> None:
    monkeypatch.setattr(flash_service, "MoonrakerClient", lambda *a, **k: _ConfigClient(config))


async def test_resolve_can_uuid_passes_through_a_real_uuid() -> None:
    uuid, err = await flash_service.resolve_can_uuid("f837f305a66f", "http://x")
    assert uuid == "f837f305a66f" and err is None


async def test_resolve_can_uuid_maps_a_friendly_name_via_the_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The Voron case: device registered as "Toolhead", real UUID lives in [mcu Toolhead].
    _patch_client(
        monkeypatch,
        {"mcu": {"serial": "/dev/x"}, "mcu Toolhead": {"canbus_uuid": "f837f305a66f"}},
    )
    uuid, err = await flash_service.resolve_can_uuid("Toolhead", "http://x")
    assert uuid == "f837f305a66f" and err is None


async def test_resolve_can_uuid_uses_the_sole_uuid_when_unambiguous(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_client(monkeypatch, {"mcu EBB": {"canbus_uuid": "aabbccddeeff"}})
    uuid, err = await flash_service.resolve_can_uuid("does-not-match", "http://x")
    assert uuid == "aabbccddeeff" and err is None


async def test_resolve_can_uuid_refuses_when_no_uuid_in_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_client(monkeypatch, {"mcu": {"serial": "/dev/x"}})
    uuid, err = await flash_service.resolve_can_uuid("Toolhead", "http://x")
    assert uuid is None and err is not None and "canbus_uuid" in err


async def test_resolve_can_uuid_refuses_on_ambiguous_match(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_client(
        monkeypatch,
        {"mcu A": {"canbus_uuid": "aaaaaaaaaaaa"}, "mcu B": {"canbus_uuid": "bbbbbbbbbbbb"}},
    )
    uuid, err = await flash_service.resolve_can_uuid("nope", "http://x")
    assert uuid is None and err is not None


async def test_stream_reports_a_nonzero_exit_code() -> None:
    import sys

    result: dict[str, int] = {}
    cmd = [sys.executable, "-c", "import sys;sys.exit(3)"]
    [line async for line in flash_service._stream(cmd, result=result)]
    assert result["rc"] == 3


async def test_stream_reports_zero_on_success() -> None:
    import sys

    result: dict[str, int] = {}
    cmd = [sys.executable, "-c", "print('ok')"]
    [line async for line in flash_service._stream(cmd, result=result)]
    assert result["rc"] == 0


async def test_stream_reports_127_when_the_binary_is_missing() -> None:
    result: dict[str, int] = {}
    lines = [ln async for ln in flash_service._stream(["definitely-not-a-binary"], result=result)]
    assert result["rc"] == 127
    assert any(ln.startswith("!! cannot run") for ln in lines)
