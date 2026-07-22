"""FilaMind Setup - component manager service.

Reads a curated catalog of installable Klipper-ecosystem components, reports what is installed
(read-only), and - only when the operator explicitly enables writes (FILAMIND_SETUP_WRITES) on
the host - installs / updates / removes them. Every mutation is gated, path-guarded under $HOME,
and shells out to git through the host's normal tooling.

Write operations are DISABLED by default: the safe, read-only state is what ships, and an operator
turns writes on per host. The same engine backs the `filamind-setup` CLI.
"""

from __future__ import annotations

import asyncio
import contextlib
import io
import json
import re
import shlex
import shutil
import time
import zipfile
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

from app.config import get_settings
from app.services import setup_confedit, setup_provenance

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


def clear_version_caches() -> None:
    """Drop the in-memory version caches so the next probe re-reads from GitHub / each clone's
    origin. Backs the "Check for updates" button, which must reflect a just-published release rather
    than a week-old cached value. (Also called with ``force`` on the probe path.) Resets the
    disk-load flag so the persisted last-known versions are re-read - a forced refresh under low
    GitHub quota must still show those (as retained fallbacks), never blank them out."""
    global _latest_cache_loaded
    _latest_cache.clear()
    _git_latest_cache.clear()
    _latest_cache_loaded = False


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
    #: Still under active development and research - the widget badges it so nobody mistakes it
    #: for a settled release (the catalog is the single source; the raw payload carries the flag).
    experimental: bool = False
    desc: str = ""
    #: Moonraker update-manager key when it differs from ``id`` (e.g. ``KlipperScreen``).
    manager_key: str = ""
    #: systemd unit name when this component runs as a service (e.g. ``crowsnest``).
    service: str = ""
    #: install directory name under ``$HOME`` when it differs from ``id`` (e.g. ``KlipperScreen``).
    dir: str = ""
    #: Subcommand handed to a first-party app's ``scripts/install.sh`` so the GUI install stands up
    #: the right deployment (FilaMind screen → ``native`` for the kiosk, not the browser preview).
    install_args: str = ""
    #: An ADDITIONAL first-party deployment a button can install on top of the default one (the
    #: FilaMind 3d ``agent``: the :8030 service that unlocks the suite widgets). Distinct from
    #: ``install_args``: when they're equal the "service" IS the main install (FilaMind screen).
    service_install: str = ""
    #: A web UI's GitHub release-zip asset (``mainsail.zip``); its presence + kind ``web-ui`` +
    #: not first-party selects the release-zip → nginx-site → Moonraker web-entry install path.
    release_asset: str = ""
    #: The ``[update_manager]`` block type to register in moonraker.conf on install (``web`` for a
    #: static UI, ``git_repo`` for a clone/extra) so updates read + apply through Moonraker. Empty
    #: when the component's own installer already registers itself.
    mr_type: str = ""
    #: A ``printer.cfg`` ``[include <file>]`` the add-on needs to be wired in (offered as a toggle).
    config_include: str = ""
    #: Klipper-extra module filenames this component provides; each is symlinked into
    #: ``~/klipper/klippy/extras`` on install (and unlinked FIRST on remove, before the clone is
    #: deleted, or Klipper would fail to start on a dangling symlink).
    extras: list[str] = field(default_factory=list)
    #: An information-only card (nothing to install here - e.g. CAN tools already ship in Klipper).
    guide: bool = False
    #: The component's installer prompts interactively (best-effort headless; may need finishing).
    interactive: bool = False


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
                experimental=bool(c.get("experimental", False)),
                desc=str(c.get("desc", "")),
                manager_key=str(c.get("manager_key", "")),
                service=str(c.get("service", "")),
                dir=str(c.get("dir", "")),
                install_args=str(c.get("install_args", "")),
                service_install=str(c.get("service_install", "")),
                release_asset=str(c.get("release_asset", "")),
                mr_type=str(c.get("mr_type", "")),
                config_include=str(c.get("config_include", "")),
                extras=list(c.get("extras", [])),
                guide=bool(c.get("guide", False)),
                interactive=bool(c.get("interactive", False)),
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


def _bash_installer(component: Component, args: str = "") -> str:
    """``curl … scripts/install.sh | bash`` for a first-party app, optionally with ``-s -- <args>``
    to pick a deployment (3d → ``agent``, screen → ``native``, a web app → ``install --port N``)."""
    cmd = f"curl -fsSL {_raw_installer(component)} | bash"
    return f"{cmd} -s -- {args}" if args else cmd


def _augment_root_failure(result: dict[str, Any], component: Component) -> dict[str, Any]:
    """A first-party install makes host changes that need root (apt for a .deb, systemd units,
    nginx). The Setup service runs with no terminal to type a sudo password, so it relies on the
    one-time passwordless-sudo grant FilaMind Flow's installer writes. When that grant is missing
    the install fails with 'a password is required'; point the operator at the single command that
    establishes it - after which every install runs from the widget with no prompt - instead of a
    cryptic error or a re-run that hits the same wall."""
    if result.get("ok"):
        return result
    out = result.get("output") or ""
    if any(s in out for s in ("terminal is required", "password is required", "sudo:")):
        result["output"] = (
            out.rstrip()
            + f"\n\nInstalling {component.name} needs root on the printer host, and the Setup "
            "widget runs without a password. Grant it once over SSH (then every install works "
            "from here, no prompt):\n  sudo bash ~/filamind-flow/scripts/install.sh sudoers"
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


def _nginx_site_port(site: str) -> int | None:
    """The port a first-party nginx app is served on, read from its ``listen N;`` directive. Lets
    the widget show where the app lives + build an "open" link, without hard-coding the default."""
    for base in ("/etc/nginx/sites-enabled", "/etc/nginx/sites-available"):
        try:
            text = (Path(base) / site).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        m = re.search(r"^\s*listen\s+(\d+)", text, re.MULTILINE)
        if m:
            return int(m.group(1))
    return None


async def _app_reachable(port: int) -> bool:
    """Best-effort 'is the app actually being served' check: a quick local GET to its nginx port.
    A site can be installed (file present) yet not served (nginx down / config error), so this is
    the truthful 'working' signal. Never raises; a non-5xx response counts as up."""
    try:
        async with httpx.AsyncClient(timeout=1.5) as client:
            r = await client.get(f"http://127.0.0.1:{port}/")
            return r.status_code < 500
    except httpx.HTTPError:
        return False


async def _service_active(unit: str) -> bool:
    """Whether a systemd unit is running right now (read-only ``is-active``; no sudo needed)."""
    res = await _run(["systemctl", "is-active", "--quiet", unit])
    return bool(res["ok"])


def section_keys(sections: list[str]) -> set[str]:
    """Moonraker config section names reduced to comparable keys: the first token, lowercased -
    ``[spoolman]`` -> ``spoolman``, ``[power Auto Lights]`` -> ``power``, ``[update_manager X]`` ->
    ``update_manager`` (which matches no component, so it can't false-positive)."""
    out: set[str] = set()
    for raw in sections:
        head = str(raw).strip().split()
        if head:
            out.add(head[0].lower())
    return out


def _install_dir_present(c: Component) -> bool:
    """The clone-to-``$HOME`` heuristic, matched case-INSENSITIVELY.

    Several ecosystem installers clone to the repo's own capitalisation (``~/Spoolman``,
    ``~/KlipperScreen``) while the catalog keys are lowercase - and Linux paths are case-sensitive,
    so an exact match silently missed those installs and reported them as available.
    """
    name = (c.dir or c.id).lower()
    home = Path.home()
    if (home / (c.dir or c.id)).is_dir():
        return True
    try:
        return any(p.name.lower() == name and p.is_dir() for p in home.iterdir())
    except OSError:
        return False


def _is_installed(
    c: Component, managed: set[str], services: set[str], sections: set[str] | None = None
) -> bool:
    """Combine the install signals, most-authoritative first:

    1. Moonraker's update-manager registry (``manager_key`` or ``id``) - the components Moonraker
       actually tracks; survives non-``$HOME`` layouts and is the source of truth when present.
    2. A managed systemd unit (``service``) - catches service-style installs (crowsnest, spoolman).
    3. A section in Moonraker's OWN config named after the component - how Moonraker is wired to a
       component that runs as a container or on another host (``[spoolman]``), where there is no
       local unit and no clone to find.
    4. For a first-party nginx app, the nginx site itself - a bare clone (downloaded but never set
       up) is NOT installed; the site only exists once its installer's web-server step succeeded.
    5. The clone-to-``$HOME`` directory heuristic (case-insensitive) - the offline fallback.
    """
    key = (c.manager_key or c.id).lower()
    if key in managed:
        return True
    if c.service and c.service.lower() in services:
        return True
    if sections and key in sections:
        return True
    if _is_nginx_app(c):
        return _nginx_site_present(c.id)
    return _install_dir_present(c)


async def probe_status(
    managed: set[str] | None = None,
    services: set[str] | None = None,
    sections: set[str] | None = None,
) -> dict[str, str]:
    """Read-only install status per component, combining Moonraker signals with the dir heuristic.

    ``managed`` (update-manager keys), ``services`` (systemd units) and ``sections`` (Moonraker's
    own config sections) come from Moonraker when reachable; when omitted/empty the detection falls
    back to the clone-to-``$HOME`` heuristic, so this stays correct offline.
    """
    catalog = load_catalog()
    m = managed or set()
    s = services or set()
    sec = sections or set()
    return {
        cid: ("installed" if _is_installed(c, m, s, sec) else "not-installed")
        for cid, c in catalog.items()
    }


def _norm_ver(v: Any) -> str:
    """Normalize a version label for comparison: trim + drop a leading ``v`` so ``v1.2.0`` and
    ``1.2.0`` don't read as different (which used to raise a false 'update available')."""
    return str(v or "").strip().lstrip("vV")


def _update_available(entry: dict[str, Any]) -> bool:
    """An update is available when Moonraker reports commits behind (list or count), or the
    installed version differs from the remote one (web UIs have no commit list, only a version)."""
    behind = entry.get("commits_behind")
    if isinstance(behind, list) and behind:
        return True
    count = entry.get("commits_behind_count")
    if isinstance(count, int) and count > 0:
        return True
    version, remote = _norm_ver(entry.get("version")), _norm_ver(entry.get("remote_version"))
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


# Update detection for installed-but-UNMANAGED git checkouts (the FilaMind apps + guppyscreen, which
# Moonraker's update_manager doesn't track): compare the local clone to its own ``origin`` with an
# anonymous fetch - no GitHub API, no token. Cached briefly so a status read doesn't re-fetch on
# every call; the asyncio.wait_for guards keep a slow/offline fetch from ever hanging the read.
_GIT_LATEST_TTL = 300.0  # 5 min
_git_latest_cache: dict[str, tuple[float, tuple[str, bool]]] = {}


async def _git_latest(dest: Path) -> tuple[str, bool]:
    """``(remote_label, update_available)`` for an unmanaged checkout by comparing ``HEAD`` to its
    ``origin`` upstream. Returns ``("", False)`` on any failure, so it degrades exactly like a
    missing lookup (offline / shallow clone / no origin → no update offered, never an error)."""
    if not (dest / ".git").is_dir():
        return ("", False)
    key = str(dest)
    now = time.time()
    hit = _git_latest_cache.get(key)
    if hit and now - hit[0] < _GIT_LATEST_TTL:
        return hit[1]

    async def git(*args: str) -> str:
        try:
            res = await asyncio.wait_for(_run(["git", "-C", str(dest), *args]), timeout=8.0)
        except TimeoutError:
            return ""
        return res["output"].strip() if res["ok"] else ""

    result: tuple[str, bool] = ("", False)
    if await git("remote", "get-url", "origin"):
        # Resolve the upstream ref: the tracked branch, else origin/HEAD, else origin/main|master.
        upstream = await git("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}")
        if not upstream:
            for cand in ("origin/HEAD", "origin/main", "origin/master"):
                if await git("rev-parse", "--verify", "--quiet", cand):
                    upstream = cand
                    break
        if upstream:
            # The catalog clones with `--depth 1`; a shallow clone can't compute HEAD..upstream, so
            # unshallow once (then a normal fetch) - otherwise every unmanaged clone always read
            # "no update". Best-effort; offline just yields no update.
            if await git("rev-parse", "--is-shallow-repository") == "true":
                await git("fetch", "--quiet", "--unshallow", "origin")
            else:
                await git("fetch", "--quiet", "origin")
            label = await git("describe", "--tags", "--always", upstream)
            try:
                behind = int(await git("rev-list", "--count", f"HEAD..{upstream}"))
            except ValueError:
                behind = 0
            if label:
                result = (label, behind > 0)
    _git_latest_cache[key] = (now, result)
    return result


async def _github_latest(repo: str, force: bool = False) -> str:
    """Latest published version of ``owner/name`` from GitHub (release tag, else newest tag). Cached
    on success for ``_LATEST_TTL``. Returns ``""`` on rate-limit / unreachable / no tags (and does
    NOT cache the empty, so it can be retried once quota is back). Never raises. ``force`` bypasses
    the freshness cache (the "Check for updates" button re-reads even a recently-cached version)."""
    now = time.time()
    hit = _latest_cache.get(repo)
    if not force and hit and now - hit[0] < _LATEST_TTL:
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
    repos_by_cid: dict[str, str], github_remaining: int | None, force: bool = False
) -> dict[str, str]:
    """Best-effort latest version per component id, for not-installed components. Repos already
    cached are free; uncached ones are fetched only when there is comfortable quota headroom (each
    may cost up to 2 requests), so a status read never exhausts the host's GitHub limit. ``force``
    (the "Check for updates" button) ignores cache freshness so newly-published releases show up,
    still bounded by the quota budget."""
    _load_latest_cache()
    now = time.time()
    repos = set(repos_by_cid.values())
    cached = (
        {}
        if force
        else {
            r: _latest_cache[r][1]
            for r in repos
            if r in _latest_cache and now - _latest_cache[r][0] < _LATEST_TTL
        }
    )
    to_fetch = [r for r in repos if r not in cached]
    # Budget the lookups: each repo costs up to 2 requests, and we reserve headroom for Moonraker's
    # own update checks. Fetch only as many as fit (partial is fine; the rest fill in over later
    # reads as the cache warms). When Moonraker does NOT report remaining quota, assume a
    # conservative floor rather than "unlimited" - treating None as no-gate would let one cold
    # read fan out across the whole catalog and exhaust GitHub's 60/hr limit.
    budget = github_remaining if github_remaining is not None else 30
    max_fetch = max(0, (budget - 10) // 2)
    # Repos that don't fit the quota budget this round: keep their last-known (disk-cached) version
    # rather than re-fetching, so a forced refresh under low quota never BLANKS a version that was
    # showing - it just doesn't update those until quota recovers.
    dropped = to_fetch[max_fetch:]
    to_fetch = to_fetch[:max_fetch]
    fetched: dict[str, str] = {}
    if to_fetch:
        sem = asyncio.Semaphore(6)

        async def one(repo: str) -> None:
            async with sem:
                fetched[repo] = await _github_latest(repo, force=force)

        await asyncio.gather(*[one(r) for r in to_fetch])
        if any(fetched.values()):
            _save_latest_cache()  # persist new versions so they survive restarts / quota droughts
    retained = {r: _latest_cache[r][1] for r in dropped if r in _latest_cache}
    versions = {**retained, **cached, **fetched}
    return {cid: versions.get(repo, "") for cid, repo in repos_by_cid.items()}


async def probe_detailed(
    version_info: dict[str, Any] | None = None,
    services: set[str] | None = None,
    github_remaining: int | None = None,
    force_refresh: bool = False,
    sections: set[str] | None = None,
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
    stamped: dict[str, str] = {}  # installed non-git (web/manual/extra) cid -> repo
    not_installed: dict[str, str] = {}
    nginx_apps: dict[str, int] = {}  # first-party nginx app cid -> served port
    service_units: dict[str, str] = {}  # installed component cid -> its systemd unit

    for cid, c in catalog.items():
        installed = _is_installed(c, managed, s, sections or set())
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
            rec["managed"] = True  # Moonraker already tracks it → hide the "register" action
        elif installed:
            git_dirs[cid] = _install_dir(c)  # git describe / HEAD-vs-origin; stamp fallback below
        else:
            not_installed[cid] = c.repo
        # First-party nginx apps (FilaMind 3d / screen): surface the served port + a runtime
        # 'running' flag so the widget can show whether they actually work and offer a restart.
        if installed and _is_nginx_app(c):
            port = _nginx_site_port(c.id)
            if port is not None:
                rec["port"] = port
                nginx_apps[cid] = port
        elif installed and c.service:
            service_units[cid] = c.service  # a plain systemd service → is-active health below
        # Whether the add-on's printer.cfg [include] is wired in (drives the 'wired in' badge).
        if installed and c.config_include:
            rec["includeActive"] = config_include_present(c.config_include)
        out[cid] = rec

    if git_dirs:
        # For an unmanaged checkout, the local clone is the only source of truth: `version` from
        # `git describe`, and `latest`/`updateAvailable` from a HEAD-vs-origin compare (no GitHub).
        paths = list(git_dirs.values())
        versions, latests = await asyncio.gather(
            asyncio.gather(*[_git_version(p) for p in paths]),
            asyncio.gather(*[_git_latest(p) for p in paths]),
        )
        for cid, version, (latest, behind) in zip(git_dirs.keys(), versions, latests, strict=True):
            if not version and not latest:
                # Installed but not actually a git checkout (a web-UI zip extract, a manual add-on):
                # fall back to the install stamp for the version + a GitHub latest lookup below.
                out[cid]["version"] = str((setup_provenance.read(cid) or {}).get("ref") or "")
                stamped[cid] = catalog[cid].repo
            else:
                out[cid]["version"] = version
                out[cid]["latest"] = latest
                out[cid]["updateAvailable"] = behind

    if nginx_apps:
        reach = await asyncio.gather(*[_app_reachable(p) for p in nginx_apps.values()])
        for cid, ok in zip(nginx_apps.keys(), reach, strict=True):
            out[cid]["running"] = ok

    if service_units:
        active = await asyncio.gather(*[_service_active(u) for u in service_units.values()])
        for cid, ok in zip(service_units.keys(), active, strict=True):
            out[cid]["running"] = ok

    # GitHub latest for both not-installed (what an install would bring) and installed-but-stamped
    # (web/manual/extra, to compute an update flag against the stamped install version).
    gh_targets = {**not_installed, **stamped}
    if gh_targets:
        for cid, latest in (
            await _latest_versions(gh_targets, github_remaining, force=force_refresh)
        ).items():
            out[cid]["latest"] = latest
            if cid in stamped:
                v, remote = _norm_ver(out[cid]["version"]), _norm_ver(latest)
                out[cid]["updateAvailable"] = bool(v and remote and v != remote)

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


# ---- automatic updates (opt-in, periodic) ----------------------------------------------------
# A background loop (app.main) calls auto_update_tick on a cadence. Updates are applied ONLY when
# the operator opted in AND the printer is idle, so a long print is never interrupted. Default off.
_AUTOUPDATE_DEFAULT_INTERVAL_H = 24


def _autoupdate_path() -> Path:
    return Path(get_settings().data_dir).expanduser() / "setup-autoupdate.json"


def _autoupdate_state() -> dict[str, Any]:
    try:
        raw = json.loads(_autoupdate_path().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        raw = {}
    return {
        "enabled": bool(raw.get("enabled", False)),
        "intervalHours": max(1, int(raw.get("intervalHours") or _AUTOUPDATE_DEFAULT_INTERVAL_H)),
        "lastRun": float(raw.get("lastRun") or 0.0),
    }


def _write_autoupdate_state(state: dict[str, Any]) -> None:
    path = _autoupdate_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state), encoding="utf-8")
    tmp.replace(path)


def autoupdate_prefs() -> dict[str, Any]:
    """Operator-facing auto-update preferences (enabled + interval); ``lastRun`` stays internal."""
    s = _autoupdate_state()
    return {"enabled": s["enabled"], "intervalHours": s["intervalHours"]}


def set_autoupdate_prefs(enabled: bool, interval_hours: int) -> dict[str, Any]:
    """Persist the auto-update toggle + interval from the widget."""
    s = _autoupdate_state()
    s["enabled"] = bool(enabled)
    s["intervalHours"] = max(1, int(interval_hours or _AUTOUPDATE_DEFAULT_INTERVAL_H))
    _write_autoupdate_state(s)
    return {"enabled": s["enabled"], "intervalHours": s["intervalHours"]}


async def _printer_busy(moonraker_url: str) -> bool:
    """True if a print is running/paused (so auto-update holds off). Unknown → True (play safe)."""
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            r = await client.get(
                f"{moonraker_url}/printer/objects/query", params={"print_stats": "state"}
            )
            stats = (r.json().get("result", {}).get("status", {}).get("print_stats", {})) or {}
            return str(stats.get("state", "")).lower() in {"printing", "paused"}
    except (httpx.HTTPError, ValueError, KeyError, TypeError):
        return True  # can't tell → never risk updating during a possible print


async def auto_update_tick(moonraker_url: str, now: float) -> dict[str, Any]:
    """One auto-update cycle, called periodically by the app's background loop. A no-op unless the
    operator opted in, writes are enabled, the interval has elapsed, and the printer is idle. Then
    it applies every available update (FilaMind apps + Moonraker-managed components) and records the
    run time. Returns a small summary for logging; never raises."""
    state = _autoupdate_state()
    if not state["enabled"] or not writes_enabled():
        return {"ran": False, "reason": "disabled"}
    if now - state["lastRun"] < state["intervalHours"] * 3600:
        return {"ran": False, "reason": "not-due"}
    if await _printer_busy(moonraker_url):
        return {"ran": False, "reason": "printer-busy"}

    from app.services.moonraker_client import MoonrakerClient

    client = MoonrakerClient(moonraker_url)
    # The config-section signal gets its own guard: it is served by an endpoint a host can refuse,
    # and folding it into the main try would take the update-manager signal down with it.
    try:
        sections = section_keys(await client.config_sections())
    except (httpx.HTTPError, ValueError):
        sections = set()
    try:
        raw = await client.update_status_full()
        vi = raw.get("version_info")
        version_info = vi if isinstance(vi, dict) else {}
        remaining = raw.get("github_requests_remaining")
        services = {s.lower() for s in await client.available_services()}
        github_remaining = remaining if isinstance(remaining, int) else None
    except (httpx.HTTPError, ValueError):
        version_info, services, github_remaining = {}, set(), None

    detailed = await probe_detailed(version_info, services, github_remaining, sections=sections)
    targets = [cid for cid, rec in detailed.items() if rec.get("updateAvailable")]
    # Record the run up front so a mid-list failure doesn't make us retry on every tick.
    state["lastRun"] = now
    _write_autoupdate_state(state)
    if not targets:
        return {"ran": True, "updated": [], "ok": []}

    managed = {k.lower() for k in version_info}

    async def mr_update(name: str) -> None:
        await client.update_client(name)

    ok: list[str] = []
    for cid in targets:
        try:
            res = await update(cid, managed, mr_update)
            if res.get("ok"):
                ok.append(cid)
        except Exception:  # one component's failure must not stop the rest
            continue
    return {"ran": True, "updated": targets, "ok": ok}


def _refused() -> dict[str, Any]:
    return {
        "refused": True,
        "output": "Installing from here is turned off. Use the “Enable installing” button "
        "above to install, update and remove components directly from this widget.",
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


async def _run_streaming(cmd: list[str], task: Any) -> dict[str, Any]:
    """Like ``_run`` but appends each output line to ``task`` as it arrives, so the widget can show
    live install progress instead of one opaque blocking call. Returns the same result dict."""
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    lines: list[str] = []
    assert proc.stdout is not None
    async for raw in proc.stdout:
        line = raw.decode(errors="replace")
        lines.append(line)
        task.append(line)
    code = await proc.wait()
    return {"ok": code == 0, "code": code, "output": "".join(lines)}


def _require(cid: str, catalog: dict[str, Component]) -> Component:
    component = catalog.get(cid)
    if component is None:
        raise ValueError(f"Unknown component: {cid}")
    return component


# ---- host operations: nginx sites, moonraker.conf / printer.cfg edits, extras, release zips ------
# Each mutation reuses ONLY the narrow passwordless-sudo grant the Setup service already holds
# (cp / rm / systemctl), never `ln` or a root `tee`; config files are user-owned so they need no
# sudo. Every edit backs up first and (for nginx) reverts on failure, so a bad step can't take
# nginx / Moonraker / Klipper down permanently.

_KLIPPER_CONFIG_DIRS = ("printer_data/config", "klipper_config")


def _klipper_config_file(name: str) -> Path | None:
    """The path to a Klipper/Moonraker config file (``moonraker.conf`` / ``printer.cfg``) under the
    standard data dir, or None if not found (a non-standard layout just skips the edit safely)."""
    for d in _KLIPPER_CONFIG_DIRS:
        p = Path.home() / d / name
        if p.is_file():
            return p
    return None


def _backup_config(path: Path) -> None:
    with contextlib.suppress(OSError):
        shutil.copy2(path, path.with_name(path.name + ".fmbak"))


def _moonraker_block_body(c: Component) -> list[str]:
    """The ``[update_manager <key>]`` body for a component, by its ``mr_type``."""
    path = f"~/{c.dir or c.id}"
    if c.mr_type == "web":
        return ["type: web", "channel: stable", f"repo: {c.repo}", f"path: {path}"]
    return [  # git_repo
        "type: git_repo",
        f"path: {path}",
        f"origin: https://github.com/{c.repo}.git",
        "is_system_service: False",
        "managed_services: klipper",
    ]


async def _register_moonraker(c: Component) -> None:
    """Add/replace this component's ``[update_manager]`` block in moonraker.conf and restart
    Moonraker so it picks it up (best-effort; a missing moonraker.conf just skips registration)."""
    if not c.mr_type:
        return
    path = _klipper_config_file("moonraker.conf")
    if path is None:
        return
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return
    new, changed = setup_confedit.upsert_update_manager(
        text, c.manager_key or c.id, _moonraker_block_body(c)
    )
    if changed:
        _backup_config(path)
        with contextlib.suppress(OSError):
            path.write_text(new, encoding="utf-8")
            await _run(["sudo", "-n", "systemctl", "restart", "moonraker"])


async def _deregister_moonraker(c: Component) -> None:
    """Drop this component's ``[update_manager]`` block from moonraker.conf; restart Moonraker."""
    path = _klipper_config_file("moonraker.conf")
    if path is None:
        return
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return
    new, changed = setup_confedit.drop_update_manager(text, c.manager_key or c.id)
    if changed:
        _backup_config(path)
        with contextlib.suppress(OSError):
            path.write_text(new, encoding="utf-8")
            await _run(["sudo", "-n", "systemctl", "restart", "moonraker"])


def _nginx_site_body(c: Component, port: int, root: Path) -> str:
    """A standard static-web-UI nginx site (SPA fallback + Moonraker proxy), like Mainsail/Fluidd
    ship. Served on ``port`` from ``root``; API/websocket proxied to Moonraker on :7125."""
    return (
        f"server {{\n"
        f"    listen {port};\n"
        f"    listen [::]:{port};\n"
        f"    server_name _;\n"
        f"    root {root};\n"
        f"    index index.html;\n"
        f"    location / {{ try_files $uri $uri/ /index.html; }}\n"
        f'    location = /index.html {{ add_header Cache-Control "no-store"; }}\n'
        f"    location /websocket {{\n"
        f"        proxy_pass http://127.0.0.1:7125/websocket;\n"
        f"        proxy_http_version 1.1;\n"
        f"        proxy_set_header Upgrade $http_upgrade;\n"
        f'        proxy_set_header Connection "upgrade";\n'
        f"        proxy_set_header Host $http_host;\n"
        f"    }}\n"
        f"    location ~ ^/(printer|api|access|machine|server|webcam.*)/ {{\n"
        f"        proxy_pass http://127.0.0.1:7125$request_uri;\n"
        f"        proxy_set_header Host $http_host;\n"
        f"        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;\n"
        f"        proxy_set_header X-Scheme $scheme;\n"
        f"    }}\n"
        f"}}\n"
    )


async def _install_nginx_site(c: Component, port: int, root: Path) -> dict[str, Any]:
    """Write + enable a third-party web UI's nginx site headless-safely: cp the file into BOTH
    sites-available and sites-enabled (avoids the ungranted ``ln``/root ``tee``), reload, and on a
    reload failure remove both files + reload again so a bad site can never take nginx down."""
    tmp = Path(get_settings().data_dir).expanduser() / f".{c.id}.nginx.tmp"
    avail = f"/etc/nginx/sites-available/{c.id}"
    enabled = f"/etc/nginx/sites-enabled/{c.id}"
    try:
        tmp.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_text(_nginx_site_body(c, port, root), encoding="utf-8")
    except OSError as exc:
        return {"ok": False, "output": f"could not stage the nginx site: {exc}"}
    for dest in (avail, enabled):
        res = await _run(["sudo", "-n", "cp", str(tmp), dest])
        if not res["ok"]:
            return res
    reload_res = await _run(["sudo", "-n", "systemctl", "reload", "nginx"])
    if not reload_res["ok"]:
        # Revert: a bad site must never leave nginx unable to reload.
        await _run(["sudo", "-n", "rm", "-f", avail, enabled])
        await _run(["sudo", "-n", "systemctl", "reload", "nginx"])
        reload_res["output"] = (
            reload_res.get("output") or ""
        ).rstrip() + f"\n\nnginx rejected the site for {c.name}; reverted (nothing changed)."
        return reload_res
    with contextlib.suppress(OSError):
        tmp.unlink()
    return {"ok": True, "output": f"{c.name} is now served on port {port}."}


async def _remove_nginx_site(c: Component) -> None:
    """Remove a web UI's nginx site (both files) and reload nginx (best-effort)."""
    await _run(
        [
            "sudo",
            "-n",
            "rm",
            "-f",
            f"/etc/nginx/sites-available/{c.id}",
            f"/etc/nginx/sites-enabled/{c.id}",
        ]
    )
    await _run(["sudo", "-n", "systemctl", "reload", "nginx"])


async def _fetch_release_zip(c: Component, dest: Path) -> dict[str, Any]:
    """Download a web UI's latest release zip and extract it to ``dest`` (replacing its contents).
    Anonymous, token-free, follows redirects; never raises (returns an error dict)."""
    url = f"https://github.com/{c.repo}/releases/latest/download/{c.release_asset}"
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=60.0) as client:
            r = await client.get(url)
        if r.status_code != 200:
            return {"ok": False, "output": f"download failed for {c.name} (HTTP {r.status_code})"}
        payload = r.content
    except httpx.HTTPError as exc:
        return {"ok": False, "output": f"could not download {c.name}: {exc}"}
    try:
        if dest.exists():
            await asyncio.to_thread(shutil.rmtree, dest)
        dest.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(lambda: zipfile.ZipFile(io.BytesIO(payload)).extractall(dest))
    except (OSError, zipfile.BadZipFile) as exc:
        return {"ok": False, "output": f"could not unpack {c.name}: {exc}"}
    return {"ok": True, "output": f"Downloaded and extracted {c.name} to {dest}."}


def _klipper_extras_dir() -> Path | None:
    p = Path.home() / "klipper" / "klippy" / "extras"
    return p if p.is_dir() else None


def _link_extras(c: Component, src_dir: Path) -> dict[str, Any]:
    """Symlink each of a Klipper extra's module files from the clone into ``klippy/extras``."""
    ext = _klipper_extras_dir()
    if ext is None:
        return {"ok": False, "output": "~/klipper/klippy/extras not found; is Klipper installed?"}
    for name in c.extras:
        source, target = src_dir / name, ext / name
        if not source.is_file():
            return {"ok": False, "output": f"{name} is not in the {c.name} clone."}
        try:
            if target.exists() or target.is_symlink():
                target.unlink()
            target.symlink_to(source)
        except OSError as exc:
            return {"ok": False, "output": f"could not link {name}: {exc}"}
    return {"ok": True, "output": f"Linked {', '.join(c.extras)} into klippy/extras."}


def _unlink_extras(names: list[str]) -> None:
    """Remove extras symlinks FIRST (before the clone is deleted): a dangling symlink in
    klippy/extras stops Klipper from starting."""
    ext = _klipper_extras_dir()
    if ext is None:
        return
    for name in names:
        with contextlib.suppress(OSError):
            (ext / name).unlink()


async def apply_config_include(file: str, add: bool) -> dict[str, Any]:
    """Add or remove an ``[include <file>]`` line in printer.cfg (backup first), then restart
    Klipper so it takes effect. Used by the widget's per-add-on 'wire in / unwire' toggle."""
    path = _klipper_config_file("printer.cfg")
    if path is None:
        return {"refused": True, "output": "printer.cfg not found; add the include manually."}
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return {"ok": False, "output": f"could not read printer.cfg: {exc}"}
    editor = setup_confedit.add_include if add else setup_confedit.drop_include
    new, changed = editor(text, file)
    if not changed:
        return {
            "ok": True,
            "output": f"[include {file}] was already {'present' if add else 'absent'}.",
        }
    _backup_config(path)
    try:
        path.write_text(new, encoding="utf-8")
    except OSError as exc:
        return {"ok": False, "output": f"could not write printer.cfg: {exc}"}
    await _run(["sudo", "-n", "systemctl", "restart", "klipper"])
    verb = "Added" if add else "Removed"
    return {"ok": True, "output": f"{verb} [include {file}] and restarted Klipper."}


def config_include_present(file: str) -> bool:
    """Whether printer.cfg currently includes ``file`` (drives the 'wired in' badge)."""
    path = _klipper_config_file("printer.cfg")
    if path is None or not file:
        return False
    try:
        return setup_confedit.has_include(path.read_text(encoding="utf-8"), file)
    except OSError:
        return False


async def service_logs(cid: str, lines: int = 200) -> dict[str, Any]:
    """The last ``lines`` of a component's systemd journal (read-only), for debugging a failed
    install/start without SSH. No writes gate - reading logs is always allowed."""
    component = _require(cid, load_catalog())
    if not component.service:
        return {"refused": True, "output": f"{component.name} has no service to show logs for."}
    res = await _run(
        ["journalctl", "-u", component.service, "-n", str(int(lines)), "--no-pager", "--output=cat"]
    )
    out = (res.get("output") or "").strip()
    if not res["ok"] and not out:
        return {"ok": False, "output": f"Could not read the journal for {component.service}."}
    return {"ok": True, "output": out or "(no recent log output)"}


async def register_component(cid: str) -> dict[str, Any]:
    """Register an installed, unmanaged git checkout with Moonraker's update manager (a ``git_repo``
    ``[update_manager]`` block), so it gains reliable, Moonraker-tracked updates."""
    component = _require(cid, load_catalog())
    if not writes_enabled():
        return _refused()
    dest = _install_dir(component)
    if not (dest / ".git").is_dir():
        return {"refused": True, "output": f"{component.name} isn't a git checkout to register."}
    path = _klipper_config_file("moonraker.conf")
    if path is None:
        return {"refused": True, "output": "moonraker.conf not found; register it manually."}
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return {"ok": False, "output": f"could not read moonraker.conf: {exc}"}
    key = component.manager_key or component.id
    # Never clobber an existing block: a component managed by its own installer already has a good
    # (possibly ``type: web``) entry, and rewriting it as git_repo would corrupt it.
    if any(ln.strip() == f"[update_manager {key}]" for ln in text.splitlines()):
        return {"ok": True, "output": f"{component.name} is already registered with Moonraker."}
    body = [
        "type: git_repo",
        f"path: ~/{component.dir or component.id}",
        f"origin: https://github.com/{component.repo}.git",
        "is_system_service: False",
    ]
    new, changed = setup_confedit.upsert_update_manager(text, key, body)
    if not changed:
        return {"ok": True, "output": f"{component.name} is already registered with Moonraker."}
    _backup_config(path)
    try:
        path.write_text(new, encoding="utf-8")
    except OSError as exc:
        return {"ok": False, "output": f"could not write moonraker.conf: {exc}"}
    await _run(["sudo", "-n", "systemctl", "restart", "moonraker"])
    prov = setup_provenance.read(cid) or {}
    setup_provenance.record(
        cid,
        method=str(prov.get("method") or "git"),
        repo=component.repo,
        ref=str(prov.get("ref") or ""),
        extras=list(prov.get("extras") or []),
        service=str(prov.get("service") or component.service),
        moonraker_key=key,
    )
    return {
        "ok": True,
        "output": f"Registered {component.name} with Moonraker; refresh in a moment.",
    }


async def toggle_include(cid: str, add: bool) -> dict[str, Any]:
    """Wire an add-on into printer.cfg (or remove it) by its catalog ``config_include``."""
    component = _require(cid, load_catalog())
    if not writes_enabled():
        return _refused()
    if not component.config_include:
        return {"refused": True, "output": f"{component.name} has no config include to manage."}
    return await apply_config_include(component.config_include, add)


def _missing_deps(
    c: Component, catalog: dict[str, Component], installed: dict[str, str]
) -> list[str]:
    """Names of this component's direct dependencies that aren't installed yet."""
    return [
        catalog[dep].name for dep in c.deps if dep in catalog and installed.get(dep) != "installed"
    ]


async def precheck_install(
    cid: str, managed: set[str] | None = None, services: set[str] | None = None
) -> dict[str, Any] | None:
    """The SYNCHRONOUS gates that must fail fast (as an HTTP 403) before any subprocess runs:
    writes disabled, or a missing dependency. Returns the refusal dict, or None if install may
    proceed. Raises ValueError for an unknown component id."""
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
    return None


async def _install_web_ui(
    c: Component, port: int | None, note: Callable[[str], None]
) -> dict[str, Any]:
    """Install a third-party static web UI (Mainsail/Fluidd): download its release zip, write an
    nginx site, and register a Moonraker ``[update_manager web]`` entry so updates flow through
    Moonraker afterwards."""
    port = port or (_nginx_site_port(c.id) or 0) or {"mainsail": 81, "fluidd": 82}.get(c.id, 80)
    if (bad := _validate_port(port)) is not None:
        return bad
    dest = _install_dir(c)
    note(f"Downloading {c.name}…")
    fetched = await _fetch_release_zip(c, dest)
    if not fetched["ok"]:
        return fetched
    note("Configuring nginx…")
    site = await _install_nginx_site(c, port, dest)
    if not site["ok"]:
        # The zip was already extracted into dest; without a working nginx site it would linger AND
        # read as "installed" via the dir heuristic. Remove the orphaned web root so a failed
        # install leaves nothing behind.
        with contextlib.suppress(OSError):
            if dest.is_dir():
                await asyncio.to_thread(shutil.rmtree, dest)
        return _augment_root_failure(site, c)
    note("Registering with Moonraker…")
    await _register_moonraker(c)
    setup_provenance.record(
        c.id,
        method="web-ui",
        repo=c.repo,
        ref=await _github_latest(c.repo),
        nginx_site=c.id,
        moonraker_key=(c.manager_key or c.id),
    )
    return {"ok": True, "output": f"{c.name} installed. {site['output']}"}


async def _install_klipper_extra(
    c: Component, run: Callable[[list[str]], Awaitable[dict[str, Any]]], note: Callable[[str], None]
) -> dict[str, Any]:
    """Install a Klipper extra (a module cloned then symlinked into ``klippy/extras``), register a
    Moonraker git ``[update_manager]`` entry, and restart Klipper so it loads the module."""
    dest = _install_dir(c)
    if not (dest / ".git").is_dir():
        note(f"Cloning {c.name}…")
        clone = await run(
            ["git", "clone", "--depth", "1", f"https://github.com/{c.repo}", str(dest)]
        )
        if not clone["ok"]:
            return clone
    note("Linking into Klipper…")
    linked = _link_extras(c, dest)
    if not linked["ok"]:
        return linked
    await _register_moonraker(c)
    note("Restarting Klipper…")
    await _run(["sudo", "-n", "systemctl", "restart", "klipper"])
    setup_provenance.record(
        c.id,
        method="extra",
        repo=c.repo,
        ref=await _git_version(dest),
        extras=c.extras,
        moonraker_key=(c.manager_key or c.id) if c.mr_type else "",
    )
    return {"ok": True, "output": f"Installed {c.name}: {linked['output']} Restarted Klipper."}


async def install(
    cid: str,
    managed: set[str] | None = None,
    services: set[str] | None = None,
    task: Any | None = None,
    port: int | None = None,
    action: str | None = None,
) -> dict[str, Any]:
    refusal = await precheck_install(cid, managed, services)
    if refusal:
        return refusal
    if port is not None and (bad := _validate_port(port)) is not None:
        return bad
    catalog = load_catalog()
    component = _require(cid, catalog)
    if component.guide:  # an info-only card (e.g. CAN tools ship in Klipper) - nothing to install
        return {"refused": True, "output": f"{component.name}: {component.desc}"}
    # When a task is supplied, stream the installer's output into it for live progress; the
    # non-subprocess steps (zip download, nginx, Moonraker) report via note().
    run = (lambda cmd: _run_streaming(cmd, task)) if task is not None else _run

    def note(msg: str) -> None:
        if task is not None:
            task.append(msg + "\n")

    # FilaMind apps (3d / screen / flow) ship a one-line installer in their repo - run it so the
    # GUI can install them even though they aren't a plain git_repo (web / tauri).
    if component.first_party:
        # A chosen port (for a first-party web app like FilaMind 3d) lets the operator install it
        # straight onto a free port - e.g. 88 when Mainsail already owns 80 - instead of installing
        # on the default and conflicting, then having to move it afterwards.
        if action == "service" and component.service_install:
            # An additional managed deployment installed by its own button (FilaMind 3d's `agent`,
            # the :8030 service that unlocks the suite widgets) - a real install, not a copy-paste.
            cmd = _bash_installer(component, component.service_install)
        elif component.install_args:
            # The app stands up its real deployment via a subcommand rather than the default install
            # (screen's `native` installs the .deb kiosk + its service, not the browser preview).
            cmd = _bash_installer(component, component.install_args)
        elif port is not None and component.type == "web":
            cmd = _bash_installer(component, f"install --port {port}")
        else:
            cmd = _bash_installer(component)
        result = _augment_root_failure(await run(["bash", "-c", cmd]), component)
        if result.get("ok"):
            setup_provenance.record(
                cid, method="first_party", repo=component.repo, service=component.service
            )
        return result

    # Third-party static web UI (Mainsail/Fluidd): release zip + nginx site + Moonraker web entry.
    if component.release_asset:
        return await _install_web_ui(component, port, note)

    # Klipper extra (a module symlinked into klippy/extras): clone + symlink + Moonraker + restart.
    if component.extras:
        return await _install_klipper_extra(component, run, note)

    if component.type not in _GIT_TYPES:
        return {
            "refused": True,
            "output": f"{component.name} installs on the printer host; "
            "open its Source for the steps.",
        }
    # Plain git component: clone + its own install.sh (which registers itself with Moonraker). Skip
    # only the CLONE when the checkout is already present, but ALWAYS re-run the installer - so
    # clicking Install again can finish a half-failed install (clone ok, install.sh failed) instead
    # of short-circuiting on the mere presence of the directory.
    dest = _install_dir(component)
    if not (dest / ".git").is_dir():
        clone = await run(
            ["git", "clone", "--depth", "1", f"https://github.com/{component.repo}", str(dest)]
        )
        if not clone["ok"]:
            return clone
    installer = dest / "install.sh"
    if installer.is_file():
        result = await run(["bash", str(installer)])
    else:
        result = {
            "ok": True,
            "output": f"Cloned {component.name}; no install.sh - finish per docs.",
        }
    if result.get("ok"):
        if component.mr_type:
            await _register_moonraker(component)
        setup_provenance.record(
            cid,
            method="git",
            repo=component.repo,
            ref=await _git_version(dest),
            service=component.service,
            moonraker_key=(component.manager_key or component.id) if component.mr_type else "",
        )
    return _augment_root_failure(result, component)


async def install_task(
    cid: str,
    task: Any,
    managed: set[str] | None = None,
    services: set[str] | None = None,
    port: int | None = None,
    action: str | None = None,
) -> None:
    """Background install: stream into ``task`` and store the final result + status on it. The
    synchronous refusals (writes-off / missing-deps) are already raised by the route's precheck, so
    here we only run the work and record the outcome."""
    try:
        result = await install(cid, managed, services, task=task, port=port, action=action)
    except Exception as exc:  # never leave the task hung
        task.append(f"!! {exc}\n")
        task.result = {"ok": False, "output": str(exc)}
        task.status = "failed"
        return
    task.result = result
    output = str(result.get("output") or "")
    if output and output not in task.log:  # short/non-streamed outputs (already-present, refused)
        task.append(output)
    task.status = "done" if result.get("ok") and not result.get("refused") else "failed"


async def update(
    cid: str,
    managed: set[str] | None = None,
    moonraker_update: Callable[[str], Awaitable[None]] | None = None,
) -> dict[str, Any]:
    """Update an installed component.

    Moonraker-managed components (web UIs like Mainsail/Fluidd, and tracked git repos like Klipper,
    Moonraker, KlipperScreen) are updated through Moonraker's own update manager - a web UI is a
    downloaded artifact, NOT a git checkout, so a raw ``git pull`` wrongly fails ("not a git
    checkout"). Only an unmanaged git checkout falls back to ``git pull --ff-only`` here.
    """
    catalog = load_catalog()
    component = _require(cid, catalog)
    if not writes_enabled():
        return _refused()
    key = (component.manager_key or component.id).lower()
    if managed and key in managed and moonraker_update is not None:
        try:
            await moonraker_update(component.manager_key or component.id)
        except Exception as exc:  # surface a clear message instead of a 500
            return {"ok": False, "output": f"Moonraker could not update {component.name}: {exc}"}
        return {
            "ok": True,
            "output": f"Update of {component.name} requested via Moonraker; it runs in the "
            "background - refresh in a moment to see the new version.",
        }
    dest = _install_dir(component)
    if not (dest / ".git").is_dir():
        return {
            "refused": True,
            "output": f"{component.name} is not a git checkout under {dest}, and Moonraker doesn't "
            "track it - update it from the host instead.",
        }
    return await _run(["git", "-C", str(dest), "pull", "--ff-only"])


def _dependents(cid: str, catalog: dict[str, Component], installed: dict[str, str]) -> list[str]:
    """Names of INSTALLED components that declare ``cid`` as a dependency (block removing it)."""
    return [
        other.name
        for other in catalog.values()
        if cid in other.deps and installed.get(other.id) == "installed"
    ]


async def _backup_before_remove(c: Component) -> str:
    """Snapshot what a removal will touch (the clone as a tar.gz + moonraker.conf + printer.cfg) to
    a timestamped folder, so an accidental uninstall is one restore away. Returns that folder."""
    root = Path(get_settings().data_dir).expanduser() / "setup-uninstall-backups"
    bdir = root / f"{c.id}-{time.strftime('%Y%m%d-%H%M%S')}"
    try:
        bdir.mkdir(parents=True, exist_ok=True)
        for name in ("moonraker.conf", "printer.cfg"):
            p = _klipper_config_file(name)
            if p is not None:
                await asyncio.to_thread(shutil.copy2, p, bdir / name)
        dest = _install_dir(c)
        if dest.is_dir():
            await asyncio.to_thread(shutil.make_archive, str(bdir / c.id), "gztar", str(dest))
    except (OSError, shutil.Error):
        pass
    return str(bdir)


async def remove(
    cid: str, confirm: str, managed: set[str] | None = None, services: set[str] | None = None
) -> dict[str, Any]:
    """Uninstall a component, reversing exactly what its install placed - so no orphaned nginx site,
    systemd unit, moonraker.conf ``[update_manager]`` block, or (worst) a dangling klippy/extras
    symlink that stops Klipper from starting. Backs up first and refuses to pull a dependency out
    from under something that needs it."""
    catalog = load_catalog()
    component = _require(cid, catalog)
    if not writes_enabled():
        return _refused()
    if confirm != component.id:
        raise ValueError("Confirmation does not match the component id")
    if component.guide:
        return {"refused": True, "output": f"{component.name} has nothing to remove here."}
    if component.id == "filamind-flow":
        # This IS the app serving the request; removing it kills the process mid-call and drops the
        # sudo grant Setup relies on. Uninstall it from the host, not from within itself.
        return {
            "refused": True,
            "output": f"{component.name} is the app you're using - uninstall it from the printer "
            "host, not from within itself.",
        }
    # Dependency guard: never remove something still depended on (e.g. Moonraker under Mainsail).
    # Use the Moonraker signals when present, so a managed/service-only dependent is still detected.
    installed = await probe_status(managed, services)
    if blockers := _dependents(cid, catalog, installed):
        return {
            "refused": True,
            "output": f"Remove {', '.join(blockers)} first - they depend on {component.name}.",
        }

    backup = await _backup_before_remove(component)
    prov = setup_provenance.read(cid) or {}

    # FilaMind apps clean up via their own installer's uninstall path (removes the nginx site etc.).
    if component.first_party:
        result = await _run(
            ["bash", "-c", f"curl -fsSL {_raw_installer(component)} | bash -s -- uninstall"]
        )
        if result.get("ok"):
            setup_provenance.remove(cid)
        result["output"] = f"{result.get('output', '')}\n(backup: {backup})"
        return result

    steps: list[str] = []
    # 1) Unlink Klipper-extras symlinks FIRST - a dangling symlink in klippy/extras would stop
    #    Klipper from starting, so it must go before the clone is deleted.
    extras = list(prov.get("extras") or component.extras)
    if extras:
        _unlink_extras(extras)
        steps.append(f"unlinked {', '.join(extras)}")
    # 2) Strip the printer.cfg [include] the add-on added.
    include = component.config_include
    if include and config_include_present(include):
        await apply_config_include(include, add=False)
        steps.append(f"removed [include {include}]")
    # 3) Remove a third-party web UI's nginx site.
    if prov.get("nginx_site") or component.release_asset:
        await _remove_nginx_site(component)
        steps.append("removed the nginx site")
    # 4) Stop + disable + remove a systemd unit.
    service = prov.get("service") or component.service
    if service:
        await _run(["sudo", "-n", "systemctl", "disable", "--now", service])
        await _run(["sudo", "-n", "rm", "-f", f"/etc/systemd/system/{service}.service"])
        await _run(["sudo", "-n", "systemctl", "daemon-reload"])
        steps.append(f"stopped + removed the {service} service")
    # 5) Deregister from Moonraker's update manager. Also fire when the component has a catalog
    #    manager_key: a self-registering installer writes an [update_manager <key>] block that our
    #    provenance never recorded, and _deregister is a safe no-op when no block is present.
    if prov.get("moonraker_key") or component.mr_type or component.manager_key:
        await _deregister_moonraker(component)
        steps.append("deregistered from Moonraker")
    # 6) Delete the clone/web-root (path-guarded: only ever a direct $HOME child).
    dest = _install_dir(component)
    if dest.is_dir() and dest.parent == Path.home():
        await asyncio.to_thread(shutil.rmtree, dest)
        steps.append(f"deleted {dest}")
    # 7) Restart Klipper so it drops the unlinked extra cleanly (an include change in step 2 already
    #    restarted it).
    if extras:
        await _run(["sudo", "-n", "systemctl", "restart", "klipper"])
        steps.append("restarted Klipper")

    setup_provenance.remove(cid)
    detail = "; ".join(steps) if steps else "nothing was installed here"
    return {"ok": True, "output": f"Removed {component.name}: {detail}.\n(backup: {backup})"}


async def restart(cid: str) -> dict[str, Any]:
    """Restart an installed component's runtime.

    First-party apps (FilaMind 3d / screen) are nginx sites with no service of their own, so a
    restart re-reads their site config with ``systemctl reload nginx``. A component that runs as its
    own systemd unit (``service``) is restarted directly. Both use the passwordless-sudo systemctl
    rule the Setup service is granted; anything else has nothing to restart from here.
    """
    catalog = load_catalog()
    component = _require(cid, catalog)
    if not writes_enabled():
        return _refused()
    if _is_nginx_app(component):
        return await _run(["sudo", "-n", "systemctl", "reload", "nginx"])
    if component.service:
        return await _run(["sudo", "-n", "systemctl", "restart", component.service])
    return {
        "refused": True,
        "output": f"{component.name} has no restartable service here; manage it from Host Control.",
    }


# Ports we never let a web UI take over (Moonraker + Klipper's common API/host ports).
_RESERVED_PORTS = {7125, 7126, 8883}


def _validate_port(port: int) -> dict[str, Any] | None:
    """A refusal dict if ``port`` is out of range or reserved, else None."""
    if not (1 <= port <= 65535):
        return {"refused": True, "output": f"Port {port} is out of range (1-65535)."}
    if port in _RESERVED_PORTS:
        return {"refused": True, "output": f"Port {port} is reserved; pick another."}
    return None


def _nginx_port_cmd(component: Component, port: int) -> str:
    """A self-reverting nginx port change for a third-party web UI (Mainsail / Fluidd): back up its
    nginx site, rewrite the ``listen`` ports, validate with ``nginx -t``, reload, and restore the
    backup on ANY failure so a bad edit can never take the UI offline. Needs root (surfaced as a
    printer command if the grant doesn't cover it). A missing site is a safe no-op."""
    key = shlex.quote(component.dir or component.manager_key or component.id)
    tmpl = (
        r"key=__KEY__; "
        r'site=$(ls "/etc/nginx/sites-available/$key" '
        r'"/etc/nginx/conf.d/$key.conf" 2>/dev/null | head -1); '
        r'[ -n "$site" ] || { echo "No nginx site found for __NAME__ (looked for $key); '
        r'edit its config manually."; exit 2; }; '
        r'sudo cp "$site" "$site.fmbak" || { echo "could not back up the nginx site"; exit 4; }; '
        r'sudo sed -ri "s/(listen[[:space:]]+(\[::\]:)?)[0-9]+/\1__PORT__/g" "$site"; '
        r"if sudo nginx -t; then sudo systemctl reload nginx && "
        r'echo "__NAME__ is now served on port __PORT__."; '
        r'else sudo cp "$site.fmbak" "$site"; '
        r'echo "nginx rejected the change; reverted, __NAME__ port unchanged."; exit 3; fi'
    )
    return (
        tmpl.replace("__KEY__", key)
        .replace("__NAME__", component.name)
        .replace("__PORT__", str(port))
    )


async def set_port(
    cid: str, port: int, managed: set[str] | None = None, services: set[str] | None = None
) -> dict[str, Any]:
    """Change the port an installed first-party web app (e.g. FilaMind 3d) is served on, by
    re-running its own installer with ``--port`` (it owns its nginx site and elevates only the
    narrow cp/chmod/systemctl steps the Setup service has passwordless sudo for).

    Third-party web UIs (Mainsail, Fluidd) are NOT changed here: their nginx site would need a
    privileged in-place edit the service is deliberately not granted, so we refuse with guidance
    rather than run a sudo command that would silently fail.
    """
    catalog = load_catalog()
    component = _require(cid, catalog)
    if not writes_enabled():
        return _refused()
    if (bad := _validate_port(port)) is not None:
        return bad
    if component.type != "web":
        return {"refused": True, "output": f"{component.name} has no web port to change."}
    status = await probe_status(managed, services)
    if status.get(cid) != "installed":
        return {"refused": True, "output": f"{component.name} is not installed."}
    if not component.first_party:
        # Third-party web UIs (Mainsail/Fluidd) have their own nginx site; edit it in place
        # (backup, nginx -t, reload, reverting on ANY failure). Needs root; surfaced as a printer
        # command if the narrow sudo grant doesn't cover it.
        cmd = _nginx_port_cmd(component, port)
        result = await _run(["bash", "-c", cmd])
        out = result.get("output") or ""
        if not result.get("ok") and any(
            s in out for s in ("terminal is required", "password is required", "sudo:")
        ):
            result["output"] = (
                out.rstrip() + f"\n\nChanging {component.name}'s port edits its nginx site, which "
                f"needs root. Run this on the printer host:\n  {cmd}"
            )
        return result
    # First-party web app: re-run its installer with the new port (it owns its nginx site).
    cmd = f"curl -fsSL {_raw_installer(component)} | bash -s -- install --port {port}"
    return await _run(["bash", "-c", cmd])
