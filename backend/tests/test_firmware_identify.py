from __future__ import annotations

from app.services.firmware_identify import match_devices


def _mcu(name: str, identifier: str) -> dict:
    return {"name": name, "identifier": identifier, "mcu": "STM32F103", "board_id": "b"}


def test_exact_identifier_match() -> None:
    devices = [{"id": "/dev/serial/by-id/usb-Klipper_stm32f103xe_AAA-if00"}]
    mcus = [_mcu("mcu", "/dev/serial/by-id/usb-Klipper_stm32f103xe_AAA-if00")]
    assert match_devices(devices, mcus)[devices[0]["id"]]["name"] == "mcu"


def test_substring_match_covers_katapult_identity() -> None:
    # The Katapult bootloader id embeds the same usb serial in a different path.
    devices = [
        {
            "id": "/dev/serial/by-id/usb-katapult_stm32f103xe_AAA-if00",
            "serial_id": "usb-Klipper_stm32f103xe_AAA-if00",
        }
    ]
    mcus = [_mcu("mcu", "/dev/serial/by-id/usb-Klipper_stm32f103xe_AAA-if00")]
    assert devices[0]["id"] in match_devices(devices, mcus)


def test_no_match_for_linux_process_or_blank_identifier() -> None:
    devices = [{"id": "linux_process"}]
    mcus = [_mcu("host_mcu", "")]
    assert match_devices(devices, mcus) == {}


def test_first_matching_mcu_wins_once() -> None:
    devices = [{"id": "X"}, {"id": "Y"}]
    mcus = [_mcu("mcu", "X"), _mcu("toolhead", "Y")]
    matched = match_devices(devices, mcus)
    assert matched["X"]["name"] == "mcu"
    assert matched["Y"]["name"] == "toolhead"
