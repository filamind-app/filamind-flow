"""Locks for the canonical stepper-motor catalog: entities, run_current snippet, routes."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from app.main import create_app
from app.services import motor_search, reference_data

client = TestClient(create_app())


def test_motors_exist_with_unique_ids() -> None:
    motors = reference_data.motors()
    assert len(motors) >= 400, "expected the canonical motor set"
    ids = [m["motor_id"] for m in motors]
    assert len(ids) == len(set(ids)), "motor_id must be unique"


def test_every_motor_has_copyable_snippet() -> None:
    for m in reference_data.motors():
        assert (m.get("configSnippet") or "").strip(), f"{m['motor_id']} has no configSnippet"


def test_motors_carry_autotune_params() -> None:
    """Motors in the autotune database carry the full datasheet params (resistance / inductance /
    holding torque / current / steps) the Motor Drivers autotune + recommender need, and every
    value is physically plausible (guards against unit/extraction errors)."""
    with_at = [m for m in reference_data.motors() if m.get("autotune")]
    assert len(with_at) >= 550, f"only {len(with_at)} motors have autotune params"
    for m in with_at:
        at = m["autotune"]
        mid = m["motor_id"]
        # all five fields present and positive
        assert at["resistance_ohm"] > 0 and at["inductance_H"] > 0, mid
        assert at["holding_torque_Nm"] > 0 and at["max_current_A"] > 0, mid
        # plausible physical ranges (NEMA34 reaches ~13 Nm / ~8 A; micro can-stack steppers
        # go down to 24 full steps/rev and ~150 ohm). A wrong value is worse than a blank.
        assert 0.05 <= at["resistance_ohm"] <= 150, f"{mid} R={at['resistance_ohm']}"
        assert 0.0001 <= at["inductance_H"] <= 0.1, f"{mid} L={at['inductance_H']}"
        assert 0.003 <= at["holding_torque_Nm"] <= 20, f"{mid} T={at['holding_torque_Nm']}"
        assert 0.05 <= at["max_current_A"] <= 9, f"{mid} I={at['max_current_A']}"
        assert at["steps_per_rev"] >= 4, f"{mid} steps={at['steps_per_rev']}"
    # the vast majority are the usual 1.8deg / 0.9deg hybrids (200 / 400 full steps)
    common = sum(1 for m in with_at if m["autotune"]["steps_per_rev"] in (200, 400))
    assert common >= len(with_at) - 20, "unexpected spread of non-standard step counts"


def test_motor_drivers_catalog_backed() -> None:
    """Convergence lock: the Motor Drivers motor catalog is served from the unified hardware
    catalog (reference_data), not a separate silo. Each entry is the flat MotorSpec shape the
    recommender needs, `model` is the unique motor_id, and a saved mapping key still resolves."""
    specs = reference_data.motor_specs()
    assert len(specs) == len(reference_data.motors()) >= 600
    models = [s["model"] for s in specs]
    assert len(models) == len(set(models)), "motor model (motor_id) must be unique for the picker"
    with_specs = [s for s in specs if s["resistance_ohm"]]
    assert len(with_specs) >= 550, "most motors carry flattened autotune params"
    for s in with_specs[:50]:
        # the exact flat top-level keys recommender.recommend() reads
        for k in ("resistance_ohm", "inductance_H", "holding_torque_Nm", "max_current_A"):
            assert s.get(k), s["model"]
        assert s["name"] and s["manufacturer"]
    # a motor resolves by motor_id, by display name, and by alias (zero-migration of saved maps)
    sample = next(m for m in reference_data.motors() if m.get("aliases"))
    assert reference_data.motor_spec_lookup(sample["motor_id"]) is not None
    assert reference_data.motor_spec_lookup(sample["name"]) is not None
    assert reference_data.motor_spec_lookup(sample["aliases"][0]) is not None
    assert reference_data.motor_spec_lookup("does-not-exist") is None


def test_motor_driver_catalog_no_external_refs() -> None:
    """The Motor Drivers data (exposed by /api/drivers/motors) must not name any other project as
    its provenance — present the reused reference data as FilaMind's own."""
    from app.services import driver_catalog

    blob = json.dumps(
        {
            "ms": reference_data.motor_specs(),
            "ds": driver_catalog.source(),
            "dd": driver_catalog.all_drivers(),
        },
        ensure_ascii=False,
    ).lower()
    for banned in (
        "ratos",
        "klipper_tmc_autotune",
        "kalico",
        "motor_database",
        "shaketune",
        "shake&tune",
        "fragmon",
        "vendored",
        "hardware-database",
    ):
        assert banned not in blob, f"leaked external reference: {banned}"


def test_motor_nema_and_step_angle_normalised() -> None:
    """Data-audit lock (Wave 4): stepAngle uses one encoding (degree sign, not '1.8 deg'/'1.8'),
    and NEMA was backfilled from part numbers so few motors are left sizeless."""
    import re

    motors = reference_data.motors()
    for m in motors:
        sa = str(m.get("stepAngle", "")).strip()
        assert not re.fullmatch(r"\d+(\.\d+)?(\s*deg)?", sa), (
            f"{m['motor_id']} stepAngle not normalised: {sa!r}"
        )
    by_id = {m["motor_id"]: m for m in motors}
    assert by_id["bigtre-17h4401s"]["nema"] == "17"  # backfilled from the part number
    sizeless = sum(1 for m in motors if not str(m.get("nema", "")).strip())
    assert sizeless <= 30, f"{sizeless} motors still have no NEMA size (backfill regressed)"


def test_run_current_recommendation_is_sane() -> None:
    """When a rated current is known, the recommended run_current is present, in the snippet,
    and conservative (below the rated phase current)."""
    checked = 0
    for m in reference_data.motors():
        rec = m.get("recommendedRunCurrent")
        if rec is None:
            continue
        checked += 1
        assert 0 < rec < 6, f"{m['motor_id']} run_current {rec} out of range"
        assert f"run_current: {rec}" in m["configSnippet"]
    assert checked >= 300, "most motors should have a recommended run_current"


def test_route_motors_list_and_detail() -> None:
    r = client.get("/api/hardware/motors", params={"limit": 5})
    assert r.status_code == 200
    body = r.json()
    assert body["total"] >= 400 and body["motors"]
    assert "configSnippet" not in body["motors"][0]  # summary stays light

    by_nema = client.get("/api/hardware/motors", params={"nema": "17"})
    assert by_nema.status_code == 200
    assert all("17" in str(m.get("nema", "")) for m in by_nema.json()["motors"])

    one_id = body["motors"][0]["motor_id"]
    one = client.get(f"/api/hardware/motors/{one_id}")
    assert one.status_code == 200
    assert "run_current" in one.json()["configSnippet"]

    assert client.get("/api/hardware/motors/does-not-exist").status_code == 404


def test_summary_is_lightweight() -> None:
    full = reference_data.motors()[0]
    summ = motor_search.summarize(full)
    assert "configSnippet" not in summ and "specs" not in summ
