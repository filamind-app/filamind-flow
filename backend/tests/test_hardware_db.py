"""The curated hardware catalog ships as a read-only SQLite database (compiled from a local JSON
source by ``scripts/build_hardware_db.py``). These guard that the compiled DB is committed and that
``reference_data`` reconstructs the same in-memory structure from it — so the public contract and
every downstream index / haystack / link-graph are unaffected by the storage change."""

from __future__ import annotations

from pathlib import Path

from app.services import reference_data as rd


def test_compiled_sqlite_is_committed() -> None:
    db = Path(rd.__file__).resolve().parent.parent / "data" / "reference" / "hardware.sqlite"
    # The repo ships the compiled DB (the human-readable source is kept local / git-ignored).
    assert db.exists(), (
        "hardware.sqlite is missing — run scripts/build_hardware_db.py and commit it"
    )
    assert db.stat().st_size > 1_000_000


def test_reconstructed_catalog_is_intact() -> None:
    # reference_data loaded from the SQLite at import; the canonical sets must be intact.
    assert len(rd.boards()) > 300
    assert len(rd.drivers()) > 40
    assert len(rd.motors()) > 600
    assert len(rd.hosts()) > 100
    assert len(rd.hardware_items()) > 3000
    assert len(rd.item_haystacks()) == len(rd.hardware_items())
    assert len(rd.catalog_categories()) == 9
    assert sum(len(rd.catalog_entities(c)) for c in rd.catalog_categories()) > 1000


def test_indexes_and_graph_resolve_from_sqlite() -> None:
    # O(1) id lookups, facets, the link graph and the ETag all derive from the rebuilt dict.
    board = rd.boards()[0]
    assert rd.board_by_id(board["board_id"]) == board
    motor = rd.motors()[0]
    assert rd.motor_by_id(motor["motor_id"]) == motor
    assert rd.dataset_etag().startswith('W/"hw-')
    assert rd.related("boards", board["board_id"]) is not None
    assert "boardClass" in rd.hardware_facets()
