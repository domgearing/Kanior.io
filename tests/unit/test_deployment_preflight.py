from pydantic import AnyUrl, SecretStr

from api.config import Environment, IdentityProviderMode, IntegrationsMode, Settings
from scripts.deployment_preflight import blockers


def test_local_configuration_is_not_deployment_ready() -> None:
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    issues = blockers(settings)
    assert any("Entra employee" in issue for issue in issues)
    assert any("isolated staging" in issue for issue in issues)
    assert any("HTTPS" in issue for issue in issues)
    assert not any(settings.database_url in issue for issue in issues)


def test_isolated_staging_configuration_has_no_automated_blockers() -> None:
    settings = Settings(
        environment=Environment.STAGING,
        integrations_mode=IntegrationsMode.LIVE,
        database_url="postgresql+psycopg://api:fictional@db.example.invalid/verelo",
        worker_database_url="postgresql+psycopg://worker:fictional@db.example.invalid/verelo",
        identity_provider=IdentityProviderMode.ENTRA,
        entra_tenant_id="00000000-0000-4000-8000-000000000001",
        entra_client_id="00000000-0000-4000-8000-000000000002",
        entra_client_secret=SecretStr("fictional-secret"),
        entra_employee_group_id="00000000-0000-4000-8000-000000000003",
        entra_redirect_uri=AnyUrl("https://api.example.invalid/api/v1/auth/entra/callback"),
        api_public_origin=AnyUrl("https://api.example.invalid"),
        public_origin=AnyUrl("https://web.example.invalid"),
        recall_webhook_url=AnyUrl("https://api.example.invalid/api/v1/webhooks/recall"),
        recall_api_base_url=AnyUrl("https://recall.example.invalid"),
        recall_api_key=SecretStr("fictional"),
        recall_webhook_secret=SecretStr("fictional"),
        assemblyai_api_key=SecretStr("fictional"),
        b2_s3_endpoint=AnyUrl("https://b2.example.invalid"),
        b2_region="fictional-region",
        b2_bucket_name="fictional-private-bucket",
        b2_application_key_id="fictional-key-id",
        b2_application_key=SecretStr("fictional"),
        session_cookie_secure=True,
        worker_tenant_id="00000000-0000-4000-8000-000000000001",
        worker_workspace_id="00000000-0000-4000-8000-000000000004",
        worker_service_identity_id="00000000-0000-4000-8000-000000000005",
        worker_project_ids="00000000-0000-4000-8000-000000000006",
        _env_file=None,  # type: ignore[call-arg]
    )
    assert blockers(settings) == []
