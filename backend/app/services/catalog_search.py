"""Generic catalog search — pure filtering/pagination over a category's canonical entities.

Hardware-free. The list endpoint returns lightweight summaries (no copyable config snippet
or full spec sheet); the full record is served by ``GET /api/hardware/catalog/{catalog_id}``.
Backs the Hardware Browser's per-category rich panels.
"""

from __future__ import annotations

from typing import Any

_MAX_LIMIT = 200
_SUMMARY_KEYS = ("catalog_id", "name", "manufacturer", "category", "subsection")


def summarize(entity: dict[str, Any]) -> dict[str, Any]:
    """An entity minus the heavy ``configSnippet`` / full ``specs``."""
    out = {k: entity.get(k) for k in _SUMMARY_KEYS if k in entity}
    specs = entity.get("specs")
    out["specCount"] = len(specs) if isinstance(specs, dict) else 0
    return out


def _haystack(e: dict[str, Any]) -> str:
    specs = e.get("specs", {})
    spec_values = " ".join(str(v) for v in specs.values()) if isinstance(specs, dict) else ""
    return " ".join(
        [
            str(e.get("manufacturer", "")),
            str(e.get("name", "")),
            str(e.get("subsection", "")),
            spec_values,
        ]
    ).lower()


def search(
    entities: list[dict[str, Any]],
    *,
    q: str = "",
    manufacturer: str = "",
    subsection: str = "",
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    """Filter entities by query / manufacturer / sub-type and return one page of summaries."""
    ql = q.strip().lower()
    man = manufacturer.strip().lower()
    sub = subsection.strip().lower()
    limit = max(1, min(int(limit), _MAX_LIMIT))
    offset = max(0, int(offset))

    def matches(e: dict[str, Any]) -> bool:
        if man and man not in str(e.get("manufacturer", "")).lower():
            return False
        if sub and str(e.get("subsection", "")).lower() != sub:
            return False
        return not (ql and ql not in _haystack(e))

    filtered = [e for e in entities if matches(e)]
    page = filtered[offset : offset + limit]
    return {
        "total": len(filtered),
        "count": len(page),
        "offset": offset,
        "limit": limit,
        "entities": [summarize(e) for e in page],
    }
