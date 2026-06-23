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
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

from app.config import get_settings

CATALOG_PATH = Path(__file__).resolve().parents[1] / "data" / "setup-catalog.json"

# Component `type`s we can install/update via a plain git clone + the component's own install.sh.
_GIT_TYPES = {"git_repo", "service"}

# Best-effort "latest version" lookups (for not-installed components) are cached so we hit GitHub at
# most once per repo per window, and are gated on Moonraker's reported remaining quota (see below).
# The cache is persisted to disk so versions stay visible across restarts and when the host's GitHub
# quota is momentarily exhausted (Moonraker shares the 60/hr unauthenticated limit) - otherwise a
# cold process with low quota would show blank versions for every not-installed component.
_LATEST_TTL = 7 * 24 * 3600.0  # versions change rarely; keep them shown for a week, refresh lazily
_latest_cache: dict[str, tuple[float, str]] = {}
_latest_cache_loaded = False


def _latest_cache_path() -> Path:
    return Path(get_settings().data_dir).expanduser() / "setup-latest-cache.json"


def _load_latest_cache() -> None:
    """Populate the in-memory cache from disk once per process, so a fresh start still shows the
    last-known versions even before (or without) a new GitHub fetch."""
    global _latest_cache_loaded
    if _latest_cache_loaded:
        return
    _latest_cache_loaded = True
    try:
        raw = json.loads(_latest_cache_path().read_text(encoding="utf-8"))
        for repo, val in raw.items():
            if isinstance(val, list) and len(val) == 2:
                _latest_cache[repo] = (float(val[0]), str(val[1]))
    except (OSError, json.JSONDecodeError, ValueError, TypeError):
        pass


def _save_latest_cache() -> None:
    try:
        path = _latest_cache_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(
            json.dumps({k: [v[0], v[1]] for k, v in _latest_cache.items()}), encoding="utf-8"
        )
        tmp.replace(path)
    except OSError:
        pass


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
    desc: str = ""
    #: Moonraker update-manager key when it differs from ``id`` (e.g. ``KlipperScreen``).
    manager_key: str = ""
    #: systemd unit name when this component runs as a service (e.g. ``crowsnest``).
    service: str = ""
    #: install directory name under ``$HOME`` when it differs from ``id`` (e.g. ``KlipperScreen``).
    dir: str = ""


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
                desc=str(c.get("desc", "")),
                manager_key=str(c.get("manager_key", "")),
                service=str(c.get("service", "")),
                dir=str(c.get("dir", "")),
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
    """Best-effort install location (most ecosystem repos clone to ~/<id>, some to a custom dir)."""
    return Path.home() / (component.dir or component.id)


def _raw_installer(component: Component) -> str:
    """The component's one-line installer (FilaMind apps ship scripts/install.sh)."""
    return f"https://raw.githubusercontent.com/{component.repo}/main/scripts/install.sh"


def suite_install_command() -> str:
    """The single command that installs the whole FilaMind suite (shown in the Setup widget)."""
    url = "https://raw.githubusercontent.com/filamind-app/filamind-setup/main/install.sh"
    return f"curl -fsSL {url} | bash"


def _augment_root_failure(result: dict[str, Any], component: Component) -> dict[str, Any]:
    """A first-party install configures the web server, which needs root. The backend service has
    no terminal to type a sudo password, so if that's why it failed, append the command to run on
    the printer host (where sudo can prompt) instead of a cryptic 'a terminal is required' error.
    """
    if result.get("ok"):
        return result
    out = result.get("output") or ""
    if any(s in out for s in ("terminal is required", "password is required", "sudo:")):
        cmd = f"curl -fsSL {_raw_installer(component)} | bash"
        result["output"] = (
            out.rstrip() + f"\n\nInstalling {component.name} needs root to set up the web server, "
            f"which can't be done from here. Run this on the printer host:\n  {cmd}"
        )
    return result


def _is_nginx_app(c: Component) -> bool:
    """A first-party web / touch app that is served by an nginx site named after its id (FilaMind
    3d, FilaMind screen). For these the clone dir alone is a false positive: the repo can be cloned
    yet the nginx step never ran (e.g. its sudo step failed), so the app is not actually served."""
    return c.first_party and c.kind in {"web-ui", "touch"}


def _nginx_site_present(site: str) -> bool:
    """True if an nginx site by this name is configured (enabled symlink or available file). Only
    needs directory-traversal on /etc/nginx (world-traversable), so the service user can read it."""
    for base in ("/etc/nginx/sites-enabled", "/etc/nginx/sites-available"):
        p = Path(base) / site
        if p.is_symlink() or p.exists():
            return True
    return False


def _is_installed(c: Component, managed: set[str], services: set[str]) -> bool:
    """Combine the install signals, most-authoritative first:

    1. Moonraker's update-manager registry (``manager_key`` or ``id``) — the components Moonraker
       actually tracks; survives non-``$HOME`` layouts and is the source of truth when present.
    2. A managed systemd unit (``service``) — catches service-style installs (crowsnest, spoolman).
    3. For a first-party nginx app, the nginx site itself — a bare clone (downloaded but never set
       up) is NOT installed; the site only exists once its installer's web-server step succeeded.
    4. The clone-to-``$HOME`` directory heuristic — the offline fallback for everything else.
    """
    key = (c.manager_key or c.id).lower()
    if key in managed:
        return True
    if c.service and c.service.lower() in services:
        return True
    if _is_nginx_app(c):
        return _nginx_site_present(c.id)
    return _install_dir(c).is_dir()


async def probe_status(
    managed: set[str] | None = None, services: set[str] | None = None
) -> dict[str, str]:
    """Read-only install status per component, combining Moonraker signals with the dir heuristic.

    ``managed`` (update-manager keys) and ``services`` (systemd units) come from Moonraker when
    reachable; when omitted/empty the detection falls back to the clone-to-``$HOME`` heuristic, so
    this stays correct offline.
    """
    catalog = load_catalog()
    m = managed or set()
    s = services or set()
    return {
        cid: ("installed" if _is_installed(c, m, s) else "not-installed")
        for cid, c in catalog.items()
    }


def _update_available(entry: dict[str, Any]) -> bool:
    """An update is available when Moonraker reports commits behind, or the installed version
    differs from the remote one (web UIs have no commit list, only a version string)."""
    behind = entry.get("commits_behind")
    if isinstance(behind, list) and behind:
        return True
    version, remote = entry.get("version"), entry.get("remote_version")
    return bool(version and remote and version != remote)


async def _git_version(dest: Path) -> str:
    """Installed version of an unmanaged git checkout, best-effort. ``describe --tags --always``
    yields the nearest tag (or a short hash when untagged); empty when it's not a git work tree."""
    if not (dest / ".git").is_dir():
        return ""
    try:
        res = await asyncio.wait_for(
            _run(["git", "-C", str(dest), "describe", "--tags", "--always"]), timeout=5.0
        )
    except TimeoutError:
        return ""  # a stalled git must never hang the status read
    return res["output"].strip() if res["ok"] else ""


async def _github_latest(repo: str) -> str:
    """Latest published version of ``owner/name`` from GitHub (release tag, else newest tag). Cached
    on success for ``_LATEST_TTL``. Returns ``""`` on rate-limit / unreachable / no tags (and does
    NOT cache the empty, so it can be retried once quota is back). Never raises."""
    now = time.time()
    hit = _latest_cache.get(repo)
    if hit and now - hit[0] < _LATEST_TTL:
        return hit[1]
    version = ""
    try:
        async with httpx.AsyncClient(timeout=4.0) as client:
            r = await client.get(f"https://api.github.com/repos/{repo}/releases/latest")
            if r.status_code == 200:
                version = str((r.json() or {}).get("tag_name") or "")
            if not version:
                r = await client.get(
                    f"https://api.github.com/repos/{repo}/tags", params={"per_page": 1}
                )
                if r.status_code == 200:
                    data = r.json()
                    if isinstance(data, list) and data:
                        version = str(data[0].get("name") or "")
    except (httpx.HTTPError, ValueError):
        version = ""
    if version:
        _latest_cache[repo] = (now, version)
    return version


async def _latest_versions(
    repos_by_cid: dict[str, str], github_remaining: int | None
) -> dict[str, str]:
    """Best-effort latest version per component id, for not-installed components. Repos already
    cached are free; uncached ones are fetched only when there is comfortable quota headroom (each
    may cost up to 2 requests), so a status read never exhausts the host's GitHub limit."""
    _load_latest_cache()
    now = time.time()
    repos = set(repos_by_cid.values())
    cached = {
        r: _latest_cache[r][1]
        for r in repos
        if r in _latest_cache and now - _latest_cache[r][0] < _LATEST_TTL
    }
    to_fetch = [r for r in repos if r not in cached]
    # Budget the lookups: each repo costs up to 2 requests, and we reserve headroom for Moonraker's
    # own update checks. Fetch only as many as fit (partial is fine; the rest fill in over later
    # reads as the cache warms). When Moonraker does NOT report remaining quota, assume a
    # conservative floor rather than "unlimited" - treating None as no-gate would let one cold
    # read fan out across the whole catalog and exhaust GitHub's 60/hr limit.
    budget = github_remaining if github_remaining is not None else 30
    max_fetch = max(0, (budget - 10) // 2)
    if len(to_fetch) > max_fetch:
        to_fetch = to_fetch[:max_fetch]
    fetched: dict[str, str] = {}
    if to_fetch:
        sem = asyncio.Semaphore(6)

        async def one(repo: str) -> None:
            async with sem:
                fetched[repo] = await _github_latest(repo)

        await asyncio.gather(*[one(r) for r in to_fetch])
        if any(fetched.values()):
            _save_latest_cache()  # persist new versions so they survive restarts / quota droughts
    versions = {**cached, **fetched}
    return {cid: versions.get(repo, "") for cid, repo in repos_by_cid.items()}


async def probe_detailed(
    version_info: dict[str, Any] | None = None,
    services: set[str] | None = None,
    github_remaining: int | None = None,
) -> dict[str, dict[str, Any]]:
    """Rich per-component status for the widget: install state + version numbers + an update flag.

    - Installed + Moonraker-managed → ``version`` / ``latest`` / ``updateAvailable`` from the
      update-manager ``version_info`` entry (the authoritative, already-fetched source).
    - Installed + unmanaged git checkout → ``version`` via ``git describe`` (local, best-effort).
    - Not-installed → ``latest`` via a quota-gated, cached GitHub lookup (so the operator can see
      what an install would bring); empty when quota is short or the repo has no published tag.
    """
    catalog = load_catalog()
    vi_map = {k.lower(): v for k, v in (version_info or {}).items() if isinstance(v, dict)}
    managed = set(vi_map.keys())
    s = services or set()

    out: dict[str, dict[str, Any]] = {}
    git_dirs: dict[str, Path] = {}
    not_installed: dict[str, str] = {}

    for cid, c in catalog.items():
        installed = _is_installed(c, managed, s)
        entry = vi_map.get((c.manager_key or c.id).lower())
        rec: dict[str, Any] = {
            "status": "installed" if installed else "not-installed",
            "version": "",
            "latest": "",
            "updateAvailable": False,
        }
        if entry is not None:
            rec["version"] = str(entry.get("version") or "")
            rec["latest"] = str(entry.get("remote_version") or "")
            rec["updateAvailable"] = bool(installed and _update_available(entry))
        elif installed:
            git_dirs[cid] = _install_dir(c)
        else:
            not_installed[cid] = c.repo
        out[cid] = rec

    if git_dirs:
        versions = await asyncio.gather(*[_git_version(p) for p in git_dirs.values()])
        for cid, version in zip(git_dirs.keys(), versions, strict=True):
            out[cid]["version"] = version

    if not_installed:
        for cid, version in (await _latest_versions(not_installed, github_remaining)).items():
            out[cid]["latest"] = version

    return out


def _writes_flag_path() -> Path:
    return Path(get_settings().data_dir).expanduser() / "setup-writes.json"


def _persisted_writes() -> bool:
    """The GUI-toggled writes flag (persisted), so installing can be enabled from the widget."""
    try:
        return bool(json.loads(_writes_flag_path().read_text(encoding="utf-8")).get("enabled"))
    except (OSError, json.JSONDecodeError):
        return False


def writes_enabled() -> bool:
    """Writes are on if the host env opts in OR the operator enabled them from the GUI."""
    return bool(get_settings().setup_writes_enabled) or _persisted_writes()


def set_writes_enabled(enabled: bool) -> bool:
    """Persist the GUI writes toggle so install/update/remove work from the widget (no CLI/env)."""
    path = _writes_flag_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps({"enabled": bool(enabled)}), encoding="utf-8")
    tmp.replace(path)
    return bool(enabled)


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


def _missing_deps(
    c: Component, catalog: dict[str, Component], installed: dict[str, str]
) -> list[str]:
    """Names of this component's direct dependencies that aren't installed yet."""
    return [
        catalog[dep].name for dep in c.deps if dep in catalog and installed.get(dep) != "installed"
    ]


async def install(
    cid: str, managed: set[str] | None = None, services: set[str] | None = None
) -> dict[str, Any]:
    catalog = load_catalog()
    component = _require(cid, catalog)
    if not writes_enabled():
        return _refused()
    # Dependency guard: refuse rather than silently clone a core dep (e.g. Klipper/Moonraker need
    # their own setup, not a bare git clone). Tell the operator what to install first.
    status = await probe_status(managed, services)
    missing = _missing_deps(component, catalog, status)
    if missing:
        return {
            "refused": True,
            "output": f"Install {', '.join(missing)} first - {component.name} depends on it.",
        }
    # FilaMind apps (3d / screen / flow) ship a one-line installer in their repo - run it so the
    # GUI can install them even though they aren't a plain git_repo (web / tauri).
    if component.first_party:
        result = await _run(["bash", "-c", f"curl -fsSL {_raw_installer(component)} | bash"])
        return _augment_root_failure(result, component)
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
    return {"ok": True, "output": f"Cloned {component.name}; no install.sh - finish per its docs."}


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
    # FilaMind apps clean up via their own installer's uninstall path (removes the nginx site etc.).
    if component.first_party:
        return await _run(
            ["bash", "-c", f"curl -fsSL {_raw_installer(component)} | bash -s -- uninstall"]
        )
    dest = _install_dir(component)
    # Path guard: only ever remove a direct child of $HOME.
    if dest.parent != Path.home() or not dest.is_dir():
        return {"refused": True, "output": f"Refusing to remove {dest} (not a direct $HOME child)."}
    await asyncio.to_thread(shutil.rmtree, dest)
    return {"ok": True, "output": f"Removed {dest}"}


# Ports we never let a web UI take over (Moonraker + Klipper's common API/host ports).
_RESERVED_PORTS = {7125, 7126, 8883}


async def set_port(
    cid: str, port: int, managed: set[str] | None = None, services: set[str] | None = None
) -> dict[str, Any]:
    """Change the port an installed web UI is served on. First-party apps re-run their own installer
    with --port; third-party UIs get a best-effort nginx ``listen`` rewrite + reload."""
    catalog = load_catalog()
    component = _require(cid, catalog)
    if not writes_enabled():
        return _refused()
    if not (1 <= port <= 65535):
        return {"refused": True, "output": f"Port {port} is out of range (1-65535)."}
    if port in _RESERVED_PORTS:
        return {"refused": True, "output": f"Port {port} is reserved; pick another."}
    if component.type != "web":
        return {"refused": True, "output": f"{component.name} has no web port to change."}
    status = await probe_status(managed, services)
    if status.get(cid) != "installed":
        return {"refused": True, "output": f"{component.name} is not installed."}
    # First-party web app: re-run its installer with the new port (it owns its nginx site).
    if component.first_party:
        cmd = f"curl -fsSL {_raw_installer(component)} | bash -s -- install --port {port}"
        return await _run(["bash", "-c", cmd])
    # Third-party web UI: rewrite the `listen` directive of its nginx site, then reload.
    site = f"/etc/nginx/sites-available/{cid}"
    script = (
        f"set -e; "
        f'test -f "{site}" || {{ echo "no nginx site at {site}"; exit 1; }}; '
        f"sudo sed -i -E 's/^([[:space:]]*listen[[:space:]]+)[0-9]+;/\\1{port};/' \"{site}\"; "
        f"sudo nginx -t && sudo systemctl reload nginx"
    )
    return await _run(["bash", "-c", script])
