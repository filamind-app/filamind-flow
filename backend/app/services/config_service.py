"""Config-file service — read the live Klipper config for the Config Editor widget.

Reads ``printer.cfg`` (and its includes) from Moonraker's ``config`` file root, parses
each file with the round-trip :mod:`klipper_config` engine, and returns a structured,
JSON-friendly view (sections → params) plus light validation issues.

Also the gated write path: ``save_config_file`` backs up then overwrites a file, and
``restart_firmware`` applies it — both refused while the printer is busy.
"""

from __future__ import annotations

import datetime
import posixpath
import re
from typing import Any

import httpx

from app.services import klipper_config
from app.services.klipper_config import ConfigFile, ConfigParam, ConfigSection
from app.services.moonraker_client import MoonrakerClient

#: TMC driver section prefixes — a ``[tmcXXXX NAME]`` must pair with a ``[NAME]`` stepper/extruder.
_TMC_PREFIXES = ("tmc2209", "tmc2208", "tmc2130", "tmc5160", "tmc2660", "tmc2240", "tmc")

#: Section types whose duplicate header across files is not a merge error (``include`` repeats).
_REPEATABLE_TYPES = frozenset({"include"})

#: Candidate names for the active config's root, in priority order — what Klipper actually loads.
_PRIMARY_ROOTS = ("printer.cfg",)

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


async def _read_all_files(client: MoonrakerClient) -> list[tuple[str, str]]:
    """Fetch every editable config file's text. A file that fails to read is skipped (best effort)."""  # noqa: E501
    files = await list_config_files(client)
    out: list[tuple[str, str]] = []
    for f in files:
        path = str(f["path"])
        try:
            out.append((path, await client.get_file_text(path, root="config")))
        except httpx.HTTPError:
            continue
    return out


def _include_targets(cfg: ConfigFile) -> list[str]:
    """Raw ``[include X]`` targets in declaration order (``X`` may be a relative path or a glob)."""
    targets: list[str] = []
    for sec in cfg.sections:
        if _section_type(sec.header) == "include":
            target = sec.header.split(None, 1)[1].strip() if " " in sec.header.strip() else ""
            if target:
                targets.append(target)
    return targets


def _glob_to_regex(pat: str) -> str:
    """Translate a Klipper include glob to a regex where ``*``/``?`` do not cross ``/`` (matching
    :func:`glob.glob` semantics, unlike :mod:`fnmatch` where ``*`` greedily swallows path
    separators). ``**`` is treated as a cross-directory wildcard."""
    out = ["^"]
    i, n = 0, len(pat)
    while i < n:
        c = pat[i]
        if c == "*":
            if pat[i : i + 2] == "**":
                out.append(".*")
                i += 2
            else:
                out.append("[^/]*")
                i += 1
        elif c == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(c))
            i += 1
    out.append("$")
    return "".join(out)


def _glob_match(pattern: str, path: str) -> bool:
    return re.match(_glob_to_regex(pattern), path) is not None


def _resolve_include(target: str, base: str, paths: set[str]) -> tuple[list[str], bool]:
    """Map an include target (Klipper resolves it relative to its file ``base``) to real file paths.

    Returns ``(matched_paths, missing)`` — ``missing`` is True only when the target genuinely can't
    be found (a broken include). Resolution prefers the exact relative path; the basename fallback
    fires *only* when exactly one file carries that basename, so two same-named files in different
    folders (e.g. a vendor source copy and the user's active copy) are never both pulled in for a
    single ``[include]`` — which would otherwise fabricate duplicate-section errors. A glob that
    matches at least one file is not missing; an ambiguous basename resolves to nothing but is not
    reported as missing (we simply don't guess).
    """
    rel = posixpath.normpath(posixpath.join(posixpath.dirname(base), target))
    if any(ch in target for ch in "*?") or any(ch in rel for ch in "*?"):
        matched = sorted(p for p in paths if _glob_match(target, p) or _glob_match(rel, p))
        return matched, not matched
    if rel in paths:
        return [rel], False
    if target in paths:
        return [target], False
    base_hits = sorted(p for p in paths if posixpath.basename(p) == posixpath.basename(target))
    if len(base_hits) == 1:
        return base_hits, False
    return [], len(base_hits) == 0  # 0 → missing; >1 → ambiguous, don't guess (not "missing")


def project_graph_from_files(files: list[tuple[str, str]]) -> dict[str, Any]:
    """Build the include-dependency graph + cross-file lint over already-fetched ``(path, raw)``.

    Pure (no I/O) so it is unit-testable. Lint rules: ``broken_include`` (a target file is missing),
    ``duplicate_section`` (the same non-``include`` header is defined in more than one file — a
    Klipper load error), and ``orphan_driver`` (a ``[tmcXXXX NAME]`` with no matching ``[NAME]``).
    """
    paths = {p for p, _ in files}
    parsed: dict[str, ConfigFile] = {p: klipper_config.parse(raw) for p, raw in files}

    # First pass: resolve include edges per file (no lint yet — that is scoped to the active tree).
    nodes: list[dict[str, Any]] = []
    includes_of: dict[str, list[str]] = {}
    missing_of: dict[str, list[str]] = {}
    included_by_someone: set[str] = set()
    for path, cfg in parsed.items():
        includes: list[str] = []
        missing: list[str] = []
        for target in _include_targets(cfg):
            matched, is_missing = _resolve_include(target, path, paths)
            if is_missing:
                missing.append(target)
            for m in matched:
                included_by_someone.add(m)
                if m not in includes:
                    includes.append(m)
        includes_of[path] = includes
        missing_of[path] = missing
        nodes.append(
            {
                "file": path,
                "sections": sum(
                    1 for s in cfg.sections if s.header != klipper_config.SAVE_CONFIG_MARKER
                ),
                "includes": includes,
                "missing": missing,
            }
        )

    # The active config is what Klipper actually loads: the primary root + everything it includes,
    # transitively. Cross-file lint is scoped to this set so dated backup copies and other services'
    # configs sitting in the same folder don't masquerade as duplicate-section / orphan errors.
    all_roots = sorted(p for p in paths if p not in included_by_someone)
    primary = next((p for p in _PRIMARY_ROOTS if p in paths), None)
    if primary is None:
        primary = all_roots[0] if all_roots else None
    active: set[str] = set()
    if primary is not None:
        stack = [primary]
        while stack:
            f = stack.pop()
            if f in active:
                continue
            active.add(f)
            stack.extend(includes_of.get(f, []))
    else:
        active = set(paths)

    lint: list[dict[str, Any]] = []
    header_locations: dict[str, list[str]] = {}
    stepper_like: set[str] = set()
    tmc_pairs: list[tuple[str, str]] = []  # (file, NAME) for each [tmcXXXX NAME] in the active tree
    for path in sorted(active):
        for target in missing_of.get(path, []):
            lint.append(
                {"level": "error", "rule": "broken_include", "file": path, "message": target}
            )
        for sec in parsed[path].sections:
            if sec.header == klipper_config.SAVE_CONFIG_MARKER:
                continue
            stype = _section_type(sec.header)
            if stype not in _REPEATABLE_TYPES:
                header_locations.setdefault(sec.header.strip().lower(), []).append(path)
            if stype.startswith(_TMC_PREFIXES) and " " in sec.header.strip():
                tmc_pairs.append((path, sec.header.split(None, 1)[1].strip().lower()))
            elif stype in {
                "stepper",
                "extruder",
                "manual_stepper",
                "heater_bed",
            } or stype.startswith("stepper_"):
                stepper_like.add(sec.header.strip().lower())

    for header, locs in sorted(header_locations.items()):
        distinct = sorted(set(locs))
        # A section defined across more than one *included* file is not an error: Klipper merges
        # such sections and the later-loaded definition wins — the normal way users override a
        # stock macro (e.g. redefining Mainsail's PAUSE in a file included later). Surface it as
        # informational so the override is visible without crying wolf. A duplicate within a single
        # file is a real problem, but the per-file validator already reports that, so skip it here.
        if len(distinct) > 1:
            lint.append(
                {
                    "level": "info",
                    "rule": "section_override",
                    "file": distinct[0],
                    "message": header,
                    "files": distinct,
                }
            )
    for path, name in tmc_pairs:
        if name not in stepper_like:
            lint.append(
                {"level": "warning", "rule": "orphan_driver", "file": path, "message": name}
            )

    nodes.sort(key=lambda n: str(n["file"]))
    # Tree roots = the active config's root only (so backups / other configs don't flood the tree);
    # fall back to every standalone file when there is no recognisable primary root.
    roots = [primary] if primary is not None else all_roots
    return {
        "reachable": True,
        "roots": roots,
        "active": sorted(active),
        "nodes": nodes,
        "lint": lint,
    }


async def gather_project(client: MoonrakerClient) -> dict[str, Any]:
    """Fetch every config file and build the include graph + cross-file lint. Degrades when down."""
    try:
        files = await _read_all_files(client)
    except httpx.HTTPError:
        return {"reachable": False, "roots": [], "active": [], "nodes": [], "lint": []}
    return project_graph_from_files(files)


async def search_project(client: MoonrakerClient, query: str, limit: int = 300) -> dict[str, Any]:
    """Case-insensitive substring search across every config file. Capped at ``limit`` matches."""
    q = query.strip().lower()
    if not q:
        return {"reachable": True, "query": query, "matches": [], "truncated": False}
    try:
        files = await _read_all_files(client)
    except httpx.HTTPError:
        return {"reachable": False, "query": query, "matches": [], "truncated": False}
    matches: list[dict[str, Any]] = []
    truncated = False
    for path, raw in files:
        for lineno, line in enumerate(raw.splitlines(), start=1):
            if q in line.lower():
                if len(matches) >= limit:
                    truncated = True
                    break
                matches.append({"file": path, "line": lineno, "text": line.rstrip()[:300]})
        if truncated:
            break
    return {"reachable": True, "query": query, "matches": matches, "truncated": truncated}


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


def _parse_backup_name(path: str) -> tuple[str, str] | None:
    """Split a backup path ``filamind-backups/<flat>.<stamp>.bak`` into ``(flat, stamp)``, or
    ``None`` if it isn't a backup we wrote. ``flat`` is the source filename with ``/`` → ``_``."""
    prefix = _BACKUP_DIR + "/"
    if not path.startswith(prefix) or not path.endswith(".bak"):
        return None
    core = path[len(prefix) : -len(".bak")]
    flat, _, stamp = core.rpartition(".")
    if not flat or not stamp:
        return None
    return flat, stamp


def _pretty_stamp(stamp: str) -> str:
    """``20260612-014530`` → ``2026-06-12 01:45:30`` (best-effort; pass through if unparseable)."""
    try:
        return datetime.datetime.strptime(stamp, "%Y%m%d-%H%M%S").strftime("%Y-%m-%d %H:%M:%S")
    except ValueError:
        return stamp


async def list_backups(client: MoonrakerClient, filename: str | None = None) -> dict[str, Any]:
    """List timestamped snapshots under ``filamind-backups/`` (newest first). With ``filename``,
    only that file's snapshots; otherwise all. ``reachable=false`` when Moonraker is down."""
    try:
        entries = await client.list_files("config")
    except httpx.HTTPError:
        return {"reachable": False, "filename": filename, "backups": []}
    flat_filter = filename.replace("/", "_") if filename else None
    items: list[dict[str, Any]] = []
    for entry in entries:
        path = str(entry.get("path", ""))
        parsed = _parse_backup_name(path)
        if parsed is None:
            continue
        flat, stamp = parsed
        if flat_filter is not None and flat != flat_filter:
            continue
        items.append(
            {
                "path": path,
                "flat": flat,
                "stamp": stamp,
                "when": _pretty_stamp(stamp),
                "size": entry.get("size"),
                "modified": entry.get("modified"),
            }
        )
    items.sort(key=lambda x: str(x["stamp"]), reverse=True)
    return {"reachable": True, "filename": filename, "backups": items}


async def read_backup(client: MoonrakerClient, path: str) -> str:
    """Fetch one backup snapshot's content (read-only). Guards that ``path`` is a real backup file.

    Raises:
        ValueError: if ``path`` is not a safe ``filamind-backups/*.bak`` path.
        httpx.HTTPError: if Moonraker is unreachable or the file is missing.
    """
    if _parse_backup_name(path) is None or ".." in path.split("/"):
        raise ValueError(f"not a backup path: {path!r}")
    return await client.get_file_text(path, root="config")


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
