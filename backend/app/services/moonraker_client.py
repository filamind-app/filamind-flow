from __future__ import annotations

from typing import Any
from urllib.parse import quote

import httpx


class MoonrakerClient:
    """Minimal async client for Moonraker's HTTP API (server-side calls only).

    The browser talks to Moonraker directly for live data; this client exists for
    privileged or aggregated operations that belong on the server side.
    """

    def __init__(self, base_url: str, *, timeout: float = 5.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    @property
    def base_url(self) -> str:
        return self._base_url

    async def _get(self, path: str) -> dict[str, Any]:
        """GETs a Moonraker endpoint and returns its ``result`` object.

        Raises:
            httpx.HTTPError: if Moonraker is unreachable or returns an error status.
        """
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.get(f"{self._base_url}{path}")
            response.raise_for_status()
            payload: object = response.json()
        if isinstance(payload, dict):
            result = payload.get("result", payload)
            if isinstance(result, dict):
                return result
        return {}

    async def get_server_info(self) -> dict[str, Any]:
        """Moonraker ``/server/info`` (klippy_state, components, ...)."""
        return await self._get("/server/info")

    async def get_printer_info(self) -> dict[str, Any]:
        """Klippy ``/printer/info`` (software_version, hostname, state)."""
        return await self._get("/printer/info")

    async def list_objects(self) -> list[str]:
        """Names of all available printer objects."""
        result = await self._get("/printer/objects/list")
        objects = result.get("objects", [])
        return [str(o) for o in objects] if isinstance(objects, list) else []

    async def query_objects(self, objects: list[str]) -> dict[str, Any]:
        """Queries the given printer objects, returning their ``status`` map."""
        if not objects:
            return {}
        query = "&".join(quote(name) for name in objects)
        result = await self._get(f"/printer/objects/query?{query}")
        status = result.get("status", {})
        return status if isinstance(status, dict) else {}

    async def query_endstops(self) -> dict[str, Any]:
        """Live endstop trigger state via ``/printer/query_endstops/status``.

        This actively triggers a query (the ``query_endstops`` object is otherwise stale
        until ``QUERY_ENDSTOPS`` runs). It's a motion-free MCU read but uses the g-code
        mutex, so call it on demand, not in a fast poll. Returns ``{axis: "open"|"TRIGGERED"}``.
        """
        result = await self._get("/printer/query_endstops/status")
        return result if isinstance(result, dict) else {}

    async def gcode_store(self, count: int = 20) -> list[dict[str, Any]]:
        """Recent G-code console responses via ``/server/gcode_store`` (oldest first).

        Each entry is ``{"message": str, "time": float, "type": str}``. Used to read
        the output of a command (e.g. ``MEASURE_AXES_NOISE``) that prints its result
        to the console rather than returning it.
        """
        result = await self._get(f"/server/gcode_store?count={count}")
        store = result.get("gcode_store", [])
        return [e for e in store if isinstance(e, dict)] if isinstance(store, list) else []

    async def run_gcode(self, script: str) -> None:
        """Runs a G-code script via ``/printer/gcode/script``.

        The request blocks until Klipper finishes the command, so a long-running
        macro (e.g. ``TEST_RESONANCES``) needs this client created with a
        correspondingly long ``timeout``.

        Raises:
            httpx.HTTPError: if Moonraker is unreachable or the command errors.
        """
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(
                f"{self._base_url}/printer/gcode/script", params={"script": script}
            )
            response.raise_for_status()
