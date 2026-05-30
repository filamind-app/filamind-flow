from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api.router import api_router
from app.config import Settings, get_settings
from app.logging_config import configure_logging

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

    app.include_router(api_router)
    logger.info(
        "FilaMind Flow backend v%s ready (moonraker=%s)",
        __version__,
        settings.moonraker_url,
    )
    return app


app = create_app()
