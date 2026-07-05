"""Pure text edits for Klipper/Moonraker config files - no filesystem, no host.

Setup needs to register a component with Moonraker's update manager (a ``[update_manager <key>]``
block in ``moonraker.conf``) and wire a config add-on in (an ``[include <file>]`` line in
``printer.cfg``), and to reverse both on removal. Keeping the text transforms pure makes them unit
testable and lets the caller own the backup + write + service-restart (see setup_manager).

Every function returns ``(new_text, changed)`` so the caller can skip a needless write + restart.
"""

from __future__ import annotations


def _section_span(lines: list[str], header: str) -> tuple[int, int] | None:
    """The ``[start, end)`` line span of the ``[header]`` section (header line through the line
    before the next ``[...]`` at column 0, or EOF), or None if the section isn't present."""
    start = next((i for i, ln in enumerate(lines) if ln.strip() == f"[{header}]"), None)
    if start is None:
        return None
    end = start + 1
    while end < len(lines) and not lines[end].lstrip().startswith("["):
        end += 1
    return start, end


def upsert_update_manager(text: str, key: str, body: list[str]) -> tuple[str, bool]:
    """Add or replace the ``[update_manager <key>]`` block with ``body`` (lines without the header).
    An existing identical block is a no-op (returns ``changed=False``)."""
    header = f"update_manager {key}"
    block = [f"[{header}]", *body]
    lines = text.splitlines()
    span = _section_span(lines, header)
    if span is None:
        # Append as a new trailing section, with a blank separator if the file isn't empty.
        prefix = lines + ([""] if lines and lines[-1].strip() else [])
        new = "\n".join(prefix + block) + "\n"
        return new, True
    start, end = span
    if lines[start:end] == block:
        return text, False
    lines[start:end] = block
    return "\n".join(lines) + ("\n" if text.endswith("\n") else ""), True


def drop_update_manager(text: str, key: str) -> tuple[str, bool]:
    """Remove the ``[update_manager <key>]`` block (and a single trailing blank line it owned)."""
    lines = text.splitlines()
    span = _section_span(lines, f"update_manager {key}")
    if span is None:
        return text, False
    start, end = span
    if end < len(lines) and not lines[end].strip():
        end += 1  # swallow one blank separator line so we don't pile up gaps
    del lines[start:end]
    return ("\n".join(lines) + "\n" if lines else ""), True


def _include_line(file: str) -> str:
    return f"[include {file}]"


def has_include(text: str, file: str) -> bool:
    target = _include_line(file)
    return any(ln.strip() == target for ln in text.splitlines())


def add_include(text: str, file: str) -> tuple[str, bool]:
    """Add ``[include <file>]`` near the top (Klipper reads includes in order; early is safest for
    settings/override files). No-op if already present."""
    if has_include(text, file):
        return text, False
    line = _include_line(file)
    return (line + "\n" + text) if text else (line + "\n"), True


def drop_include(text: str, file: str) -> tuple[str, bool]:
    """Remove every ``[include <file>]`` line."""
    target = _include_line(file)
    lines = text.splitlines()
    kept = [ln for ln in lines if ln.strip() != target]
    if len(kept) == len(lines):
        return text, False
    return ("\n".join(kept) + "\n" if kept else ""), True
