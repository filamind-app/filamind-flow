#!/usr/bin/env python3
"""Bake the stepper-motor database CSV into the JSON the backend ships.

Reads ``app/data/sources/stepper_motors.csv`` (the vendored motor database — 5
datasheet parameters per motor) and writes ``app/data/motor_catalog.json``, which
``motor_catalog.py`` loads at runtime to back the Motor Drivers motor picker.

Run from anywhere:  python backend/scripts/bake_motor_catalog.py
Re-run whenever the source CSV changes, then commit the regenerated JSON.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

_DATA = Path(__file__).resolve().parent.parent / "app" / "data"
_SOURCE = _DATA / "sources" / "stepper_motors.csv"
_OUT = _DATA / "motor_catalog.json"

#: CSV column -> output key (and whether it's a float).
_FLOAT_FIELDS = ("resistance_ohm", "inductance_H", "holding_torque_Nm", "max_current_A")


def _num(value: str) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int(value: str) -> int | None:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def bake() -> dict[str, object]:
    motors: list[dict[str, object]] = []
    with _SOURCE.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            model = (row.get("model") or "").strip()
            if not model:
                continue
            motors.append(
                {
                    "manufacturer": (row.get("manufacturer") or "").strip(),
                    "model": model,
                    "resistance_ohm": _num(row.get("resistance_ohm", "")),
                    "inductance_H": _num(row.get("inductance_H", "")),
                    "holding_torque_Nm": _num(row.get("holding_torque_Nm", "")),
                    "max_current_A": _num(row.get("max_current_A", "")),
                    "steps_per_rev": _int(row.get("steps_per_rev", "")) or 200,
                    "source": (row.get("source") or "").strip(),
                }
            )
    motors.sort(key=lambda m: (str(m["manufacturer"]).lower(), str(m["model"]).lower()))
    manufacturers = sorted({str(m["manufacturer"]) for m in motors if m["manufacturer"]})
    return {
        "source": "Baked from app/data/sources/stepper_motors.csv "
        "(hardware-database/01-stepper-motors) by scripts/bake_motor_catalog.py.",
        "count": len(motors),
        "manufacturers": manufacturers,
        "motors": motors,
    }


def main() -> None:
    catalog = bake()
    _OUT.write_text(json.dumps(catalog, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(
        f"wrote {_OUT} — {catalog['count']} motors, {len(catalog['manufacturers'])} manufacturers"
    )


if __name__ == "__main__":
    main()
