from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from api.identity_routes import create_identity_router
from domain.errors import DomainError
from domain.identity import EstablishedSession


class FakeEntra:
    def begin(self) -> tuple[str, str]:
        return "https://login.microsoftonline.com/test", "browser-secret"

    def complete(self, state: str, code: str, browser: str) -> EstablishedSession:
        if (state, code, browser) != ("state", "code", "browser-secret"):
            raise ValueError("unbound_flow")
        return EstablishedSession("opaque-session", "csrf-secret")

    def logout(self, opaque_token: str, source: str, request_id: str) -> None:
        pass


def test_entra_browser_flow_binds_cookie_and_redirects_safely() -> None:
    app = FastAPI()

    @app.exception_handler(DomainError)
    def safe_error(_request, error: DomainError) -> JSONResponse:  # type: ignore[no-untyped-def]
        return JSONResponse({"code": error.code}, status_code=error.status_code)

    app.state.public_origin = "https://dev.verelo.io"
    app.include_router(create_identity_router(None, cookie_secure=True, entra_provider=FakeEntra()))  # type: ignore[arg-type]
    with TestClient(app, base_url="https://dev-api.verelo.io") as client:
        assert client.get("/api/v1/auth/mode").json() == {"provider": "entra"}
        assert (
            client.post(
                "/api/v1/auth/magic-link/request", json={"email": "employee@example.invalid"}
            ).status_code
            == 404
        )
        started = client.get("/api/v1/auth/entra/start", follow_redirects=False)
        assert started.status_code == 302
        assert started.headers["location"] == "https://login.microsoftonline.com/test"
        assert "httponly" in started.headers["set-cookie"].lower()
        assert "samesite=none" in started.headers["set-cookie"].lower()
        completed = client.post(
            "/api/v1/auth/entra/callback",
            data={"state": "state", "code": "code"},
            follow_redirects=False,
        )
        assert completed.status_code == 303
        assert completed.headers["location"] == "https://dev.verelo.io"
        assert "verelo_session=opaque-session" in completed.headers["set-cookie"]

    with TestClient(app, base_url="https://dev-api.verelo.io") as unbound:
        denied = unbound.post(
            "/api/v1/auth/entra/callback",
            data={"state": "state", "code": "code"},
            follow_redirects=False,
        )
        assert denied.status_code == 303
        assert denied.headers["location"].endswith("?sign_in_error=1")
        assert "verelo_session=" not in denied.headers["set-cookie"]
