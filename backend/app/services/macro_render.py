"""Macro expansion for the G-code simulator — renders Klipper's own macro template dialect.

Klipper macros are Jinja2 templates with **single-brace** value expressions (``{ params.X }``) and
``{% … %}`` control flow. This module renders that exact dialect in a
:class:`~jinja2.sandbox.SandboxedEnvironment` (same delimiters Klipper configures), so the offline
simulator can expand loops, conditionals and ``{% set %}`` the way the printer would.

Missing ``printer`` state is tolerated (a :class:`~jinja2.ChainableUndefined` renders to nothing and
chains through attribute access), since an offline render has no live machine. If a template can't
render at all (e.g. arithmetic on absent printer state), it falls back to the dependency-free
literal substitution of ``{ params.X | default(…) }`` so a partial preview still works — with a
warning. ``render`` returns ``(text, warnings)``.
"""

from __future__ import annotations

import math
import re

from jinja2 import ChainableUndefined
from jinja2.sandbox import SandboxedEnvironment

#: A ``{ ... }`` value expression (not ``{% ... %}`` and not ``{{ ... }}``).
_EXPR = re.compile(r"\{(?!%)\s*([^{}]*?)\s*\}")
#: ``default(VALUE)`` (optionally with extra args) inside an expression's filter chain.
_DEFAULT = re.compile(r"default\(\s*([^,)]*?)\s*(?:,[^)]*)?\)", re.IGNORECASE)
#: A ``params.NAME`` / ``params['NAME']`` / bare ``NAME`` variable reference.
_VAR = re.compile(r"^(?:params\s*[.\[]\s*['\"]?)?([A-Za-z_][A-Za-z0-9_]*)")

#: Klipper configures Jinja with single-brace value delimiters; mirror that exactly. Sandboxed so a
#: user macro can't reach dangerous attributes during the offline render.
_ENV = SandboxedEnvironment(
    block_start_string="{%",
    block_end_string="%}",
    variable_start_string="{",
    variable_end_string="}",
    comment_start_string="{#",
    comment_end_string="#}",
    undefined=ChainableUndefined,
    autoescape=False,
)


def _noop(*_args: object, **_kwargs: object) -> str:
    """Stub for Klipper's ``action_*`` side-effect globals — they produce no G-code text."""
    return ""


def _context(params: dict[str, str], printer: dict[str, object] | None) -> dict[str, object]:
    return {
        "params": dict(params),
        "printer": printer if isinstance(printer, dict) else {},
        "math": math,
        "action_respond_info": _noop,
        "action_raise_error": _noop,
        "action_emergency_stop": _noop,
        "action_call_remote_method": _noop,
        "action_log": _noop,
    }


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
    var_match = _VAR.match(expr)
    name = var_match.group(1) if var_match else None
    default_match = _DEFAULT.search(expr)
    default = _unquote(default_match.group(1)) if default_match else None

    value: str | None = None
    if name is not None:
        for key in (name, name.upper(), name.lower()):
            if key in params:
                value = str(params[key])
                break
    if value is None:
        value = default
    if value is None:
        return None
    for part in expr.split("|")[1:]:
        part = part.strip()
        if part.lower().startswith("default"):
            continue
        value = _apply_filter(value, part)
    return value


def render_literal(gcode: str, params: dict[str, str] | None = None) -> tuple[str, list[str]]:
    """The dependency-free fallback: substitute ``{ params.X | default(…) }`` only; leaves
    ``{% … %}`` control flow and unresolved expressions intact (each warned once)."""
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


def render(
    gcode: str,
    params: dict[str, str] | None = None,
    printer: dict[str, object] | None = None,
) -> tuple[str, list[str]]:
    """Render a Klipper macro body with real (sandboxed) Jinja → ``(text, warnings)``.

    Expands ``{ … }`` expressions and ``{% … %}`` control flow against ``params`` (and an optional
    ``printer`` state map; missing state renders to nothing). Falls back to literal substitution —
    with a warning — if the template raises (e.g. it depends on live printer state this offline
    render doesn't have).
    """
    params = params or {}
    try:
        rendered = _ENV.from_string(gcode).render(**_context(params, printer))
        return rendered, []
    except Exception as exc:  # any render failure degrades to the literal subset
        text, warns = render_literal(gcode, params)
        note = f"Full macro render failed ({type(exc).__name__}); showing a literal substitution."
        return text, [note, *warns]
