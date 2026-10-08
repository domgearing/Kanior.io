"""Validated process configuration; secrets are injected only through the environment."""

from __future__ import annotations

from enum import StrEnum
from uuid import UUID

from pydantic import AnyUrl, Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(StrEnum):
    LOCAL = "local"
    TEST = "test"
    STAGING = "staging"
    PRODUCTION = "production"


class IntegrationsMode(StrEnum):
    FAKE = "fake"
    LIVE = "live"


class IdentityProviderMode(StrEnum):
    MAGIC_LINK = "magic_link"
    ENTRA = "entra"


class MagicLinkDeliveryMode(StrEnum):
    LOCAL = "local"
    MICROSOFT_GRAPH = "microsoft_graph"


class Settings(BaseSettings):
    """Settings shared by the API and worker processes.

    The application never logs this object because it may contain secret values.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="VERELO_",
        extra="ignore",
    )

    environment: Environment = Environment.LOCAL
    database_url: str = "postgresql+psycopg://verelo_api:verelo_api@127.0.0.1:5432/verelo"
    migrator_database_url: str = (
        "postgresql+psycopg://verelo_migrator:verelo_migrator@127.0.0.1:5432/verelo"
    )
    worker_database_url: str = (
        "postgresql+psycopg://verelo_worker:verelo_worker@127.0.0.1:5432/verelo"
    )
    local_admin_database_url: SecretStr = SecretStr(
        "postgresql+psycopg://verelo_admin:verelo_admin@127.0.0.1:5432/verelo"
    )
    object_storage_root: str = ".artifacts/objects"
    integrations_mode: IntegrationsMode = IntegrationsMode.FAKE
    api_host: str = "127.0.0.1"
    api_port: int = Field(default=8000, ge=1, le=65535)
    log_level: str = "INFO"
    identity_provider: IdentityProviderMode = IdentityProviderMode.MAGIC_LINK
    magic_link_delivery: MagicLinkDeliveryMode = MagicLinkDeliveryMode.LOCAL
    magic_link_base_url: AnyUrl = AnyUrl("http://127.0.0.1:5173/auth/verify")
    development_mailbox_root: str = ".artifacts/dev-mailbox"
    session_cookie_secure: bool = False

    graph_mail_tenant_id: str | None = None
    graph_mail_client_id: str | None = None
    graph_mail_client_secret: SecretStr | None = None
    graph_mail_sender: str | None = None
    graph_mail_base_url: AnyUrl = AnyUrl("https://graph.microsoft.com/v1.0")
    graph_mail_authority_url: AnyUrl = AnyUrl("https://login.microsoftonline.com")

    integration_connect_timeout_seconds: float = Field(default=5, gt=0, le=60)
    integration_request_timeout_seconds: float = Field(default=30, gt=0, le=300)
    integration_transfer_idle_timeout_seconds: float = Field(default=120, gt=0, le=1800)
    integration_transfer_deadline_seconds: float = Field(default=1800, gt=0, le=7200)
    integration_max_http_attempts: int = Field(default=3, ge=1, le=10)

    # Optional only because fake adapters are the default foundation behavior.
    openai_api_key: SecretStr | None = None
    assemblyai_api_key: SecretStr | None = None
    b2_application_key: SecretStr | None = None
    assemblyai_api_base_url: AnyUrl = AnyUrl("https://api.assemblyai.com")
    assemblyai_speech_model: str = "universal-3-5-pro"
    assemblyai_max_concurrent_jobs: int = Field(default=1, ge=1, le=100)
    b2_s3_endpoint: AnyUrl | None = None
    b2_region: str | None = None
    b2_bucket_name: str | None = None
    b2_key_prefix: str = "verelo-smoke/"
    b2_application_key_id: str | None = None
    b2_purge_application_key_id: str | None = None
    b2_purge_application_key: SecretStr | None = None
    b2_backup_bucket_name: str | None = None
    b2_backup_key_prefix: str = "verelo-smoke/"
    b2_backup_application_key_id: str | None = None
    b2_backup_application_key: SecretStr | None = None
    recall_region: str | None = None
    recall_api_base_url: AnyUrl | None = None
    recall_api_key: SecretStr | None = None
    recall_webhook_secret: SecretStr | None = None
    recall_webhook_url: AnyUrl | None = None
    recall_capture_mode: str = "audio_only"
    entra_client_secret: SecretStr | None = None
    entra_tenant_id: str | None = None
    entra_client_id: str | None = None
    entra_redirect_uri: AnyUrl | None = None
    entra_employee_group_id: str | None = None
    public_origin: AnyUrl | None = None
    api_public_origin: AnyUrl | None = None
    worker_tenant_id: str | None = None
    worker_workspace_id: str | None = None
    worker_service_identity_id: str | None = None
    worker_project_ids: str = ""
    worker_run_once: bool = False

    @model_validator(mode="after")
    def validate_runtime_mode(self) -> Settings:
        if self.identity_provider is IdentityProviderMode.ENTRA:
            required_entra = {
                "entra_tenant_id": self.entra_tenant_id,
                "entra_client_id": self.entra_client_id,
                "entra_client_secret": self.entra_client_secret,
                "entra_redirect_uri": self.entra_redirect_uri,
                "entra_employee_group_id": self.entra_employee_group_id,
            }
            if any(not value for value in required_entra.values()):
                raise ValueError("Entra sign-in configuration is incomplete")
            try:
                for identifier in (
                    self.entra_tenant_id,
                    self.entra_client_id,
                    self.entra_employee_group_id,
                ):
                    UUID(str(identifier))
            except ValueError as error:
                raise ValueError("Entra tenant, client, and group IDs must be UUIDs") from error
            if self.entra_redirect_uri is None or self.entra_redirect_uri.scheme != "https":
                raise ValueError("Entra redirect URI must use HTTPS")
            if self.public_origin is None or self.public_origin.scheme != "https":
                raise ValueError("Entra sign-in requires an HTTPS public origin")
            if not self.session_cookie_secure:
                raise ValueError("Entra sign-in requires secure session cookies")
            if self.api_public_origin is None or self.api_public_origin.scheme != "https":
                raise ValueError("Entra sign-in requires an HTTPS API public origin")
            expected_callback = (
                str(self.api_public_origin).rstrip("/") + "/api/v1/auth/entra/callback"
            )
            if str(self.entra_redirect_uri) != expected_callback:
                raise ValueError("Entra redirect URI must match the public-origin callback")
        if (
            self.environment is Environment.PRODUCTION
            and self.integrations_mode is IntegrationsMode.FAKE
        ):
            raise ValueError("production cannot use fake integrations")
        if self.environment not in {Environment.LOCAL, Environment.TEST} and (
            self.identity_provider is IdentityProviderMode.MAGIC_LINK
        ):
            raise ValueError(
                "development magic-link identity is limited to local/test environments"
            )
        if (
            self.environment not in {Environment.LOCAL, Environment.TEST}
            and not self.session_cookie_secure
        ):
            raise ValueError("non-local session cookies must be secure")
        if self.magic_link_delivery is MagicLinkDeliveryMode.MICROSOFT_GRAPH:
            if self.integrations_mode is not IntegrationsMode.LIVE:
                raise ValueError("Microsoft Graph mail requires live integrations mode")
            required = {
                "graph_mail_tenant_id": self.graph_mail_tenant_id,
                "graph_mail_client_id": self.graph_mail_client_id,
                "graph_mail_client_secret": self.graph_mail_client_secret,
                "graph_mail_sender": self.graph_mail_sender,
            }
            missing = [
                name
                for name, value in required.items()
                if value is None
                or (isinstance(value, str) and not value.strip())
                or (isinstance(value, SecretStr) and not value.get_secret_value())
            ]
            if missing:
                raise ValueError(
                    "Microsoft Graph mail configuration is incomplete: " + ", ".join(missing)
                )
            sender = self.graph_mail_sender
            if sender is None or "@" not in sender:
                raise ValueError("Microsoft Graph mail sender must be an email address")
        if self.integrations_mode is IntegrationsMode.LIVE:
            if self.assemblyai_speech_model != "universal-3-5-pro":
                raise ValueError("live AssemblyAI model must be universal-3-5-pro")
            if self.recall_capture_mode != "audio_only":
                raise ValueError("live Recall capture mode must be audio_only")
            for name, prefix in {
                "b2_key_prefix": self.b2_key_prefix,
                "b2_backup_key_prefix": self.b2_backup_key_prefix,
            }.items():
                if not prefix.strip() or prefix.startswith("/") or ".." in prefix:
                    raise ValueError(f"{name} must be a non-empty relative prefix")
        return self


def get_settings() -> Settings:
    """Build settings on demand so tests can control environment variables."""

    return Settings()
