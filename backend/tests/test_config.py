from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.main import create_app
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


def test_config_unavailable_without_klipper(tmp_path: Path) -> None:
    client = _client(tmp_path, klipper_dir=str(tmp_path / "no-klipper-here"))

    tree = client.post("/api/firmware/config/tree", json={"values": []})
    assert tree.status_code == 503

    profiles = client.get("/api/firmware/config/profiles").json()
    assert profiles["kconfig_available"] is False
    assert profiles["profiles"] == []
