"""Provider-neutral interactive identity boundary and development magic-link provider."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from secrets import token_urlsafe
from typing import Protocol
from urllib.parse import quote
from uuid import uuid4

from sqlalchemy import Engine, text

from domain.errors import DomainError


@dataclass(frozen=True)
class EstablishedSession:
    opaque_token: str
    csrf_token: str


class IdentityProvider(Protocol):
    """Stable boundary an Entra authorization-code adapter can implement later."""

    def begin(self, identifier: str, source: str, request_id: str) -> None: ...

    def complete(self, credential: str, source: str, request_id: str) -> EstablishedSession: ...

    def logout(self, opaque_token: str, source: str, request_id: str) -> None: ...


class MagicLinkDelivery(Protocol):
    def deliver(self, recipient: str, link: str, expires_at: str) -> None: ...


class DevelopmentPasswordDelivery(Protocol):
    def deliver_password(self, recipient: str, password: str, expires_at: str) -> None: ...


def normalize_email(value: str) -> str:
    local, domain = value.strip().rsplit("@", 1)
    return f"{local.casefold()}@{domain.casefold()}"


def _digest(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()


class MagicLinkIdentityProvider:
    """Development-only passwordless provider; authorization remains internal."""

    def __init__(
        self,
        engine: Engine,
        delivery: MagicLinkDelivery,
        base_url: str,
        password_delivery: DevelopmentPasswordDelivery | None = None,
    ) -> None:
        self._engine = engine
        self._delivery = delivery
        self._base_url = base_url
        self._password_delivery = password_delivery

    def _request_challenge(
        self, email: str, credential: str, source: str, request_id: str
    ) -> str | None:
        with self._engine.begin() as connection:
            row = (
                connection.execute(
                    text(
                        """SELECT * FROM verelo_request_magic_link(
                        :challenge,:token,:email,:email_hash,:source_hash,:request_id)"""
                    ),
                    {
                        "challenge": uuid4(),
                        "token": _digest(credential),
                        "email": email,
                        "email_hash": _digest(email),
                        "source_hash": _digest(source),
                        "request_id": request_id,
                    },
                )
                .mappings()
                .one()
            )
        return row["expires_at"].isoformat() if row["deliver"] else None

    def begin(self, identifier: str, source: str, request_id: str) -> None:
        email = normalize_email(identifier)
        raw_token = token_urlsafe(32)
        expires_at = self._request_challenge(email, raw_token, source, request_id)
        if expires_at:
            link = f"{self._base_url}#token={quote(raw_token, safe='')}"
            try:
                self._delivery.deliver(email, link, expires_at)
            except OSError:
                # The public response remains neutral; the unused challenge expires naturally.
                return

    def begin_password(self, identifier: str, source: str, request_id: str) -> None:
        if self._password_delivery is None:
            raise DomainError("not_found", 404, "The resource was not found.")
        email = normalize_email(identifier)
        password = token_urlsafe(32)
        expires_at = self._request_challenge(email, f"{email}\0{password}", source, request_id)
        if expires_at:
            try:
                self._password_delivery.deliver_password(email, password, expires_at)
            except OSError:
                return

    def complete_password(
        self, identifier: str, password: str, source: str, request_id: str
    ) -> EstablishedSession:
        if self._password_delivery is None:
            raise DomainError("not_found", 404, "The resource was not found.")
        credential = f"{normalize_email(identifier)}\0{password}"
        try:
            return self.complete(credential, source, request_id)
        except DomainError as error:
            raise DomainError(
                "unauthenticated", 401, "The password is invalid or expired."
            ) from error

    def complete(self, credential: str, source: str, request_id: str) -> EstablishedSession:
        opaque_token = token_urlsafe(32)
        csrf_token = token_urlsafe(32)
        with self._engine.begin() as connection:
            row = (
                connection.execute(
                    text(
                        """SELECT * FROM verelo_consume_magic_link(
                        :credential,:session_id,:session_hash,:csrf,:csrf_hash,:source_hash,:request_id)"""
                    ),
                    {
                        "credential": _digest(credential),
                        "session_id": uuid4(),
                        "session_hash": _digest(opaque_token),
                        "csrf": csrf_token,
                        "csrf_hash": _digest(csrf_token),
                        "source_hash": _digest(source),
                        "request_id": request_id,
                    },
                )
                .mappings()
                .one_or_none()
            )
        if row is None:
            raise DomainError("unauthenticated", 401, "The sign-in link is invalid or expired.")
        return EstablishedSession(opaque_token=opaque_token, csrf_token=csrf_token)

    def logout(self, opaque_token: str, source: str, request_id: str) -> None:
        with self._engine.begin() as connection:
            connection.execute(
                text("SELECT verelo_logout_session(:token,:source,:request_id)"),
                {
                    "token": _digest(opaque_token),
                    "source": _digest(source),
                    "request_id": request_id,
                },
            ).scalar_one()
