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
    haystacks: list[str] | None = None,
) -> dict[str, Any]:
    """Filter ``items`` by query / category / manufacturer and return one page.

    ``q`` matches anywhere (manufacturer, name, category, sub-section, or any spec value).
    ``category`` is an exact (case-insensitive) match; ``manufacturer`` is a substring match.
    ``haystacks`` (optional, aligned to ``items`` by index) supplies precomputed lowercased
    search strings so the free-text scan does not rebuild them on every request.
    """
    ql = q.strip().lower()
    cat = category.strip().lower()
    man = manufacturer.strip().lower()
    limit = max(1, min(int(limit), _MAX_LIMIT))
    offset = max(0, int(offset))
    hay_list: list[str] = haystacks or []
    use_hay = len(hay_list) == len(items) and len(hay_list) > 0

    def matches(item: dict[str, Any], idx: int) -> bool:
        if cat and str(item.get("category", "")).lower() != cat:
            return False
        if man and man not in str(item.get("manufacturer", "")).lower():
            return False
        if not ql:
            return True
        hay = hay_list[idx] if use_hay else _haystack(item)
        return ql in hay

    filtered = [it for i, it in enumerate(items) if matches(it, i)]
    page = filtered[offset : offset + limit]
    return {
        "total": len(filtered),
        "count": len(page),
        "offset": offset,
        "limit": limit,
        "items": page,
    }
