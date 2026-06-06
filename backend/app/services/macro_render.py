"""Macro variable substitution for the G-code simulator (dependency-free).

Klipper macros are Jinja2 templates. The simulator can't reproduce Klipper's full runtime
(printer state, loops, conditionals) without the live machine, so this module handles the
*common, safe* subset: ``{ ... }`` value expressions that reference macro ``params`` with an
optional ``default`` — e.g. ``G1 X{ params.X | default(100) } F{ params.F|default(3000) }``.

Resolved values are substituted; unresolved expressions are left intact and reported as a
warning. ``{% ... %}`` control flow (loops / conditionals) is **not** evaluated — a single
warning is emitted when it is present (full Jinja is future work, and would need the jinja2
engine plus a model of the printer's runtime state).
"""

from __future__ import annotations

import re

#: A ``{ ... }`` value expression (not ``{% ... %}`` and not ``{{ ... }}``).
_EXPR = re.compile(r"\{(?!%)\s*([^{}]*?)\s*\}")
#: ``default(VALUE)`` (optionally with extra args) inside an expression's filter chain.
_DEFAULT = re.compile(r"default\(\s*([^,)]*?)\s*(?:,[^)]*)?\)", re.IGNORECASE)
#: A ``params.NAME`` / ``params['NAME']`` / bare ``NAME`` variable reference.
_VAR = re.compile(r"^(?:params\s*[.\[]\s*['\"]?)?([A-Za-z_][A-Za-z0-9_]*)")


def _unquote(text: str) -> str:
    text = text.strip()
    if len(text) >= 2 and text[0] in "'\"" and text[-1] == text[0]:
        return text[1:-1]
    return text


def _apply_filter(value: str, name: str) -> str:
    name = name.strip().lower()
    try:
        if name == "int":
            return str(int(float(value)))
        if name == "float":
            return str(float(value))
    except ValueError:
        return value
    if name == "upper":
        return value.upper()
    if name == "lower":
        return value.lower()
    return value


def _resolve(expr: str, params: dict[str, str]) -> str | None:
    """Resolve a single ``{ ... }`` expression to a string, or ``None`` if unresolved."""
    # Pull the variable name and an optional default out of the (possibly filtered) expression.
    var_match = _VAR.match(expr)
    name = var_match.group(1) if var_match else None
    default_match = _DEFAULT.search(expr)
    default = _unquote(default_match.group(1)) if default_match else None

    value: str | None = None
    if name is not None:
        # Case-insensitive lookup (Klipper params are conventionally upper-case).
        for key in (name, name.upper(), name.lower()):
            if key in params:
                value = str(params[key])
                break
    if value is None:
        value = default
    if value is None:
        return None

    # Apply any trailing simple filters (skip the default() filter itself).
    for part in expr.split("|")[1:]:
        part = part.strip()
        if part.lower().startswith("default"):
            continue
        value = _apply_filter(value, part)
    return value


def render(gcode: str, params: dict[str, str] | None = None) -> tuple[str, list[str]]:
    """Substitute ``{ params.X | default(...) }`` expressions; return ``(text, warnings)``.

    Pure: no Jinja engine, no printer state. ``{% ... %}`` control flow is left untouched
    (with a warning); unresolved value expressions are left intact (each warned once).
    """
    params = params or {}
    warnings: list[str] = []
    if "{%" in gcode:
        warnings.append(
            "Jinja control flow ({% … %}) is not simulated — those lines may be skipped."
        )

    unresolved: set[str] = set()

    def sub(match: re.Match[str]) -> str:
        expr = match.group(1).strip()
        if not expr:
            return match.group(0)
        value = _resolve(expr, params)
        if value is None:
            if expr not in unresolved:
                unresolved.add(expr)
                warnings.append(f"Unresolved expression {{ {expr} }} — left as-is.")
            return match.group(0)
        return value

    return _EXPR.sub(sub, gcode), warnings
