from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api.router import api_router
from app.config import Settings, get_settings
from app.logging_config import configure_logging
from app.services import reference_data

#: The hardware DB is immutable after load, so its GET responses are safely cacheable;
#: a weak ETag (changes on redeploy) lets browsers skip re-downloading on card re-expand.
_HW_CACHE_CONTROL = "public, max-age=300"

logger = logging.getLogger("filamind")


def create_app(settings: Settings | None = None) -> FastAPI:
    """Application factory.

    Building the app in a function (rather than at import time) keeps it trivial
    to configure and to instantiate fresh in tests.
    """
    settings = settings or get_settings()
    configure_logging(settings.log_level)

    @asynccontextmanager
    async def _lifespan(_app: FastAPI) -> AsyncIterator[None]:  # pragma: no cover - plumbing
        import asyncio

        from app.services import rules_engine

        async def _rules_loop() -> None:
            """Background rules tick - a cheap no-op until the operator enables the engine."""
            prev: dict[str, bool] = {}
            while True:
                try:
                    prev = await rules_engine.tick(settings.data_dir, settings.moonraker_url, prev)
                except Exception:  # never let the loop die on a transient error
                    logger.exception("rules engine tick failed")
                await asyncio.sleep(settings.rules_tick_seconds)

        async def _autoupdate_loop() -> None:
            """Periodic opt-in auto-update; a no-op until the operator enables it in the Setup
            widget. The tick itself enforces the chosen interval and only updates while idle."""
            import time as _time

            from app.services import setup_manager

            while True:
                await asyncio.sleep(900)  # check often; the tick gates on interval + printer-idle
                try:
                    summary = await setup_manager.auto_update_tick(
                        settings.moonraker_url, _time.time()
                    )
                    if summary.get("ran") and summary.get("ok"):
                        logger.info("auto-update applied: %s", summary["ok"])
                except Exception:  # never let the loop die on a transient error
                    logger.exception("auto-update tick failed")

        tasks = [asyncio.create_task(_autoupdate_loop())]
        if settings.rules_tick_seconds > 0:
            tasks.append(asyncio.create_task(_rules_loop()))
        try:
            yield
        finally:
            # Shutdown: stop the background loops + close the pooled connection to Moonraker.
            for t in tasks:
                t.cancel()
            from app.services.moonraker_client import close_shared_client

            await close_shared_client()

    app = FastAPI(
        title="FilaMind Flow",
        version=__version__,
        summary="Extensible Neo-Brutalist control panel for Klipper / Moonraker.",
        lifespan=_lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def hardware_cache(request: Request, call_next):  # type: ignore[no-untyped-def]
        """ETag + Cache-Control for the immutable hardware-DB reads (304 on a match)."""
        path = request.url.path
        if request.method in ("GET", "HEAD") and path.startswith("/api/hardware"):
            etag = reference_data.dataset_etag()
            if request.headers.get("if-none-match") == etag:
                return Response(
                    status_code=304, headers={"ETag": etag, "Cache-Control": _HW_CACHE_CONTROL}
                )
            response = await call_next(request)
            if response.status_code == 200:
                response.headers["ETag"] = etag
                response.headers["Cache-Control"] = _HW_CACHE_CONTROL
            return response
        return await call_next(request)

    app.include_router(api_router)
    logger.info(
        "FilaMind Flow backend v%s ready (moonraker=%s)",
        __version__,
        settings.moonraker_url,
    )
    return app


app = create_app()
