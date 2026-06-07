"""Locks for the generic canonical catalog (9 remaining categories): entities, snippet, routes."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import create_app
from app.services import catalog_search, reference_data

client = TestClient(create_app())

EXPECTED_CATS = {
    "Sensors & Probes",
    "Hotends & Heaters",
    "Fans, Power & Bed",
    "Motion & Mechanical",
    "Nozzles",
    "Extruders",
    "Filament Materials",
    "Electronics & Wiring",
    "Cameras & Displays",
}


def test_catalog_covers_remaining_categories() -> None:
    cats = set(reference_data.catalog_categories())
    assert cats >= EXPECTED_CATS, f"missing catalog categories: {EXPECTED_CATS - cats}"


def test_every_catalog_entity_has_id_and_snippet() -> None:
    seen = set()
    for cat in reference_data.catalog_categories():
        ents = reference_data.catalog_entities(cat)
        assert ents, f"{cat} has no entities"
        for e in ents:
            assert (e.get("configSnippet") or "").strip(), f"{e.get('catalog_id')} missing snippet"
            cid = e["catalog_id"]
            assert cid not in seen, f"duplicate catalog_id {cid}"
            seen.add(cid)


def test_catalog_names_are_products_not_swapped_specs() -> None:
    """Data-audit lock (Wave 1): no catalog entity may carry a bare interface word / pure voltage /
    pure thread as its `name` while a real product sits in `manufacturer` (the column-swap bug).
    Each row's `name` must carry real product identity."""
    import re

    generic = {"connectors", "connector", "i2c", "spi", "wire", "cable"}
    offenders = []
    for cat in reference_data.catalog_categories():
        for e in reference_data.catalog_entities(cat):
            name = str(e.get("name", "")).strip()
            mfr = str(e.get("manufacturer", "")).strip()
            nl = name.lower()
            looks_spec = (
                nl in generic
                or re.match(r"^[\d.]+\s*v(\s*(or|/)\s*[\d.]+\s*v)?$", nl)
                or re.match(r"^m\d+\s*[×x]\s*[\d.]+$", nl)  # noqa: RUF001 (data uses mult-sign)
            )
            if looks_spec and mfr and not mfr.lower().startswith("generic") and mfr != "—":
                offenders.append((e.get("catalog_id"), name, mfr))
    assert not offenders, (
        f"{len(offenders)} catalog rows still have a swapped spec-as-name, e.g. {offenders[:5]}"
    )
    # recovered identities
    by_id = {
        e["catalog_id"]: e
        for cat in reference_data.catalog_categories()
        for e in reference_data.catalog_entities(cat)
    }
    assert by_id["sens-max6675-spi"]["name"] == "MAX6675"
    assert by_id["elec-xt30-xt30u-connectors"]["name"] == "XT30 / XT30U"


def test_manufacturer_field_has_no_junk() -> None:
    """Data-audit lock (Wave 3): a catalog `manufacturer` must never be a spec/junk value
    (a bare number, a dimension, a StallGuard description, an em-dash)."""
    import re

    bad = []
    for cat in reference_data.catalog_categories():
        for e in reference_data.catalog_entities(cat):
            m = str(e.get("manufacturer", "")).strip()
            if not m:
                continue
            if (
                re.fullmatch(r"[\d.,/×x\s-]+", m)  # noqa: RUF001 (data uses mult-sign)
                or m == "—"
                or re.search(r"stallguard|tstep", m, re.I)
            ):
                bad.append((e.get("catalog_id"), m))
    assert not bad, f"{len(bad)} catalog manufacturers are junk, e.g. {bad[:5]}"
    by_id = {
        e["catalog_id"]: e
        for cat in reference_data.catalog_categories()
        for e in reference_data.catalog_entities(cat)
    }
    assert by_id["elec-10-55"]["name"] == "10 AWG"  # bare-AWG reconstructed
    assert not any(
        h.get("manufacturer") == "Compute" for h in reference_data.hosts()
    )  # truncation fixed


def test_config_snippet_integrity() -> None:
    """Data-audit lock (Wave 5): SPI thermocouple sensors carry the correct Klipper config (not a
    generic ADC-thermistor placeholder); no entity has a non-URL configSource; no snippet header
    has a parenthetical annotation inside the brackets."""
    import re

    by_id = {
        e["catalog_id"]: e
        for cat in reference_data.catalog_categories()
        for e in reference_data.catalog_entities(cat)
    }
    mx = by_id["sens-max6675-spi"]["configSnippet"]
    assert (
        "sensor_type: MAX6675" in mx and "spi_software" in mx and "<Klipper sensor name" not in mx
    )
    # no non-URL configSource anywhere
    for cat in reference_data.catalog_categories():
        for e in reference_data.catalog_entities(cat):
            cs = str(e.get("configSource", "")).strip()
            assert not cs or cs.lower().startswith(("http", "//")), (
                f"{e['catalog_id']} configSource not a URL"
            )
    for b in reference_data.boards():
        cs = str(b.get("configSource", "")).strip()
        assert not cs or cs.lower().startswith(("http", "//")), (
            f"{b['board_id']} configSource not a URL"
        )
        for hdr in re.findall(r"^\s*\[([^\]]+)\]", str(b.get("configSnippet", "")), re.M):
            assert "(" not in hdr, f"{b['board_id']} has an invalid section header [{hdr}]"


def test_extruder_snippet_has_gear_ratio_or_rotation() -> None:
    ext = reference_data.catalog_entities("Extruders")
    assert ext
    assert all("[extruder]" in e["configSnippet"] for e in ext)


def test_route_catalog_list_and_detail() -> None:
    r = client.get("/api/hardware/catalog", params={"category": "Extruders", "limit": 5})
    assert r.status_code == 200
    body = r.json()
    assert body["total"] >= 50 and body["entities"]
    assert "configSnippet" not in body["entities"][0]  # summary stays light

    cid = body["entities"][0]["catalog_id"]
    one = client.get(f"/api/hardware/catalog/{cid}")
    assert one.status_code == 200 and "configSnippet" in one.json()

    assert client.get("/api/hardware/catalog", params={"category": "Nope"}).status_code == 404
    assert client.get("/api/hardware/catalog/nope-nope").status_code == 404


def test_summary_is_lightweight() -> None:
    e = reference_data.catalog_entities("Sensors & Probes")[0]
    summ = catalog_search.summarize(e)
    assert "configSnippet" not in summ and "specs" not in summ
