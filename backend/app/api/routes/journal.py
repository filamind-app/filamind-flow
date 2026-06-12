"""Printer-journal endpoint — one merged timeline of flashes, config saves and tuning runs."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from app.config import Settings, get_settings
from app.services import journal
from app.services.moonraker_client import MoonrakerClient

router = APIRouter(prefix="/journal", tags=["journal"])


@router.get("")
async def get_journal(settings: Settings = Depends(get_settings)) -> dict[str, Any]:
    """Everything that happened to this machine, newest first: firmware flashes, config saves
    (from the backup snapshots), and tuning runs (from the input-shaper archive)."""
    client = MoonrakerClient(settings.moonraker_url)
    return await journal.gather_journal(client, settings.data_dir)
