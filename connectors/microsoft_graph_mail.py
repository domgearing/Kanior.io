"""Microsoft Graph delivery adapter for allowlisted magic-link messages."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from typing import Any
from urllib.parse import quote

import httpx


class MicrosoftGraphMagicLinkDelivery:
    """Send a sign-in link through one dedicated Exchange Online mailbox.

    The adapter deliberately exposes only the provider-neutral ``deliver`` method.
    It never returns access tokens or Graph response bodies to the identity layer.
    """

    def __init__(
        self,
        *,
        tenant_id: str,
        client_id: str,
        client_secret: str,
        sender: str,
        graph_base_url: str = "https://graph.microsoft.com/v1.0",
        authority_base_url: str = "https://login.microsoftonline.com",
        connect_timeout_seconds: float = 5,
        request_timeout_seconds: float = 30,
        max_attempts: int = 3,
        client: httpx.Client | None = None,
        clock: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self._tenant_id = tenant_id
        self._client_id = client_id
        self._client_secret = client_secret
        self._sender = sender
        self._graph_base_url = graph_base_url.rstrip("/")
        self._authority_base_url = authority_base_url.rstrip("/")
        self._max_attempts = max_attempts
        self._clock = clock
        self._sleeper = sleeper
        self._client = client or httpx.Client(
            timeout=httpx.Timeout(request_timeout_seconds, connect=connect_timeout_seconds)
        )
        self._token: str | None = None
        self._token_expires_at = 0.0
        self._token_lock = threading.Lock()

    def deliver(self, recipient: str, link: str, expires_at: str) -> None:
        token = self._access_token()
        endpoint = f"{self._graph_base_url}/users/{quote(self._sender, safe='')}/sendMail"
        payload = {
            "message": {
                "subject": "Your Verelo sign-in link",
                "body": {
                    "contentType": "Text",
                    "content": (
                        "Use this single-use link to sign in to Verelo:\n\n"
                        f"{link}\n\nThis link expires at {expires_at}. "
                        "If you did not request it, you can ignore this email."
                    ),
                },
                "toRecipients": [{"emailAddress": {"address": recipient}}],
            },
            "saveToSentItems": True,
        }
        response = self._request_with_retry(
            "POST",
            endpoint,
            headers={"Authorization": f"Bearer {token}"},
            json=payload,
        )
        if response.status_code != 202:
            raise OSError("Microsoft Graph did not accept the sign-in email.")

    def _access_token(self) -> str:
        with self._token_lock:
            now = self._clock()
            if self._token is not None and now < self._token_expires_at:
                return self._token
            endpoint = (
                f"{self._authority_base_url}/{quote(self._tenant_id, safe='')}/oauth2/v2.0/token"
            )
            response = self._request_with_retry(
                "POST",
                endpoint,
                data={
                    "client_id": self._client_id,
                    "client_secret": self._client_secret,
                    "scope": "https://graph.microsoft.com/.default",
                    "grant_type": "client_credentials",
                },
            )
            if response.status_code != 200:
                raise OSError("Microsoft Graph authentication failed.")
            try:
                body = response.json()
                token = body["access_token"]
                expires_in = int(body["expires_in"])
            except (KeyError, TypeError, ValueError) as error:
                raise OSError("Microsoft Graph returned an invalid token response.") from error
            if not isinstance(token, str) or not token or expires_in <= 0:
                raise OSError("Microsoft Graph returned an invalid token response.")
            self._token = token
            self._token_expires_at = now + max(0, expires_in - 60)
            return token

    def _request_with_retry(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        for attempt in range(self._max_attempts):
            try:
                response = self._client.request(method, url, **kwargs)
            except httpx.TransportError as error:
                if attempt + 1 >= self._max_attempts:
                    raise OSError("Microsoft Graph is unavailable.") from error
                self._sleeper(min(2**attempt, 30))
                continue
            if response.status_code != 429 and response.status_code < 500:
                return response
            if attempt + 1 >= self._max_attempts:
                return response
            self._sleeper(self._retry_delay(response, attempt))
        raise OSError("Microsoft Graph is unavailable.")

    @staticmethod
    def _retry_delay(response: httpx.Response, attempt: int) -> float:
        raw_retry_after: str = response.headers.get("Retry-After", "")
        try:
            retry_after = float(raw_retry_after)
        except ValueError:
            retry_after = 0.0
        exponential_delay = float(2**attempt)
        return min(max(retry_after, exponential_delay), 30.0)
