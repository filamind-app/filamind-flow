"""KlipperScreen theme builder — generate a touchscreen theme from a color palette, write it to
the host, list/delete generated themes, and activate one.

A KlipperScreen theme is a folder ``<klipperscreen_dir>/styles/<name>/`` holding ``style.css`` (GTK
CSS whose palette is a block of ``@define-color`` variables) + ``style.conf`` (JSON graph colors).
That folder is OUTSIDE every Moonraker file root, so — unlike the conf — it is written **host-side**
(plain file I/O; the backend runs as the printer user). The CSS is rendered from FilaMind's own
template (not copied from any upstream theme). Activating a theme just sets ``[main] theme`` in
``KlipperScreen.conf`` (which IS in the config root), preserving KlipperScreen's auto-generated
``#~#`` block, then the caller restarts KlipperScreen.
"""

from __future__ import annotations

import json
import os
import re
import shutil
from typing import Any

from app.services import config_service, screen_service
from app.services.moonraker_client import MoonrakerClient

#: A generated-theme marker dropped in the folder so we only ever list/delete OUR themes, never a
#: stock one (z-bolt / material-*) the user installed.
MARKER = ".filamind-theme"

#: Theme name: a folder name, so keep it to safe characters (no traversal, no separators).
_SAFE_NAME = re.compile(r"^[A-Za-z0-9 _-]{1,40}$")
_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")
_AUTO_MARKER = "#~#"

#: The themeable palette tokens (KlipperScreen's GTK ``@define-color`` names) + sane defaults.
PALETTE_TOKENS = (
    "bg",
    "text",
    "text-inv",
    "lines",
    "active",
    "color1",
    "color2",
    "color3",
    "color4",
    "error",
    "warning",
)
DEFAULT_PALETTE: dict[str, str] = {
    "bg": "#161616",
    "text": "#e8e8e8",
    "text-inv": "#161616",
    "lines": "#9a9a9a",
    "active": "#2c2c2c",
    "color1": "#c8643c",
    "color2": "#3b82f6",
    "color3": "#22c55e",
    "color4": "#eab308",
    "error": "#ef4444",
    "warning": "#f59e0b",
}


def _styles_dir(klipperscreen_dir: str) -> str:
    return os.path.join(os.path.expanduser(klipperscreen_dir), "styles")


def _clean_palette(palette: dict[str, Any] | None) -> dict[str, str]:
    """Defaults overlaid with caller-supplied tokens; only known tokens + valid #RRGGBB kept."""
    out = dict(DEFAULT_PALETTE)
    for token, value in (palette or {}).items():
        if token in PALETTE_TOKENS and isinstance(value, str) and _HEX.match(value):
            out[token] = value.lower()
    return out


def render_style_css(name: str, palette: dict[str, Any] | None, radius: int = 8) -> str:
    """FilaMind's own GTK-CSS template: a ``@define-color`` palette block + the selectors that
    reference it. No upstream theme's CSS is copied — this is an original, minimal layout."""
    p = _clean_palette(palette)
    r = max(0, min(int(radius) if isinstance(radius, (int, float)) else 8, 30))
    defs = "\n".join(f"@define-color {tok} {p[tok]};" for tok in PALETTE_TOKENS)
    return f"""/* FilaMind Flow — theme "{name}" (recolor from the panel) */
{defs}

window {{ background-color: @bg; color: @text; }}
.message {{ color: @text; }}
button {{
  background-color: @active;
  color: @text;
  border: 1px solid @lines;
  border-radius: {r}px;
}}
button:active, .button_active {{ background-color: @color1; color: @text-inv; }}
button.color1 {{ border-color: @color1; }}
button.color2 {{ border-color: @color2; }}
button.color3 {{ border-color: @color3; }}
button.color4 {{ border-color: @color4; }}
.distbutton {{ background-color: @active; }}
entry {{ background-color: @bg; color: @text; border: 1px solid @lines; }}
dialog, .dialog {{ background-color: @bg; color: @text; }}
.titlebar {{ background-color: @active; color: @text; }}
.error {{ color: @error; }}
.warning {{ color: @warning; }}
"""


def render_style_conf(palette: dict[str, Any] | None) -> str:
    """The JSON ``style.conf`` sidecar — per-sensor graph colors, drawn from the accent palette."""
    p = _clean_palette(palette)
    return json.dumps(
        {
            "graph_colors": {
                "extruder": [p["color1"]],
                "bed": [p["color2"]],
                "fan": [p["color3"], p["color4"]],
                "sensor": [p["color4"], p["color3"], p["color2"]],
            }
        },
        indent=2,
    )


def list_themes(klipperscreen_dir: str) -> list[dict[str, Any]]:
    """Installed theme folders, each flagged ``generated`` when FilaMind created it."""
    styles = _styles_dir(klipperscreen_dir)
    out: list[dict[str, Any]] = []
    try:
        entries = sorted(os.listdir(styles))
    except OSError:
        return out
    for entry in entries:
        path = os.path.join(styles, entry)
        if not os.path.isdir(path) or entry == "printers":
            continue
        out.append({"name": entry, "generated": os.path.exists(os.path.join(path, MARKER))})
    return out


def _validate_name(name: str) -> None:
    if not _SAFE_NAME.match(name or ""):
        raise ValueError(
            "Theme name may use letters, numbers, spaces, hyphens and underscores only."
        )


def generate_theme(
    klipperscreen_dir: str, name: str, palette: dict[str, Any] | None, radius: int = 8
) -> dict[str, Any]:
    """Write ``styles/<name>/`` (style.css + style.conf + marker), host-side. Refuses to overwrite
    a stock (non-generated) theme; snapshots a prior generated one of the same name first."""
    _validate_name(name)
    styles = _styles_dir(klipperscreen_dir)
    dest = os.path.join(styles, name)
    if os.path.isdir(dest) and not os.path.exists(os.path.join(dest, MARKER)):
        raise ValueError(f'"{name}" is an existing theme not created here — pick another name.')
    if os.path.isdir(dest):  # back up our prior version before overwriting
        backup = os.path.join(styles, f".filamind-backup-{name}")
        shutil.rmtree(backup, ignore_errors=True)
        shutil.copytree(dest, backup)
    os.makedirs(dest, exist_ok=True)
    with open(os.path.join(dest, "style.css"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(render_style_css(name, palette, radius))
    with open(os.path.join(dest, "style.conf"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(render_style_conf(palette))
    with open(os.path.join(dest, MARKER), "w", encoding="utf-8") as fh:
        fh.write("Generated by FilaMind Flow.\n")
    return {"name": name, "path": dest}


def delete_theme(klipperscreen_dir: str, name: str) -> None:
    """Delete a FilaMind-GENERATED theme (refuses to touch a stock theme)."""
    _validate_name(name)
    dest = os.path.join(_styles_dir(klipperscreen_dir), name)
    if not os.path.isdir(dest):
        raise ValueError(f'Theme "{name}" does not exist.')
    if not os.path.exists(os.path.join(dest, MARKER)):
        raise ValueError(f'"{name}" was not created here — refusing to delete a stock theme.')
    shutil.rmtree(dest)


def set_main_theme(raw: str, name: str) -> str:
    """Set ``[main] theme = <name>`` in KlipperScreen.conf text, leaving the auto-generated ``#~#``
    block untouched. Adds the key (or the whole ``[main]`` section) if missing."""
    lines = raw.split("\n")
    auto_start = next(
        (i for i, ln in enumerate(lines) if ln.lstrip().startswith(_AUTO_MARKER)), len(lines)
    )
    user, auto = lines[:auto_start], lines[auto_start:]
    theme_re = re.compile(r"^\s*theme\s*[:=].*$", re.IGNORECASE)
    main_idx = next((i for i, ln in enumerate(user) if ln.strip().lower() == "[main]"), None)
    if main_idx is not None:
        j = main_idx + 1
        while j < len(user) and not user[j].strip().startswith("["):
            if theme_re.match(user[j]):
                user[j] = f"theme = {name}"
                return "\n".join([*user, *auto])
            j += 1
        user.insert(main_idx + 1, f"theme = {name}")
        return "\n".join([*user, *auto])
    return "\n".join(["[main]", f"theme = {name}", "", *user, *auto])


async def activate_theme(client: MoonrakerClient, name: str) -> dict[str, Any]:
    """Point ``[main] theme`` at ``name`` via the gated conf save (backup + stale-write guard)."""
    _validate_name(name)
    view = await config_service.read_config_file(client, screen_service.CONF_FILE)
    new_text = set_main_theme(str(view.get("raw", "")), name)
    return await config_service.save_config_file(
        client, screen_service.CONF_FILE, new_text, str(view.get("sha256") or "") or None
    )
