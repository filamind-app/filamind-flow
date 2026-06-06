"""Hardware-DB search — pure filtering/pagination over the reference component list.

Hardware-free: filters the curated component rows by free-text query, category and
manufacturer, and paginates. Backs the Hardware Browser widget's ``/api/hardware`` route.
"""

from __future__ import annotations

from typing import Any

#: Hard cap so a request can never ask for the whole 3,600-row table at once.
_MAX_LIMIT = 200


def _haystack(item: dict[str, Any]) -> str:
    specs = item.get("specs", {})
    spec_values = " ".join(str(v) for v in specs.values()) if isinstance(specs, dict) else ""
    return " ".join(
        [
            str(item.get("manufacturer", "")),
            str(item.get("name", "")),
            str(item.get("category", "")),
            str(item.get("subsection", "")),
            spec_values,
        ]
    ).lower()


def search(
    items: list[dict[str, Any]],
    *,
    q: str = "",
    category: str = "",
    manufacturer: str = "",
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    """Filter ``items`` by query / category / manufacturer and return one page.

    ``q`` matches anywhere (manufacturer, name, category, sub-section, or any spec value).
    ``category`` is an exact (case-insensitive) match; ``manufacturer`` is a substring match.
    """
    ql = q.strip().lower()
    cat = category.strip().lower()
    man = manufacturer.strip().lower()
    limit = max(1, min(int(limit), _MAX_LIMIT))
    offset = max(0, int(offset))

    def matches(item: dict[str, Any]) -> bool:
        if cat and str(item.get("category", "")).lower() != cat:
            return False
        if man and man not in str(item.get("manufacturer", "")).lower():
            return False
        return not (ql and ql not in _haystack(item))

    filtered = [it for it in items if matches(it)]
    page = filtered[offset : offset + limit]
    return {
        "total": len(filtered),
        "count": len(page),
        "offset": offset,
        "limit": limit,
        "items": page,
    }
