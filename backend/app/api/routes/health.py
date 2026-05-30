from __future__ import annotations

from fastapi import APIRouter

from app import __version__
from app.models.schemas import HealthResponse

router = APIRouter(tags=["system"])


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Liveness probe for the FilaMind Flow backend."""
    return HealthResponse(status="ok", service="filamind-flow", version=__version__)
