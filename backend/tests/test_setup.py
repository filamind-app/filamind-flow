from __future__ import annotations

import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.services import setup_manager, setup_provenance

client = TestClient(create_app())


@pytest.fixture(autouse=True)
def _isolate_provenance(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Keep install-stamp writes out of the real data dir (and hermetic per test)."""
    monkeypatch.setattr(setup_provenance, "_path", lambda: tmp_path / "setup-installed.json")


def test_catalog_lists_components() -> None:
    r = client.get("/api/setup/catalog")
    assert r.status_code == 200
    ids = {c["id"] for g in r.json()["groups"] for c in g["components"]}
    assert {"klipper", "moonraker", "filamind-flow"} <= ids


def test_status_is_read_only_by_default() -> None:
    r = client.get("/api/setup/status")
    assert r.status_code == 200
    body = r.json()
    assert body["writesEnabled"] is False  # GUI writes off until the host opts in
    assert "klipper" in body["status"]


def test_install_refused_when_writes_disabled() -> None:
    r = client.post("/api/setup/install", json={"id": "klipper"})
    assert r.status_code == 403


def test_unknown_component_is_404() -> None:
    r = client.post("/api/setup/install", json={"id": "does-not-exist"})
    assert r.status_code == 404


def test_logs_refused_for_a_serviceless_component() -> None:
    # Klipper has no managed systemd unit in the catalog, so there's no journal to show here.
    assert client.post("/api/setup/logs", json={"id": "klipper"}).status_code == 403


def test_register_and_include_require_writes() -> None:
    # Both mutate host config, so they refuse (403) while GUI writes are off (the default).
    assert client.post("/api/setup/register", json={"id": "guppyscreen"}).status_code == 403
    assert client.post("/api/setup/include", json={"id": "kamp", "add": True}).status_code == 403


def test_resolve_order_puts_dependencies_first() -> None:
    catalog = setup_manager.load_catalog()
    order = setup_manager.resolve_order(["mainsail"], catalog)
    assert order.index("klipper") < order.index("moonraker") < order.index("mainsail")


def test_every_component_has_a_description() -> None:
    catalog = setup_manager.load_catalog()
    assert catalog, "catalog should not be empty"
    assert all(c.desc for c in catalog.values()), "every component needs a description"


def test_update_available_normalizes_versions_and_uses_count() -> None:
    upd = setup_manager._update_available
    # A leading 'v' must not read as a difference (v1.2.0 == 1.2.0 → up to date).
    assert upd({"version": "v1.2.0", "remote_version": "1.2.0"}) is False
    assert upd({"version": "1.2.0", "remote_version": "1.3.0"}) is True
    # commits_behind_count (int) is honored when the commits_behind list is absent.
    assert upd({"commits_behind_count": 3}) is True
    assert upd({"commits_behind_count": 0}) is False


async def test_status_uses_moonraker_signals_then_dir_heuristic() -> None:
    # An update-manager key (case-insensitive) marks a component installed even when its directory
    # name differs from its id (KlipperScreen) and nothing is on disk.
    status = await setup_manager.probe_status(managed={"klipperscreen"}, services=set())
    assert status["klipperscreen"] == "installed"
    # A managed systemd unit is the secondary signal.
    status = await setup_manager.probe_status(managed=set(), services={"crowsnest"})
    assert status["crowsnest"] == "installed"


async def test_status_counts_a_moonraker_config_section_as_installed() -> None:
    # Spoolman commonly runs as a container or on another host - no local unit and no clone to find -
    # but Moonraker is wired to it by a `[spoolman]` section, which means it IS installed and in use.
    status = await setup_manager.probe_status(managed=set(), services=set(), sections={"spoolman"})
    assert status["spoolman"] == "installed"
    # The signal is per-component, not a blanket: an unrelated component stays available.
    assert status["cartographer"] == "not-installed"


def test_section_keys_reduces_moonraker_sections_to_their_first_token() -> None:
    keys = setup_manager.section_keys(
        ["spoolman", "power Auto Lights", "update_manager mainsail", "   ", "Timelapse"]
    )
    assert keys == {"spoolman", "power", "update_manager", "timelapse"}


async def test_dir_heuristic_matches_a_differently_cased_clone(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Installers clone to the repo's own capitalisation (~/Spoolman) while the catalog key is
    # lowercase - and Linux paths are case-sensitive, so an exact match read it as not installed.
    (tmp_path / "Spoolman").mkdir()
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    status = await setup_manager.probe_status(managed=set(), services=set())
    assert status["spoolman"] == "installed"


async def test_probe_detailed_reports_versions_and_update_flag() -> None:
    # Versions + an update flag come from Moonraker's update-manager version_info: a git component
    # with commits behind, a web component whose version differs from remote, and an up-to-date one.
    # github_remaining=0 keeps it hermetic - not-installed components never hit the network.
    version_info = {
        "klipper": {
            "version": "v0.13.0-689",
            "remote_version": "v0.13.0-699",
            "commits_behind": [{}] * 10,
        },
        "moonraker": {
            "version": "v0.10.0-29",
            "remote_version": "v0.10.0-29",
            "commits_behind": [],
        },
        "mainsail": {"version": "v2.17.0", "remote_version": "v2.18.0"},  # web UI: no commit list
    }
    detailed = await setup_manager.probe_detailed(version_info, services=set(), github_remaining=0)
    assert detailed["klipper"]["status"] == "installed"
    assert detailed["klipper"]["version"] == "v0.13.0-689"
    assert detailed["klipper"]["latest"] == "v0.13.0-699"
    assert detailed["klipper"]["updateAvailable"] is True
    assert detailed["moonraker"]["updateAvailable"] is False  # current == remote
    assert detailed["mainsail"]["updateAvailable"] is True  # version != remote_version
    # A component Moonraker doesn't track and isn't on disk: not-installed, no update offered.
    assert detailed["guppyscreen"]["status"] == "not-installed"
    assert detailed["guppyscreen"]["updateAvailable"] is False


async def test_unmanaged_git_checkout_surfaces_updates(monkeypatch) -> None:
    # A component Moonraker doesn't track but that IS installed as a local git clone (the FilaMind
    # apps, guppyscreen) must still get `latest` + updateAvailable - from the local clone vs its own
    # origin, NOT from GitHub. Hermetic: monkeypatch the install signal + the two git helpers so no
    # real git/network runs.
    monkeypatch.setattr(
        setup_manager, "_is_installed", lambda c, m, s, sec=frozenset(): c.id == "guppyscreen"
    )

    async def _ver(_dest: object) -> str:
        return "07409cb"

    async def _behind(_dest: object) -> tuple[str, bool]:
        return ("ab12cd3", True)

    monkeypatch.setattr(setup_manager, "_git_version", _ver)
    monkeypatch.setattr(setup_manager, "_git_latest", _behind)
    d = await setup_manager.probe_detailed({}, services=set(), github_remaining=0)
    assert d["guppyscreen"]["status"] == "installed"
    assert d["guppyscreen"]["version"] == "07409cb"
    assert d["guppyscreen"]["latest"] == "ab12cd3"
    assert d["guppyscreen"]["updateAvailable"] is True

    async def _level(_dest: object) -> tuple[str, bool]:
        return ("07409cb", False)

    monkeypatch.setattr(setup_manager, "_git_latest", _level)
    d = await setup_manager.probe_detailed({}, services=set(), github_remaining=0)
    assert d["guppyscreen"]["updateAvailable"] is False  # level with origin -> no update offered


async def test_check_for_updates_forces_a_fresh_lookup(monkeypatch) -> None:
    # A recently-cached version is served from cache normally, but force=True (the "Check for
    # updates" button) re-fetches so a just-published release shows up instead of a week-old value.
    setup_manager._latest_cache.clear()
    setup_manager._latest_cache_loaded = True
    monkeypatch.setattr(setup_manager, "_save_latest_cache", lambda: None)
    setup_manager._latest_cache["owner/repo"] = (time.time(), "v1.0.0")  # fresh cache entry
    calls: list[tuple[str, bool]] = []

    async def fake_latest(repo: str, force: bool = False) -> str:
        calls.append((repo, force))
        return "v2.0.0"

    monkeypatch.setattr(setup_manager, "_github_latest", fake_latest)

    out = await setup_manager._latest_versions({"c": "owner/repo"}, github_remaining=200)
    assert out["c"] == "v1.0.0" and calls == []  # served from cache, no fetch

    out = await setup_manager._latest_versions(
        {"c": "owner/repo"}, github_remaining=200, force=True
    )
    assert out["c"] == "v2.0.0" and calls == [("owner/repo", True)]  # re-fetched


def test_clear_version_caches_empties_both_and_allows_reload() -> None:
    setup_manager._latest_cache["x"] = (1.0, "v1")
    setup_manager._git_latest_cache["/y"] = (1.0, ("v1", False))
    setup_manager._latest_cache_loaded = True
    setup_manager.clear_version_caches()
    assert not setup_manager._latest_cache and not setup_manager._git_latest_cache
    assert setup_manager._latest_cache_loaded is False  # disk values can be re-read next time


async def test_force_refresh_retains_cached_versions_under_low_quota(monkeypatch) -> None:
    # A forced "Check for updates" under LOW GitHub quota must re-fetch what fits the budget but
    # keep the last-known (cached) version for the rest - never blank a version that was showing.
    setup_manager._latest_cache.clear()
    setup_manager._latest_cache_loaded = True  # simulate disk already loaded (no clobber)
    monkeypatch.setattr(setup_manager, "_save_latest_cache", lambda: None)
    for i in range(5):
        setup_manager._latest_cache[f"owner/repo{i}"] = (time.time(), f"v{i}.0")
    fetched: list[str] = []

    async def fake_latest(repo: str, force: bool = False) -> str:
        fetched.append(repo)
        return "vNEW"

    monkeypatch.setattr(setup_manager, "_github_latest", fake_latest)
    repos = {f"c{i}": f"owner/repo{i}" for i in range(5)}
    # budget 14 → max_fetch = (14-10)//2 = 2: only 2 re-fetched, the other 3 retained.
    out = await setup_manager._latest_versions(repos, github_remaining=14, force=True)
    assert len(fetched) == 2  # quota budget honored
    assert all(v for v in out.values())  # NONE blanked
    assert sum(1 for v in out.values() if v == "vNEW") == 2  # fresh
    assert sum(1 for v in out.values() if v != "vNEW") == 3  # retained last-known


async def test_latest_version_lookups_are_quota_capped(monkeypatch) -> None:
    # Best-effort GitHub lookups for not-installed components must never exhaust the host's quota.
    setup_manager._latest_cache.clear()
    setup_manager._latest_cache_loaded = True  # skip disk load
    monkeypatch.setattr(setup_manager, "_save_latest_cache", lambda: None)  # don't touch disk
    calls: list[str] = []

    async def fake_latest(repo: str, force: bool = False) -> str:
        calls.append(repo)
        return "v1.0.0"

    monkeypatch.setattr(setup_manager, "_github_latest", fake_latest)
    repos = {f"c{i}": f"owner/repo{i}" for i in range(27)}  # a large not-installed set

    # Moonraker did not report remaining quota (None) → a conservative finite budget, never
    # "unlimited": only a capped subset is fetched (the rest fill in over later reads).
    await setup_manager._latest_versions(repos, github_remaining=None)
    assert 0 < len(calls) <= 10

    # No quota → fetch nothing at all (keeps the status read hermetic).
    calls.clear()
    out = await setup_manager._latest_versions(repos, github_remaining=0)
    assert calls == []
    assert all(v == "" for v in out.values())

    # Plenty of quota → fetch them all.
    calls.clear()
    await setup_manager._latest_versions(repos, github_remaining=200)
    assert len(calls) == 27


async def test_latest_versions_served_from_disk_cache_without_github(monkeypatch, tmp_path) -> None:
    # Once a version is cached on disk, a not-installed component shows it even on a fresh process
    # with GitHub quota exhausted - no network hit. This keeps versions from going blank.
    monkeypatch.setattr(
        setup_manager, "_latest_cache_path", lambda: tmp_path / "setup-latest-cache.json"
    )
    setup_manager._latest_cache.clear()
    setup_manager._latest_cache_loaded = False
    setup_manager._latest_cache["owner/repo"] = (time.time(), "v9.9.9")
    setup_manager._save_latest_cache()

    # Simulate a fresh process: drop the in-memory cache so it must reload from disk.
    setup_manager._latest_cache.clear()
    setup_manager._latest_cache_loaded = False
    called: list[str] = []

    async def boom(repo: str) -> str:
        called.append(repo)
        return ""

    monkeypatch.setattr(setup_manager, "_github_latest", boom)
    out = await setup_manager._latest_versions({"c": "owner/repo"}, github_remaining=0)
    assert out["c"] == "v9.9.9"  # served from disk
    assert called == []  # no GitHub request needed


async def test_first_party_nginx_app_needs_its_site_not_just_a_clone(monkeypatch, tmp_path) -> None:
    # A first-party web / touch app (FilaMind 3d / screen) is "installed" only once its nginx site
    # exists. A bare clone (the repo cloned, but the web-server step never ran, e.g. its sudo step
    # failed) must NOT read as installed, or the Setup widget shows a phantom install the user can
    # never switch to. Make every clone dir "present" so only the nginx-site rule can gate these.
    monkeypatch.setattr(setup_manager, "_install_dir", lambda c: tmp_path)  # tmp_path exists
    monkeypatch.setattr(setup_manager, "_nginx_site_present", lambda site: False)
    status = await setup_manager.probe_status(managed=set(), services=set())
    assert status["filamind-screen"] == "not-installed"
    assert status["filamind-3d"] == "not-installed"
    # Once the nginx site is configured, the same app reads installed.
    sites = {"filamind-screen", "filamind-3d"}
    monkeypatch.setattr(setup_manager, "_nginx_site_present", lambda site: site in sites)
    status = await setup_manager.probe_status(managed=set(), services=set())
    assert status["filamind-screen"] == "installed"
    assert status["filamind-3d"] == "installed"


async def test_install_refuses_when_a_dependency_is_missing(monkeypatch, tmp_path) -> None:
    # With writes enabled but nothing installed, installing a git_repo component whose dependency
    # is absent is refused with a clear "install X first" message (never a silent core clone).
    monkeypatch.setattr(setup_manager, "writes_enabled", lambda: True)
    # Isolate detection from the real $HOME so the guard is deterministic and can never clone:
    # every component resolves to an absent temp dir, so Klipper reads as not-installed.
    monkeypatch.setattr(setup_manager, "_install_dir", lambda c: tmp_path / c.id)
    result = await setup_manager.install("moonraker", managed=set(), services=set())
    assert result.get("refused") is True
    assert "Klipper" in result["output"]  # Moonraker depends on Klipper


async def test_web_ui_installs_via_zip_nginx_and_moonraker(monkeypatch) -> None:
    # A third-party web UI (Mainsail) now one-click installs: fetch its release zip, write an nginx
    # site, register a Moonraker [update_manager web] entry, and stamp the install.
    monkeypatch.setattr(setup_manager, "writes_enabled", lambda: True)
    calls: list[str] = []

    async def fake_zip(c, dest):
        calls.append("zip")
        return {"ok": True, "output": "downloaded"}

    async def fake_site(c, port, root):
        calls.append(f"nginx:{port}")
        return {"ok": True, "output": f"served on {port}"}

    async def fake_register(c):
        calls.append("register")

    async def fake_latest(repo):
        return "v2.18.0"

    stamped: dict = {}
    monkeypatch.setattr(setup_manager, "_fetch_release_zip", fake_zip)
    monkeypatch.setattr(setup_manager, "_install_nginx_site", fake_site)
    monkeypatch.setattr(setup_manager, "_register_moonraker", fake_register)
    monkeypatch.setattr(setup_manager, "_github_latest", fake_latest)
    monkeypatch.setattr(
        setup_manager.setup_provenance, "record", lambda cid, **kw: stamped.update({cid: kw})
    )

    result = await setup_manager.install(
        "mainsail", managed={"klipper", "moonraker"}, services=set()
    )
    assert result.get("ok") is True
    assert "zip" in calls and "register" in calls and any(c.startswith("nginx:") for c in calls)
    assert stamped["mainsail"]["method"] == "web-ui"
    assert stamped["mainsail"]["nginx_site"] == "mainsail"
    assert stamped["mainsail"]["ref"] == "v2.18.0"


async def test_guide_component_is_not_installable(monkeypatch) -> None:
    # An info-only card (CAN tools ship inside Klipper) refuses install with its guidance text.
    monkeypatch.setattr(setup_manager, "writes_enabled", lambda: True)
    result = await setup_manager.install("can-tools", managed={"klipper"}, services=set())
    assert result.get("refused") is True
    assert "CAN" in result["output"]


async def test_first_party_app_installs_via_its_one_liner(monkeypatch) -> None:
    # FilaMind apps (3d / screen / flow) are web/tauri but DO install from the GUI by running their
    # own one-line installer, even though they aren't a plain git_repo.
    monkeypatch.setattr(setup_manager, "writes_enabled", lambda: True)
    monkeypatch.setattr(setup_manager.setup_provenance, "record", lambda *a, **k: None)
    captured: list[list[str]] = []

    async def fake_run(cmd: list[str]) -> dict:
        captured.append(cmd)
        return {"ok": True, "output": "installed"}

    monkeypatch.setattr(setup_manager, "_run", fake_run)
    result = await setup_manager.install(
        "filamind-3d", managed={"klipper", "moonraker"}, services=set()
    )
    assert result.get("ok") is True
    assert captured, "installer command was not run"
    cmd = " ".join(captured[0])
    assert "curl" in cmd and "filamind-3d/main/scripts/install.sh" in cmd


async def test_remove_refuses_removing_the_app_itself(monkeypatch) -> None:
    # Removing filamind-flow would kill the process serving the request + drop the sudo grant.
    monkeypatch.setattr(setup_manager, "writes_enabled", lambda: True)
    result = await setup_manager.remove("filamind-flow", "filamind-flow")
    assert result.get("refused") is True
    assert "the app you're using" in result["output"]


async def test_register_does_not_clobber_an_existing_block(monkeypatch, tmp_path) -> None:
    # A component already tracked by Moonraker (its installer wrote the block) must stay untouched.
    monkeypatch.setattr(setup_manager, "writes_enabled", lambda: True)
    conf = tmp_path / "moonraker.conf"
    original = "[update_manager crowsnest]\ntype: git_repo\npath: ~/crowsnest\nchannel: beta\n"
    conf.write_text(original, encoding="utf-8")
    (tmp_path / ".git").mkdir()
    monkeypatch.setattr(
        setup_manager, "_klipper_config_file", lambda n: conf if n == "moonraker.conf" else None
    )
    monkeypatch.setattr(setup_manager, "_install_dir", lambda c: tmp_path)

    result = await setup_manager.register_component("crowsnest")
    assert result.get("ok") is True and "already registered" in result["output"]
    assert conf.read_text(encoding="utf-8") == original  # left byte-for-byte untouched


async def test_reinstall_reruns_installer_when_already_cloned(monkeypatch, tmp_path) -> None:
    # A half-failed install (clone ok, install.sh failed) must be finishable by clicking Install
    # again: the clone is skipped but install.sh is re-run (not short-circuited on dir presence).
    monkeypatch.setattr(setup_manager, "writes_enabled", lambda: True)
    monkeypatch.setattr(setup_manager, "_install_dir", lambda c: tmp_path)
    (tmp_path / ".git").mkdir()
    (tmp_path / "install.sh").write_text("#!/bin/bash\n", encoding="utf-8")
    ran: list[list[str]] = []

    async def fake_run(cmd):
        ran.append(cmd)
        return {"ok": True, "output": ""}

    async def fake_ver(_d):
        return "v1"

    monkeypatch.setattr(setup_manager, "_run", fake_run)
    monkeypatch.setattr(setup_manager, "_git_version", fake_ver)

    result = await setup_manager.install(
        "crowsnest", managed={"klipper", "moonraker"}, services=set()
    )
    assert result.get("ok") is True
    assert any("install.sh" in " ".join(c) for c in ran)  # installer re-ran
    assert not any(c[:2] == ["git", "clone"] for c in ran)  # clone skipped (already present)


async def test_remove_refuses_when_a_dependent_is_installed(monkeypatch) -> None:
    # Never pull a dependency out from under something that needs it: Moonraker installed blocks
    # removing Klipper.
    monkeypatch.setattr(setup_manager, "writes_enabled", lambda: True)

    async def fake_status(*a, **k):
        return {"moonraker": "installed"}

    monkeypatch.setattr(setup_manager, "probe_status", fake_status)
    result = await setup_manager.remove("klipper", "klipper")
    assert result.get("refused") is True
    assert "Moonraker" in result["output"]


async def test_remove_klipper_extra_unlinks_before_deleting(monkeypatch, tmp_path) -> None:
    # The Klipper-brick fix: an extra's symlink must be unlinked BEFORE anything else, so a dangling
    # symlink can never stop Klipper from starting; and Klipper is restarted afterwards.
    monkeypatch.setattr(setup_manager, "writes_enabled", lambda: True)

    async def no_deps(*a, **k):
        return {}

    async def fake_backup(c):
        return str(tmp_path / "bk")

    order: list[str] = []
    monkeypatch.setattr(setup_manager, "probe_status", no_deps)
    monkeypatch.setattr(setup_manager, "_backup_before_remove", fake_backup)
    monkeypatch.setattr(
        setup_manager, "_unlink_extras", lambda names: order.append(f"unlink:{names}")
    )

    async def fake_run(cmd):
        order.append("run:" + " ".join(cmd))
        return {"ok": True, "output": ""}

    async def fake_dereg(c):
        order.append("dereg")

    monkeypatch.setattr(setup_manager, "_run", fake_run)
    monkeypatch.setattr(setup_manager, "_deregister_moonraker", fake_dereg)
    removed: list[str] = []
    monkeypatch.setattr(setup_manager.setup_provenance, "remove", lambda cid: removed.append(cid))

    result = await setup_manager.remove("gcode-shell-cmd", "gcode-shell-cmd")
    assert result.get("ok") is True
    # unlink happens first, and a klipper restart happens after.
    assert order[0] == "unlink:['gcode_shell_command.py']"
    assert any("restart klipper" in s for s in order)
    assert removed == ["gcode-shell-cmd"]


async def test_first_party_screen_installs_its_native_kiosk(monkeypatch) -> None:
    # Installing FilaMind screen from the GUI runs its `native` subcommand, which installs the .deb
    # kiosk and writes filamind-screen-kiosk.service - so the screen becomes switchable in the
    # Screen Manager (previously the GUI only cloned + served the nginx preview, never the kiosk).
    monkeypatch.setattr(setup_manager, "writes_enabled", lambda: True)
    captured: list[list[str]] = []

    async def fake_run(cmd: list[str]) -> dict:
        captured.append(cmd)
        return {"ok": True, "output": "installed"}

    monkeypatch.setattr(setup_manager, "_run", fake_run)
    result = await setup_manager.install(
        "filamind-screen", managed={"klipper", "moonraker"}, services=set()
    )
    assert result.get("ok") is True
    cmd = " ".join(captured[0])
    assert "filamind-screen/main/scripts/install.sh" in cmd
    assert "bash -s -- native" in cmd


async def test_first_party_3d_installs_its_agent_via_the_service_action(monkeypatch) -> None:
    # The 3d "agent" (managed :8030 service that unlocks the suite widgets) is now a real GUI
    # install via action="service" - replacing the old copy-paste one-liner. It runs
    # `scripts/install.sh agent`.
    monkeypatch.setattr(setup_manager, "writes_enabled", lambda: True)
    captured: list[list[str]] = []

    async def fake_run(cmd: list[str]) -> dict:
        captured.append(cmd)
        return {"ok": True, "output": "agent installed"}

    monkeypatch.setattr(setup_manager, "_run", fake_run)
    result = await setup_manager.install(
        "filamind-3d", managed={"klipper", "moonraker"}, services=set(), action="service"
    )
    assert result.get("ok") is True
    cmd = " ".join(captured[0])
    assert "filamind-3d/main/scripts/install.sh" in cmd
    assert "bash -s -- agent" in cmd


def test_autoupdate_prefs_default_off_and_persist(monkeypatch, tmp_path) -> None:
    # Auto-update is opt-in: off by default, and the toggle + interval persist across reads.
    path = tmp_path / "setup-autoupdate.json"
    monkeypatch.setattr(setup_manager, "_autoupdate_path", lambda: path)
    assert setup_manager.autoupdate_prefs() == {"enabled": False, "intervalHours": 24}
    assert setup_manager.set_autoupdate_prefs(True, 6) == {"enabled": True, "intervalHours": 6}
    assert setup_manager.autoupdate_prefs() == {"enabled": True, "intervalHours": 6}


async def test_autoupdate_tick_is_a_noop_when_disabled(monkeypatch, tmp_path) -> None:
    # When disabled it returns immediately, before ever touching Moonraker or running an update.
    path = tmp_path / "setup-autoupdate.json"
    monkeypatch.setattr(setup_manager, "_autoupdate_path", lambda: path)
    monkeypatch.setattr(setup_manager, "writes_enabled", lambda: True)
    out = await setup_manager.auto_update_tick("http://127.0.0.1:7125", now=1_000_000.0)
    assert out == {"ran": False, "reason": "disabled"}


async def test_third_party_port_change_edits_nginx_with_a_safe_revert(monkeypatch) -> None:
    # Mainsail/Fluidd (third-party web UIs) are no longer refused: changing the port edits their
    # nginx site in place, validated by `nginx -t` and reverted on any failure. Assert the run
    # carries that safety harness and the chosen port.
    monkeypatch.setattr(setup_manager, "writes_enabled", lambda: True)

    async def fake_probe(managed: set[str] | None, services: set[str] | None) -> dict[str, str]:
        return {"mainsail": "installed"}

    monkeypatch.setattr(setup_manager, "probe_status", fake_probe)
    captured: list[list[str]] = []

    async def fake_run(cmd: list[str]) -> dict:
        captured.append(cmd)
        return {"ok": True, "output": "Mainsail is now served on port 8088."}

    monkeypatch.setattr(setup_manager, "_run", fake_run)
    result = await setup_manager.set_port("mainsail", 8088, managed=set(), services=set())
    assert result.get("refused") is not True
    cmd = " ".join(captured[0])
    assert "key=mainsail" in cmd and "8088" in cmd
    assert "nginx -t" in cmd and "fmbak" in cmd and "exit 3" in cmd  # validate + revert


async def test_first_party_install_sudo_failure_surfaces_the_command(monkeypatch) -> None:
    # The backend service has no terminal for a sudo password; if the install fails for that reason,
    # the result points at the one-time passwordless-sudo grant that lets the headless widget
    # install apps without a prompt (re-running the app's own installer would hit the same wall).
    monkeypatch.setattr(setup_manager, "writes_enabled", lambda: True)

    async def fake_run(cmd: list[str]) -> dict:
        return {"ok": False, "output": "sudo: a terminal is required to read the password"}

    monkeypatch.setattr(setup_manager, "_run", fake_run)
    r = await setup_manager.install("filamind-3d", managed={"klipper", "moonraker"}, services=set())
    assert r.get("ok") is False
    assert "sudo bash ~/filamind-flow/scripts/install.sh sudoers" in r["output"]


def test_status_exposes_autoupdate_prefs_and_is_decoupled_from_the_cli() -> None:
    # The widget is self-contained: status carries the auto-update prefs and no longer advertises
    # the external filamind-setup CLI one-liner.
    r = client.get("/api/setup/status")
    assert r.status_code == 200
    body = r.json()
    assert "suiteCommand" not in body
    assert set(body["autoUpdate"]) == {"enabled", "intervalHours"}
    assert body["autoUpdate"]["enabled"] is False  # opt-in: off by default


def test_writes_can_be_enabled_from_the_gui(monkeypatch, tmp_path) -> None:
    # The widget can turn writes on itself (persisted) - no CLI and no env var needed.
    flag = tmp_path / "setup-writes.json"
    monkeypatch.setattr(setup_manager, "_writes_flag_path", lambda: flag)
    assert setup_manager.writes_enabled() is False
    setup_manager.set_writes_enabled(True)
    assert setup_manager.writes_enabled() is True
    assert flag.exists()
    setup_manager.set_writes_enabled(False)
    assert setup_manager.writes_enabled() is False


async def test_set_port_rejects_out_of_range_and_reserved(monkeypatch) -> None:
    monkeypatch.setattr(setup_manager, "writes_enabled", lambda: True)
    bad = await setup_manager.set_port("filamind-3d", 70000, managed={"filamind-3d"})
    assert bad.get("refused") is True
    reserved = await setup_manager.set_port("filamind-3d", 7125, managed={"filamind-3d"})
    assert reserved.get("refused") is True


async def test_set_port_refuses_non_web_component(monkeypatch) -> None:
    monkeypatch.setattr(setup_manager, "writes_enabled", lambda: True)
    r = await setup_manager.set_port("klipper", 8080, managed={"klipper"})
    assert r.get("refused") is True
    assert "no web port" in r["output"]


async def test_set_port_first_party_reruns_installer_with_port(monkeypatch) -> None:
    monkeypatch.setattr(setup_manager, "writes_enabled", lambda: True)
    captured: list[list[str]] = []

    async def fake_run(cmd: list[str]) -> dict:
        captured.append(cmd)
        return {"ok": True, "output": "ok"}

    monkeypatch.setattr(setup_manager, "_run", fake_run)
    # filamind-3d is a first-party web app and "installed" via the managed signal.
    r = await setup_manager.set_port("filamind-3d", 8090, managed={"filamind-3d"}, services=set())
    assert r.get("ok") is True
    assert "install --port 8090" in " ".join(captured[0])


def test_dependency_guard_passes_through_route_when_writes_off() -> None:
    # The route still refuses with 403 at the writes gate before any dependency work.
    r = client.post("/api/setup/install", json={"id": "mainsail"})
    assert r.status_code == 403


async def test_update_delegates_managed_component_to_moonraker(monkeypatch) -> None:
    # Mainsail is a web UI (a downloaded artifact, NOT a git checkout) but IS Moonraker-managed, so
    # update must go through Moonraker's update manager - never a raw `git pull` against ~/mainsail
    # (that's the "Mainsail is not a git checkout" failure we're fixing).
    monkeypatch.setattr(setup_manager, "writes_enabled", lambda: True)
    called: list[str] = []

    async def mr_update(name: str) -> None:
        called.append(name)

    r = await setup_manager.update("mainsail", managed={"mainsail"}, moonraker_update=mr_update)
    assert r.get("ok") is True
    assert called == ["mainsail"]  # delegated by manager_key/id, not git-pulled


async def test_update_unmanaged_non_git_is_refused(monkeypatch, tmp_path) -> None:
    # A component Moonraker doesn't track and that isn't a git checkout can't be updated from here:
    # refuse clearly instead of a git pull that errors.
    monkeypatch.setattr(setup_manager, "writes_enabled", lambda: True)
    monkeypatch.setattr(setup_manager, "_install_dir", lambda c: tmp_path / "nope")
    r = await setup_manager.update("guppyscreen", managed=set())
    assert r.get("refused") is True


async def test_first_party_install_with_port_passes_it(monkeypatch) -> None:
    # A chosen port installs FilaMind 3d straight onto it (e.g. 88 when Mainsail owns 80).
    monkeypatch.setattr(setup_manager, "writes_enabled", lambda: True)
    captured: list[list[str]] = []

    async def fake_run(cmd: list[str]) -> dict:
        captured.append(cmd)
        return {"ok": True, "output": "ok"}

    monkeypatch.setattr(setup_manager, "_run", fake_run)
    r = await setup_manager.install(
        "filamind-3d", managed={"klipper", "moonraker"}, services=set(), port=88
    )
    assert r.get("ok") is True
    assert "install --port 88" in " ".join(captured[0])


async def test_install_rejects_out_of_range_port(monkeypatch) -> None:
    monkeypatch.setattr(setup_manager, "writes_enabled", lambda: True)
    r = await setup_manager.install(
        "filamind-3d", managed={"klipper", "moonraker"}, services=set(), port=70000
    )
    assert r.get("refused") is True


async def test_restart_first_party_app_reloads_nginx(monkeypatch) -> None:
    # FilaMind 3d is an nginx site (no service of its own), so "restart" reloads nginx.
    monkeypatch.setattr(setup_manager, "writes_enabled", lambda: True)
    captured: list[list[str]] = []

    async def fake_run(cmd: list[str]) -> dict:
        captured.append(cmd)
        return {"ok": True, "output": "reloaded"}

    monkeypatch.setattr(setup_manager, "_run", fake_run)
    r = await setup_manager.restart("filamind-3d")
    assert r.get("ok") is True
    assert captured and "reload" in captured[0] and "nginx" in captured[0]


async def test_restart_refused_when_writes_disabled(monkeypatch) -> None:
    monkeypatch.setattr(setup_manager, "writes_enabled", lambda: False)
    r = await setup_manager.restart("filamind-3d")
    assert r.get("refused") is True
