from __future__ import annotations

from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.main import create_app
from app.services.board_service import _classify_serial_mode, _parse_dfu_line


def test_classify_serial_mode() -> None:
    assert _classify_serial_mode("usb-Klipper_stm32f103_X-if00") == "service"
    assert _classify_serial_mode("usb-Kalico_stm32g0b1_Y-if00") == "service"
    assert _classify_serial_mode("usb-katapult_stm32f103_Z-if00") == "ready"
    assert _classify_serial_mode("usb-CanBoot_rp2040_W-if00") == "ready"
    assert _classify_serial_mode("usb-1a86_USB_Single_Serial-if00") == "unknown"


def test_parse_dfu_line() -> None:
    line = (
        'Found DFU: [0483:df11] ver=0200, devnum=12, cfg=1, intf=0, '
        'path="1-1.2", alt=0, name="@Internal Flash", serial="357236543131"'
    )
    parsed = _parse_dfu_line(line)
    assert parsed is not None
    assert parsed["id"] == "357236543131"
    assert "0483:df11" in parsed["name"]
    assert _parse_dfu_line("Not a DFU line") is None


def test_boards_discovery_graceful() -> None:
    """With no reachable Moonraker and no scannable hardware, discovery is empty."""
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: Settings(
        moonraker_url="http://127.0.0.1:1",
        klipper_dir="/nonexistent/klipper",
        katapult_dir="/nonexistent/katapult",
    )
    client = TestClient(app)

    response = client.get("/api/firmware/boards")

    assert response.status_code == 200
    body = response.json()
    assert isinstance(body["boards"], list)
    assert set(body["scanned"]) == {"configured", "serial", "can", "dfu"}
    assert body["scanned"]["configured"] == 0
