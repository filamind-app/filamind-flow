"""Webcam discovery + same-origin snapshot proxy.

The panel is served on its own port; the printer's webcam is served by the host's main web
server (``/webcam/…`` on port 80), which the panel's nginx does not proxy. So the browser can't
reach the camera at the panel's origin directly. This service lets the backend (which *is* on the
host) fetch the snapshot and hand it back through ``/api/camera/snapshot`` — same origin as the
panel, no host/port assumptions in the build.

Pure URL helpers are unit-testable; the snapshot fetch needs a live host.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit

import httpx

from app.services.moonraker_client import MoonrakerClient

#: Snapshot fetches are small JPEGs from the local host — keep the timeout short.
_SNAPSHOT_TIMEOUT_S = 10.0


class CameraUnavailable(RuntimeError):
    """Raised when no usable webcam (or snapshot URL) is configured."""


def host_root(moonraker_url: str) -> str:
    """The host's web root for webcam URLs.

    Webcam paths from Moonraker are relative to the host's main web server (port 80), not
    Moonraker's own port — so drop the port from ``moonraker_url`` and keep scheme + host.
    """
    parts = urlsplit(moonraker_url)
    scheme = parts.scheme or "http"
    host = parts.hostname or "localhost"
    return f"{scheme}://{host}"


def resolve_url(moonraker_url: str, path_or_url: str) -> str:
    """Absolute, host-reachable URL for a (possibly relative) webcam path."""
    candidate = (path_or_url or "").strip()
    if candidate.startswith(("http://", "https://")):
        return candidate
    if not candidate.startswith("/"):
        candidate = "/" + candidate
    return host_root(moonraker_url) + candidate


def _enabled(cam: dict[str, Any]) -> bool:
    return bool(cam.get("enabled", True))


async def list_cameras(client: MoonrakerClient) -> list[dict[str, Any]]:
    """Enabled webcams as ``{name, service, snapshot_url, stream_url}`` (raw URLs as configured)."""
    cams = await client.list_webcams()
    out: list[dict[str, Any]] = []
    for cam in cams:
        if not _enabled(cam):
            continue
        out.append(
            {
                "name": str(cam.get("name") or "camera"),
                "service": str(cam.get("service") or ""),
                "snapshot_url": str(cam.get("snapshot_url") or ""),
                "stream_url": str(cam.get("stream_url") or ""),
            }
        )
    return out


def pick(cameras: list[dict[str, Any]], name: str | None) -> dict[str, Any] | None:
    """The named camera (case-insensitive), else the first enabled one, else None."""
    if not cameras:
        return None
    if name:
        needle = name.strip().lower()
        for cam in cameras:
            if str(cam.get("name", "")).lower() == needle:
                return cam
    return cameras[0]


async def snapshot(
    moonraker_url: str, client: MoonrakerClient, name: str | None = None
) -> tuple[bytes, str]:
    """Fetch one JPEG snapshot for the named (or default) webcam.

    Returns ``(image_bytes, content_type)``.

    Raises:
        CameraUnavailable: if no webcam (or no snapshot URL) is configured.
        httpx.HTTPError: if the host webcam endpoint is unreachable or errors.
    """
    cam = pick(await list_cameras(client), name)
    if cam is None:
        raise CameraUnavailable("No webcam is configured on this printer.")
    if not cam["snapshot_url"]:
        raise CameraUnavailable(f"Webcam '{cam['name']}' has no snapshot URL configured.")
    url = resolve_url(moonraker_url, cam["snapshot_url"])
    async with httpx.AsyncClient(timeout=_SNAPSHOT_TIMEOUT_S) as http:
        response = await http.get(url)
        response.raise_for_status()
    content_type = response.headers.get("content-type", "image/jpeg")
    return response.content, content_type
