"""Mission-control overview - the home page's per-block aggregation."""

from __future__ import annotations

from typing import Any

import pytest

from app.services import overview


async def test_setup_block_excludes_the_host_virtual_mcu(monkeypatch: pytest.MonkeyPatch) -> None:
    """The Klipper host process (`/tmp/klipper_host_mcu`) is a virtual MCU, not a control board the
    user confirms - it must NOT count toward the "confirm your boards" total, or the step could
    never reach done (host MCUs often carry no board_id)."""

    async def fake_topo(_client: Any, _dd: str) -> dict[str, Any]:
        return {
            "mcus": [
                {"name": "mcu", "board_id": "m8p-v2-0", "identifier": "usb-Klipper_stm32h723-if00"},
                {"name": "ebbcan", "board_id": "sb2209-v1-0-rp2040", "identifier": "72e5b6ba7195"},
                # the host process - no confirmable board, identifier is the Unix socket:
                {"name": "pi2", "board_id": None, "identifier": "/tmp/klipper_host_mcu"},
            ]
        }

    monkeypatch.setattr(overview.board_topology, "gather_topology", fake_topo)
    monkeypatch.setattr("app.services.motor_mapping.read_mapping", lambda _dd: [])

    out = await overview._setup_block(object(), "/data")
    # 2 real boards, both identified -> the checklist can complete (was 2/3 = stuck before the fix).
    assert out["boards_total"] == 2
    assert out["boards_identified"] == 2


async def test_setup_block_counts_a_host_mcu_that_did_match(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Even when the host MCU auto-matches a host board (board_id set), it's still excluded from the
    board count - the count reflects only physical control boards, consistently."""

    async def fake_topo(_client: Any, _dd: str) -> dict[str, Any]:
        return {
            "mcus": [
                {"name": "mcu", "board_id": "m8p-v2-0", "identifier": "usb-Klipper_x-if00"},
                {"name": "pi2", "board_id": "cb2", "identifier": "/tmp/klipper_host_mcu"},
            ]
        }

    monkeypatch.setattr(overview.board_topology, "gather_topology", fake_topo)
    monkeypatch.setattr("app.services.motor_mapping.read_mapping", lambda _dd: [])

    out = await overview._setup_block(object(), "/data")
    assert out["boards_total"] == 1 and out["boards_identified"] == 1
