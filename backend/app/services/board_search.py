"""Board-DB search — pure filtering/pagination over the canonical board entities.

Hardware-free. The list endpoint returns lightweight summaries (no per-port detail);
the full ``ports[]`` record is served by ``GET /api/boards/{board_id}``. Backs the
Board Topology link and the Hardware Browser's board section.
"""

from __future__ import annotations

from typing import Any

_MAX_LIMIT = 200

#: Keys included in a board summary (everything except the heavy ``ports`` list).
_SUMMARY_KEYS = (
    "board_id",
    "manufacturer",
    "model",
    "display_name",
    "boardClass",
    "portsSummary",
    "linkStatus",
)


def summarize(board: dict[str, Any]) -> dict[str, Any]:
    """A board record minus the heavy ``ports`` list, plus a port count."""
    out = {k: board.get(k) for k in _SUMMARY_KEYS if k in board}
    ports = board.get("ports")
    out["portCount"] = len(ports) if isinstance(ports, list) else 0
    return out


def _haystack(b: dict[str, Any]) -> str:
    specs = b.get("specs", {})
    spec_values = " ".join(str(v) for v in specs.values()) if isinstance(specs, dict) else ""
    aliases = " ".join(str(a) for a in b.get("aliases", []) if isinstance(b.get("aliases"), list))
    return " ".join(
        [
            str(b.get("manufacturer", "")),
            str(b.get("model", "")),
            str(b.get("display_name", "")),
            aliases,
            spec_values,
        ]
    ).lower()


def search(
    boards: list[dict[str, Any]],
    *,
    q: str = "",
    manufacturer: str = "",
    board_class: str = "",
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    """Filter boards by query / manufacturer / class and return one page of summaries."""
    ql = q.strip().lower()
    man = manufacturer.strip().lower()
    cls = board_class.strip().lower()
    limit = max(1, min(int(limit), _MAX_LIMIT))
    offset = max(0, int(offset))

    def matches(b: dict[str, Any]) -> bool:
        if man and man not in str(b.get("manufacturer", "")).lower():
            return False
        if cls and str(b.get("boardClass", "")).lower() != cls:
            return False
        return not (ql and ql not in _haystack(b))

    filtered = [b for b in boards if matches(b)]
    page = filtered[offset : offset + limit]
    return {
        "total": len(filtered),
        "count": len(page),
        "offset": offset,
        "limit": limit,
        "boards": [summarize(b) for b in page],
    }
