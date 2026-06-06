"""Tests for the Phase 0 reference-data layer (loader + read-only API)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import create_app
from app.services import reference_data


def test_stallguard_dataset_loads_with_per_driver_overrides() -> None:
    data = reference_data.stallguard_profiles()
    assert isinstance(data.get("base"), dict) and data["base"], "base constants present"
    overrides = data["overrides"]
    # TMC2240 + TMC2209 carry overrides; TMC5160 inherits the base (empty override set).
    assert overrides["tmc2240"], "tmc2240 has overrides"
    assert overrides["tmc2209"], "tmc2209 has overrides"
    assert data["field_by_driver"]["tmc2209"] == "sgthrs"
    assert data["field_by_driver"]["tmc5160"] == "sgt"


def test_resolved_profile_merges_base_with_overrides() -> None:
    base = reference_data.stallguard_profiles()["base"]
    sg2 = reference_data.resolved_profile("tmc5160")
    # TMC5160 = pure base (no overrides) + its field.
    assert sg2["field"] == "sgt"
    assert sg2["constants"]["WARMUP_DRIFT_THRESHOLD"] == base["WARMUP_DRIFT_THRESHOLD"]
    # TMC2240 overrides the warmup threshold to 0.04 (steeper saturation handling).
    sg2240 = reference_data.resolved_profile("tmc2240")
    assert sg2240["constants"]["WARMUP_DRIFT_THRESHOLD"] == 0.04
    # Unknown driver still falls back to the base set (never empty).
    assert reference_data.resolved_profile("tmcXXXX")["constants"]


def test_hotends_and_boards_and_macros_load() -> None:
    hotends = reference_data.hotends()
    assert len(hotends) >= 6
    assert all("name" in h for h in hotends)
    boards = reference_data.board_patterns()
    assert len(boards["board_patterns"]) >= 30
    assert len(boards["mcu_patterns"]) >= 10
    macros = reference_data.macros()
    assert len(macros) >= 10
    assert any(m.get("name") == "QUAD_GANTRY_LEVEL" for m in macros)


def test_reference_endpoints_serve_the_datasets() -> None:
    client = TestClient(create_app())
    assert client.get("/api/reference/stallguard").status_code == 200
    r = client.get("/api/reference/stallguard/tmc2209")
    assert r.status_code == 200 and r.json()["field"] == "sgthrs"
    assert client.get("/api/reference/hotends").status_code == 200
    assert client.get("/api/reference/boards").status_code == 200
    assert len(client.get("/api/reference/macros").json()) >= 10
