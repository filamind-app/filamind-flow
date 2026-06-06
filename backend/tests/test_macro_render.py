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


def test_case_insensitive_lookup() -> None:
    out, _ = macro_render.render("G1 Z{ params.z }", {"Z": "5"})
    assert out == "G1 Z5"


def test_int_filter() -> None:
    out, _ = macro_render.render("G1 E{ params.E | default(5.0) | int }", {})
    assert out == "G1 E5"


def test_unresolved_left_intact_and_warned() -> None:
    out, warns = macro_render.render("G1 X{ params.MISSING }", {})
    assert "{ params.MISSING }" in out
    assert any("Unresolved" in w for w in warns)


def test_control_flow_warned_not_evaluated() -> None:
    src = "{% for i in range(3) %}\nG1 X{ params.STEP|default(10) }\n{% endfor %}"
    out, warns = macro_render.render(src, {})
    assert "{% for" in out  # control flow left untouched
    assert "G1 X10" in out  # value expr still substituted
    assert any("control flow" in w.lower() for w in warns)


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
