from __future__ import annotations

from fastapi.testclient import TestClient

from api.main import create_app


def test_health_and_readiness_do_not_expose_configuration() -> None:
    client = TestClient(create_app())
    assert client.get("/health").json() == {"status": "ok"}
    assert client.get("/ready").status_code == 200
