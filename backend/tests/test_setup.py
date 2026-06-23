from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import create_app
from app.services import setup_manager

client = TestClient(create_app())


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


def test_resolve_order_puts_dependencies_first() -> None:
    catalog = setup_manager.load_catalog()
    order = setup_manager.resolve_order(["mainsail"], catalog)
    assert order.index("klipper") < order.index("moonraker") < order.index("mainsail")


def test_every_component_has_a_description() -> None:
    catalog = setup_manager.load_catalog()
    assert catalog, "catalog should not be empty"
    assert all(c.desc for c in catalog.values()), "every component needs a description"


async def test_status_uses_moonraker_signals_then_dir_heuristic() -> None:
    # An update-manager key (case-insensitive) marks a component installed even when its directory
    # name differs from its id (KlipperScreen) and nothing is on disk.
    status = await setup_manager.probe_status(managed={"klipperscreen"}, services=set())
    assert status["klipperscreen"] == "installed"
    # A managed systemd unit is the secondary signal.
    status = await setup_manager.probe_status(managed=set(), services={"crowsnest"})
    assert status["crowsnest"] == "installed"


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


async def test_latest_version_lookups_are_quota_capped(monkeypatch) -> None:
    # Best-effort GitHub lookups for not-installed components must never exhaust the host's quota.
    setup_manager._latest_cache.clear()
    calls: list[str] = []

    async def fake_latest(repo: str) -> str:
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


async def test_install_of_non_first_party_non_git_type_is_refused(monkeypatch) -> None:
    # Third-party web / manual components are catalog-only for now; the GUI refuses them up front
    # (the widget shows a "CLI only" hint). mainsail is type "web" and not first-party.
    monkeypatch.setattr(setup_manager, "writes_enabled", lambda: True)
    result = await setup_manager.install(
        "mainsail", managed={"klipper", "moonraker"}, services=set()
    )
    assert result.get("refused") is True
    assert "isn't supported yet" in result["output"]


async def test_first_party_app_installs_via_its_one_liner(monkeypatch) -> None:
    # FilaMind apps (3d / screen / flow) are web/tauri but DO install from the GUI by running their
    # own one-line installer, even though they aren't a plain git_repo.
    monkeypatch.setattr(setup_manager, "writes_enabled", lambda: True)
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


async def test_first_party_install_sudo_failure_surfaces_the_command(monkeypatch) -> None:
    # The backend service has no terminal for a sudo password; if the install fails for that reason,
    # the result tells the user the exact command to run on the printer host.
    monkeypatch.setattr(setup_manager, "writes_enabled", lambda: True)

    async def fake_run(cmd: list[str]) -> dict:
        return {"ok": False, "output": "sudo: a terminal is required to read the password"}

    monkeypatch.setattr(setup_manager, "_run", fake_run)
    r = await setup_manager.install("filamind-3d", managed={"klipper", "moonraker"}, services=set())
    assert r.get("ok") is False
    assert "Run this on the printer host" in r["output"]
    assert "filamind-3d/main/scripts/install.sh" in r["output"]


def test_status_exposes_the_suite_install_command() -> None:
    r = client.get("/api/setup/status")
    assert r.status_code == 200
    assert "filamind-setup" in r.json()["suiteCommand"]


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
