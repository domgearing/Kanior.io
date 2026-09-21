"""Start the foundation worker process without processing provisional job types."""

from __future__ import annotations

import logging

from api.config import get_settings


def main() -> None:
    settings = get_settings()
    logging.basicConfig(level=settings.log_level)
    logging.getLogger(__name__).info(
        "worker started", extra={"environment": settings.environment.value}
    )


if __name__ == "__main__":
    main()
