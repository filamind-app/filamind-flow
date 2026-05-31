from __future__ import annotations

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
