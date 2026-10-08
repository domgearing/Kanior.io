"""Single-tenant Entra authorization-code adapter; tokens never reach clients."""

from __future__ import annotations

import json
from hashlib import sha256
from secrets import token_urlsafe
from typing import Any
from uuid import UUID, uuid4

import jwt
import msal  # type: ignore[import-untyped]
from jwt import PyJWKClient
from sqlalchemy import Engine, text

from domain.errors import DomainError
from domain.identity import EstablishedSession


def _digest(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()


def admitted_employee(claims: dict[str, Any], tenant: str, client: str, group: str) -> UUID:
    """Check the signed token's identity against exact tenant assignment rules."""
    try:
        expected_tenant = UUID(tenant)
        object_id = UUID(claims["oid"])
        issuer = f"https://login.microsoftonline.com/{expected_tenant}/v2.0"
        groups = claims["groups"]
        if not (
            claims.get("ver") == "2.0"
            and claims.get("tid") == str(expected_tenant)
            and claims.get("iss") == issuer
            and claims.get("aud") == client
            and claims.get("acct") in (0, "0")
            and isinstance(groups, list)
            and group in groups
            and not claims.get("_claim_names")
        ):
            raise ValueError("identity_not_admitted")
        return object_id
    except (KeyError, TypeError, ValueError) as error:
        raise DomainError("unauthenticated", 401, "Employee sign-in was not accepted.") from error


def verified_id_token(
    token: str, *, tenant: str, client: str, nonce: str, keys: PyJWKClient
) -> dict[str, Any]:
    """Verify signature, time, issuer, audience, and the PKCE flow's nonce."""
    try:
        signing_key = keys.get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            audience=client,
            issuer=f"https://login.microsoftonline.com/{tenant}/v2.0",
            options={"require": ["exp", "iat", "tid", "oid", "nonce"]},
        )
        expected_nonce = sha256(nonce.encode("ascii")).hexdigest()
        if claims.get("nonce") != expected_nonce:
            raise ValueError("nonce_mismatch")
        return claims
    except jwt.PyJWKClientConnectionError as error:
        raise DomainError(
            "dependency_unavailable", 503, "Employee sign-in is unavailable."
        ) from error
    except (jwt.PyJWTError, ValueError, UnicodeError) as error:
        raise DomainError("unauthenticated", 401, "Employee sign-in was not accepted.") from error


class EntraAuthorizationCodeAdapter:
    def __init__(
        self,
        engine: Engine,
        *,
        tenant_id: str,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
        employee_group_id: str,
    ) -> None:
        self._engine = engine
        self._tenant = str(UUID(tenant_id))
        self._client_id = str(UUID(client_id))
        self._group = str(UUID(employee_group_id))
        self._redirect_uri = redirect_uri
        self._keys = PyJWKClient(
            f"https://login.microsoftonline.com/{self._tenant}/discovery/v2.0/keys",
            cache_jwk_set=True,
            lifespan=3600,
            timeout=5,
        )
        self._msal = msal.ConfidentialClientApplication(
            self._client_id,
            client_credential=client_secret,
            authority=f"https://login.microsoftonline.com/{self._tenant}",
            validate_authority=True,
        )

    def begin(self) -> tuple[str, str]:
        try:
            flow = self._msal.initiate_auth_code_flow(
                scopes=["User.Read"],
                redirect_uri=self._redirect_uri,
                response_mode="form_post",
            )
        except Exception as error:
            raise DomainError(
                "dependency_unavailable", 503, "Employee sign-in is unavailable."
            ) from error
        state = flow.get("state")
        auth_uri = flow.get("auth_uri")
        if not isinstance(state, str) or not isinstance(auth_uri, str):
            raise DomainError("dependency_unavailable", 503, "Employee sign-in is unavailable.")
        browser_secret = token_urlsafe(32)
        with self._engine.begin() as connection:
            connection.execute(
                text("SELECT verelo_begin_entra_flow(:state,:browser,CAST(:flow AS jsonb))"),
                {
                    "state": _digest(state),
                    "browser": _digest(browser_secret),
                    "flow": json.dumps(flow),
                },
            )
        return auth_uri, browser_secret

    def complete(self, state: str, code: str, browser_secret: str) -> EstablishedSession:
        if not state or not code or not browser_secret:
            raise DomainError("unauthenticated", 401, "Employee sign-in was not accepted.")
        with self._engine.begin() as connection:
            flow = connection.execute(
                text("SELECT verelo_take_entra_flow(:state,:browser)"),
                {"state": _digest(state), "browser": _digest(browser_secret)},
            ).scalar_one_or_none()
        if not isinstance(flow, dict):
            raise DomainError("unauthenticated", 401, "Employee sign-in was not accepted.")
        try:
            result = self._msal.acquire_token_by_auth_code_flow(
                flow, {"state": state, "code": code}, scopes=["User.Read"]
            )
        except (ValueError, RuntimeError) as error:
            raise DomainError(
                "unauthenticated", 401, "Employee sign-in was not accepted."
            ) from error
        except Exception as error:
            raise DomainError(
                "dependency_unavailable", 503, "Employee sign-in is unavailable."
            ) from error
        token = result.get("id_token")
        if not isinstance(token, str) or not isinstance(flow.get("nonce"), str):
            raise DomainError("unauthenticated", 401, "Employee sign-in was not accepted.")
        claims = verified_id_token(
            token,
            tenant=self._tenant,
            client=self._client_id,
            nonce=flow["nonce"],
            keys=self._keys,
        )
        oid = admitted_employee(claims, self._tenant, self._client_id, self._group)
        opaque = token_urlsafe(32)
        csrf = token_urlsafe(32)
        with self._engine.begin() as connection:
            admitted = connection.execute(
                text("""SELECT verelo_create_entra_session(
                    :tenant,:oid,:session,:token,:csrf,:csrf_hash)"""),
                {
                    "tenant": self._tenant,
                    "oid": oid,
                    "session": uuid4(),
                    "token": _digest(opaque),
                    "csrf": csrf,
                    "csrf_hash": _digest(csrf),
                },
            ).scalar_one()
        if not admitted:
            raise DomainError("unauthenticated", 401, "Employee sign-in was not accepted.")
        return EstablishedSession(opaque_token=opaque, csrf_token=csrf)

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
