"""Round-trip Klipper INI engine — the Track A foundation for config-editing widgets.

Klipper's ``printer.cfg`` is an INI-like dialect with a few quirks the stdlib
``configparser`` mangles, so this engine parses and re-emits it losslessly:

* ``[section name]`` headers where the name may contain spaces (e.g. ``stepper_x``,
  ``tmc2209 stepper_x``).
* ``key: value`` and ``key = value`` params — the separator is preserved per param.
* Full-line comments (``#``/``;`` lines) and inline comments (`` #`` after a value).
* Blank lines and arbitrary indentation, kept verbatim.
* Multi-line values: continuation lines indented under a key (Klipper's ``gcode:`` /
  ``points:`` style) are folded into the owning param's value.
* The auto-generated ``#*# <---------- SAVE_CONFIG ---------->`` block at the tail of a
  saved config — its ``#*#`` lines are kept as raw section content, never reformatted.

The contract that matters: ``dump(parse(text)) == text`` for representative configs.
Each section/param caches its original ``raw`` text and is re-emitted verbatim unless a
caller mutates it, so untouched regions survive a round trip byte-for-byte.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

#: Marks the start of Klipper's auto-saved (``SAVE_CONFIG``) block.
SAVE_CONFIG_MARKER = "#*#"


@dataclass
class ConfigParam:
    """A single ``key: value`` (or ``key = value``) entry inside a section.

    ``raw`` holds the exact source lines (including any continuation lines and the inline
    comment) so an unmodified param re-emits verbatim.
    """

    key: str
    value: str
    separator: str = ":"
    comment: str | None = None
    raw: str | None = None


@dataclass
class ConfigSection:
    """A ``[header]`` block: its params plus any comment/blank lines that lead it.

    ``header`` is the full text between the brackets (e.g. ``tmc2209 stepper_x``); ``name``
    is the part after the first token (``stepper_x``) or empty for single-token headers.
    ``raw_lines`` caches the section's exact source for verbatim re-emit.
    """

    header: str
    name: str = ""
    params: list[ConfigParam] = field(default_factory=list)
    header_comments: list[str] = field(default_factory=list)
    raw_lines: list[str] = field(default_factory=list)

    def get(self, key: str) -> ConfigParam | None:
        """First param matching ``key`` (case-insensitive), or ``None``."""
        lowered = key.lower()
        return next((p for p in self.params if p.key.lower() == lowered), None)

    def value(self, key: str, default: str | None = None) -> str | None:
        """Convenience: the value of ``key`` (case-insensitive) or ``default``."""
        param = self.get(key)
        return param.value if param is not None else default


@dataclass
class ConfigFile:
    """A parsed config: ordered sections plus any comment/blank lines before the first."""

    sections: list[ConfigSection] = field(default_factory=list)
    leading_comments: list[str] = field(default_factory=list)

    def get(self, header: str) -> ConfigSection | None:
        """First section whose ``header`` matches (case-insensitive), or ``None``."""
        lowered = header.lower()
        return next((s for s in self.sections if s.header.lower() == lowered), None)


# ── parsing ──────────────────────────────────────────────────────────────────
def _split_header(header: str) -> tuple[str, str]:
    """Split a header into ``(type, name)`` on the first run of whitespace."""
    parts = header.split(None, 1)
    if len(parts) == 2:
        return parts[0], parts[1].strip()
    return header, ""


def _is_blank_or_comment(line: str) -> bool:
    stripped = line.strip()
    return stripped == "" or stripped.startswith(("#", ";"))


def _is_continuation(line: str) -> bool:
    """A non-blank line that is indented and is not itself a comment line."""
    if line.strip() == "":
        return False
    if not (line.startswith((" ", "\t"))):
        return False
    return not line.lstrip().startswith(("#", ";"))


def _split_inline_comment(value: str) -> tuple[str, str | None]:
    """Split a value on its inline comment (`` #`` or `` ;``), respecting that a comment
    char only starts a comment when preceded by whitespace (Klipper's rule)."""
    for idx in range(1, len(value)):
        if value[idx] in "#;" and value[idx - 1] in " \t":
            return value[:idx].rstrip(), value[idx:]
    return value, None


def _parse_param(line: str) -> tuple[str, str, str, str | None] | None:
    """Parse a ``key: value`` line into ``(key, value, separator, comment)``.

    Returns ``None`` if the line has no ``:``/``=`` separator.
    """
    colon = line.find(":")
    equals = line.find("=")
    if colon == -1 and equals == -1:
        return None
    if colon == -1:
        sep_idx, separator = equals, "="
    elif equals == -1:
        sep_idx, separator = colon, ":"
    else:
        sep_idx, separator = (colon, ":") if colon < equals else (equals, "=")
    key = line[:sep_idx].strip()
    if key == "":
        return None
    rest = line[sep_idx + 1 :]
    value_part, comment = _split_inline_comment(rest)
    return key, value_part.strip(), separator, comment


def parse(text: str) -> ConfigFile:
    """Parse Klipper config ``text`` into a :class:`ConfigFile`, preserving order and raw text."""
    lines = text.splitlines(keepends=True)
    cfg = ConfigFile()
    current: ConfigSection | None = None
    pending_comments: list[str] = []
    current_param: ConfigParam | None = None
    in_save_config = False

    def flush_param() -> None:
        nonlocal current_param
        current_param = None

    i = 0
    while i < len(lines):
        raw_line = lines[i]
        line = raw_line.rstrip("\n").rstrip("\r")
        stripped = line.strip()

        # Once inside the SAVE_CONFIG block everything is kept as raw section content.
        if in_save_config and current is not None:
            current.raw_lines.append(raw_line)
            i += 1
            continue

        if stripped.startswith(SAVE_CONFIG_MARKER):
            # Begin the auto-saved tail: treat it as its own pseudo-section so its
            # ``#*#`` lines round-trip untouched.
            flush_param()
            section = ConfigSection(header=SAVE_CONFIG_MARKER, name="")
            section.header_comments = pending_comments
            section.raw_lines = [raw_line]
            pending_comments = []
            cfg.sections.append(section)
            current = section
            in_save_config = True
            i += 1
            continue

        # Continuation line for a multi-line value.
        if current_param is not None and _is_continuation(line):
            current_param.value = current_param.value + "\n" + line
            current_param.raw = (current_param.raw or "") + raw_line
            if current is not None:
                current.raw_lines.append(raw_line)
            i += 1
            continue

        if stripped.startswith("[") and stripped.endswith("]"):
            flush_param()
            header = stripped[1:-1].strip()
            section = ConfigSection(header=header)
            section.header, section.name = header, _split_header(header)[1]
            section.header_comments = pending_comments
            section.raw_lines = [raw_line]
            pending_comments = []
            cfg.sections.append(section)
            current = section
            i += 1
            continue

        if _is_blank_or_comment(line):
            flush_param()
            if current is None:
                cfg.leading_comments.append(raw_line)
            else:
                current.raw_lines.append(raw_line)
            i += 1
            continue

        # A key/value line within a section.
        parsed = _parse_param(line)
        if parsed is not None and current is not None:
            key, value, separator, comment = parsed
            param = ConfigParam(
                key=key, value=value, separator=separator, comment=comment, raw=raw_line
            )
            current.params.append(param)
            current.raw_lines.append(raw_line)
            current_param = param
            i += 1
            continue

        # Anything else (e.g. a stray line before the first section) is kept verbatim.
        flush_param()
        if current is None:
            cfg.leading_comments.append(raw_line)
        else:
            current.raw_lines.append(raw_line)
        i += 1

    return cfg


# ── dumping ──────────────────────────────────────────────────────────────────
def _dump_section(section: ConfigSection) -> str:
    """Re-emit a section: verbatim from ``raw_lines`` when present, else rebuilt."""
    if section.raw_lines:
        return "".join(section.raw_lines)

    out: list[str] = list(section.header_comments)
    out.append(f"[{section.header}]\n")
    for param in section.params:
        out.append(_dump_param(param))
    return "".join(out)


def _dump_param(param: ConfigParam) -> str:
    """Re-emit a param: verbatim from ``raw`` when present, else rebuilt."""
    if param.raw is not None:
        return param.raw
    sep = f" {param.separator} " if param.separator else " "
    line = f"{param.key}{sep}{param.value}"
    if param.comment:
        line = f"{line} {param.comment.lstrip()}"
    return line + "\n"


def dump(cfg: ConfigFile) -> str:
    """Serialize a :class:`ConfigFile` back to text.

    Untouched sections (those still carrying their ``raw_lines``) re-emit verbatim, so
    ``dump(parse(text)) == text`` for representative configs.
    """
    out: list[str] = list(cfg.leading_comments)
    for section in cfg.sections:
        out.append(_dump_section(section))
    return "".join(out)


# ── validation ───────────────────────────────────────────────────────────────
def validate(cfg: ConfigFile) -> list[dict[str, Any]]:
    """Light structural checks. Returns a list of ``{level, message, section?, line?}``.

    Only reports things that are unambiguously wrong regardless of section schema:
    duplicate section headers, empty section names, and params outside any section.
    """
    issues: list[dict[str, Any]] = []

    seen: dict[str, int] = {}
    for section in cfg.sections:
        if section.header == SAVE_CONFIG_MARKER:
            continue
        if section.header.strip() == "":
            issues.append({"level": "error", "message": "Section with an empty header."})
            continue
        lowered = section.header.lower()
        seen[lowered] = seen.get(lowered, 0) + 1

    for header, count in seen.items():
        if count > 1:
            issues.append(
                {
                    "level": "error",
                    "message": f"Duplicate section header '[{header}]' ({count} times).",
                    "section": header,
                }
            )

    # A param outside any section: only possible if leading_comments holds a key/value line.
    for raw in cfg.leading_comments:
        line = raw.strip()
        if line == "" or line.startswith(("#", ";", "[")):
            continue
        if _parse_param(line) is not None:
            issues.append(
                {
                    "level": "warning",
                    "message": f"Parameter outside any section: '{line}'.",
                }
            )

    return issues
