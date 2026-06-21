"""Material brain - CRUD for the saved filament profiles (the first-class 'material' entity).

Storage only at this stage: the flow-vs-hotend-ceiling cross-check and the SET_MATERIAL apply
path build on top in later steps. SUITE-only at the host level (a flow-A innovation).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.config import Settings, get_settings
from app.models.schemas import MaterialFlowCheck, MaterialProfile
from app.services import material_service, material_store, max_flow_store

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


@router.get("/{material_id}/flow-check", response_model=MaterialFlowCheck)
async def material_flow_check(
    material_id: str,
    hotend: str | None = None,
    settings: Settings = Depends(get_settings),
) -> MaterialFlowCheck:
    """Cross-check the profile's max volumetric flow vs the hotend's catalog ceiling.

    The hotend comes from the ``hotend`` query param, else the last saved Max-Flow run's hotend.
    """
    material = material_store.get_material(settings.data_dir, material_id)
    if material is None:
        raise HTTPException(status_code=404, detail="material not found")
    use_hotend = hotend
    if not use_hotend:
        last = max_flow_store.read_last(settings.data_dir)
        if last:
            use_hotend = last.get("hotend")
    verdict = material_service.check_flow(float(material["max_volumetric_flow"]), use_hotend)
    return MaterialFlowCheck(**verdict)


@router.delete("/{material_id}")
async def delete_material(
    material_id: str, settings: Settings = Depends(get_settings)
) -> dict[str, bool]:
    """Remove a profile by id (404 if it was not present)."""
    if not material_store.remove_material(settings.data_dir, material_id):
        raise HTTPException(status_code=404, detail="material not found")
    return {"ok": True}
