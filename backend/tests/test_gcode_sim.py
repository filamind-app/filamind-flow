"""Tests for the offline G-code motion simulator (pure) + the simulate route."""

from __future__ import annotations

from typing import Any

from app.services import gcode_sim


def test_absolute_moves_path_and_bounds() -> None:
    out = gcode_sim.simulate("G90\nG1 X10 Y0 F3000\nG1 X10 Y20")
    assert out["move_count"] == 2
    assert out["bounds"]["max_x"] == 10
    assert out["bounds"]["max_y"] == 20
    # path2d starts at origin then each endpoint.
    assert out["path2d"][0] == {"x": 0.0, "y": 0.0, "extruding": False}
    assert out["path2d"][-1]["x"] == 10
    assert out["path2d"][-1]["y"] == 20


def test_total_distance_and_time() -> None:
    # One 100 mm move at F6000 (=100 mm/s) → 1.0 s.
    out = gcode_sim.simulate("G90\nG1 X100 Y0 F6000")
    assert out["total_distance_mm"] == 100.0
    assert out["est_time_s"] == 1.0


def test_extrusion_absolute_vs_relative() -> None:
    # Absolute E: G1 X10 E5 then G1 X20 E8 → deltas 5 then 3 = 8 total.
    abs_out = gcode_sim.simulate("G90\nM82\nG1 X10 E5 F3000\nG1 X20 E8")
    assert abs_out["total_extrude_mm"] == 8.0
    assert all(s["extruding"] for s in abs_out["segments"])
    # Relative E: each move's E is its own delta.
    rel_out = gcode_sim.simulate("G90\nM83\nG1 X10 E5 F3000\nG1 X20 E3")
    assert rel_out["total_extrude_mm"] == 8.0


def test_relative_xyz() -> None:
    out = gcode_sim.simulate("G90\nG1 X10 Y10 F3000\nG91\nG1 X5 Y5")
    # 10,10 then +5,+5 = 15,15
    assert out["path2d"][-1] == {"x": 15.0, "y": 15.0, "extruding": False}


def test_g92_set_position() -> None:
    out = gcode_sim.simulate("G90\nG1 X50 F3000\nG92 X0\nG1 X10")
    # After G92 X0 the head is at logical 0; G1 X10 moves 10 mm.
    last = out["segments"][-1]
    assert last["from"][0] == 0.0
    assert last["to"][0] == 10.0
    assert last["dist"] == 10.0


def test_g28_home_to_origin() -> None:
    out = gcode_sim.simulate("G90\nG1 X50 Y50 F3000\nG28\nG1 X5")
    home_then_move = out["segments"][-1]
    assert home_then_move["from"][0] == 0.0  # homed to 0
    assert home_then_move["to"][0] == 5.0


def test_comments_and_blank_lines_skipped() -> None:
    out = gcode_sim.simulate("; a comment\n\nG90\nG1 X10 F3000 ; inline\n")
    assert out["move_count"] == 1
    assert out["bounds"]["max_x"] == 10


def test_unknown_command_warns() -> None:
    out = gcode_sim.simulate("G90\nM117 hello\nFOO\nG1 X1 F600")
    assert any("M117" in w for w in out["warnings"])
    assert any("FOO" in w for w in out["warnings"])
    assert out["move_count"] == 1


def test_empty_program() -> None:
    out = gcode_sim.simulate("")
    assert out["move_count"] == 0
    assert out["bounds"]["max_x"] == 0.0  # infinities collapsed to a zero box
    assert out["total_distance_mm"] == 0.0


# ── route ────────────────────────────────────────────────────────────────────
def test_route_simulate() -> None:
    from fastapi.testclient import TestClient

    from app.main import create_app

    resp = TestClient(create_app()).post(
        "/api/macro/simulate", json={"gcode": "G90\nG1 X10 Y10 F3000"}
    )
    assert resp.status_code == 200
    body: dict[str, Any] = resp.json()
    assert body["move_count"] == 1
    assert body["bounds"]["max_x"] == 10


# ── machine limits (bed-envelope + speed cap) ────────────────────────────────
def test_simulate_flags_out_of_bounds_and_over_speed() -> None:
    limits = {"min": [0.0, 0.0, 0.0], "max": [200.0, 200.0, 200.0], "max_velocity": 100.0}
    # X400 is past the 200 envelope; F12000 mm/min = 200 mm/s > the 100 mm/s cap.
    out = gcode_sim.simulate("G90\nG1 X400 Y10 F12000", limits)
    seg = out["segments"][0]
    assert seg["out_of_bounds"] is True and seg["over_speed"] is True
    kinds = {v["kind"] for v in out["violations"]}
    assert {"out_of_bounds", "over_speed"} <= kinds
    oob = next(v for v in out["violations"] if v["kind"] == "out_of_bounds")
    assert oob["axis"] == "X" and oob["value"] == 400.0


def test_simulate_no_violations_within_limits() -> None:
    limits = {"min": [0.0, 0.0, 0.0], "max": [200.0, 200.0, 200.0], "max_velocity": 100.0}
    out = gcode_sim.simulate("G90\nG1 X100 Y100 F3000", limits)  # F3000 = 50 mm/s, in bounds
    assert out["violations"] == []
    assert out["segments"][0]["out_of_bounds"] is False
    # Without limits, nothing is flagged (backward-compatible).
    plain = gcode_sim.simulate("G90\nG1 X400 Y10 F99999")
    assert plain["violations"] == [] and plain["segments"][0]["out_of_bounds"] is False
