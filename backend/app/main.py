from __future__ import annotations

import logging

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

    app = FastAPI(
        title="FilaMind Flow",
        version=__version__,
        summary="Extensible Neo-Brutalist control panel for Klipper / Moonraker.",
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
