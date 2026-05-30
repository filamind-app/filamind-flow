from __future__ import annotations

import uvicorn

from app.config import get_settings


def main() -> None:
    """Runs the server via ``python -m app``."""
    settings = get_settings()
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level,
    )


if __name__ == "__main__":
    main()
