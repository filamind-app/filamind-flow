"""Tests for the Max-Flow last-result store (atomic write + graceful read)."""

from __future__ import annotations

import pathlib

from app.services import max_flow_store


def test_write_then_read_round_trip(tmp_path: pathlib.Path) -> None:
    result = {
        "max_flow_mm3s": 24.0,
        "slip_flow": 26.0,
        "recommend": {"balanced": 21.6},
        "driver": "tmc2209",
        "method": "accel",
        "noise": "not persisted",  # only the headline fields are kept
    }
    max_flow_store.write_last(
        str(tmp_path), result, hotend="Dragon HF", expected_max_flow_mm3s=30.0
    )
    out = max_flow_store.read_last(str(tmp_path))
    assert out is not None
    assert out["max_flow_mm3s"] == 24.0
    assert out["method"] == "accel"
    assert out["hotend"] == "Dragon HF"
    assert out["expected_max_flow_mm3s"] == 30.0
    assert "noise" not in out
    assert "at" in out


def test_read_missing_is_none(tmp_path: pathlib.Path) -> None:
    assert max_flow_store.read_last(str(tmp_path)) is None


def test_read_corrupt_is_none(tmp_path: pathlib.Path) -> None:
    (tmp_path / "max-flow-last.json").write_text("{ not json", encoding="utf-8")
    assert max_flow_store.read_last(str(tmp_path)) is None


def test_optional_fields_omitted_when_absent(tmp_path: pathlib.Path) -> None:
    max_flow_store.write_last(str(tmp_path), {"max_flow_mm3s": 18.0})
    out = max_flow_store.read_last(str(tmp_path))
    assert out is not None
    assert "hotend" not in out and "expected_max_flow_mm3s" not in out
