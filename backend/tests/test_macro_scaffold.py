"""Tests for the START_PRINT / END_PRINT scaffold generator + the gated append write path."""

from __future__ import annotations

from typing import Any

import pytest

from app.services import config_service, macro_scaffold


def test_generate_tailors_leveling_and_bounds() -> None:
    ctx = {
        "kinematics": "corexy",
        "bounds": {"min": [0, 0, -5], "max": [355, 364, 347]},
        "leveling": ["z_tilt", "bed_mesh"],
        "has_bed": True,
        "has_extruder": True,
    }
    out = macro_scaffold.generate(ctx)
    assert "[gcode_macro START_PRINT]" in out["start"]
    assert "[gcode_macro END_PRINT]" in out["end"]
    # The configured leveling + mesh appear; QGL (not configured) does not.
    assert "Z_TILT_ADJUST" in out["start"]
    assert "BED_MESH_CALIBRATE" in out["start"]
    assert "QUAD_GANTRY_LEVEL" not in out["start"]
    # Bed heating present (has_bed) and the prime line sits inside the envelope.
    assert "M190 S{BED}" in out["start"]
    assert "X5.0 Y5.0" in out["start"]
    keys = {n["key"] for n in out["notes"]}
    assert {"kinematics", "bounds", "leveling_ztilt", "mesh"} <= keys


def test_generate_without_bed_or_leveling() -> None:
    out = macro_scaffold.generate({"kinematics": "cartesian", "bounds": None, "has_bed": False})
    assert "M190" not in out["start"]  # no bed wait
    assert "M140 S0" not in out["end"]  # no bed-off
    assert "no quad_gantry_level / z_tilt" in out["start"]
    keys = {n["key"] for n in out["notes"]}
    assert "leveling_none" in keys and "no_bed" in keys


def test_context_from_live_detects_sections() -> None:
    configfile = {
        "configfile": {
            "settings": {
                "printer": {"kinematics": "corexy"},
                "heater_bed": {},
                "extruder": {},
                "z_tilt": {},
                "bed_mesh": {},
                "stepper_x": {},
            }
        }
    }
    toolhead = {"axis_minimum": [0, 0, -5], "axis_maximum": [355, 364, 347], "max_velocity": 700}
    ctx = macro_scaffold.context_from_live(configfile, toolhead)
    assert ctx["kinematics"] == "corexy"
    assert ctx["has_bed"] is True and ctx["has_extruder"] is True
    assert "z_tilt" in ctx["leveling"] and "bed_mesh" in ctx["leveling"]
    assert ctx["bounds"] == {"min": [0.0, 0.0, -5.0], "max": [355.0, 364.0, 347.0]}


class _FakeClient:
    def __init__(self, text: str = "", *, state: str = "standby") -> None:
        self._text = text
        self._state = state
        self.uploads: list[tuple[str, str]] = []

    async def get_file_text(self, path: str, root: str = "config") -> str:
        return self._text

    async def list_files(self, root: str = "config") -> list[dict[str, Any]]:
        return []

    async def delete_file(self, path: str, root: str = "config") -> None:
        return None

    async def query_objects(self, objects: list[str]) -> dict[str, Any]:
        return {"print_stats": {"state": self._state}}

    async def upload_file(self, path: str, content: str, root: str = "config") -> dict[str, Any]:
        self.uploads.append((path, content))
        return {"item": {"path": path}}


async def test_append_block_appends_through_gated_save() -> None:
    client = _FakeClient(text="[mcu]\nserial: /dev/x\n")
    block = "[gcode_macro START_PRINT]\ngcode:\n  G28\n"
    result = await config_service.append_block(client, "printer.cfg", block)  # type: ignore[arg-type]
    assert result["ok"] is True
    # A backup (original) then the appended content were written.
    assert len(client.uploads) == 2
    _, final = client.uploads[1]
    assert "[mcu]" in final and "[gcode_macro START_PRINT]" in final


async def test_append_block_refuses_duplicate_macro() -> None:
    client = _FakeClient(text="[gcode_macro START_PRINT]\ngcode:\n  G28\n")
    block = "[gcode_macro START_PRINT]\ngcode:\n  G28\n"
    with pytest.raises(ValueError, match="already defined"):
        await config_service.append_block(client, "printer.cfg", block)  # type: ignore[arg-type]
    assert client.uploads == []  # nothing written


async def test_append_block_refused_when_busy() -> None:
    client = _FakeClient(text="", state="printing")
    with pytest.raises(config_service.ConfigBusyError):
        await config_service.append_block(  # type: ignore[arg-type]
            client, "printer.cfg", "[gcode_macro X]\ngcode:\n  G28\n"
        )
