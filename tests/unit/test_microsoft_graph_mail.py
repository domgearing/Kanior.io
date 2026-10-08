from __future__ import annotations

import json

import httpx
import pytest

from connectors.microsoft_graph_mail import MicrosoftGraphMagicLinkDelivery


def test_graph_mail_uses_client_credentials_and_dedicated_sender() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path.endswith("/oauth2/v2.0/token"):
            return httpx.Response(200, json={"access_token": "synthetic-token", "expires_in": 3600})
        return httpx.Response(202)

    delivery = MicrosoftGraphMagicLinkDelivery(
        tenant_id="10000000-0000-4000-8000-000000000001",
        client_id="10000000-0000-4000-8000-000000000002",
        client_secret="fictional-secret",
        sender="verelo-login@example.invalid",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    delivery.deliver(
        "employee@example.invalid",
        "https://verelo.example.invalid/auth/verify#token=fictional-token",
        "2026-09-25T12:10:00+00:00",
    )
    delivery.deliver(
        "second@example.invalid",
        "https://verelo.example.invalid/auth/verify#token=second-fictional-token",
        "2026-09-25T12:11:00+00:00",
    )

    assert len(requests) == 3
    token_request, first_mail, second_mail = requests
    assert token_request.url.path.endswith("/oauth2/v2.0/token")
    assert b"scope=https%3A%2F%2Fgraph.microsoft.com%2F.default" in token_request.content
    assert first_mail.url.path.endswith("/users/verelo-login@example.invalid/sendMail")
    assert first_mail.headers["Authorization"] == "Bearer synthetic-token"
    payload = json.loads(first_mail.content)
    assert payload["message"]["toRecipients"][0]["emailAddress"]["address"] == (
        "employee@example.invalid"
    )
    assert "fictional-token" in payload["message"]["body"]["content"]
    assert second_mail.headers["Authorization"] == "Bearer synthetic-token"


def test_graph_mail_retries_throttling_without_exposing_provider_body() -> None:
    attempts = 0
    delays: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        if request.url.path.endswith("/oauth2/v2.0/token"):
            return httpx.Response(200, json={"access_token": "token", "expires_in": 3600})
        attempts += 1
        return httpx.Response(
            429,
            headers={"Retry-After": "2"},
            json={"error": {"message": "sensitive provider diagnostic"}},
        )

    delivery = MicrosoftGraphMagicLinkDelivery(
        tenant_id="tenant",
        client_id="client",
        client_secret="secret",
        sender="sender@example.invalid",
        max_attempts=2,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        sleeper=delays.append,
    )

    with pytest.raises(OSError, match="did not accept") as caught:
        delivery.deliver("employee@example.invalid", "https://example.invalid/link", "soon")

    assert attempts == 2
    assert delays == [2]
    assert "sensitive provider diagnostic" not in str(caught.value)
