"""Config-file service — read the live Klipper config for the Config Editor widget.

Reads ``printer.cfg`` (and its includes) from Moonraker's ``config`` file root, parses
each file with the round-trip :mod:`klipper_config` engine, and returns a structured,
JSON-friendly view (sections → params) plus light validation issues.

Also the gated write path: ``save_config_file`` backs up then overwrites a file, and
``restart_firmware`` applies it — both refused while the printer is busy.
"""

from __future__ import annotations

import datetime
from typing import Any

import httpx

from app.services import klipper_config
from app.services.klipper_config import ConfigFile, ConfigParam, ConfigSection
from app.services.moonraker_client import MoonrakerClient

#: File extensions treated as editable Klipper config files.
_CONFIG_SUFFIXES = (".cfg", ".conf")

#: Subdirectory (under the config root) where pre-save backups are kept.
_BACKUP_DIR = "filamind-backups"


class ConfigBusyError(RuntimeError):
    """Raised when a write/restart is refused because the printer is busy."""


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


async def gather_drift(client: MoonrakerClient, filename: str) -> dict[str, Any]:
    """Compare the on-disk file to what Klipper is actually running (the live ``configfile``).

    Klipper runs the LOADED config, which can diverge from disk — an edit not yet restarted, or a
    pending ``SAVE_CONFIG`` Klipper computed but hasn't written. Returns the pending flag, Klipper's
    own parse warnings, and a per-param drift list (single-line params whose on-disk value differs
    from the live one). Degrades to ``reachable=false`` when Moonraker is down.
    """
    _reject_unsafe(filename)
    try:
        configfile = await client.query_objects(["configfile"])
        raw = await client.get_file_text(filename, root="config")
    except httpx.HTTPError:
        return {
            "reachable": False,
            "save_config_pending": False,
            "pending_items": {},
            "warnings": [],
            "drifts": [],
        }
    cfobj = configfile.get("configfile")
    cfobj = cfobj if isinstance(cfobj, dict) else {}
    live_raw = cfobj.get("config")
    live: dict[str, Any] = live_raw if isinstance(live_raw, dict) else {}

    drifts: list[dict[str, str]] = []
    for sec in klipper_config.parse(raw).sections:
        if sec.header == klipper_config.SAVE_CONFIG_MARKER:
            continue  # the SAVE_CONFIG block is Klipper-managed — never diff it
        live_sec = live.get(sec.header.strip().lower())
        if not isinstance(live_sec, dict):
            continue
        for param in sec.params:
            disk = (param.value or "").strip()
            raw_live = live_sec.get(param.key.strip().lower())
            if raw_live is None:
                continue
            live_val = str(raw_live).strip()
            if "\n" in disk or "\n" in live_val:
                continue  # skip multi-line values (gcode / bed_mesh points) — too fuzzy to diff
            if disk and live_val and disk != live_val:
                drifts.append(
                    {"section": sec.header, "key": param.key, "disk": disk, "live": live_val}
                )

    return {
        "reachable": True,
        "save_config_pending": bool(cfobj.get("save_config_pending")),
        "pending_items": cfobj.get("save_config_pending_items") or {},
        "warnings": [str(w) for w in (cfobj.get("warnings") or [])],
        "drifts": drifts,
    }


def adopt_param(content: str, section: str, key: str, value: str) -> str:
    """Set one param's value in ``content`` via the round-trip engine and return the new text.

    Pure (no I/O): only the target param's line is rewritten; every other param re-emits verbatim.
    Returns ``content`` unchanged if the param isn't found.
    """
    cfg = klipper_config.parse(content)
    target_sec = section.strip().lower()
    target_key = key.strip().lower()
    for sec in cfg.sections:
        if sec.header.strip().lower() != target_sec:
            continue
        for param in sec.params:
            if param.key.strip().lower() == target_key:
                param.value = value
                # Rebuild just this line in Klipper's convention (``key: value`` / ``key = value``),
                # preserving any inline comment; every other param keeps its verbatim ``raw``.
                sep = " = " if param.separator == "=" else ": "
                line = f"{param.key}{sep}{value}"
                if param.comment:
                    line = f"{line} {param.comment.lstrip()}"
                param.raw = line + "\n"
                sec.raw_lines = []  # rebuild the section so the new value takes effect
                return klipper_config.dump(cfg)
    return content


async def _is_busy(client: MoonrakerClient) -> bool:
    """True while the printer is printing, paused, or in error — block writes and restarts
    then. Reads ``print_stats.state`` (mirrors the Motor Drivers write guard)."""
    status = await client.query_objects(["print_stats"])
    stats = status.get("print_stats")
    if not isinstance(stats, dict):
        return False
    return str(stats.get("state", "")).lower() in ("printing", "paused", "error")


def _backup_path(filename: str, now: datetime.datetime) -> str:
    """A timestamped backup path under the backup subdir (kept out of the .cfg/.conf list)."""
    flat = filename.replace("/", "_")
    stamp = now.strftime("%Y%m%d-%H%M%S")
    return f"{_BACKUP_DIR}/{flat}.{stamp}.bak"


async def save_config_file(client: MoonrakerClient, filename: str, content: str) -> dict[str, Any]:
    """Back up the current file, then overwrite it with ``content``. Read-after-parse only —
    never auto-restarts (that's a separate, explicit action).

    Refuses while the printer is busy (printing / paused / error). The existing file (if any)
    is copied to ``filamind-backups/`` first, so a bad edit is always recoverable.

    Raises:
        ValueError: if ``filename`` is not a safe in-root path.
        ConfigBusyError: if the printer is busy.
        httpx.HTTPError: if Moonraker is unreachable or rejects the write.
    """
    _reject_unsafe(filename)
    if await _is_busy(client):
        raise ConfigBusyError("Refusing to write the config while the printer is busy.")

    # Back up the current content first (best-effort: a brand-new file has nothing to back up).
    backup: str | None = None
    try:
        current = await client.get_file_text(filename, root="config")
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code != 404:
            raise
        current = None
    if current is not None:
        backup = _backup_path(filename, datetime.datetime.now())
        await client.upload_file(backup, current, root="config")

    await client.upload_file(filename, content, root="config")

    view = build_file_view(filename, content)
    return {
        "ok": True,
        "filename": filename,
        "backup": backup,
        "issues": view["issues"],
        "section_count": view["section_count"],
    }


async def restart_firmware(client: MoonrakerClient) -> dict[str, Any]:
    """Trigger ``FIRMWARE_RESTART`` so a saved config takes effect. Refused while busy.

    Raises:
        ConfigBusyError: if the printer is busy.
        httpx.HTTPError: if Moonraker is unreachable or the restart fails.
    """
    if await _is_busy(client):
        raise ConfigBusyError("Refusing to restart while the printer is busy.")
    await client.firmware_restart()
    return {"ok": True}
