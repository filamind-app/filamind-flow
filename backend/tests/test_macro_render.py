"""Tests for macro variable substitution (pure) + the rendered simulate route."""

from __future__ import annotations

from app.services import macro_render


def test_param_substitution() -> None:
    out, warns = macro_render.render("G1 X{ params.X } Y{ params.Y }", {"X": "10", "Y": "20"})
    assert out == "G1 X10 Y20"
    assert warns == []


def test_default_when_param_missing() -> None:
    out, warns = macro_render.render("M104 S{ params.EXTRUDER | default(200) }", {})
    assert out == "M104 S200"
    assert warns == []


def test_param_overrides_default() -> None:
    out, _ = macro_render.render("M140 S{ params.BED|default(60) }", {"BED": "75"})
    assert out == "M140 S75"


def test_exact_param_name() -> None:
    out, _ = macro_render.render("G1 Z{ params.Z }", {"Z": "5"})
    assert out == "G1 Z5"


def test_int_filter() -> None:
    out, _ = macro_render.render("G1 E{ params.E | default(5.0) | int }", {})
    assert out == "G1 E5"


def test_missing_param_renders_empty() -> None:
    # Real Jinja: a missing variable with no default renders to nothing (matches the printer).
    out, warns = macro_render.render("M117{ params.MISSING }", {})
    assert out == "M117"
    assert warns == []


def test_for_loop_is_expanded() -> None:
    src = "{% for i in range(3) %}G1 Z{ i * 5 }\n{% endfor %}"
    out, warns = macro_render.render(src, {})
    assert out == "G1 Z0\nG1 Z5\nG1 Z10\n"
    assert warns == []


def test_conditional_on_param() -> None:
    src = "{% if params.PURGE|default(1)|int %}G1 X50 E10\n{% endif %}G28"
    skipped, _ = macro_render.render(src, {"PURGE": "0"})
    taken, _ = macro_render.render(src, {"PURGE": "1"})
    assert skipped == "G28"
    assert taken == "G1 X50 E10\nG28"


def test_printer_state_macro_falls_back_with_warning() -> None:
    # An offline render has no live printer state, so arithmetic on it can't evaluate → fall back.
    src = "{% if printer.heater_bed.temperature > 60 %}M117 hot{% endif %}"
    out, warns = macro_render.render(src, {})
    assert any("literal substitution" in w.lower() for w in warns)
    assert "{% if" in out  # the unevaluated template is left literal for the fallback


def test_no_expressions_unchanged() -> None:
    src = "G28\nG1 X10 Y10 F3000"
    out, warns = macro_render.render(src, {})
    assert out == src
    assert warns == []


# ── route integration ─────────────────────────────────────────────────────────
def test_route_simulate_renders_params() -> None:
    from fastapi.testclient import TestClient

    from app.main import create_app

    client = TestClient(create_app())
    resp = client.post(
        "/api/macro/simulate",
        json={"gcode": "G90\nG1 X{ params.LEN|default(50) } Y0 F6000", "params": {"LEN": "100"}},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["move_count"] == 1
    assert body["bounds"]["max_x"] == 100  # rendered from params


def test_route_simulate_uses_default_without_params() -> None:
    from fastapi.testclient import TestClient

    from app.main import create_app

    client = TestClient(create_app())
    resp = client.post(
        "/api/macro/simulate", json={"gcode": "G90\nG1 X{ params.LEN|default(40) } F6000"}
    )
    assert resp.status_code == 200
    assert resp.json()["bounds"]["max_x"] == 40
