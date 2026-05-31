from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.main import create_app
from app.services import devices_store
from app.services.firmware_profiles import ProfileNameError, validate_name

FIXTURE_KLIPPER = str(Path(__file__).parent / "fixtures" / "fake_klipper")


def _client(tmp_path: Path, klipper_dir: str = FIXTURE_KLIPPER) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: Settings(
        moonraker_url="http://127.0.0.1:1",
        klipper_dir=klipper_dir,
        data_dir=str(tmp_path),
    )
    return TestClient(app)


def test_validate_name_rejects_traversal() -> None:
    assert validate_name("EBB36 v1.2") == "EBB36 v1.2"
    for bad in ("", "../etc/passwd", "a/b", "x..y", "name\ninjection"):
        with pytest.raises(ProfileNameError):
            validate_name(bad)


def test_config_tree_loads_and_reacts(tmp_path: Path) -> None:
    client = _client(tmp_path)

    base = client.post("/api/firmware/config/tree", json={"values": []})
    assert base.status_code == 200
    names = {node["name"] for node in base.json()}
    assert "DEMO_USB" in names
    # DEMO_SERIAL depends on !DEMO_USB, hidden while USB (the default) is on.
    assert "DEMO_SERIAL" not in names

    # Live preview: turning USB off reveals the serial-device option.
    reacted = client.post(
        "/api/firmware/config/tree",
        json={"values": [{"name": "DEMO_USB", "value": "n"}]},
    )
    assert "DEMO_SERIAL" in {node["name"] for node in reacted.json()}


def test_profile_save_list_delete(tmp_path: Path) -> None:
    client = _client(tmp_path)

    saved = client.post(
        "/api/firmware/config/profiles",
        json={"name": "demo", "values": [{"name": "DEMO_CLOCK_FREQ", "value": "16000000"}]},
    )
    assert saved.status_code == 200

    listing = client.get("/api/firmware/config/profiles").json()
    assert listing["kconfig_available"] is True
    assert any(p["name"] == "demo" for p in listing["profiles"])

    config_text = (tmp_path / "firmware-profiles" / "demo.config").read_text()
    assert "CONFIG_DEMO_CLOCK_FREQ=16000000" in config_text

    assert client.delete("/api/firmware/config/profiles/demo").status_code == 200
    assert client.delete("/api/firmware/config/profiles/demo").status_code == 404


def _all_names(nodes: list[dict]) -> set[str]:
    """Collects every symbol name in the tree, descending into nested submenus."""
    return set(_flat_nodes(nodes))


def _flat_nodes(nodes: list[dict]) -> dict[str, dict]:
    """Flattens the tree to ``{name: node}``, descending into nested submenus."""
    out: dict[str, dict] = {}
    for node in nodes:
        out[node["name"]] = node
        out.update(_flat_nodes(node.get("children", [])))
    return out


def test_low_level_menus_forced_visible(tmp_path: Path) -> None:
    client = _client(tmp_path)

    # DEMO_LOWLEVEL_TWEAK depends on LOW_LEVEL_OPTIONS, which defaults to 'n', so
    # kconfiglib nests it as a child of that gate. The editor force-enables the
    # gate, so the tweak must appear (nested) without the user touching anything.
    tree = client.post("/api/firmware/config/tree", json={"values": []})
    assert tree.status_code == 200
    assert "DEMO_LOWLEVEL_TWEAK" in _all_names(tree.json())


def test_download_artifact(tmp_path: Path) -> None:
    client = _client(tmp_path)

    # No build yet → 404.
    assert client.get("/api/firmware/config/profiles/demo/artifact").status_code == 404

    # Drop a fake built binary where artifact_path_for looks for it.
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)
    (artifacts / "demo.bin").write_bytes(b"\x7fELF fake firmware")

    got = client.get("/api/firmware/config/profiles/demo/artifact")
    assert got.status_code == 200
    assert got.content == b"\x7fELF fake firmware"
    assert "demo.bin" in got.headers["content-disposition"]

    # Path-traversal names are rejected before touching the filesystem.
    assert client.get("/api/firmware/config/profiles/..%2fevil/artifact").status_code in (400, 404)


def test_menu_and_comment_nodes_serialize(tmp_path: Path) -> None:
    # Regression: menu / comment MenuNodes have no `help` attribute in kconfiglib;
    # serializing them must not raise (this used to 500 for STM32 etc.).
    client = _client(tmp_path)
    tree = client.post("/api/firmware/config/tree", json={"values": []})
    assert tree.status_code == 200

    by_type = [(n["name"], n["type"], n["help"]) for n in tree.json()]
    menus = [t for t in by_type if t[1] == "menu"]
    assert menus, f"expected a menu node, got {by_type}"
    assert menus[0][2] is None  # help is None, not an error
    # The option nested inside the menu is reachable.
    assert "DEMO_MENU_OPT" in _all_names(tree.json())


def test_nodes_expose_default_and_dependency(tmp_path: Path) -> None:
    client = _client(tmp_path)
    # Turn USB off so the serial option (which depends on !DEMO_USB) is shown.
    tree = client.post(
        "/api/firmware/config/tree", json={"values": [{"name": "DEMO_USB", "value": "n"}]}
    )
    nodes = _flat_nodes(tree.json())

    assert nodes["DEMO_CLOCK_FREQ"]["default"] == "8000000"
    assert "DEMO_USB" in (nodes["DEMO_SERIAL"]["dep_str"] or "")


def test_rename_profile_moves_config_artifact_and_device_refs(tmp_path: Path) -> None:
    client = _client(tmp_path)
    client.post("/api/firmware/config/profiles", json={"name": "old", "values": []})

    # Pretend it was built: drop an artifact + build-info sidecar.
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)
    (artifacts / "old.bin").write_bytes(b"FW")
    (artifacts / "old.build_info.json").write_text('{"version": "v1"}')
    # A device that points at the profile.
    devices_store.save_device(str(tmp_path), {"id": "dev1", "name": "Board", "profile": "old"})

    renamed = client.post("/api/firmware/config/profiles/old/rename", json={"new_name": "new"})
    assert renamed.status_code == 200

    profiles = tmp_path / "firmware-profiles"
    assert not (profiles / "old.config").exists()
    assert (profiles / "new.config").exists()
    assert (artifacts / "new.bin").exists() and not (artifacts / "old.bin").exists()
    assert (artifacts / "new.build_info.json").exists()
    assert devices_store.get_device(str(tmp_path), "dev1")["profile"] == "new"

    # Collision → 409, missing source → 404.
    client.post("/api/firmware/config/profiles", json={"name": "other", "values": []})
    assert (
        client.post("/api/firmware/config/profiles/new/rename", json={"new_name": "other"})
    ).status_code == 409
    assert (
        client.post("/api/firmware/config/profiles/ghost/rename", json={"new_name": "x"})
    ).status_code == 404


def test_duplicate_profile_copies_config(tmp_path: Path) -> None:
    client = _client(tmp_path)
    client.post(
        "/api/firmware/config/profiles",
        json={"name": "src", "values": [{"name": "DEMO_CLOCK_FREQ", "value": "16000000"}]},
    )

    dup = client.post("/api/firmware/config/profiles/src/duplicate", json={"new_name": "copy"})
    assert dup.status_code == 200

    profiles = tmp_path / "firmware-profiles"
    assert (profiles / "src.config").read_text() == (profiles / "copy.config").read_text()
    # Source is untouched; duplicating onto an existing name → 409.
    assert (profiles / "src.config").exists()
    assert (
        client.post("/api/firmware/config/profiles/src/duplicate", json={"new_name": "copy"})
    ).status_code == 409


def test_config_unavailable_without_klipper(tmp_path: Path) -> None:
    client = _client(tmp_path, klipper_dir=str(tmp_path / "no-klipper-here"))

    tree = client.post("/api/firmware/config/tree", json={"values": []})
    assert tree.status_code == 503

    profiles = client.get("/api/firmware/config/profiles").json()
    assert profiles["kconfig_available"] is False
    assert profiles["profiles"] == []
