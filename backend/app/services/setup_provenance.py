"""Install provenance for Setup components - what each install actually placed on the host.

Live install methods (a git clone, a web-UI release zip + nginx site, a Klipper-extra symlink, a
first-party installer) leave different footprints, and re-deriving that footprint from the
filesystem is fragile. This records it once at install time so two things become reliable:

* **update reading** - the recorded ``ref`` is the authoritative installed version even for a
  manual / non-git / web install that ``git describe`` can't read; and
* **clean removal** - :func:`record` captures exactly what to tear down (extras symlinks,
  printer.cfg includes, the nginx site, the systemd unit, the Moonraker ``[update_manager]`` key),
  so :func:`remove` reverses the install instead of a blind ``rmtree`` that leaves residue behind.

A small JSON under the data dir, best-effort (never raises into a request), mirroring the atomic
write / graceful read idiom used by the other Setup stores.
"""

from __future__ import annotations

import contextlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from app.config import get_settings


def _path() -> Path:
    return Path(get_settings().data_dir).expanduser() / "setup-installed.json"


def _read_all() -> dict[str, dict[str, Any]]:
    try:
        data = json.loads(_path().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return {k: v for k, v in data.items() if isinstance(v, dict)} if isinstance(data, dict) else {}


def read_all() -> dict[str, dict[str, Any]]:
    """Every recorded install, keyed by component id."""
    return _read_all()


def read(cid: str) -> dict[str, Any] | None:
    """The install record for one component, or None if it wasn't installed through the widget."""
    return _read_all().get(cid)


def record(
    cid: str,
    *,
    method: str,
    repo: str = "",
    ref: str = "",
    extras: list[str] | None = None,
    includes: list[str] | None = None,
    nginx_site: str = "",
    service: str = "",
    moonraker_key: str = "",
) -> None:
    """Stamp what an install placed (best-effort). ``method`` is ``git`` / ``web-ui`` / ``extra`` /
    ``first_party``; the rest is the teardown footprint clean-removal reverses."""
    data = _read_all()
    data[cid] = {
        "method": method,
        "repo": repo,
        "ref": ref,
        "extras": list(extras or []),
        "includes": list(includes or []),
        "nginx_site": nginx_site,
        "service": service,
        "moonraker_key": moonraker_key,
        "at": datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S"),
    }
    _write(data)


def remove(cid: str) -> None:
    """Forget a component's install record (after a successful uninstall)."""
    data = _read_all()
    if data.pop(cid, None) is not None:
        _write(data)


def _write(data: dict[str, dict[str, Any]]) -> None:
    with contextlib.suppress(OSError):
        path = _path()
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        tmp.replace(path)
