"""Config-file service — read the live Klipper config for the Config Editor widget.

Reads ``printer.cfg`` (and its includes) from Moonraker's ``config`` file root, parses
each file with the round-trip :mod:`klipper_config` engine, and returns a structured,
JSON-friendly view (sections → params) plus light validation issues.

Also the gated write path: ``save_config_file`` backs up then overwrites a file, and
``restart_firmware`` applies it — both refused while the printer is busy.
"""

from __future__ import annotations

import datetime
import hashlib
import posixpath
import re
from typing import Any

import httpx

from app.services import field_policy, klipper_config, motor_mapping, printer_guard, reference_data
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


class ConfigConflictError(RuntimeError):
    """Raised when a save is refused because the file changed on disk since it was loaded
    (e.g. a ``SAVE_CONFIG`` landed, or another UI edited it) — saving would clobber that."""


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


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def build_file_view(filename: str, raw: str) -> dict[str, Any]:
    """Parse ``raw`` config text into the structured editor view (pure, no I/O).

    ``sha256`` fingerprints the loaded content — the client echoes it back on save so a file
    that changed on disk in the meantime is detected instead of silently clobbered.
    """
    cfg: ConfigFile = klipper_config.parse(raw)
    return {
        "filename": filename,
        "raw": raw,
        "sha256": _sha256(raw),
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


def _to_float(value: Any) -> float | None:
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


async def gather_sanity(client: MoonrakerClient, data_dir: str = "") -> dict[str, Any]:
    """Cross-check each ``[tmcXXXX NAME]`` driver's configured ``run_current`` / ``microsteps``
    against authoritative catalog facts: the driver model's full-scale current ceiling and — when a
    motor is assigned to that stepper in the Motor Drivers mapping — the motor's datasheet rating.

    Findings (``{level, rule, section, detail}``):
      * ``over_driver_cap`` / ``near_driver_cap`` — run_current above / within 10% of the driver's
        full-scale RMS ceiling (a current the silicon can't deliver / a thermal-margin warning).
      * ``over_motor_rating`` / ``near_motor_rating`` — run_current above / within 10% of the
        mapped motor's rated current (recommended is ~0.7x, so near the rating runs hot).
      * ``odd_microsteps`` — microsteps not a power of two in 1…256.

    Honest about gaps: a driver with no curated current ceiling (e.g. TMC2240, whose limit depends
    on an external Rref resistor) and a stepper with no motor assigned simply get no current finding
    rather than a fabricated one. Degrades to ``reachable=false`` when Moonraker is down.
    """
    try:
        configfile = await client.query_objects(["configfile"])
    except httpx.HTTPError:
        return {"reachable": False, "findings": [], "checked": 0}
    cfobj = configfile.get("configfile")
    cfobj = cfobj if isinstance(cfobj, dict) else {}
    config = cfobj.get("config")
    config = config if isinstance(config, dict) else {}
    mapping = motor_mapping.read_mapping(data_dir)

    findings: list[dict[str, Any]] = []
    checked = 0
    for header, params in config.items():
        parts = str(header).split(None, 1)
        if not parts or not parts[0].lower().startswith("tmc"):
            continue
        if not isinstance(params, dict):
            continue
        checked += 1
        model = parts[0].lower()
        name = parts[1].strip().lower() if len(parts) > 1 else ""
        run_current = _to_float(params.get("run_current"))
        microsteps = _to_float(params.get("microsteps"))

        # Driver full-scale ceiling (alias-resolved; no rref → TMC2240 is skipped, not fabricated).
        info = reference_data.driver_info_lookup(model)
        canonical = str(info.get("model")) if info and info.get("model") else model
        cap = field_policy.code_cap(canonical.lower())
        if run_current is not None and cap is not None and cap > 0:
            if run_current > cap + 1e-9:
                findings.append(
                    {
                        "level": "error",
                        "rule": "over_driver_cap",
                        "section": header,
                        "detail": {"run_current": run_current, "cap": round(cap, 3)},
                    }
                )
            elif run_current > 0.9 * cap:
                findings.append(
                    {
                        "level": "warning",
                        "rule": "near_driver_cap",
                        "section": header,
                        "detail": {"run_current": run_current, "cap": round(cap, 3)},
                    }
                )

        # Mapped-motor rating (only when this stepper has a motor assigned).
        motor_model = mapping.get(name)
        spec = reference_data.motor_spec_lookup(motor_model) if motor_model else None
        motor_max = _to_float(spec.get("max_current_A")) if spec else None
        if run_current is not None and motor_max is not None and motor_max > 0:
            if run_current > motor_max + 1e-9:
                findings.append(
                    {
                        "level": "error",
                        "rule": "over_motor_rating",
                        "section": header,
                        "detail": {
                            "run_current": run_current,
                            "motor": spec.get("name") if spec else motor_model,
                            "max_current": round(motor_max, 3),
                        },
                    }
                )
            elif run_current > 0.9 * motor_max:
                findings.append(
                    {
                        "level": "warning",
                        "rule": "near_motor_rating",
                        "section": header,
                        "detail": {
                            "run_current": run_current,
                            "motor": spec.get("name") if spec else motor_model,
                            "max_current": round(motor_max, 3),
                        },
                    }
                )

        if microsteps is not None:
            ms = int(microsteps)
            if ms < 1 or ms > 256 or (ms & (ms - 1)) != 0:
                findings.append(
                    {
                        "level": "warning",
                        "rule": "odd_microsteps",
                        "section": header,
                        "detail": {"microsteps": ms},
                    }
                )

    return {"reachable": True, "findings": findings, "checked": checked}


async def append_block(client: MoonrakerClient, filename: str, block: str) -> dict[str, Any]:
    """Append a config ``block`` (e.g. generated macros) to ``filename`` through the gated save.

    Refuses (``ValueError``) if any ``[gcode_macro NAME]`` in the block is already defined in the
    target file — so a generated START_PRINT never silently duplicates an existing one. Otherwise it
    reads the current text, appends with a blank-line separator, and writes via ``save_config_file``
    (which backs up first and refuses while the printer is busy).

    Raises:
        ValueError: unsafe path or a duplicate macro name.
        ConfigBusyError: the printer is busy.
        httpx.HTTPError: Moonraker error.
    """
    _reject_unsafe(filename)
    try:
        current = await client.get_file_text(filename, root="config")
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code != 404:
            raise
        current = ""

    existing = {
        s.name.strip().lower()
        for s in klipper_config.parse(current).sections
        if _section_type(s.header) == "gcode_macro"
    }
    dups = [
        s.name
        for s in klipper_config.parse(block).sections
        if _section_type(s.header) == "gcode_macro" and s.name.strip().lower() in existing
    ]
    if dups:
        raise ValueError(f"already defined in {filename}: {', '.join(dups)}")

    body = block.strip() + "\n"
    new_text = f"{current.rstrip()}\n\n{body}" if current.strip() else body
    return await save_config_file(client, filename, new_text)


async def _is_busy(client: MoonrakerClient) -> bool:
    """True while the printer is printing, paused, or in error — block writes and restarts
    then. Delegates to the shared :mod:`printer_guard` busy definition."""
    return await printer_guard.is_busy(client)


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


async def _prune_backups(client: MoonrakerClient, flat: str, keep_n: int) -> None:
    """Keep only the newest ``keep_n`` snapshots of one source file under ``filamind-backups/``.

    Best-effort housekeeping: a listing or per-file delete failure never fails the save that
    triggered it (the new backup is already written).
    """
    if keep_n <= 0:
        return
    try:
        entries = await client.list_files("config")
    except httpx.HTTPError:
        return
    mine: list[tuple[str, str]] = []  # (stamp, path)
    for entry in entries:
        path = str(entry.get("path", ""))
        parsed = _parse_backup_name(path)
        if parsed is not None and parsed[0] == flat:
            mine.append((parsed[1], path))
    mine.sort(reverse=True)  # newest stamp first
    for _, path in mine[keep_n:]:
        try:
            await client.delete_file(path, root="config")
        except httpx.HTTPError:
            continue


async def save_config_file(
    client: MoonrakerClient,
    filename: str,
    content: str,
    expected_sha256: str | None = None,
    *,
    keep_n: int = 20,
) -> dict[str, Any]:
    """Back up the current file, then overwrite it with ``content``. Read-after-parse only —
    never auto-restarts (that's a separate, explicit action).

    Refuses while the printer is busy (printing / paused / error). With ``expected_sha256``
    (the fingerprint of the content the editor loaded), refuses when the file changed on disk
    in the meantime — a landed ``SAVE_CONFIG`` or a parallel edit would otherwise be silently
    clobbered. The existing file (if any) is copied to ``filamind-backups/`` first, and that
    file's snapshots are pruned to the newest ``keep_n``.

    Raises:
        ValueError: if ``filename`` is not a safe in-root path.
        ConfigBusyError: if the printer is busy.
        ConfigConflictError: if the on-disk content no longer matches ``expected_sha256``.
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
    if expected_sha256 and current is not None and _sha256(current) != expected_sha256:
        raise ConfigConflictError(
            f"{filename} changed on disk since it was loaded — saving would overwrite that "
            "change. Reload the file (the backup timeline shows what differs)."
        )
    if current is not None:
        backup = _backup_path(filename, datetime.datetime.now())
        await client.upload_file(backup, current, root="config")
        await _prune_backups(client, filename.replace("/", "_"), keep_n)

    await client.upload_file(filename, content, root="config")

    view = build_file_view(filename, content)
    return {
        "ok": True,
        "filename": filename,
        "backup": backup,
        "sha256": view["sha256"],
        "issues": view["issues"],
        "section_count": view["section_count"],
    }


async def restart_firmware(client: MoonrakerClient) -> dict[str, Any]:
    """Trigger ``FIRMWARE_RESTART`` so a saved config takes effect. Refused while busy and while
    another actuating operation (a resonance test, a flash…) holds the printer's exclusive slot —
    restarting mid-test would abort it with the machine in an arbitrary state.

    Raises:
        ConfigBusyError: if the printer is busy or another operation holds the slot.
        httpx.HTTPError: if Moonraker is unreachable or the restart fails.
    """
    if await _is_busy(client):
        raise ConfigBusyError("Refusing to restart while the printer is busy.")
    try:
        async with printer_guard.acquire("firmware_restart"):
            await client.firmware_restart()
    except printer_guard.GuardBusyError as exc:
        raise ConfigBusyError(str(exc)) from exc
    return {"ok": True}
