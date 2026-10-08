from __future__ import annotations

import pytest
from pydantic import AnyUrl, SecretStr, ValidationError

from api.config import (
    Environment,
    IdentityProviderMode,
    IntegrationsMode,
    MagicLinkDeliveryMode,
    Settings,
)


def test_defaults_use_fake_integrations_for_local_foundation() -> None:
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    assert settings.environment == "local"
    assert settings.integrations_mode == "fake"


def test_production_rejects_fake_integrations() -> None:
    with pytest.raises(ValidationError, match="production cannot use fake integrations"):
        Settings(
            environment=Environment.PRODUCTION,
            integrations_mode=IntegrationsMode.FAKE,
            _env_file=None,  # type: ignore[call-arg]
        )


def test_graph_mail_requires_live_complete_configuration() -> None:
    with pytest.raises(ValidationError, match="requires live integrations mode"):
        Settings(
            magic_link_delivery=MagicLinkDeliveryMode.MICROSOFT_GRAPH,
            _env_file=None,  # type: ignore[call-arg]
        )

    with pytest.raises(ValidationError, match="configuration is incomplete"):
        Settings(
            integrations_mode=IntegrationsMode.LIVE,
            magic_link_delivery=MagicLinkDeliveryMode.MICROSOFT_GRAPH,
            _env_file=None,  # type: ignore[call-arg]
        )


def test_graph_mail_configuration_accepts_injected_secret() -> None:
    settings = Settings(
        integrations_mode=IntegrationsMode.LIVE,
        magic_link_delivery=MagicLinkDeliveryMode.MICROSOFT_GRAPH,
        graph_mail_tenant_id="fictional-tenant",
        graph_mail_client_id="fictional-client",
        graph_mail_client_secret=SecretStr("fictional-secret"),
        graph_mail_sender="verelo-login@example.invalid",
        _env_file=None,  # type: ignore[call-arg]
    )
    assert settings.graph_mail_client_secret is not None
    assert settings.graph_mail_client_secret.get_secret_value() == "fictional-secret"


def test_entra_requires_complete_https_configuration() -> None:
    with pytest.raises(ValidationError, match="Entra sign-in configuration is incomplete"):
        Settings(
            environment=Environment.STAGING,
            identity_provider=IdentityProviderMode.ENTRA,
            _env_file=None,  # type: ignore[call-arg]
        )

    settings = Settings(
        environment=Environment.STAGING,
        integrations_mode=IntegrationsMode.LIVE,
        identity_provider=IdentityProviderMode.ENTRA,
        entra_tenant_id="00000000-0000-4000-8000-000000000001",
        entra_client_id="00000000-0000-4000-8000-000000000002",
        entra_client_secret=SecretStr("fictional-secret"),
        entra_employee_group_id="00000000-0000-4000-8000-000000000003",
        entra_redirect_uri=AnyUrl("https://staging-api.example.invalid/api/v1/auth/entra/callback"),
        api_public_origin=AnyUrl("https://staging-api.example.invalid"),
        public_origin=AnyUrl("https://staging.example.invalid"),
        session_cookie_secure=True,
        _env_file=None,  # type: ignore[call-arg]
    )
    assert settings.identity_provider is IdentityProviderMode.ENTRA
