from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.main import create_app


def _client(tmp_path: Path) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_settings] = lambda: Settings(
        moonraker_url="http://127.0.0.1:1",
        data_dir=str(tmp_path),
    )
    return TestClient(app)


def test_external_upload_list_update_download_delete(tmp_path: Path) -> None:
    client = _client(tmp_path)
    blob = b"\x00\x01firmware"

    up = client.post("/api/firmware/external?name=vendor_fw&ext=bin", content=blob)
    assert up.status_code == 200
    body = up.json()
    assert body["name"] == "vendor_fw"
    assert body["filename"] == "vendor_fw.bin"
    assert body["size"] == len(blob)
    assert body["method"] == "serial"  # default

    listed = client.get("/api/firmware/external").json()["firmware"]
    assert any(f["name"] == "vendor_fw" for f in listed)

    upd = client.post(
        "/api/firmware/external/vendor_fw/meta",
        json={"method": "dfu", "offset": "0x08002000", "label": "My Vendor FW"},
    )
    assert upd.status_code == 200
    assert upd.json()["method"] == "dfu"
    assert upd.json()["offset"] == "0x08002000"
    assert upd.json()["label"] == "My Vendor FW"

    dl = client.get("/api/firmware/external/vendor_fw/download")
    assert dl.status_code == 200
    assert dl.content == blob

    assert client.delete("/api/firmware/external/vendor_fw").status_code == 200
    assert client.delete("/api/firmware/external/vendor_fw").status_code == 404
    # updating a missing firmware → 404.
    assert client.post("/api/firmware/external/ghost/meta", json={"notes": "x"}).status_code == 404


def test_external_reads_embedded_properties(tmp_path: Path) -> None:
    client = _client(tmp_path)
    blob = b"\x00\x01junk Klipper v0.12.0-345-gabcdef12 build on stm32f103xe\x00more"
    up = client.post("/api/firmware/external?name=fw2&ext=bin", content=blob)
    assert up.status_code == 200
    body = up.json()
    assert body["detected_version"] == "v0.12.0-345-gabcdef12"
    assert "stm32" in (body["detected_mcu"] or "")


def test_external_reads_version_from_zlib_data_dict(tmp_path: Path) -> None:
    # Klipper raw .bin stores the version/MCU in a zlib-compressed data dictionary,
    # not plain strings — the inspector must decompress it.
    import zlib

    client = _client(tmp_path)
    data_dict = (
        b'{"app":"Klipper","version":"v0.12.0-5-gabc1234",'
        b'"config":{"MCU":"stm32f103xe","CLOCK_FREQ":72000000}}'
    )
    blob = b"\x00\xffARMCODE\x00" + zlib.compress(data_dict) + b"\xfetail"
    up = client.post("/api/firmware/external?name=fw3&ext=bin", content=blob)
    assert up.status_code == 200
    body = up.json()
    assert body["detected_version"] == "v0.12.0-5-gabc1234"
    assert body["detected_app"] == "Klipper"
    assert body["detected_mcu"] == "stm32f103xe"
    # The full baked-in config section is surfaced (read-only).
    assert body["detected_config"] == {"MCU": "stm32f103xe", "CLOCK_FREQ": "72000000"}


def test_external_rejects_bad_name_and_ext(tmp_path: Path) -> None:
    client = _client(tmp_path)
    assert (
        client.post("/api/firmware/external?name=..%2fevil&ext=bin", content=b"x").status_code
        == 400
    )
    assert client.post("/api/firmware/external?name=ok&ext=exe", content=b"x").status_code == 400
