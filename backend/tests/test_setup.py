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


def test_status_exposes_the_suite_install_command() -> None:
    r = client.get("/api/setup/status")
    assert r.status_code == 200
    assert "filamind-setup" in r.json()["suiteCommand"]


def test_dependency_guard_passes_through_route_when_writes_off() -> None:
    # The route still refuses with 403 at the writes gate before any dependency work.
    r = client.post("/api/setup/install", json={"id": "mainsail"})
    assert r.status_code == 403
