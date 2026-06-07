"""Host-DB search — pure filtering/pagination over the canonical host-computer entities.

Hardware-free. The list endpoint returns lightweight summaries (no copyable config snippet
or full spec sheet); the full record is served by ``GET /api/hardware/hosts/{host_id}``.
Backs the Hardware Browser's Hosts section.
"""

from __future__ import annotations

from typing import Any

_MAX_LIMIT = 200

#: Keys included in a host summary (everything except the heavy snippet + full specs).
_SUMMARY_KEYS = (
    "host_id",
    "name",
    "manufacturer",
    "kind",
    "soc",
    "ram",
    "klipperOs",
    "klipperOpen",
)


def summarize(host: dict[str, Any]) -> dict[str, Any]:
    """A host record minus the heavy ``configSnippet`` / full ``specs``."""
    out = {k: host.get(k) for k in _SUMMARY_KEYS if k in host}
    specs = host.get("specs")
    out["specCount"] = len(specs) if isinstance(specs, dict) else 0
    return out


def _haystack(h: dict[str, Any]) -> str:
    specs = h.get("specs", {})
    spec_values = " ".join(str(v) for v in specs.values()) if isinstance(specs, dict) else ""
    return " ".join(
        [
            str(h.get("manufacturer", "")),
            str(h.get("name", "")),
            str(h.get("soc", "")),
            str(h.get("kind", "")),
            spec_values,
        ]
    ).lower()


def search(
    hosts: list[dict[str, Any]],
    *,
    q: str = "",
    manufacturer: str = "",
    kind: str = "",
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    """Filter hosts by query / manufacturer / kind and return one page of summaries."""
    ql = q.strip().lower()
    man = manufacturer.strip().lower()
    knd = kind.strip().lower()
    limit = max(1, min(int(limit), _MAX_LIMIT))
    offset = max(0, int(offset))

    def matches(h: dict[str, Any]) -> bool:
        if man and man not in str(h.get("manufacturer", "")).lower():
            return False
        if knd and str(h.get("kind", "")).lower() != knd:
            return False
        return not (ql and ql not in _haystack(h))

    filtered = [h for h in hosts if matches(h)]
    page = filtered[offset : offset + limit]
    return {
        "total": len(filtered),
        "count": len(page),
        "offset": offset,
        "limit": limit,
        "hosts": [summarize(h) for h in page],
    }
