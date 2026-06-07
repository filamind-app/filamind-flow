"""Locks for the DB-2 linking backbone: graph integrity (no dangling edges), manufacturer
canonicalisation + resolution, whitelist MCU extraction, relation symmetry, and the
``/manufacturers`` / ``/mcus`` / ``/{type}/{id}/related`` / ``?expand=related`` endpoints."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import create_app
from app.services import hardware_links, reference_data

client = TestClient(create_app())


# ── graph integrity (the CI edge-validator) ───────────────────────────────────
def test_no_dangling_edges() -> None:
    g = reference_data.link_graph()
    for key, neighbours in g.adjacency.items():
        assert key in g.summaries, f"adjacency node {key!r} missing a summary"
        for edge in neighbours:
            assert edge["key"] in g.summaries, f"edge to {edge['key']!r} dangles"
            assert edge["rel"]


def test_every_referenced_manufacturer_and_mcu_exists() -> None:
    # walk the ACTUAL adjacency edges (the data path the API serves), not the pre-guarded map —
    # so this would genuinely fail if resolution ever emitted a hub-less edge.
    g = reference_data.link_graph()
    for neighbours in g.adjacency.values():
        for edge in neighbours:
            kind, ident = edge["key"].split(":", 1)
            if kind == "manufacturer":
                assert ident in g.manufacturer_by_id, f"edge → unknown manufacturer {ident!r}"
            elif kind == "mcu":
                assert ident in g.mcu_by_id, f"edge → unknown mcu {ident!r}"


def test_relations_are_symmetric() -> None:
    boards = reference_data.boards()
    # board↔mcu: a board that lists an mcu must be reachable back from that mcu
    sample = next(b for b in boards if hardware_links.board_mcu_ids(b))
    bid = sample["board_id"]
    rel = reference_data.related("boards", bid)
    assert rel is not None
    for mcu_summary in rel["groups"].get("mcus", []):
        back = reference_data.related("mcus", mcu_summary["id"])
        assert any(s["id"] == bid for s in back["groups"].get("boards", []))
    # board↔driver: a board's supported/onboard driver must list the board back
    g = reference_data.link_graph()
    dboard = next(
        (
            b["board_id"]
            for b in boards
            if any(
                e["rel"] in ("onboardDrivers", "supportedDrivers")
                for e in g.adjacency.get(f"board:{b['board_id']}", [])
            )
        ),
        None,
    )
    assert dboard is not None
    drel = reference_data.related("boards", dboard)
    drivers = drel["groups"].get("supportedDrivers", []) + drel["groups"].get("onboardDrivers", [])
    for d in drivers:
        back = reference_data.related("drivers", d["id"])
        assert any(s["id"] == dboard for s in back["groups"].get("boards", []))


# ── manufacturer canonicalisation ─────────────────────────────────────────────
def test_manufacturer_aliases_resolve_to_one_id() -> None:
    resolver = hardware_links.ManufacturerResolver(reference_data.hardware_manufacturers())
    variants = ("BigTreeTech", "BTT", "BIGTREETECH (BTT)", "BigTreeTech / BIQU")
    ids = {resolver.resolve(v) for v in variants}
    ids.discard(None)
    assert len(ids) == 1, f"BTT variants resolved to {ids}"
    # junk / spec-fragment strings must NOT resolve to a manufacturer
    assert resolver.resolve("26") is None
    assert resolver.resolve("TMC StallGuard") is None


def test_generic_placeholders_are_not_manufacturers() -> None:
    names = {m["name"].lower() for m in reference_data.manufacturers_canonical()}
    for placeholder in ("generic (clone)", "reprap (open)"):
        assert placeholder not in names
    # but real recurring brands missing from the directory ARE derived
    assert any(m["origin"] == "derived" for m in reference_data.manufacturers_canonical())


def test_descriptor_words_do_not_resolve_to_brands() -> None:
    # generic descriptor words buried in a brand name must NOT become brand identifiers
    resolver = hardware_links.ManufacturerResolver(reference_data.hardware_manufacturers())
    for word in ("module", "pcb", "smart", "power", "plastic", "endstop", "pro", "build"):
        assert word not in resolver._uniq_token, f"{word!r} wrongly promoted to a brand token"
    assert resolver.resolve('Encoder / motion (generic "smart")') is None
    assert resolver.resolve("LM2596 buck module") is None
    assert resolver.resolve("Generic PCB screw terminal") is None


def test_real_brand_with_placeholder_cobrand_survives() -> None:
    # word-bounded placeholder regex on the PRIMARY chunk only: "Aus3D / Reprapworld" is real
    assert not hardware_links._is_placeholder_manufacturer("Aus3D / Reprapworld")
    assert not hardware_links._is_placeholder_manufacturer("ReprapWorld")
    # but the bare community name IS a placeholder
    assert hardware_links._is_placeholder_manufacturer("RepRap (open)")
    by_id = reference_data.link_graph().manufacturer_by_id
    assert "aus3d" in by_id


def test_brand_spacing_variants_unify() -> None:
    # "MeanWell" must resolve to the same id as "Mean Well" (no spurious derived split)
    resolver = hardware_links.ManufacturerResolver(reference_data.hardware_manufacturers())
    assert resolver.resolve("MeanWell") == resolver.resolve("Mean Well") is not None
    assert not any(
        m["manufacturer_id"] == "meanwell" for m in reference_data.manufacturers_canonical()
    )


def test_board_driver_edges_are_token_exact() -> None:
    # the TMC5160T variant must NOT bleed into boards that merely list TMC5160/TMC5161
    g = reference_data.link_graph()
    t_boards = {e["key"] for e in g.adjacency.get("driver:tmc5160t", []) if e["rel"] == "boards"}
    base_boards = {e["key"] for e in g.adjacency.get("driver:tmc5160", []) if e["rel"] == "boards"}
    # the bogus cross-boundary matches are gone (far fewer than the real TMC5160 set)
    assert len(t_boards) <= 2 < len(base_boards)


def test_manufacturer_membercount_matches_edges() -> None:
    g = reference_data.link_graph()
    for man in reference_data.manufacturers_canonical():
        key = f"manufacturer:{man['manufacturer_id']}"
        member_edges = sum(1 for e in g.adjacency.get(key, []))
        assert man["memberCount"] == member_edges


# ── MCU whitelist extraction ──────────────────────────────────────────────────
def test_mcu_normalisation_strips_package_and_rejects_noise() -> None:
    assert hardware_links.normalize_mcu("STM32F407VET6")[0] == "stm32f407"
    assert hardware_links.normalize_mcu("STM32G0B1CBT6")[0] == "stm32g0b1"
    assert hardware_links.normalize_mcu("ATSAMC21G18A")[0] == "samc21"
    assert hardware_links.normalize_mcu("ATSAMD51J19A")[0] == "samd51"  # SAMD family not dropped
    assert hardware_links.normalize_mcu("ATMEGA2560")[0] == "atmega2560"
    assert hardware_links.normalize_mcu("RP2040")[0] == "rp2040"
    # noise / host SoCs / package fragments are NOT MCUs
    for noise in ("ZGT6", "RK3566", "CB1", "CM4", "DDR3", "NEMA23", "MIPS32"):
        assert hardware_links.normalize_mcu(noise) is None


def test_mcu_entities_present_and_clean() -> None:
    ids = {m["mcu_id"] for m in reference_data.mcus()}
    assert {"rp2040", "stm32f103", "atmega2560"} <= ids
    assert not ({"rk3566", "cb1", "ddr3", "nema23", "zgt6"} & ids)
    for m in reference_data.mcus():
        assert m["boardCount"] >= 1


# ── endpoints ─────────────────────────────────────────────────────────────────
def test_facets_endpoint() -> None:
    body = client.get("/api/hardware/facets").json()
    assert "mainboard" in body["boardClass"]
    assert "17" in body["nema"] and all(s.isdigit() for s in body["nema"])  # normalised to size
    assert {"sbc", "x86"} <= set(body["kind"])


def test_manufacturers_endpoint_is_canonical() -> None:
    rows = client.get("/api/hardware/manufacturers").json()
    assert rows and all("manufacturer_id" in m and "memberCount" in m for m in rows)
    # sorted most-connected first
    assert rows[0]["memberCount"] >= rows[-1]["memberCount"]
    top = rows[0]["manufacturer_id"]
    assert client.get(f"/api/hardware/manufacturers/{top}").json()["manufacturer_id"] == top
    assert client.get("/api/hardware/manufacturers/__nope__").status_code == 404
    assert client.get("/api/hardware/manufacturers", params={"q": "btt"}).json()


def test_mcus_endpoint() -> None:
    body = client.get("/api/hardware/mcus").json()
    assert body["total"] == len(body["items"]) >= 10
    assert client.get("/api/hardware/mcus/rp2040").json()["mcu_id"] == "rp2040"
    assert client.get("/api/hardware/mcus/__nope__").status_code == 404
    fam = client.get("/api/hardware/mcus", params={"family": "stm32f4"}).json()
    assert fam["items"] and all("stm32f4" in m["family"].lower() for m in fam["items"])


def test_related_endpoint_and_expand() -> None:
    bid = client.get("/api/hardware/boards", params={"limit": 1}).json()["boards"][0]["board_id"]
    rel = client.get(f"/api/hardware/boards/{bid}/related").json()
    assert rel["type"] == "board" and rel["id"] == bid
    assert isinstance(rel["groups"], dict) and isinstance(rel["counts"], dict)
    # expand inlines the same data on the detail endpoint
    expanded = client.get(f"/api/hardware/boards/{bid}", params={"expand": "related"}).json()
    assert "related" in expanded and "relatedCounts" in expanded
    # unknown type / id → 404
    assert client.get("/api/hardware/widgets/foo/related").status_code == 404
    assert client.get("/api/hardware/boards/__nope__/related").status_code == 404
