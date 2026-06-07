"""Driver-DB search — pure filtering/pagination over the canonical stepper-driver entities.

Hardware-free. The list endpoint returns lightweight summaries (no copyable config snippet
or full spec sheet); the full record is served by ``GET /api/hardware/drivers/{driver_id}``.
Backs the Hardware Browser's Drivers section.
"""

from __future__ import annotations

from typing import Any

_MAX_LIMIT = 200

#: Keys included in a driver summary (everything except the heavy snippet + full specs).
_SUMMARY_KEYS = (
    "driver_id",
    "name",
    "manufacturer",
    "chip",
    "interface",
    "klipperSupported",
    "klipperSection",
    "sensorless",
)


def summarize(driver: dict[str, Any]) -> dict[str, Any]:
    """A driver record minus the heavy ``configSnippet`` / full ``specs``, plus a spec count."""
    out = {k: driver.get(k) for k in _SUMMARY_KEYS if k in driver}
    specs = driver.get("specs")
    out["specCount"] = len(specs) if isinstance(specs, dict) else 0
    return out


def _haystack(d: dict[str, Any]) -> str:
    specs = d.get("specs", {})
    spec_values = " ".join(str(v) for v in specs.values()) if isinstance(specs, dict) else ""
    aliases = " ".join(str(a) for a in d.get("aliases", []) if isinstance(d.get("aliases"), list))
    return " ".join(
        [
            str(d.get("manufacturer", "")),
            str(d.get("name", "")),
            str(d.get("chip", "")),
            aliases,
            spec_values,
        ]
    ).lower()


def search(
    drivers: list[dict[str, Any]],
    *,
    q: str = "",
    manufacturer: str = "",
    klipper_only: bool = False,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    """Filter drivers by query / manufacturer / Klipper-support and return one page of summaries."""
    ql = q.strip().lower()
    man = manufacturer.strip().lower()
    limit = max(1, min(int(limit), _MAX_LIMIT))
    offset = max(0, int(offset))

    def matches(d: dict[str, Any]) -> bool:
        if man and man not in str(d.get("manufacturer", "")).lower():
            return False
        if klipper_only and not d.get("klipperSupported"):
            return False
        return not (ql and ql not in _haystack(d))

    filtered = [d for d in drivers if matches(d)]
    page = filtered[offset : offset + limit]
    return {
        "total": len(filtered),
        "count": len(page),
        "offset": offset,
        "limit": limit,
        "drivers": [summarize(d) for d in page],
    }
