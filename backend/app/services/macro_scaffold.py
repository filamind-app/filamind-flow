"""START_PRINT / END_PRINT scaffold generator — tailored to THIS printer.

Reads the live config (kinematics, build envelope, which leveling sections are configured, whether a
heated bed exists) and emits two ready-to-edit macros whose homing / leveling / mesh / park steps
and prime-line coordinates fit the actual machine — rather than a generic copy-paste a user has to
fix up. Pure ``generate(ctx)`` for testability; ``gather`` owns the (graceful) Moonraker fetch.

The macros are written through the Config Editor's existing gated save (backup + refuse-while-
printing) via ``config_service.append_block`` — this is the Macro Designer's first write path.
"""

from __future__ import annotations

from typing import Any

import httpx

from app.services import live_state
from app.services.moonraker_client import MoonrakerClient


def _round(value: float) -> float:
    return round(value, 1)


def generate(ctx: dict[str, Any]) -> dict[str, Any]:
    """Build START_PRINT + END_PRINT + structured notes from a context dict (pure).

    ``ctx`` keys: ``kinematics`` (str), ``bounds`` ({"min":[x,y,z], "max":[x,y,z]} or None),
    ``leveling`` (list of section types present), ``has_bed`` (bool), ``has_extruder`` (bool).
    """
    bounds = ctx.get("bounds") if isinstance(ctx.get("bounds"), dict) else None
    leveling = [str(s).lower() for s in (ctx.get("leveling") or [])]
    has_bed = bool(ctx.get("has_bed"))
    kinematics = str(ctx.get("kinematics") or "cartesian")

    if bounds and isinstance(bounds.get("min"), list) and isinstance(bounds.get("max"), list):
        mnx, mny = float(bounds["min"][0]), float(bounds["min"][1])
        mxx, mxy = float(bounds["max"][0]), float(bounds["max"][1])
    else:
        mnx, mny, mxx, mxy = 0.0, 0.0, 200.0, 200.0

    # Prime line: a short purge near the front-left corner, clamped inside the envelope.
    px0, py0 = _round(mnx + 5), _round(mny + 5)
    px1 = _round(min(px0 + 50, mxx - 5))
    park_x, park_y = _round((mnx + mxx) / 2), _round(mxy - 5)

    notes: list[dict[str, Any]] = [{"key": "kinematics", "params": {"k": kinematics}}]
    if bounds:
        notes.append(
            {
                "key": "bounds",
                "params": {
                    "x0": _round(mnx),
                    "y0": _round(mny),
                    "x1": _round(mxx),
                    "y1": _round(mxy),
                },
            }
        )

    # Leveling line: the strongest configured method wins; mesh is separate.
    if "quad_gantry_level" in leveling:
        level_line = "    QUAD_GANTRY_LEVEL"
        notes.append({"key": "leveling_qgl", "params": {}})
    elif "z_tilt" in leveling:
        level_line = "    Z_TILT_ADJUST"
        notes.append({"key": "leveling_ztilt", "params": {}})
    else:
        level_line = "    # (no quad_gantry_level / z_tilt configured)"
        notes.append({"key": "leveling_none", "params": {}})

    mesh_line = ""
    if "bed_mesh" in leveling:
        mesh_line = "    BED_MESH_CALIBRATE\n"
        notes.append({"key": "mesh", "params": {}})
    if not has_bed:
        notes.append({"key": "no_bed", "params": {}})

    bed_set = "    M140 S{BED}\n" if has_bed else ""
    bed_wait = "    M190 S{BED}\n" if has_bed else ""
    bed_var = "    {% set BED = params.BED|default(60)|float %}\n" if has_bed else ""

    start = (
        "[gcode_macro START_PRINT]\n"
        "description: Heat, home, level, mesh and prime (generated for this printer)\n"
        "gcode:\n"
        f"{bed_var}"
        "    {% set EXTRUDER = params.EXTRUDER|default(200)|float %}\n"
        f"{bed_set}"
        "    M104 S150                      ; pre-warm nozzle (no ooze while leveling)\n"
        "    G28                            ; home all axes\n"
        f"{level_line}\n"
        f"{bed_wait}"
        f"{mesh_line}"
        "    M109 S{EXTRUDER}               ; wait for full nozzle temp\n"
        "    G90\n"
        "    G92 E0\n"
        f"    G1 X{px0} Y{py0} Z0.3 F3000    ; move to prime start\n"
        f"    G1 X{px1} Y{py0} E15 F1500     ; draw a prime line\n"
        "    G92 E0\n"
    )

    end = (
        "[gcode_macro END_PRINT]\n"
        "description: Cool down, park and disable (generated for this printer)\n"
        "gcode:\n"
        "    M104 S0                        ; nozzle off\n"
        f"{'    M140 S0                        ; bed off' + chr(10) if has_bed else ''}"
        "    M106 S0                        ; part fan off\n"
        "    G91\n"
        "    G1 E-2 F1800                   ; small retract\n"
        "    G1 Z10 F600                    ; lift the nozzle clear\n"
        "    G90\n"
        f"    G1 X{park_x} Y{park_y} F6000   ; park at the front\n"
        "    M84                            ; disable steppers\n"
    )

    return {"start": start, "end": end, "notes": notes}


def context_from_live(configfile: Any, toolhead: Any) -> dict[str, Any]:
    """Derive the generator context from the live ``configfile`` + ``toolhead`` objects (pure)."""
    settings = live_state.settings_of(configfile)
    present = {str(k).split(None, 1)[0].lower() for k in settings}
    printer_raw = settings.get("printer")
    printer: dict[str, Any] = printer_raw if isinstance(printer_raw, dict) else {}
    limits = live_state.limits_of(toolhead)
    return {
        "kinematics": str(printer.get("kinematics") or "cartesian"),
        "bounds": {"min": limits["min"], "max": limits["max"]} if limits else None,
        "leveling": [s for s in ("quad_gantry_level", "z_tilt", "bed_mesh") if s in present],
        "has_bed": "heater_bed" in present,
        "has_extruder": "extruder" in present,
    }


async def gather(client: MoonrakerClient) -> dict[str, Any]:
    """Fetch live state and generate the scaffold. ``reachable=false`` (with a generic fallback
    context) when Moonraker is down so the UI still offers a sensible template."""
    try:
        objs = await client.query_objects(["configfile", "toolhead"])
        reachable = True
    except httpx.HTTPError:
        objs = {}
        reachable = False
    ctx = context_from_live(objs, objs.get("toolhead") if isinstance(objs, dict) else None)
    result = generate(ctx)
    return {"reachable": reachable, "context": ctx, **result}
