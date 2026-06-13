"""KlipperScreen control — read/edit its config and restart it to apply.

KlipperScreen's config (``KlipperScreen.conf``) lives in Moonraker's ``config`` file root, right
next to ``printer.cfg``, so reading and the gated, backed-up write reuse the Config Editor's
machinery wholesale (:mod:`app.services.config_service` — busy-refusal, SHA-256 stale-write guard,
timestamped pre-save backup + prune). Applying a change means restarting the KlipperScreen
*service* (it doesn't hot-reload), which Moonraker does via ``/machine/services/restart`` when
KlipperScreen is in its allowed-services list. Everything here is read-only except the explicit
save / restart.
"""

from __future__ import annotations

import re
from typing import Any

from app.services import config_service
from app.services.moonraker_client import MoonrakerClient

CONF_FILE = "KlipperScreen.conf"
SERVICE = "KlipperScreen"

#: A couple of headline options surfaced in the status line (cheap regex over the user section;
#: the full editor reads/writes the whole file). Matches ``theme: z-bolt`` / ``language = en``.
_MAIN_OPTION = re.compile(r"(?im)^\s*(theme|language|lang)\s*[:=]\s*(\S+)")


async def status(client: MoonrakerClient) -> dict[str, Any]:
    """Whether KlipperScreen is present + restartable, whether its conf exists, and the current
    theme / language — so the widget can offer itself only when there's something to control."""
    out: dict[str, Any] = {
        "present": False,
        "restartable": False,
        "conf_exists": False,
        "theme": None,
        "language": None,
    }
    try:
        info = await client.machine_system_info()
        available = info.get("available_services")
        if isinstance(available, list) and SERVICE in available:
            out["present"] = True
            out["restartable"] = True
    except Exception:
        pass
    try:
        files = await client.list_files("config")
        out["conf_exists"] = any(f.get("path") == CONF_FILE for f in files)
    except Exception:
        pass
    if out["conf_exists"]:
        # The conf existing means KlipperScreen is installed even if an older Moonraker didn't
        # report it in available_services (the editor still works; restart may just be manual).
        out["present"] = True
        try:
            text = await client.get_file_text(CONF_FILE, root="config")
            for key, value in _MAIN_OPTION.findall(text):
                if key == "theme":
                    out["theme"] = value
                else:
                    out["language"] = value
        except Exception:
            pass
    return out


async def read_conf(client: MoonrakerClient) -> dict[str, Any]:
    """The current ``KlipperScreen.conf`` as an editor view (raw + sha256 + parsed sections)."""
    return await config_service.read_config_file(client, CONF_FILE)


async def save_conf(
    client: MoonrakerClient, content: str, expected_sha256: str | None
) -> dict[str, Any]:
    """Gated save (backup + busy-refusal + stale-write precondition), enforcing LF line endings
    (KlipperScreen requires UNIX endings)."""
    normalized = content.replace("\r\n", "\n").replace("\r", "\n")
    return await config_service.save_config_file(client, CONF_FILE, normalized, expected_sha256)


async def restart(client: MoonrakerClient) -> None:
    """Restart the KlipperScreen service so an edited config / theme takes effect."""
    await client.restart_service(SERVICE)


# ── Graphical [main] options editor ──────────────────────────────────────────
# These read/write individual options in [main] as plain text so the form editor never has to
# round-trip the whole file through a parser, and KlipperScreen's auto-generated #~# block is
# always left untouched (only the user-authored portion above it is edited).
_KV = re.compile(r"^\s*([A-Za-z0-9_]+)\s*[:=]\s*(.*?)\s*$")
_KEY = re.compile(r"^[A-Za-z0-9_]{1,40}$")


def _split_auto(raw: str) -> tuple[list[str], list[str]]:
    lines = raw.split("\n")
    cut = next((i for i, ln in enumerate(lines) if ln.lstrip().startswith("#~#")), len(lines))
    return lines[:cut], lines[cut:]


def read_main_options(raw: str) -> dict[str, str]:
    """Parse the user-authored ``[main]`` section into ``{key: value}`` (ignores the #~# block)."""
    user, _ = _split_auto(raw)
    start = next((i for i, ln in enumerate(user) if ln.strip().lower() == "[main]"), None)
    out: dict[str, str] = {}
    if start is None:
        return out
    j = start + 1
    while j < len(user) and not user[j].strip().startswith("["):
        line = user[j]
        if not line.lstrip().startswith("#"):
            m = _KV.match(line)
            if m:
                out[m.group(1).lower()] = m.group(2)
        j += 1
    return out


def set_options(raw: str, section: str, options: dict[str, str]) -> str:
    """Set several params in ``[section]`` (add or replace each), preserving the #~# auto-block."""
    out = raw
    for key, value in options.items():
        if not _KEY.match(key):
            continue
        out = _set_one(out, section, key, str(value))
    return out


def _set_one(raw: str, section: str, key: str, value: str) -> str:
    user, auto = _split_auto(raw)
    header = f"[{section}]"
    sec = next((i for i, ln in enumerate(user) if ln.strip().lower() == header.lower()), None)
    key_re = re.compile(rf"^\s*{re.escape(key)}\s*[:=].*$", re.IGNORECASE)
    if sec is not None:
        j = sec + 1
        while j < len(user) and not user[j].strip().startswith("["):
            if key_re.match(user[j]) and not user[j].lstrip().startswith("#"):
                user[j] = f"{key} = {value}"
                return "\n".join([*user, *auto])
            j += 1
        user.insert(sec + 1, f"{key} = {value}")
        return "\n".join([*user, *auto])
    return "\n".join([header, f"{key} = {value}", "", *user, *auto])


# ── Menu tree editor ─────────────────────────────────────────────────────────
# The on-screen menus are config-defined trees of [menu <tree> <tok> <tok>...] sections. We read
# them into a flat list (the frontend rebuilds the tree from the path) and write them back by
# stripping every existing [menu ...] block from the user portion and re-emitting the supplied
# ones — KlipperScreen resolves menus by their path, not file order, so this is safe. The #~#
# auto-block and all non-menu sections are preserved.
_MENU_HEADER = re.compile(r"^\[menu\s+(.+?)\]\s*$", re.IGNORECASE)
_TOKEN = re.compile(r"^[A-Za-z0-9_]+$")
_MENU_PROPS = ("name", "icon", "style", "panel", "method", "params", "enable", "confirm")

#: Built-in panels a menu item's ``panel:`` can open (for the action picker).
PANELS = (
    "move",
    "temperature",
    "extrude",
    "fan",
    "fine_tune",
    "gcodes",
    "job_status",
    "bed_level",
    "bed_mesh",
    "zcalibrate",
    "input_shaper",
    "limits",
    "retraction",
    "network",
    "power",
    "led",
    "pins",
    "spoolman",
    "console",
    "gcode_macros",
    "notifications",
    "settings",
    "system",
    "updater",
    "camera",
    "lock_screen",
)


def read_menus(raw: str) -> list[dict[str, Any]]:
    """Flatten the user-portion ``[menu ...]`` sections into ``{id, tree, parent, props}`` items."""
    user, _ = _split_auto(raw)
    items: list[dict[str, Any]] = []
    i = 0
    while i < len(user):
        m = _MENU_HEADER.match(user[i].strip())
        if not m:
            i += 1
            continue
        path = m.group(1).split()
        props: dict[str, str] = {}
        i += 1
        while i < len(user) and not user[i].strip().startswith("["):
            if not user[i].lstrip().startswith("#"):
                kv = _KV.match(user[i])
                if kv:
                    props[kv.group(1).lower()] = kv.group(2)
            i += 1
        if path:
            items.append(
                {
                    "id": " ".join(path),
                    "tree": path[0],
                    "parent": " ".join(path[:-1]) if len(path) > 1 else path[0],
                    "props": props,
                }
            )
    return items


def write_menus(raw: str, items: list[dict[str, Any]]) -> str:
    """Replace every ``[menu ...]`` section with the supplied items, preserving the rest + #~#."""
    user, auto = _split_auto(raw)
    kept: list[str] = []
    i = 0
    while i < len(user):
        if _MENU_HEADER.match(user[i].strip()):
            i += 1
            while i < len(user) and not user[i].strip().startswith("["):
                i += 1
            continue
        kept.append(user[i])
        i += 1
    while kept and kept[-1].strip() == "":
        kept.pop()

    out: list[str] = []
    for item in items:
        path = str(item.get("id") or "").strip()
        if not path or not all(_TOKEN.match(tok) for tok in path.split()):
            continue
        out.append("")
        out.append(f"[menu {path}]")
        props = item.get("props") or {}
        ordered = [*_MENU_PROPS, *(k for k in props if k not in _MENU_PROPS)]
        for key in ordered:
            if not _TOKEN.match(key):
                continue
            value = props.get(key)
            if value is None or str(value) == "":
                continue
            # one option per line, LF — values can't span lines, so strip any embedded newlines.
            out.append(f"{key}: {str(value).replace(chr(10), ' ').strip()}")
    return "\n".join([*kept, *out, "", *auto])
