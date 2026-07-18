"""Tests for the structural config lint (config_lint.lint_config)."""

from __future__ import annotations

from typing import Any

import httpx

from app.services import config_lint
from app.services.moonraker_client import MoonrakerClient


def _rules(result: dict[str, Any]) -> list[str]:
    return [f["rule"] for f in result["findings"]]


async def test_lint_aggregates_sources(monkeypatch: Any) -> None:
    async def fake_pin_doctor(_client: Any, _data_dir: str) -> dict[str, Any]:
        return {
            "reachable": True,
            "mcus": [
                {
                    "name": "mcu",
                    "findings": [
                        {"kind": "double_assign", "pin": "PA1", "sections": ["stepper_x", "fan"]},
                        {"kind": "caveat", "pin": "PB0", "message": "mains on a logic pin"},
                    ],
                }
            ],
        }

    async def fake_query(_self: Any, _objs: Any) -> dict[str, Any]:
        return {
            "configfile": {
                "settings": {
                    "printer": {"kinematics": "corexy"},
                    "stepper_x": {},
                    "extruder": {"min_temp": 250, "max_temp": 200},  # inverted -> error
                },
                "warnings": [
                    {"message": "Option 'foo' is deprecated", "section": "printer"},
                    "a bare-string warning",
                ],
                "save_config_pending": True,
            }
        }

    monkeypatch.setattr("app.services.board_topology.gather_pin_doctor", fake_pin_doctor)
    monkeypatch.setattr(MoonrakerClient, "query_objects", fake_query)

    result = await config_lint.lint_config(MoonrakerClient("http://x"), "")
    rules = _rules(result)
    assert result["reachable"] is True
    assert "double_assigned_pin" in rules
    assert "pin_caveat" in rules
    assert rules.count("klipper_warning") == 2
    # A pending SAVE_CONFIG is runtime state, not a structural lint finding: even with the flag set
    # it must NOT appear here (the drift panel owns it).
    assert "save_config_pending" not in rules
    assert "heater_temp_range" in rules
    # printer + a stepper exist -> no structural-absence findings
    assert "missing_printer" not in rules
    assert "no_stepper" not in rules


async def test_lint_flags_missing_structure(monkeypatch: Any) -> None:
    async def empty_pin_doctor(_client: Any, _data_dir: str) -> dict[str, Any]:
        return {"reachable": True, "mcus": []}

    async def fake_query(_self: Any, _objs: Any) -> dict[str, Any]:
        return {"configfile": {"settings": {"mcu": {}, "fan": {}}}}

    monkeypatch.setattr("app.services.board_topology.gather_pin_doctor", empty_pin_doctor)
    monkeypatch.setattr(MoonrakerClient, "query_objects", fake_query)

    rules = _rules(await config_lint.lint_config(MoonrakerClient("http://x"), ""))
    assert "missing_printer" in rules
    assert "no_stepper" in rules


async def test_lint_unreachable(monkeypatch: Any) -> None:
    async def boom(_self: Any, _objs: Any) -> dict[str, Any]:
        raise httpx.ConnectError("down")

    monkeypatch.setattr(MoonrakerClient, "query_objects", boom)
    result = await config_lint.lint_config(MoonrakerClient("http://x"), "")
    assert result == {"reachable": False, "findings": [], "checked": 0}
