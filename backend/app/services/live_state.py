"""Shared "live snapshot" accessors for the printer's running state — the ground truth Klipper is
actually executing, read via Moonraker's ``configfile`` object. Backs the Macro Designer's
live-macro import (+ later the bed-envelope overlay) and the Config Editor's disk-vs-live healer.

Pure helpers over the already-fetched ``configfile`` payload; the route owns the (gracefully
degrading) Moonraker fetch so a down printer never raises here.
"""

from __future__ import annotations

import re
from typing import Any

_MACRO_PREFIX = "gcode_macro "
#: A ``{ params.NAME | default(VALUE) }`` expression → (name, default). Mirrors macro_render so the
#: discovered params match what the simulator substitutes.
_PARAM_DEFAULT = re.compile(
    r"params\s*[.\[]\s*['\"]?([A-Za-z_][A-Za-z0-9_]*)['\"]?\]?[^{}]*?\|\s*default\(\s*"
    r"([^,)]*?)\s*(?:,[^)]*)?\)",
    re.IGNORECASE,
)
#: Any ``params.NAME`` reference (to also surface params that have no default).
_PARAM_ANY = re.compile(r"params\s*[.\[]\s*['\"]?([A-Za-z_][A-Za-z0-9_]*)", re.IGNORECASE)


def settings_of(configfile: Any) -> dict[str, Any]:
    """The live ``configfile.settings`` dict (every typed ``[section]``), or ``{}`` if absent."""
    obj = configfile.get("configfile") if isinstance(configfile, dict) else None
    settings = obj.get("settings") if isinstance(obj, dict) else None
    return settings if isinstance(settings, dict) else {}


def _num(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    return float(value) if isinstance(value, (int, float)) else None


def limits_of(toolhead: Any) -> dict[str, Any] | None:
    """The printer's real build envelope + speed cap from the live ``toolhead`` object
    (``axis_minimum/maximum`` [x,y,z(,e)] + ``max_velocity`` mm/s + ``max_accel``), or ``None`` if
    the shape isn't there. Used to ground the offline simulator in THIS machine's bounds."""
    if not isinstance(toolhead, dict):
        return None
    amin = toolhead.get("axis_minimum")
    amax = toolhead.get("axis_maximum")
    if not (
        isinstance(amin, list) and isinstance(amax, list) and len(amin) >= 3 and len(amax) >= 3
    ):
        return None
    lo = [_num(amin[i]) for i in range(3)]
    hi = [_num(amax[i]) for i in range(3)]
    if any(v is None for v in lo) or any(v is None for v in hi):
        return None
    return {
        "min": lo,
        "max": hi,
        "max_velocity": _num(toolhead.get("max_velocity")),
        "max_accel": _num(toolhead.get("max_accel")),
    }


def _unquote(text: str) -> str:
    text = text.strip()
    if len(text) >= 2 and text[0] in "'\"" and text[-1] == text[0]:
        return text[1:-1]
    return text


def _params_of(gcode: str) -> dict[str, str]:
    """Discover ``params.X`` in a macro body, keyed UPPER-case → default value (``""`` if none)."""
    params: dict[str, str] = {}
    for match in _PARAM_DEFAULT.finditer(gcode):
        params[match.group(1).upper()] = _unquote(match.group(2))
    for match in _PARAM_ANY.finditer(gcode):
        params.setdefault(match.group(1).upper(), "")
    return params


def gcode_macros(settings: dict[str, Any]) -> list[dict[str, Any]]:
    """Every ``[gcode_macro NAME]`` in the live config → its body, description, discovered params,
    and initial ``variable_*`` values — sorted by name. Pure over ``settings_of(configfile)``."""
    out: list[dict[str, Any]] = []
    for key, cfg in settings.items():
        if not isinstance(cfg, dict) or not str(key).lower().startswith(_MACRO_PREFIX):
            continue
        name = str(key)[len(_MACRO_PREFIX) :].strip()
        gcode = str(cfg.get("gcode") or "")
        variables = {k[len("variable_") :]: cfg[k] for k in cfg if str(k).startswith("variable_")}
        out.append(
            {
                "name": name,
                "gcode": gcode,
                "description": str(cfg.get("description") or ""),
                "params": _params_of(gcode),
                "variables": variables,
            }
        )
    out.sort(key=lambda m: str(m["name"]).lower())
    return out
