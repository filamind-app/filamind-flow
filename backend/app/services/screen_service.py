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
