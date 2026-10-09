"""ASGI entrypoint for the built single-user local runtime."""

from pathlib import Path

from api.local_release import create_local_release_app
from api.main import app as api_app

app = create_local_release_app(Path(__file__).resolve().parents[1] / "web" / "dist", api_app)
