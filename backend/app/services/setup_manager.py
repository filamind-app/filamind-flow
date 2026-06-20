"""FilaMind Setup — component manager service.

Reads a curated catalog of installable Klipper-ecosystem components, reports what is installed
(read-only), and — only when the operator explicitly enables writes (FILAMIND_SETUP_WRITES) on
the host — installs / updates / removes them. Every mutation is gated, path-guarded under $HOME,
and shells out to git through the host's normal tooling.

Write operations are DISABLED by default: the safe, read-only state is what ships, and an operator
turns writes on per host. The same engine backs the `filamind-setup` CLI.
"""

from __future__ import annotations

import asyncio
import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.config import get_settings

CATALOG_PATH = Path(__file__).resolve().parents[1] / "data" / "setup-catalog.json"

# Component `type`s we can install/update via a plain git clone + the component's own install.sh.
_GIT_TYPES = {"git_repo", "service"}


@dataclass
class Component:
    id: str
    name: str
    kind: str
    repo: str
    type: str
    group: str
    deps: list[str] = field(default_factory=list)
    first_party: bool = False


def load_catalog() -> dict[str, Component]:
    data = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    out: dict[str, Component] = {}
    for grp in data["groups"]:
        for c in grp["components"]:
            out[c["id"]] = Component(
                id=c["id"],
                name=c["name"],
                kind=c["kind"],
                repo=c["repo"],
                type=c["type"],
                group=grp["group"],
                deps=list(c.get("deps", [])),
                first_party=bool(c.get("first_party", False)),
            )
    return out


def catalog_payload() -> dict[str, Any]:
    """The catalog as the widget consumes it: groups, each with its components."""
    return json.loads(CATALOG_PATH.read_text(encoding="utf-8"))


def resolve_order(ids: list[str], catalog: dict[str, Component]) -> list[str]:
    """Topological order so dependencies install first (e.g. moonraker before mainsail)."""
    seen: set[str] = set()
    order: list[str] = []

    def visit(cid: str) -> None:
        if cid in seen or cid not in catalog:
            return
        seen.add(cid)
        for dep in catalog[cid].deps:
            visit(dep)
        order.append(cid)

    for cid in ids:
        visit(cid)
    return order


def _install_dir(component: Component) -> Path:
    """Best-effort install location (most ecosystem repos clone to ~/<id>)."""
    return Path.home() / component.id


async def probe_status() -> dict[str, str]:
    """Read-only: 'installed' if the component's directory is present, else 'not-installed'.

    Heuristic (clone-to-$HOME convention); web UIs served elsewhere may read as not-installed.
    """
    catalog = load_catalog()
    return {
        cid: ("installed" if _install_dir(c).is_dir() else "not-installed")
        for cid, c in catalog.items()
    }


def writes_enabled() -> bool:
    return bool(get_settings().setup_writes_enabled)


def _refused() -> dict[str, Any]:
    return {
        "refused": True,
        "output": "GUI setup writes are disabled. Enable FILAMIND_SETUP_WRITES on the host "
        "(or use the filamind-setup CLI) to install/update/remove from here.",
    }


async def _run(cmd: list[str]) -> dict[str, Any]:
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    stdout, _ = await proc.communicate()
    return {
        "ok": proc.returncode == 0,
        "code": proc.returncode,
        "output": stdout.decode(errors="replace"),
    }


def _require(cid: str, catalog: dict[str, Component]) -> Component:
    component = catalog.get(cid)
    if component is None:
        raise ValueError(f"Unknown component: {cid}")
    return component


async def install(cid: str) -> dict[str, Any]:
    catalog = load_catalog()
    component = _require(cid, catalog)
    if not writes_enabled():
        return _refused()
    if component.type not in _GIT_TYPES:
        return {
            "refused": True,
            "output": f"GUI install of '{component.type}' components isn't supported yet; "
            "use the filamind-setup CLI.",
        }
    dest = _install_dir(component)
    if dest.exists():
        return {"ok": True, "output": f"{component.name} already present at {dest}"}
    url = f"https://github.com/{component.repo}"
    clone = await _run(["git", "clone", "--depth", "1", url, str(dest)])
    if not clone["ok"]:
        return clone
    installer = dest / "install.sh"
    if installer.is_file():
        return await _run(["bash", str(installer)])
    return {"ok": True, "output": f"Cloned {component.name}; no install.sh — finish per its docs."}


async def update(cid: str) -> dict[str, Any]:
    catalog = load_catalog()
    component = _require(cid, catalog)
    if not writes_enabled():
        return _refused()
    dest = _install_dir(component)
    if not (dest / ".git").is_dir():
        return {"refused": True, "output": f"{component.name} is not a git checkout under {dest}."}
    return await _run(["git", "-C", str(dest), "pull", "--ff-only"])


async def remove(cid: str, confirm: str) -> dict[str, Any]:
    catalog = load_catalog()
    component = _require(cid, catalog)
    if not writes_enabled():
        return _refused()
    if confirm != component.id:
        raise ValueError("Confirmation does not match the component id")
    dest = _install_dir(component)
    # Path guard: only ever remove a direct child of $HOME.
    if dest.parent != Path.home() or not dest.is_dir():
        return {"refused": True, "output": f"Refusing to remove {dest} (not a direct $HOME child)."}
    await asyncio.to_thread(shutil.rmtree, dest)
    return {"ok": True, "output": f"Removed {dest}"}
