"""Material brain - CRUD for the saved filament profiles (the first-class 'material' entity).

Storage only at this stage: the flow-vs-hotend-ceiling cross-check and the SET_MATERIAL apply
path build on top in later steps. SUITE-only at the host level (a flow-A innovation).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.config import Settings, get_settings
from app.models.schemas import MaterialProfile
from app.services import material_store

router = APIRouter(prefix="/material", tags=["material"])


@router.get("", response_model=list[MaterialProfile])
async def list_materials(settings: Settings = Depends(get_settings)) -> list[MaterialProfile]:
    """Every saved filament profile (newest writes last)."""
    return [MaterialProfile(**m) for m in material_store.read_materials(settings.data_dir)]


@router.post("", response_model=MaterialProfile)
async def save_material(
    profile: MaterialProfile,
    old_id: str | None = None,
    settings: Settings = Depends(get_settings),
) -> MaterialProfile:
    """Insert or update a profile. A blank id is derived from the name; ``old_id`` renames."""
    record = material_store.save_material(settings.data_dir, profile.model_dump(), old_id)
    return MaterialProfile(**record)


@router.delete("/{material_id}")
async def delete_material(
    material_id: str, settings: Settings = Depends(get_settings)
) -> dict[str, bool]:
    """Remove a profile by id (404 if it was not present)."""
    if not material_store.remove_material(settings.data_dir, material_id):
        raise HTTPException(status_code=404, detail="material not found")
    return {"ok": True}
