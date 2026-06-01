from __future__ import annotations

from fastapi import APIRouter

from app.api.routes import firmware, health, moonraker, shaper

api_router = APIRouter(prefix="/api")
api_router.include_router(health.router)
api_router.include_router(moonraker.router)
api_router.include_router(firmware.router)
api_router.include_router(shaper.router)
