"""Config-file service — read the live Klipper config for the Config Editor widget.

Reads ``printer.cfg`` (and its includes) from Moonraker's ``config`` file root, parses
each file with the round-trip :mod:`klipper_config` engine, and returns a structured,
JSON-friendly view (sections → params) plus light validation issues.

Read-only: this module never writes. The gated save path lands in a later phase.
"""

from __future__ import annotations

from typing import Any

from app.services import klipper_config
from app.services.klipper_config import ConfigFile, ConfigParam, ConfigSection
from app.services.moonraker_client import MoonrakerClient

#: File extensions treated as editable Klipper config files.
_CONFIG_SUFFIXES = (".cfg", ".conf")


def _param_view(param: ConfigParam) -> dict[str, Any]:
    return {
        "key": param.key,
        "value": param.value,
        "separator": param.separator,
        "comment": param.comment,
    }


def _section_type(header: str) -> str:
    """The first token of a header (``tmc2209 stepper_x`` → ``tmc2209``)."""
    return header.split(None, 1)[0] if header.strip() else ""


def _section_view(section: ConfigSection) -> dict[str, Any]:
    return {
        "header": section.header,
        "type": _section_type(section.header),
        "name": section.name,
        "is_save_config": section.header == klipper_config.SAVE_CONFIG_MARKER,
        "params": [_param_view(p) for p in section.params],
    }


def build_file_view(filename: str, raw: str) -> dict[str, Any]:
    """Parse ``raw`` config text into the structured editor view (pure, no I/O)."""
    cfg: ConfigFile = klipper_config.parse(raw)
    return {
        "filename": filename,
        "raw": raw,
        "sections": [_section_view(s) for s in cfg.sections],
        "section_count": sum(
            1 for s in cfg.sections if s.header != klipper_config.SAVE_CONFIG_MARKER
        ),
        "issues": klipper_config.validate(cfg),
    }


def _is_config_file(path: str) -> bool:
    return path.lower().endswith(_CONFIG_SUFFIXES)


def _reject_unsafe(filename: str) -> None:
    """Guard against path traversal — only plain paths within the config root are allowed."""
    parts = filename.split("/")
    if filename.startswith("/") or filename == "" or ".." in parts:
        raise ValueError(f"invalid config path: {filename!r}")


async def list_config_files(client: MoonrakerClient) -> list[dict[str, Any]]:
    """List editable config files (``.cfg`` / ``.conf``) under Moonraker's ``config`` root."""
    entries = await client.list_files("config")
    files = [
        {"path": path, "size": entry.get("size"), "modified": entry.get("modified")}
        for entry in entries
        if isinstance((path := str(entry.get("path", ""))), str) and _is_config_file(path)
    ]
    files.sort(key=lambda f: str(f["path"]))
    return files


async def read_config_file(client: MoonrakerClient, filename: str) -> dict[str, Any]:
    """Fetch one config file and parse it into the structured editor view.

    Raises:
        ValueError: if ``filename`` is not a safe in-root path.
        httpx.HTTPError: if Moonraker is unreachable or the file is missing.
    """
    _reject_unsafe(filename)
    raw = await client.get_file_text(filename, root="config")
    return build_file_view(filename, raw)
