"""Tests for the shared live-state accessors (gcode_macro extraction from the live configfile)."""

from __future__ import annotations

from typing import Any

from app.services import live_state


def _configfile(settings: dict[str, Any]) -> dict[str, Any]:
    return {"configfile": {"settings": settings}}


def test_settings_of_extracts_or_empty() -> None:
    assert live_state.settings_of(_configfile({"a": {}})) == {"a": {}}
    assert live_state.settings_of({}) == {}
    assert live_state.settings_of({"configfile": {}}) == {}


def test_gcode_macros_body_params_and_variables() -> None:
    settings = {
        "gcode_macro start_print": {
            "gcode": "G28\nG1 X{params.X|default(20)} Y{params.Y|default(10)} S{params.TEMP}",
            "description": "Prime + level",
            "variable_z_offset": 0.2,
        },
        "stepper_x": {"step_pin": "PA1"},  # not a macro — ignored
    }
    macros = live_state.gcode_macros(settings)
    assert len(macros) == 1
    m = macros[0]
    assert m["name"] == "start_print"
    assert "G28" in m["gcode"]
    assert m["description"] == "Prime + level"
    # defaults discovered; TEMP has no default → empty string; variables surfaced
    assert m["params"] == {"X": "20", "Y": "10", "TEMP": ""}
    assert m["variables"] == {"z_offset": 0.2}


def test_gcode_macros_sorted_and_handles_no_gcode() -> None:
    macros = live_state.gcode_macros(
        {"gcode_macro Zeta": {"gcode": "G28"}, "gcode_macro alpha": {}}
    )
    assert [m["name"] for m in macros] == ["alpha", "Zeta"]
    assert macros[0]["gcode"] == "" and macros[0]["params"] == {}
