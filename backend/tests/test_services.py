from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.services import services_service


def test_parse_services_filters_protected_and_reads_state() -> None:
    out = (
        "klipper.service loaded active running Klipper\n"
        "klipper-mcu.service loaded inactive dead Klipper MCU\n"
        "moonraker.service loaded active running Moonraker\n"
        "filamind-flow.service loaded active running FilaMind Flow\n"
    )
    services = services_service._parse_services(out)
    names = [s["name"] for s in services]
    assert "filamind-flow" not in names  # our own service is protected
    assert {"name": "klipper", "active": True} in services
    assert {"name": "klipper-mcu", "active": False} in services


def test_order_key_starts_low_level_first_stops_last() -> None:
    key = services_service._order_key
    assert key("klipper-mcu", "start") < key("moonraker", "start")
    assert key("moonraker", "stop") < key("klipper-mcu", "stop")


async def test_list_all_services_parses_substate_and_keeps_own(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    canned = (
        "klipper.service loaded active running Klipper\n"
        "moonraker.service loaded active running Moonraker\n"
        "KlipperScreen.service loaded inactive dead KlipperScreen\n"
        "filamind-flow.service loaded active running FilaMind\n"
    )

    async def fake_run(_cmd: list[str]) -> tuple[int, str]:
        return 0, canned

    monkeypatch.setattr(services_service, "_run", fake_run)
    units = await services_service.list_all_services()
    by = {u["name"]: u for u in units}
    assert by["klipper"] == {"name": "klipper", "active": True, "sub_state": "running"}
    assert by["KlipperScreen"]["active"] is False
    assert by["KlipperScreen"]["sub_state"] == "dead"
    # The read-only doctor listing does NOT drop our own unit (that filter is only for the
    # manageable start/stop set).
    assert "filamind-flow" in by


def test_services_routes() -> None:
    client = TestClient(create_app())

    listed = client.get("/api/firmware/services")
    assert listed.status_code == 200
    assert "services" in listed.json()

    assert client.post("/api/firmware/services/restart").status_code == 200
    assert client.post("/api/firmware/services/bogus").status_code == 400
