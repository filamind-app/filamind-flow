"""Tests for the Setup install-provenance stamp."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.services import setup_provenance


@pytest.fixture(autouse=True)
def _tmp_store(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(setup_provenance, "_path", lambda: tmp_path / "setup-installed.json")


def test_record_read_roundtrip() -> None:
    setup_provenance.record(
        "kamp",
        method="extra",
        repo="kyleisah/Klipper-Adaptive-Meshing-Purging",
        ref="v2.0",
        extras=["kamp.py"],
        includes=["KAMP_Settings.cfg"],
        moonraker_key="KAMP",
    )
    rec = setup_provenance.read("kamp")
    assert rec is not None
    assert rec["method"] == "extra" and rec["ref"] == "v2.0"
    assert rec["extras"] == ["kamp.py"] and rec["includes"] == ["KAMP_Settings.cfg"]
    assert rec["moonraker_key"] == "KAMP" and rec["at"]
    assert "kamp" in setup_provenance.read_all()


def test_missing_reads_none() -> None:
    assert setup_provenance.read("nope") is None
    assert setup_provenance.read_all() == {}


def test_remove_forgets() -> None:
    setup_provenance.record("mainsail", method="web-ui", nginx_site="mainsail")
    assert setup_provenance.read("mainsail") is not None
    setup_provenance.remove("mainsail")
    assert setup_provenance.read("mainsail") is None
    setup_provenance.remove("mainsail")  # idempotent, never raises


def test_corrupt_store_reads_empty(tmp_path: Path) -> None:
    (tmp_path / "setup-installed.json").write_text("{bad", encoding="utf-8")
    assert setup_provenance.read_all() == {}
