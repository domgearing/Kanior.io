"""Serve the built local web application beside the existing API routes."""

from __future__ import annotations

from pathlib import Path

from fastapi.responses import FileResponse
from starlette.applications import Starlette
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles
from starlette.types import ASGIApp


def create_local_release_app(dist: Path, backend: ASGIApp) -> Starlette:
    index = dist / "index.html"
    assets = dist / "assets"
    if not index.is_file() or not assets.is_dir():
        raise RuntimeError("Build the web app before starting the local release")

    async def web_index(_request):  # type: ignore[no-untyped-def]
        return FileResponse(index, headers={"Cache-Control": "no-store"})

    return Starlette(
        routes=[
            Route("/", web_index),
            Route("/auth/verify", web_index),
            Mount("/assets", app=StaticFiles(directory=assets)),
            Mount("/", app=backend),
        ]
    )
