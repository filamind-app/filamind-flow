"""Linux host control endpoints — read (and, in later phases, change) the printer host's OS state.

Phase 1: a read-only health + OS-state monitor (CPU / temp / memory / disk / network / time /
locale). The system-changing actions (services, cleanup, time/locale/hostname/power) land in later
phases behind confirmations and the host's passwordless-sudo rule.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from app.config import Settings, get_settings
from app.services import host_control_service

router = APIRouter(prefix="/host", tags=["host"])


@router.get("/monitor")
async def host_monitor(settings: Settings = Depends(get_settings)) -> dict[str, Any]:
    """Read-only snapshot of host health + OS state for the Host Control widget."""
    return await host_control_service.monitor(settings.data_dir)
