"""Known-Good Packs: snapshot the printer's config files and restore them later (gated)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response

from app.config import Settings, get_settings
from app.models.schemas import (
    KgpCreateRequest,
    KgpDetail,
    KgpList,
    KgpPack,
    KgpRestoreResult,
)
from app.services import known_good_pack

router = APIRouter(prefix="/kgp", tags=["kgp"])


@router.get("", response_model=KgpList)
async def list_packs(settings: Settings = Depends(get_settings)) -> KgpList:
    """All saved known-good packs (newest first)."""
    return KgpList(packs=[KgpPack(**p) for p in known_good_pack.list_packs(settings.data_dir)])


@router.post("", response_model=KgpPack)
async def create_pack(req: KgpCreateRequest, settings: Settings = Depends(get_settings)) -> KgpPack:
    """Snapshot every live config file into a new pack (read-only on the printer)."""
    meta = await known_good_pack.create_pack(settings.data_dir, settings.moonraker_url, req.label)
    return KgpPack(**meta)


@router.get("/{pack_id}", response_model=KgpDetail)
async def pack_detail(pack_id: str, settings: Settings = Depends(get_settings)) -> KgpDetail:
    """A pack's summary + the config files it holds."""
    try:
        known_good_pack.validate_pack_id(pack_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    pack = next(
        (p for p in known_good_pack.list_packs(settings.data_dir) if p.get("id") == pack_id), None
    )
    if pack is None:
        raise HTTPException(status_code=404, detail="pack not found")
    return KgpDetail(**pack, files=known_good_pack.pack_files(settings.data_dir, pack_id))


@router.post("/{pack_id}/restore", response_model=KgpRestoreResult)
async def restore_pack(
    pack_id: str, settings: Settings = Depends(get_settings)
) -> KgpRestoreResult:
    """Write a pack's files back to the printer (gated; a restart is needed to apply)."""
    try:
        known_good_pack.validate_pack_id(pack_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    result = await known_good_pack.restore_pack(settings.data_dir, settings.moonraker_url, pack_id)
    return KgpRestoreResult(**result)


@router.delete("/{pack_id}", status_code=204)
async def delete_pack(pack_id: str, settings: Settings = Depends(get_settings)) -> Response:
    """Delete a pack."""
    try:
        known_good_pack.validate_pack_id(pack_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not known_good_pack.delete_pack(settings.data_dir, pack_id):
        raise HTTPException(status_code=404, detail="pack not found")
    return Response(status_code=204)
