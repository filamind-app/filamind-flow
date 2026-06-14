#!/usr/bin/env python3
"""Apply a community catalog submission to the hardware database (maintainer-only).

A user submits a new part from the app (Hardware Browser → Suggest a part), which opens a GitHub
issue containing a JSON fragment. After reviewing it, a maintainer runs this tool to merge that
fragment into the curated ``hardware.json`` (kept locally, git-ignored) and rebuild the shipped
``hardware.sqlite``:

    python scripts/apply_submission.py fragment.json          # validate + merge + rebuild
    python scripts/apply_submission.py - < fragment.json      # read from stdin
    python scripts/apply_submission.py fragment.json --force   # replace an existing entry by id
    python scripts/apply_submission.py fragment.json --no-build # merge only, skip the sqlite rebuild

The fragment's part type is inferred from its id key (``motor_id`` → motor, ``board_id`` → board, …)
or its shape (a manufacturer carries no id); override with ``--type``. Validation enforces the
required fields and the expected sub-object shapes before anything is written.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

_REF_DIR = (
    Path(__file__).resolve().parent.parent / "backend" / "app" / "data" / "reference"
)
JSON_PATH = _REF_DIR / "hardware.json"

# Part type → required top-level fields.
REQUIRED: dict[str, list[str]] = {
    "motor": ["motor_id", "manufacturer", "name"],
    "driver": ["driver_id", "manufacturer", "name"],
    "host": ["host_id", "manufacturer", "name"],
    "board": ["board_id", "manufacturer", "model"],
    "manufacturer": ["name"],
    "catalog": [
        "catalog_id",
        "category",
        "name",
    ],  # hotends and every other catalog item
}
# Part type → its id key (manufacturers carry none).
ID_KEY: dict[str, str | None] = {
    "motor": "motor_id",
    "driver": "driver_id",
    "host": "host_id",
    "board": "board_id",
    "manufacturer": None,
    "catalog": "catalog_id",
}
# Part type → the canonical entity array it merges into (catalog is special: a dict keyed by category).
TARGET_ARRAY: dict[str, str] = {
    "motor": "motors",
    "driver": "drivers",
    "host": "hosts",
    "board": "boards",
    "manufacturer": "manufacturers",
}
# These top-level fields, when present, must be JSON objects.
_DICT_FIELDS = ("specs", "autotune", "caps", "maxFlow")
# Matches the frontend slugify() output: lowercase alphanumeric segments joined by single hyphens
# (no leading/trailing/double hyphens). Digit-leading slugs are allowed — real part ids have them.
_SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def infer_type(fragment: dict[str, Any]) -> str | None:
    """Best-effort part type from the fragment's shape (id key, then manufacturer-like)."""
    for key, part in (
        ("motor_id", "motor"),
        ("driver_id", "driver"),
        ("board_id", "board"),
        ("host_id", "host"),
        ("catalog_id", "catalog"),  # hotends are catalog items keyed by category
    ):
        if key in fragment:
            return part
    if "name" in fragment and not any(k.endswith("_id") for k in fragment):
        return "manufacturer"
    return None


def validate(part_type: str, fragment: dict[str, Any]) -> list[str]:
    """Return a list of human-readable problems; empty means the fragment is acceptable."""
    errors: list[str] = []
    if part_type not in REQUIRED:
        return [f"unknown part type: {part_type}"]
    for key in REQUIRED[part_type]:
        value = fragment.get(key)
        if value is None or (isinstance(value, str) and not value.strip()):
            errors.append(f"missing required field: {key}")
    for key in _DICT_FIELDS:
        if key in fragment and not isinstance(fragment[key], dict):
            errors.append(f"{key} must be an object")
    if "ports" in fragment and not isinstance(fragment["ports"], list):
        errors.append("ports must be a list")
    id_key = ID_KEY[part_type]
    if id_key:
        slug = fragment.get(id_key)
        if isinstance(slug, str) and slug and not _SLUG_RE.match(slug):
            errors.append(
                f"{id_key} must be a slug (lowercase letters, digits and hyphens)"
            )
    return errors


def _find(bucket: list[Any], pred: Any) -> int | None:
    for i, entry in enumerate(bucket):
        if isinstance(entry, dict) and pred(entry):
            return i
    return None


def merge(
    data: dict[str, Any], part_type: str, fragment: dict[str, Any], *, force: bool
) -> str:
    """Merge the fragment into ``data`` in place. Returns 'added' or 'replaced'. Raises ValueError
    on a duplicate id when ``force`` is False."""
    if part_type == "catalog":
        category = str(fragment.get("category") or "").strip()
        if not category:
            raise ValueError("catalog submission needs a 'category'")
        bucket = data.setdefault("catalog", {}).setdefault(category, [])
        id_key: str | None = "catalog_id"
    else:
        bucket = data.setdefault(TARGET_ARRAY[part_type], [])
        id_key = ID_KEY[part_type]

    if id_key:
        existing = _find(bucket, lambda e: e.get(id_key) == fragment.get(id_key))
        dup_desc = f"{id_key} '{fragment.get(id_key)}'"
    else:  # manufacturer: dedupe by case-insensitive name
        name = str(fragment.get("name", "")).strip().lower()
        existing = _find(
            bucket, lambda e: str(e.get("name", "")).strip().lower() == name
        )
        dup_desc = f"manufacturer '{fragment.get('name')}'"

    if existing is not None:
        if not force:
            raise ValueError(
                f"{dup_desc} already exists — re-run with --force to replace it"
            )
        bucket[existing] = fragment
        return "replaced"
    bucket.append(fragment)
    return "added"


def _rebuild_sqlite() -> None:
    """Regenerate hardware.sqlite via the sibling build script (imported lazily)."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import build_hardware_db  # noqa: PLC0415 — lazy so importing this module never triggers a build

    build_hardware_db.build()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Apply a catalog submission to the hardware DB."
    )
    parser.add_argument("fragment", help="Path to the JSON fragment, or '-' for stdin.")
    parser.add_argument(
        "--type",
        dest="part_type",
        choices=sorted(REQUIRED),
        help="Override the inferred part type.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Replace an existing entry with the same id.",
    )
    parser.add_argument(
        "--no-build", action="store_true", help="Merge only; skip the sqlite rebuild."
    )
    args = parser.parse_args(argv)

    raw = (
        sys.stdin.read()
        if args.fragment == "-"
        else Path(args.fragment).read_text(encoding="utf-8")
    )
    try:
        fragment = json.loads(raw)
    except json.JSONDecodeError as exc:
        return _fail(f"fragment is not valid JSON: {exc}")
    if not isinstance(fragment, dict):
        return _fail("fragment must be a JSON object")

    part_type = args.part_type or infer_type(fragment)
    if not part_type:
        return _fail("could not infer the part type — pass --type")

    problems = validate(part_type, fragment)
    if problems:
        return _fail("invalid submission:\n  - " + "\n  - ".join(problems))

    if not JSON_PATH.exists():
        return _fail(
            f"{JSON_PATH} not found. This is a maintainer tool — it edits the curated, git-ignored "
            "hardware.json, which only maintainers hold locally."
        )
    data = json.loads(JSON_PATH.read_text(encoding="utf-8"))
    try:
        action = merge(data, part_type, fragment, force=args.force)
    except ValueError as exc:
        return _fail(str(exc))

    JSON_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    label = fragment.get(ID_KEY[part_type] or "name") or fragment.get("name")
    print(f"{action} {part_type}: {label}")

    if not args.no_build:
        _rebuild_sqlite()
        print("Rebuilt hardware.sqlite — review the diff and commit it.")
    return 0


def _fail(message: str) -> int:
    print(f"error: {message}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
