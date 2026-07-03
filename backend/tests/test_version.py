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


def test_flashed_record_joins_linked_identities(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    """A flash recorded under ONE of a board's identities stays visible under the others - a board
    re-enumerated as its bootloader port must not lose its recorded version."""
    times = iter(["2026-07-02 10:00:00", "2026-07-02 10:00:01", "2026-07-02 10:00:02"])
    monkeypatch.setattr(version_store, "_now", lambda: next(times))
    data = str(tmp_path)
    klipper_id = "/dev/serial/by-id/usb-Klipper_stm32f446xx_AB-if00"
    katapult_id = "/dev/serial/by-id/usb-katapult_stm32f446xx_AB-if00"
    version_store.record_flash(data, klipper_id, "octopus", {"version": "v1", "commit": "c1"})
    # looked up under the OTHER identity via the identity set
    record = version_store.flashed_record(data, {katapult_id, klipper_id})
    assert record is not None and record["version"] == "v1"
    # no identity matches -> None
    assert version_store.flashed_record(data, {"unrelated"}) is None
    # several matching records -> the newest wins
    version_store.record_flash(data, katapult_id, "octopus", {"version": "v2", "commit": "c2"})
    record = version_store.flashed_record(data, {katapult_id, klipper_id})
    assert record is not None and record["version"] == "v2"
    # case-insensitive: records keyed by the flash-time id ("PI2") must be found from Moonraker's
    # lowercased section names ("pi2")
    version_store.record_flash(data, "PI2", "linux_host", {"version": "v3", "commit": "c3"})
    record = version_store.flashed_record(data, {"pi2"})
    assert record is not None and record["version"] == "v3"
