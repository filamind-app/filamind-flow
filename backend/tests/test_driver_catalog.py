"""Locks for the canonical stepper-driver catalog: dedup, Klipper config snippets, routes."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import create_app
from app.services import driver_search, reference_data

client = TestClient(create_app())


def test_drivers_exist_and_deduped() -> None:
    drivers = reference_data.drivers()
    assert len(drivers) >= 40, "expected the canonical driver set"
    ids = [d["driver_id"] for d in drivers]
    assert len(ids) == len(set(ids)), "driver_id must be unique (deduped)"
    # core TMC chips present
    for chip in ("tmc2209", "tmc2208", "tmc2130", "tmc5160", "tmc2240"):
        assert chip in ids, f"{chip} missing"


def test_every_driver_has_copyable_snippet() -> None:
    """The whole point: every driver carries a copyable config snippet (the copy section)."""
    for d in reference_data.drivers():
        snip = (d.get("configSnippet") or "").strip()
        assert snip, f"{d['driver_id']} has no configSnippet"


def test_tmc_drivers_emit_a_real_klipper_section() -> None:
    """Klipper-managed TMC drivers must produce a real [tmcXXXX ...] block; standalone
    drivers must NOT claim a section (honest: current set by Vref pot)."""
    for d in reference_data.drivers():
        if d.get("klipperSupported"):
            sec = d.get("klipperSection")
            assert sec and sec.startswith("tmc"), f"{d['driver_id']} TMC but no section"
            assert f"[{sec} stepper" in d["configSnippet"], f"{d['driver_id']} missing section"
        else:
            assert not d.get("klipperSection"), f"{d['driver_id']} non-TMC must not claim a section"


def test_route_drivers_list_and_detail() -> None:
    r = client.get("/api/hardware/drivers", params={"limit": 5})
    assert r.status_code == 200
    body = r.json()
    assert body["total"] >= 40 and body["drivers"]
    # summary stays light — no snippet in the list
    assert "configSnippet" not in body["drivers"][0]

    klip = client.get("/api/hardware/drivers", params={"klipper_only": True})
    assert klip.status_code == 200
    assert all(d["klipperSupported"] for d in klip.json()["drivers"])

    one = client.get("/api/hardware/drivers/tmc2209")
    assert one.status_code == 200
    detail = one.json()
    assert detail["driver_id"] == "tmc2209"
    assert "[tmc2209 stepper" in detail["configSnippet"]

    assert client.get("/api/hardware/drivers/does-not-exist").status_code == 404


def test_summary_is_lightweight() -> None:
    full = reference_data.driver_by_id("tmc2209")
    assert full is not None
    summ = driver_search.summarize(full)
    assert "configSnippet" not in summ and summ["specCount"] >= 1
