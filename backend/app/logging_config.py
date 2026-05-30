from __future__ import annotations

import logging


def configure_logging(level: str) -> None:
    """Configures root logging with a concise single-line format."""
    logging.basicConfig(
        level=level.upper(),
        format="%(asctime)s %(levelname)-7s %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )
