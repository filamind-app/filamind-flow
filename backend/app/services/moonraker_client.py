from __future__ import annotations

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

    async def get_server_info(self) -> dict[str, object]:
        """Returns Moonraker's ``/server/info`` result payload.

        Raises:
            httpx.HTTPError: if Moonraker is unreachable or returns an error status.
        """
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.get(f"{self._base_url}/server/info")
            response.raise_for_status()
            payload: object = response.json()

        if isinstance(payload, dict):
            result = payload.get("result", payload)
            if isinstance(result, dict):
                return result
        return {}
