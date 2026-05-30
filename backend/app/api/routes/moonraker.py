from __future__ import annotations

import httpx
from fastapi import APIRouter, Depends

from app.config import Settings, get_settings
from app.models.schemas import MoonrakerStatus
from app.services.moonraker_client import MoonrakerClient

router = APIRouter(prefix="/moonraker", tags=["moonraker"])


@router.get("/status", response_model=MoonrakerStatus)
async def moonraker_status(settings: Settings = Depends(get_settings)) -> MoonrakerStatus:
    """Backend-side reachability probe for the configured Moonraker instance."""
    client = MoonrakerClient(settings.moonraker_url)
    try:
        info = await client.get_server_info()
    except httpx.HTTPError as exc:
        return MoonrakerStatus(reachable=False, moonraker_url=client.base_url, detail=str(exc))

    klippy_state = info.get("klippy_state")
    return MoonrakerStatus(
        reachable=True,
        moonraker_url=client.base_url,
        klippy_state=str(klippy_state) if klippy_state is not None else None,
    )
