"""Material brain - a saved registry of filament profiles (the first-class "material" entity).

Each profile carries the numbers tuning/slicer-sync/maintenance build on: temps, density, and the
key **max volumetric flow** (mm3/s). Persisted as a JSON list under ``<data_dir>/materials.json``
with atomic writes - same shape as ``devices_store`` - so it roams with the printer's data dir.

This is the storage layer only: the flow-vs-hotend-ceiling cross-check and the SET_MATERIAL apply
path build on top of it in later steps.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any

#: Every field a material carries, with its default. Unknown keys are dropped on normalise.
_MATERIAL_DEFAULTS: dict[str, Any] = {
    "id": "",
    "name": "",
    #: Free-form family (PLA / PETG / ABS / ASA / TPU / PC / Nylon / ...).
    "material": "PLA",
    "brand": "",
    "color": "",
    "diameter": 1.75,
    #: g/cm3 - used to convert volumetric flow to mass flow downstream.
    "density": 1.24,
    "nozzle_temp": 210,
    "bed_temp": 60,
    #: mm3/s - the headline tuning value (0 = unmeasured/unknown).
    "max_volumetric_flow": 0.0,
    "notes": "",
}


def slug(name: str) -> str:
    """A filesystem/url-safe id from a display name (``"PolyTerra PLA"`` -> ``"polyterra-pla"``)."""
    s = re.sub(r"[^a-z0-9]+", "-", name.strip().lower()).strip("-")
    return s or "material"


def materials_path(data_dir: str) -> str:
    """The material registry file (``<data_dir>/materials.json``)."""
    return os.path.join(os.path.expanduser(data_dir), "materials.json")


def _normalise(material: dict[str, Any]) -> dict[str, Any]:
    """Returns the material with exactly the known fields, each defaulted."""
    merged = {**_MATERIAL_DEFAULTS, **material}
    return {key: merged[key] for key in _MATERIAL_DEFAULTS}


def read_materials(data_dir: str) -> list[dict[str, Any]]:
    """Returns the saved materials (empty if none / unreadable). Skips id-less rows."""
    try:
        with open(materials_path(data_dir)) as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(data, list):
        return []
    return [_normalise(m) for m in data if isinstance(m, dict) and m.get("id")]


def write_materials(data_dir: str, materials: list[dict[str, Any]]) -> None:
    """Atomically writes the material registry."""
    path = materials_path(data_dir)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.tmp"
    with open(tmp, "w") as handle:
        json.dump([_normalise(m) for m in materials], handle, indent=2)
    os.replace(tmp, path)


def get_material(data_dir: str, material_id: str) -> dict[str, Any] | None:
    """Returns a single material by id, or None."""
    for material in read_materials(data_dir):
        if material["id"] == material_id:
            return material
    return None


def save_material(
    data_dir: str, material: dict[str, Any], old_id: str | None = None
) -> dict[str, Any]:
    """Inserts or updates a material, matched by ``old_id`` (for renames) or its id.

    A blank id is derived from the name; collisions get a numeric suffix so two
    same-named materials stay distinct.
    """
    record = _normalise(material)
    auto_id = not record["id"]  # a blank id means "derive one" (and de-collide if needed)
    if auto_id:
        record["id"] = slug(str(record["name"]))
    materials = read_materials(data_dir)
    ids = {m["id"] for m in materials}
    if auto_id and record["id"] in ids:
        base, n = record["id"], 2
        while f"{base}-{n}" in ids:
            n += 1
        record["id"] = f"{base}-{n}"
    key = old_id or record["id"]
    for index, existing in enumerate(materials):
        if existing["id"] == key:
            materials[index] = record
            break
    else:
        materials.append(record)
    write_materials(data_dir, materials)
    return record


def remove_material(data_dir: str, material_id: str) -> bool:
    """Removes a material from the registry. Returns False if it was not present."""
    materials = read_materials(data_dir)
    kept = [m for m in materials if m["id"] != material_id]
    if len(kept) == len(materials):
        return False
    write_materials(data_dir, kept)
    return True
