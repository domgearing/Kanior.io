"""Opaque server-session resolution and CSRF validation."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from secrets import compare_digest
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Request
from sqlalchemy import Engine, text

from api.database import bind_context
from contracts.models import AuthContext
from domain.errors import DomainError


@dataclass(frozen=True)
class AuthSession:
    context: AuthContext
    csrf_token: str
    csrf_sha256: str


def _engine(request: Request) -> Engine:
    return request.app.state.engine  # type: ignore[no-any-return]


def resolve_session(request: Request, engine: Annotated[Engine, Depends(_engine)]) -> AuthSession:
    token = request.cookies.get("verelo_session")
    if not token:
        raise DomainError("unauthenticated", 401, "Authentication is required.")
    digest = sha256(token.encode()).hexdigest()
    with engine.connect() as connection:
        row = (
            connection.execute(
                text("SELECT * FROM verelo_resolve_session(:digest)"), {"digest": digest}
            )
            .mappings()
            .one_or_none()
        )
    if row is None:
        raise DomainError("unauthenticated", 401, "Authentication is required.")
    context = AuthContext(
        principal_kind="employee",
        principal_id=row["user_id"],
        tenant_id=row["tenant_id"],
        workspace_id=row["workspace_id"],
        authorization_epoch=row["authorization_epoch"],
        capabilities=[],
        request_id=str(request.state.request_id),
    )
    with engine.begin() as connection:
        bind_context(connection, context)
        capabilities = connection.execute(
            text(
                """SELECT capability FROM user_capabilities
                WHERE tenant_id=:tenant AND user_id=:user AND enabled"""
            ),
            {"tenant": context.tenant_id, "user": context.principal_id},
        ).scalars()
        context = context.model_copy(update={"capabilities": list(capabilities)})
        touched = connection.execute(
            text("SELECT verelo_touch_session(:session_id)"),
            {"session_id": row["session_id"]},
        ).scalar_one()
        if not touched:
            raise DomainError("unauthenticated", 401, "Authentication is required.")
    return AuthSession(context, row["csrf_token"], row["csrf_sha256"])


def require_csrf(
    request: Request, session: Annotated[AuthSession, Depends(resolve_session)]
) -> AuthSession:
    supplied = request.headers.get("X-CSRF-Token", "")
    origin = request.headers.get("Origin")
    configured = getattr(request.app.state, "public_origin", None)
    valid_origin = configured is None or origin == configured
    if (
        not supplied
        or not valid_origin
        or not compare_digest(sha256(supplied.encode()).hexdigest(), session.csrf_sha256)
    ):
        raise DomainError("forbidden", 403, "The requested action is not permitted.")
    return session


def synthetic_session(
    *,
    principal_id: UUID,
    tenant_id: UUID,
    workspace_id: UUID,
    request_id: str,
    csrf_token: str = "synthetic-csrf-token-value-00000000",
    capabilities: tuple[str, ...] = (),
) -> AuthSession:
    """Test-only constructor; never registered as an HTTP authentication mode."""

    context = AuthContext(
        principal_kind="employee",
        principal_id=principal_id,
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        authorization_epoch=0,
        capabilities=list(capabilities),  # type: ignore[arg-type]
        request_id=request_id,
    )
    return AuthSession(context, csrf_token, sha256(csrf_token.encode()).hexdigest())
