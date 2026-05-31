from __future__ import annotations

from pathlib import Path

from app.services import version_store


def test_build_info_roundtrip(tmp_path: Path) -> None:
    data = str(tmp_path)
    version_store.write_build_info(
        data, "host-mcu", {"version": "v0.13.0-660-gabc", "commit": "abc", "date": "d"}
    )
    info = version_store.read_build_info(data, "host-mcu")
    assert info is not None
    assert info["version"] == "v0.13.0-660-gabc"
    assert info["built_at"]  # a timestamp was stamped on write
    assert version_store.read_build_info(data, "never-built") is None


def test_flash_record_tracks_version(tmp_path: Path) -> None:
    data = str(tmp_path)
    assert version_store.flashed_version(data, "linux_process") is None

    version_store.record_flash(
        data, "linux_process", "host-mcu", {"version": "v0.13.0-660-gabc", "commit": "abc"}
    )
    assert version_store.flashed_version(data, "linux_process") == "v0.13.0-660-gabc"

    record = version_store.flash_records(data)["linux_process"]
    assert record["profile"] == "host-mcu"
    assert record["flashed_at"]
