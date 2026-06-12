"""Machine Doctor endpoint — one scan over every read-only analyzer, one graded report."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from app.config import Settings, get_settings
from app.services import machine_doctor

router = APIRouter(prefix="/doctor", tags=["doctor"])


@router.get("/scan")
async def doctor_scan(settings: Settings = Depends(get_settings)) -> dict[str, Any]:
    """Run the full read-only scan (pins, driver values, drift, project lint, firmware sync,
    hardware changes, install health) and return the A-F graded report. Read-only — runs
    nothing on the printer; an unreachable analyzer degrades to ``status: "unknown"``."""
    return await machine_doctor.run_scan(settings)
