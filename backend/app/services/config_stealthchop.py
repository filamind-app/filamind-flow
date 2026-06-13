"""Surgical, marker-tagged edits to a printer.cfg's ``[<driver> extruder]`` StallGuard mode.

The Max-Flow test's StallGuard preflight reads the *config* (``configfile.settings``), so for an
SG4 extruder (TMC2209/2240) sitting in SpreadCycle the only way to let the test run is to add a
``stealthchop_threshold`` to the extruder's TMC section and ``FIRMWARE_RESTART``. These helpers do
that as a **temporary, reversible** edit: the line we add carries a unique marker comment so we
only ever touch our own line — never the user's settings — and the revert simply **comments it
out** (leaving a visible, inert trace), so the printer.cfg is restored after the test.

Everything here is pure text manipulation and unit-testable; the actual file write + restart live
in :mod:`app.services.max_flow_service`.
"""

from __future__ import annotations

#: Unique trailing comment that tags the line FilaMind added, so enable/revert only touch our line.
MARKER = "# filamind-maxflow"


def _section_bounds(lines: list[str], header: str) -> tuple[int, int] | None:
    """``(first_body_index, end_exclusive)`` of the ``header`` section, or None if absent.

    The header must be a real (uncommented) section line equal to ``header`` once stripped; the
    section body runs until the next uncommented ``[...]`` header or end of file. SAVE_CONFIG's
    ``#*# [...]`` autosave lines are commented, so they never match.
    """
    start: int | None = None
    for i, line in enumerate(lines):
        stripped = line.strip()
        if start is None:
            if stripped == header:
                start = i + 1
        elif stripped.startswith("[") and not stripped.startswith("#"):
            return (start, i)
    if start is not None:
        return (start, len(lines))
    return None


def apply_stealthchop(cfg_text: str, driver: str, value: int) -> tuple[str, bool]:
    """Ensure an **active** marker-tagged ``stealthchop_threshold`` in ``[<driver> extruder]``.

    Returns ``(new_text, changed)``. No change (``changed=False``) when the section is absent or
    the user already has their *own* active ``stealthchop_threshold`` (we never override it). A
    previously commented-out marker line is reactivated rather than duplicated.
    """
    header = f"[{driver.lower()} extruder]"
    lines = cfg_text.split("\n")
    bounds = _section_bounds(lines, header)
    if bounds is None:
        return cfg_text, False
    start, end = bounds
    our_line = f"stealthchop_threshold: {value}  {MARKER}"
    # Scan the whole section before deciding: a user's own active line must win even if a
    # commented marker from a previous run sits above it (otherwise we'd produce two active lines —
    # a fatal duplicate-option config error). Remember our marker line to reactivate, if present.
    marker_idx: int | None = None
    for i in range(start, end):
        stripped = lines[i].strip()
        if MARKER in stripped and "stealthchop_threshold" in stripped:
            if marker_idx is None:
                marker_idx = i
            continue
        if stripped.startswith("stealthchop_threshold") and not stripped.startswith("#"):
            return cfg_text, False  # the user has their own active line — never override it
    if marker_idx is not None:
        lines[marker_idx] = our_line  # reactivate / refresh our own line (no duplicate)
        return "\n".join(lines), True
    lines.insert(start, our_line)
    return "\n".join(lines), True


def comment_stealthchop(cfg_text: str, driver: str) -> tuple[str, bool]:
    """Comment out the **active** marker-tagged line we added (idempotent).

    Returns ``(new_text, changed)``. Only ever touches a line carrying our :data:`MARKER`, so the
    user's own config is never altered. Already-commented or missing → ``changed=False``.
    """
    header = f"[{driver.lower()} extruder]"
    lines = cfg_text.split("\n")
    bounds = _section_bounds(lines, header)
    if bounds is None:
        return cfg_text, False
    start, end = bounds
    changed = False
    for i in range(start, end):
        stripped = lines[i].strip()
        if (
            MARKER in stripped
            and "stealthchop_threshold" in stripped
            and not stripped.startswith("#")
        ):
            lines[i] = "# " + lines[i].lstrip()
            changed = True
    return "\n".join(lines), changed
