from __future__ import annotations

from fastapi import APIRouter

from app.api.routes import drivers, firmware, health, moonraker, reference, shaper

api_router = APIRouter(prefix="/api")
api_router.include_router(health.router)
api_router.include_router(moonraker.router)
api_router.include_router(firmware.router)
api_router.include_router(shaper.router)
api_router.include_router(drivers.router)
api_router.include_router(reference.router)
