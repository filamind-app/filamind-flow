"""Motor-DB search — pure filtering/pagination over the canonical stepper-motor entities.

Hardware-free. The list endpoint returns lightweight summaries (no copyable config snippet
or full spec sheet); the full record is served by ``GET /api/hardware/motors/{motor_id}``.
Backs the Hardware Browser's Motors section.
"""

from __future__ import annotations

from typing import Any

_MAX_LIMIT = 200

#: Keys included in a motor summary (everything except the heavy snippet + full specs).
_SUMMARY_KEYS = (
    "motor_id",
    "name",
    "manufacturer",
    "nema",
    "stepAngle",
    "ratedCurrent",
    "holdingTorque",
    "recommendedRunCurrent",
)


def summarize(motor: dict[str, Any]) -> dict[str, Any]:
    """A motor record minus the heavy ``configSnippet`` / full ``specs``."""
    out = {k: motor.get(k) for k in _SUMMARY_KEYS if k in motor}
    presets = motor.get("currentPresets")
    out["presetCount"] = len(presets) if isinstance(presets, list) else 0
    return out


def _haystack(m: dict[str, Any]) -> str:
    specs = m.get("specs", {})
    spec_values = " ".join(str(v) for v in specs.values()) if isinstance(specs, dict) else ""
    aliases = " ".join(str(a) for a in m.get("aliases", []) if isinstance(m.get("aliases"), list))
    return " ".join(
        [
            str(m.get("manufacturer", "")),
            str(m.get("name", "")),
            str(m.get("nema", "")),
            aliases,
            spec_values,
        ]
    ).lower()


def search(
    motors: list[dict[str, Any]],
    *,
    q: str = "",
    manufacturer: str = "",
    nema: str = "",
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    """Filter motors by query / manufacturer / NEMA size and return one page of summaries."""
    ql = q.strip().lower()
    man = manufacturer.strip().lower()
    nm = nema.strip().lower()
    limit = max(1, min(int(limit), _MAX_LIMIT))
    offset = max(0, int(offset))

    def matches(m: dict[str, Any]) -> bool:
        if man and man not in str(m.get("manufacturer", "")).lower():
            return False
        if nm and nm not in str(m.get("nema", "")).lower():
            return False
        return not (ql and ql not in _haystack(m))

    filtered = [m for m in motors if matches(m)]
    page = filtered[offset : offset + limit]
    return {
        "total": len(filtered),
        "count": len(page),
        "offset": offset,
        "limit": limit,
        "motors": [summarize(m) for m in page],
    }
