"""Webcam endpoints — discovery + a same-origin snapshot proxy.

The panel's nginx doesn't proxy the host's ``/webcam/`` path, so the browser can't load the
camera at the panel origin. ``GET /api/camera/snapshot`` fetches the JPEG host-side and returns
it through the API (same origin as the panel). ``GET /api/camera/list`` reports what's available
so the UI only shows a camera when one is configured.
"""

from __future__ import annotations

from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Response

from app.config import Settings, get_settings
from app.services import camera_service
from app.services.moonraker_client import MoonrakerClient

router = APIRouter(prefix="/camera", tags=["camera"])


@router.get("/list")
async def camera_list(settings: Settings = Depends(get_settings)) -> dict[str, Any]:
    """Configured webcams (empty when none / Moonraker unreachable — the UI then hides the view)."""
    client = MoonrakerClient(settings.moonraker_url)
    try:
        cameras = await camera_service.list_cameras(client)
    except httpx.HTTPError:
        cameras = []
    return {
        "available": bool(cameras),
        "cameras": [{"name": c["name"], "service": c["service"]} for c in cameras],
    }


@router.get("/snapshot")
async def camera_snapshot(
    name: str | None = None, settings: Settings = Depends(get_settings)
) -> Response:
    """Proxy one JPEG snapshot of the named (or default) webcam, same-origin and uncached."""
    client = MoonrakerClient(settings.moonraker_url, timeout=10.0)
    try:
        content, content_type = await camera_service.snapshot(settings.moonraker_url, client, name)
    except camera_service.CameraUnavailable as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"camera fetch failed: {exc}") from exc
    # Defense-in-depth: only ever serve an image type same-origin, and never sniff (the upstream
    # content-type comes from the host webcam, not the client, but don't trust it blindly).
    if not content_type.lower().startswith("image/"):
        content_type = "application/octet-stream"
    return Response(
        content=content,
        media_type=content_type,
        headers={"Cache-Control": "no-store, max-age=0", "X-Content-Type-Options": "nosniff"},
    )
