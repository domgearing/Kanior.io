from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.local_release import create_local_release_app


def test_local_release_serves_built_web_and_preserves_api(tmp_path: Path) -> None:
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<html>Verelo</html>", encoding="utf-8")
    (dist / "assets" / "app.js").write_text("const ready = true;", encoding="utf-8")
    backend = FastAPI()

    @backend.get("/ready")
    def ready() -> dict[str, str]:
        return {"status": "ready"}

    with TestClient(create_local_release_app(dist, backend)) as client:
        for route in ("/", "/auth/verify"):
            response = client.get(route)
            assert response.status_code == 200
            assert "Verelo" in response.text
            assert response.headers["cache-control"] == "no-store"
        assert client.get("/assets/app.js").status_code == 200
        assert client.get("/ready").json() == {"status": "ready"}
        assert client.get("/assets/missing.js").status_code == 404


def test_local_release_requires_a_complete_build(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="Build the web app"):
        create_local_release_app(tmp_path, FastAPI())
