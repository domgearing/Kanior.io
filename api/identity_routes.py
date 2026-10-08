"""Interactive authentication routes independent of project authorization."""

from __future__ import annotations

from typing import Annotated
from urllib.parse import parse_qs

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import RedirectResponse

from api.auth import AuthSession, require_csrf
from connectors.microsoft_entra import EntraAuthorizationCodeAdapter
from contracts.models import (
    AuthenticationMode,
    AuthenticationResult,
    LogoutResult,
    MagicLinkConsume,
    MagicLinkRequest,
    MagicLinkRequestAccepted,
)
from domain.errors import DomainError
from domain.identity import IdentityProvider


def _source(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _require_exact_origin(request: Request) -> None:
    configured = getattr(request.app.state, "public_origin", None)
    if configured is not None and request.headers.get("Origin") != configured:
        raise DomainError("forbidden", 403, "The requested action is not permitted.")


def create_identity_router(
    provider: IdentityProvider | None,
    *,
    cookie_secure: bool,
    entra_provider: EntraAuthorizationCodeAdapter | None = None,
) -> APIRouter:
    router = APIRouter(prefix="/api/v1/auth", tags=["identity"])

    @router.get("/mode", response_model=AuthenticationMode, operation_id="get_authentication_mode")
    def authentication_mode() -> AuthenticationMode:
        return AuthenticationMode(provider="entra" if entra_provider else "magic_link")

    @router.post("/magic-link/request", response_model=MagicLinkRequestAccepted, status_code=202)
    def request_magic_link(body: MagicLinkRequest, request: Request) -> MagicLinkRequestAccepted:
        if entra_provider is not None:
            raise DomainError("not_found", 404, "The resource was not found.")
        assert provider is not None
        _require_exact_origin(request)
        provider.begin(body.email, _source(request), str(request.state.request_id))
        return MagicLinkRequestAccepted(
            status="accepted",
            message="If the account is eligible, a sign-in link will be sent.",
        )

    @router.post("/magic-link/consume", response_model=AuthenticationResult)
    def consume_magic_link(
        body: MagicLinkConsume, request: Request, response: Response
    ) -> AuthenticationResult:
        if entra_provider is not None:
            raise DomainError("not_found", 404, "The resource was not found.")
        assert provider is not None
        _require_exact_origin(request)
        session = provider.complete(body.token, _source(request), str(request.state.request_id))
        response.set_cookie(
            "verelo_session",
            session.opaque_token,
            secure=cookie_secure,
            httponly=True,
            samesite="lax",
            max_age=8 * 60 * 60,
            path="/",
        )
        return AuthenticationResult(status="authenticated")

    if entra_provider is not None:

        @router.get("/entra/start", include_in_schema=False)
        def start_entra() -> RedirectResponse:
            authorization_url, browser_secret = entra_provider.begin()
            redirect = RedirectResponse(authorization_url, status_code=302)
            redirect.set_cookie(
                "verelo_entra_flow",
                browser_secret,
                secure=True,
                httponly=True,
                samesite="none",
                max_age=600,
                path="/api/v1/auth/entra",
            )
            return redirect

        @router.post("/entra/callback", include_in_schema=False)
        async def complete_entra(request: Request) -> RedirectResponse:
            origin = str(request.app.state.public_origin)
            redirect = RedirectResponse(origin, status_code=303)
            redirect.delete_cookie(
                "verelo_entra_flow",
                path="/api/v1/auth/entra",
                secure=True,
                httponly=True,
                samesite="none",
            )
            media_type = request.headers.get("content-type", "").split(";", 1)[0]
            if media_type != "application/x-www-form-urlencoded":
                redirect.headers["Location"] = origin + "/?sign_in_error=1"
                return redirect
            raw = bytearray()
            async for chunk in request.stream():
                raw.extend(chunk)
                if len(raw) > 4096:
                    redirect.headers["Location"] = origin + "/?sign_in_error=1"
                    return redirect
            try:
                fields = parse_qs(raw.decode("ascii"), strict_parsing=True)
                state, code = fields["state"], fields["code"]
                if len(state) != 1 or len(code) != 1:
                    raise ValueError("invalid_auth_response")
                session = entra_provider.complete(
                    state[0], code[0], request.cookies.get("verelo_entra_flow", "")
                )
            except (UnicodeError, ValueError, KeyError, DomainError):
                redirect.headers["Location"] = origin + "/?sign_in_error=1"
                return redirect
            redirect.set_cookie(
                "verelo_session",
                session.opaque_token,
                secure=True,
                httponly=True,
                samesite="lax",
                max_age=8 * 60 * 60,
                path="/",
            )
            return redirect

    @router.post("/logout", response_model=LogoutResult)
    def logout(
        request: Request,
        response: Response,
        session: Annotated[AuthSession, Depends(require_csrf)],
    ) -> LogoutResult:
        del session
        token = request.cookies.get("verelo_session")
        if token:
            active_provider = entra_provider or provider
            assert active_provider is not None
            active_provider.logout(token, _source(request), str(request.state.request_id))
        response.delete_cookie("verelo_session", path="/", secure=cookie_secure, httponly=True)
        return LogoutResult(status="signed_out")

    return router
