"""Tests for scripts/apply_submission.py — the maintainer tool that merges a community catalog
submission into the hardware database. The script lives outside the package, so it's loaded by path;
these tests cover inference, validation and merge logic without touching the real JSON.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parent.parent.parent / "scripts" / "apply_submission.py"
_spec = importlib.util.spec_from_file_location("apply_submission", _SCRIPT)
assert _spec and _spec.loader
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)


def test_infer_type_from_id_key() -> None:
    assert mod.infer_type({"motor_id": "ldo-42"}) == "motor"
    assert mod.infer_type({"driver_id": "tmc2209"}) == "driver"
    assert mod.infer_type({"board_id": "btt-octopus"}) == "board"
    assert mod.infer_type({"host_id": "btt-cb1"}) == "host"
    assert mod.infer_type({"catalog_id": "bambu-hotend"}) == "catalog"


def test_infer_type_manufacturer_and_unknown() -> None:
    assert mod.infer_type({"name": "Creality", "country": "China"}) == "manufacturer"
    assert mod.infer_type({"specs": {}}) is None


def test_validate_flags_missing_required() -> None:
    errors = mod.validate("motor", {"motor_id": "x"})
    assert any("manufacturer" in e for e in errors)
    assert any("name" in e for e in errors)


def test_validate_shapes_and_slug() -> None:
    assert mod.validate("motor", {"motor_id": "Bad Slug!", "manufacturer": "M", "name": "N"})
    assert mod.validate("motor", {"motor_id": "ok", "manufacturer": "M", "name": "N", "specs": []})
    # a clean fragment passes
    assert (
        mod.validate("motor", {"motor_id": "ldo-42", "manufacturer": "LDO", "name": "42STH"}) == []
    )


def test_merge_adds_motor() -> None:
    data: dict = {}
    action = mod.merge(
        data, "motor", {"motor_id": "ldo-42", "manufacturer": "LDO", "name": "42STH"}, force=False
    )
    assert action == "added"
    assert data["motors"][0]["motor_id"] == "ldo-42"


def test_merge_rejects_duplicate_without_force() -> None:
    data = {"motors": [{"motor_id": "ldo-42", "name": "old"}]}
    with pytest.raises(ValueError, match="already exists"):
        mod.merge(
            data, "motor", {"motor_id": "ldo-42", "manufacturer": "LDO", "name": "new"}, force=False
        )


def test_merge_replaces_with_force() -> None:
    data = {"motors": [{"motor_id": "ldo-42", "name": "old"}]}
    action = mod.merge(
        data, "motor", {"motor_id": "ldo-42", "manufacturer": "LDO", "name": "new"}, force=True
    )
    assert action == "replaced"
    assert len(data["motors"]) == 1
    assert data["motors"][0]["name"] == "new"


def test_merge_catalog_into_category_bucket() -> None:
    data: dict = {}
    frag = {"catalog_id": "bambu-hotend", "category": "Hotends & Heaters", "name": "H2D"}
    action = mod.merge(data, "catalog", frag, force=False)
    assert action == "added"
    assert data["catalog"]["Hotends & Heaters"][0]["catalog_id"] == "bambu-hotend"


def test_merge_manufacturer_dedupes_by_name() -> None:
    data = {"manufacturers": [{"name": "Creality"}]}
    with pytest.raises(ValueError, match="already exists"):
        mod.merge(data, "manufacturer", {"name": "creality"}, force=False)
