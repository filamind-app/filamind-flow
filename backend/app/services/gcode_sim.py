"""Offline G-code motion simulator — the Macro Designer core (Track A).

Pure and hardware-free: parse a G-code program and compute the toolhead path, bounding box,
total travel / extrusion, a rough time estimate, and a per-command timeline. Literal G-code in
— macro / Jinja expansion and the built-in macro library are a later slice.

Supported: ``G0`` / ``G1`` moves (X/Y/Z/E/F), ``G90`` / ``G91`` (absolute / relative XYZ),
``M82`` / ``M83`` (absolute / relative extrusion), ``G92`` (set position), ``G28`` (home → 0).
Inline ``;`` comments are stripped; unrecognised commands are recorded as warnings and skipped.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

_AXES = ("X", "Y", "Z", "E", "F")


@dataclass
class _State:
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    e: float = 0.0
    f: float = 0.0  # feedrate, mm/min
    absolute_xyz: bool = True
    absolute_e: bool = True


def _parse_words(rest: str) -> dict[str, float]:
    """Parse ``X10 Y20 F3000`` into ``{"X": 10.0, ...}`` (ignores unparseable words)."""
    words: dict[str, float] = {}
    for token in rest.split():
        letter = token[:1].upper()
        if letter in _AXES:
            try:
                words[letter] = float(token[1:])
            except ValueError:
                continue
    return words


def _strip_comment(line: str) -> str:
    idx = line.find(";")
    return line if idx == -1 else line[:idx]


def lint(gcode: str) -> list[dict[str, Any]]:
    """Static safety checks over a macro body (no execution) — the classic Klipper foot-guns:

    * ``gcode_state_unbalanced`` — a ``SAVE_GCODE_STATE`` without a matching ``RESTORE_GCODE_STATE``
      (or vice-versa), which leaks the saved positioning / extruder mode.
    * ``ends_relative`` — the program switches to relative (``G91`` / ``M83``) and ends there
      without restoring, leaving the printer in relative mode for whatever runs next.
    * ``extrude_before_home`` — an extruding move before any ``G28`` (cold / un-homed extrude risk).

    Structured findings ``{level, line, rule}`` — the UI renders the message + fix per rule. Some
    may not apply to a fragment that assumes the caller already homed / set a mode.
    """
    abs_xyz = True
    abs_e = True
    homed = False
    used_rel_xyz = False
    used_rel_e = False
    saves = 0
    restores = 0
    e_pos = 0.0
    extrude_before_home: int | None = None

    for lineno, raw in enumerate(gcode.splitlines(), start=1):
        line = _strip_comment(raw).strip()
        if not line:
            continue
        parts = line.split(None, 1)
        cmd = parts[0].upper()
        if cmd == "SAVE_GCODE_STATE":
            saves += 1
        elif cmd == "RESTORE_GCODE_STATE":
            restores += 1
        elif cmd == "G28":
            homed = True
        elif cmd == "G90":
            abs_xyz = True
        elif cmd == "G91":
            abs_xyz = False
            used_rel_xyz = True
        elif cmd == "M82":
            abs_e = True
        elif cmd == "M83":
            abs_e = False
            used_rel_e = True
        elif cmd in ("G0", "G1") and len(parts) > 1:
            words = _parse_words(parts[1])
            if "E" in words:
                delta = words["E"] - e_pos if abs_e else words["E"]
                e_pos = words["E"] if abs_e else e_pos + words["E"]
                if delta > 1e-9 and not homed and extrude_before_home is None:
                    extrude_before_home = lineno

    findings: list[dict[str, Any]] = []
    if saves != restores:
        findings.append({"level": "error", "line": None, "rule": "gcode_state_unbalanced"})
    if restores == 0 and ((used_rel_xyz and not abs_xyz) or (used_rel_e and not abs_e)):
        findings.append({"level": "warn", "line": None, "rule": "ends_relative"})
    if extrude_before_home is not None:
        findings.append(
            {"level": "warn", "line": extrude_before_home, "rule": "extrude_before_home"}
        )
    return findings


def simulate(gcode: str, limits: dict[str, Any] | None = None) -> dict[str, Any]:
    """Simulate a literal G-code program → path, bounds, totals, timeline (pure).

    When ``limits`` is given (the printer's real envelope ``{min, max, max_velocity}`` from
    ``live_state.limits_of``), each move is checked against it: a destination outside the build area
    is flagged ``out_of_bounds`` and a feedrate above ``max_velocity`` is flagged ``over_speed``, on
    the segment + in a structured ``violations`` list (the UI renders them)."""
    state = _State()
    segments: list[dict[str, Any]] = []
    path2d: list[dict[str, Any]] = [{"x": 0.0, "y": 0.0, "extruding": False}]
    timeline: list[dict[str, Any]] = []
    warnings: list[str] = []
    seen_unknown: set[str] = set()
    violations: list[dict[str, Any]] = []
    lim_min = limits.get("min") if isinstance(limits, dict) else None
    lim_max = limits.get("max") if isinstance(limits, dict) else None
    max_vel = limits.get("max_velocity") if isinstance(limits, dict) else None

    bounds = {
        "min_x": math.inf,
        "max_x": -math.inf,
        "min_y": math.inf,
        "max_y": -math.inf,
        "min_z": math.inf,
        "max_z": -math.inf,
    }

    def grow_bounds(x: float, y: float, z: float) -> None:
        bounds["min_x"] = min(bounds["min_x"], x)
        bounds["max_x"] = max(bounds["max_x"], x)
        bounds["min_y"] = min(bounds["min_y"], y)
        bounds["max_y"] = max(bounds["max_y"], y)
        bounds["min_z"] = min(bounds["min_z"], z)
        bounds["max_z"] = max(bounds["max_z"], z)

    grow_bounds(0.0, 0.0, 0.0)
    total_distance = 0.0
    total_extrude = 0.0
    est_time_s = 0.0
    move_count = 0

    for lineno, raw in enumerate(gcode.splitlines(), start=1):
        line = _strip_comment(raw).strip()
        if not line:
            continue
        parts = line.split(None, 1)
        cmd = parts[0].upper()
        words = _parse_words(parts[1]) if len(parts) > 1 else {}

        if cmd in ("G0", "G1"):
            if "F" in words:
                state.f = words["F"]
            x0, y0, z0 = state.x, state.y, state.z
            if state.absolute_xyz:
                nx = words.get("X", state.x)
                ny = words.get("Y", state.y)
                nz = words.get("Z", state.z)
            else:
                nx = state.x + words.get("X", 0.0)
                ny = state.y + words.get("Y", 0.0)
                nz = state.z + words.get("Z", 0.0)
            if "E" in words:
                e_delta = words["E"] if not state.absolute_e else words["E"] - state.e
                state.e = words["E"] if state.absolute_e else state.e + words["E"]
            else:
                e_delta = 0.0
            dist = math.dist((x0, y0, z0), (nx, ny, nz))
            extruding = e_delta > 1e-9 and dist > 1e-9
            out_of_bounds = False
            over_speed = False
            if lim_min and lim_max:
                for i, (coord, axis) in enumerate(((nx, "X"), (ny, "Y"), (nz, "Z"))):
                    if coord < lim_min[i] - 1e-6 or coord > lim_max[i] + 1e-6:
                        out_of_bounds = True
                        violations.append(
                            {
                                "line": lineno,
                                "kind": "out_of_bounds",
                                "axis": axis,
                                "value": round(coord, 2),
                                "limit": [lim_min[i], lim_max[i]],
                            }
                        )
                if max_vel and dist > 1e-9 and state.f / 60.0 > max_vel + 1e-6:
                    over_speed = True
                    violations.append(
                        {
                            "line": lineno,
                            "kind": "over_speed",
                            "value": round(state.f / 60.0, 1),
                            "limit": round(max_vel, 1),
                        }
                    )
            segments.append(
                {
                    "line": lineno,
                    "from": [round(x0, 4), round(y0, 4), round(z0, 4)],
                    "to": [round(nx, 4), round(ny, 4), round(nz, 4)],
                    "e_delta": round(e_delta, 5),
                    "dist": round(dist, 4),
                    "feedrate": state.f,
                    "extruding": extruding,
                    "out_of_bounds": out_of_bounds,
                    "over_speed": over_speed,
                }
            )
            path2d.append({"x": round(nx, 4), "y": round(ny, 4), "extruding": extruding})
            state.x, state.y, state.z = nx, ny, nz
            grow_bounds(nx, ny, nz)
            total_distance += dist
            if e_delta > 0:
                total_extrude += e_delta
            travel = dist if dist > 1e-9 else abs(e_delta)
            if state.f > 0 and travel > 0:
                est_time_s += travel / (state.f / 60.0)
            move_count += 1
            timeline.append({"line": lineno, "cmd": cmd, "action": "move"})
        elif cmd == "G90":
            state.absolute_xyz = True
            timeline.append({"line": lineno, "cmd": cmd, "action": "absolute XYZ"})
        elif cmd == "G91":
            state.absolute_xyz = False
            timeline.append({"line": lineno, "cmd": cmd, "action": "relative XYZ"})
        elif cmd == "M82":
            state.absolute_e = True
            timeline.append({"line": lineno, "cmd": cmd, "action": "absolute E"})
        elif cmd == "M83":
            state.absolute_e = False
            timeline.append({"line": lineno, "cmd": cmd, "action": "relative E"})
        elif cmd == "G92":
            for letter, attr in (("X", "x"), ("Y", "y"), ("Z", "z"), ("E", "e")):
                if letter in words:
                    setattr(state, attr, words[letter])
            timeline.append({"line": lineno, "cmd": cmd, "action": "set position"})
        elif cmd == "G28":
            # Home → model as origin (real homing goes to the endstop position).
            for letter, attr in (("X", "x"), ("Y", "y"), ("Z", "z")):
                if not words or letter in words:
                    setattr(state, attr, 0.0)
            grow_bounds(state.x, state.y, state.z)
            timeline.append({"line": lineno, "cmd": cmd, "action": "home"})
        else:
            if cmd not in seen_unknown:
                seen_unknown.add(cmd)
                warnings.append(f"Unsupported command '{cmd}' (line {lineno}) — skipped")

    if move_count == 0:  # no moves → collapse the seeded infinities to a zero box
        bounds = dict.fromkeys(bounds, 0.0)

    return {
        "segments": segments,
        "path2d": path2d,
        "timeline": timeline,
        "bounds": {k: round(v, 4) for k, v in bounds.items()},
        "total_distance_mm": round(total_distance, 3),
        "total_extrude_mm": round(total_extrude, 4),
        "est_time_s": round(est_time_s, 2),
        "move_count": move_count,
        "command_count": len(timeline),
        "warnings": warnings,
        "violations": violations,
        "limits": limits if isinstance(limits, dict) else None,
    }
