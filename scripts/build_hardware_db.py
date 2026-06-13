#!/usr/bin/env python3
"""Bake the curated hardware data into the read-only ``hardware.sqlite`` that ships in the repo.

Maintainer-only. The editable source — ``hardware.json`` — is kept **locally** and is NOT committed
(it's git-ignored); only the compiled ``hardware.sqlite`` ships. After editing the JSON, run this to
regenerate the database, then commit the new ``hardware.sqlite``:

    python scripts/build_hardware_db.py

The schema is intentionally simple: one row per entity (the entity object stored as JSON in a
``data`` column, original order preserved via ``pos``), so :mod:`app.services.reference_data` can
reconstruct the exact same in-memory structure it built from the JSON — the public contract and all
downstream indexes/haystacks/graph are unchanged. Inserts are ordered + the file is VACUUMed so the
output is stable for the same input (small git diffs).
"""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

_REF_DIR = Path(__file__).resolve().parent.parent / "backend" / "app" / "data" / "reference"
JSON_PATH = _REF_DIR / "hardware.json"
DB_PATH = _REF_DIR / "hardware.sqlite"

#: Canonical entity arrays + the id field used for the indexed ``id`` column (None where there's no id).
_ENTITY_KINDS = {
    "manufacturers": None,
    "items": None,
    "boards": "board_id",
    "drivers": "driver_id",
    "motors": "motor_id",
    "hosts": "host_id",
}


def _dumps(obj: object) -> str:
    # Compact, UTF-8, original key order preserved (json.loads kept insertion order) — so an
    # entity round-trips byte-identically and the build is deterministic for the same input.
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


def build() -> None:
    if not JSON_PATH.exists():
        sys.exit(f"Source not found: {JSON_PATH} (the curated JSON is kept locally — restore it).")
    data = json.loads(JSON_PATH.read_text(encoding="utf-8"))
    if DB_PATH.exists():
        DB_PATH.unlink()

    con = sqlite3.connect(DB_PATH)
    try:
        con.execute("PRAGMA page_size=4096")
        con.executescript(
            """
            CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE entities (
                kind TEXT NOT NULL, pos INTEGER NOT NULL, id TEXT, data TEXT NOT NULL,
                PRIMARY KEY (kind, pos)
            );
            CREATE TABLE catalog (
                category TEXT NOT NULL, pos INTEGER NOT NULL, id TEXT, data TEXT NOT NULL,
                PRIMARY KEY (category, pos)
            );
            CREATE INDEX idx_entities_id ON entities (kind, id);
            CREATE INDEX idx_catalog_id ON catalog (id);
            """
        )
        catalog = data.get("catalog") or {}
        con.executemany(
            "INSERT INTO meta (key, value) VALUES (?, ?)",
            [
                ("_meta", _dumps(data.get("_meta", {}))),
                ("categories", _dumps(data.get("categories", []))),
                ("catalog_categories", _dumps(list(catalog.keys()))),
            ],
        )
        for kind, id_key in _ENTITY_KINDS.items():
            rows = data.get(kind) or []
            con.executemany(
                "INSERT INTO entities (kind, pos, id, data) VALUES (?, ?, ?, ?)",
                [
                    (kind, i, str(r.get(id_key)) if id_key and r.get(id_key) else None, _dumps(r))
                    for i, r in enumerate(rows)
                    if isinstance(r, dict)
                ],
            )
        for category, rows in catalog.items():
            con.executemany(
                "INSERT INTO catalog (category, pos, id, data) VALUES (?, ?, ?, ?)",
                [
                    (category, i, str(r.get("catalog_id")) if r.get("catalog_id") else None, _dumps(r))
                    for i, r in enumerate(rows)
                    if isinstance(r, dict)
                ],
            )
        con.commit()
        con.execute("VACUUM")
        con.commit()
    finally:
        con.close()

    counts = {k: len(data.get(k) or []) for k in _ENTITY_KINDS}
    counts["catalog"] = sum(len(v) for v in catalog.values())
    print(f"Built {DB_PATH} ({DB_PATH.stat().st_size:,} bytes) — {counts}")


if __name__ == "__main__":
    build()
