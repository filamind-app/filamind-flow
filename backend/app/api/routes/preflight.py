"""Pre-print readiness gate route (read-only)."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.config import Settings, get_settings
from app.models.schemas import PreflightResult
from app.services import preflight_service

router = APIRouter(prefix="/preflight", tags=["preflight"])


@router.get("", response_model=PreflightResult)
async def get_preflight(settings: Settings = Depends(get_settings)) -> PreflightResult:
    """Read-only readiness checks before starting a print."""
    result = await preflight_service.preflight(settings.moonraker_url)
    return PreflightResult(**result)
