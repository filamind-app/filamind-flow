from __future__ import annotations

from fastapi import APIRouter

from app.api.routes import (
    camera,
    config,
    doctor,
    drivers,
    firmware,
    guard,
    hardware,
    health,
    journal,
    macro,
    maxflow,
    moonraker,
    overview,
    reference,
    screen,
    shaper,
    tasks,
    topology,
)

api_router = APIRouter(prefix="/api")
api_router.include_router(health.router)
api_router.include_router(guard.router)
api_router.include_router(doctor.router)
api_router.include_router(overview.router)
api_router.include_router(tasks.router)
api_router.include_router(journal.router)
api_router.include_router(moonraker.router)
api_router.include_router(firmware.router)
api_router.include_router(shaper.router)
api_router.include_router(drivers.router)
api_router.include_router(reference.router)
api_router.include_router(config.router)
api_router.include_router(maxflow.router)
api_router.include_router(topology.router)
api_router.include_router(macro.router)
api_router.include_router(hardware.router)
api_router.include_router(camera.router)
api_router.include_router(screen.router)
