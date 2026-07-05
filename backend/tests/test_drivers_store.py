"""Tests for the driver-tuning readiness store."""

from __future__ import annotations

from pathlib import Path

from app.services import drivers_store


def test_write_then_read_roundtrip(tmp_path: Path) -> None:
    drivers_store.write_tuned(str(tmp_path), "stepper_x", "apply")
    last = drivers_store.read_last(str(tmp_path))
    assert last is not None
    assert last["stepper"] == "stepper_x" and last["method"] == "apply" and last["at"]
    assert drivers_store.is_tuned(str(tmp_path)) is True


def test_missing_is_untuned(tmp_path: Path) -> None:
    assert drivers_store.read_last(str(tmp_path)) is None
    assert drivers_store.is_tuned(str(tmp_path)) is False


def test_empty_data_dir_is_a_noop() -> None:
    # No data dir configured → never write, never crash, always reads as untuned.
    drivers_store.write_tuned("", "stepper_x", "apply")
    assert drivers_store.is_tuned("") is False


def test_corrupt_file_reads_as_untuned(tmp_path: Path) -> None:
    (tmp_path / "drivers-tuned.json").write_text("{not json", encoding="utf-8")
    assert drivers_store.read_last(str(tmp_path)) is None
    assert drivers_store.is_tuned(str(tmp_path)) is False


def test_autotune_method_is_recorded(tmp_path: Path) -> None:
    drivers_store.write_tuned(str(tmp_path), "stepper_y", "autotune")
    last = drivers_store.read_last(str(tmp_path))
    assert last is not None and last["method"] == "autotune"
