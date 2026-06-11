"""Lock the TMC-capability data so the three sources can't drift (audit §4c.2).

Driver StallGuard fields live in three places — the catalog ``drivers[].caps`` block (typed,
served as ``DriverInfo`` via ``reference_data.driver_infos``), ``stallguard_profiles.json``
(field_by_driver), and ``field_policy._POLICY`` (editable fields per model). These tests assert
they agree, so a future edit to one without the others fails CI.
"""

from __future__ import annotations

from typing import Any

from app.services import field_policy as fp
from app.services import reference_data


def _catalog_drivers() -> list[dict[str, Any]]:
    return reference_data.driver_infos()


def test_stallguard_field_agrees_catalog_vs_profiles() -> None:
    for d in _catalog_drivers():
        model, field = d.get("model"), d.get("stallguard_field")
        if not model or not field:
            continue
        prof = reference_data.stallguard_field(model)
        if prof is not None:  # profiles may legitimately omit a model
            assert prof == field, f"{model}: driver_info={field!r} but stallguard_profiles={prof!r}"


def test_field_policy_covers_each_stallguard_field() -> None:
    for d in _catalog_drivers():
        model, field = d.get("model"), d.get("stallguard_field")
        if not model or not field:
            continue
        policy = fp._POLICY.get(field)
        assert policy is not None, f"field_policy has no policy for StallGuard field {field!r}"
        assert (not policy.models) or (model in policy.models), (
            f"field_policy field {field!r} is not applicable to {model} (models={policy.models})"
        )
