"""Minimal FastAPI application startup surface."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from api.config import get_settings


def create_app() -> FastAPI:
    """Create the application without registering provisional product routes."""

    app = FastAPI(
        title="Kanior API", version="0.1.0", docs_url=None, redoc_url=None, openapi_url=None
    )

    @app.get("/health", include_in_schema=False)
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/ready", include_in_schema=False)
    async def readiness() -> JSONResponse:
        settings = get_settings()
        return JSONResponse(
            status_code=200,
            content={"status": "ready", "environment": settings.environment.value},
        )

    return app


app = create_app()
