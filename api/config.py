"""Validated process configuration; secrets are injected only through the environment."""

from __future__ import annotations

from enum import StrEnum

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


class Settings(BaseSettings):
    """Settings shared by the API and worker processes.

    The application never logs this object because it may contain secret values.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="KANIOR_",
        extra="ignore",
    )

    environment: Environment = Environment.LOCAL
    database_url: str = "postgresql+psycopg://kanior_api:kanior_api@localhost:5432/kanior"
    integrations_mode: IntegrationsMode = IntegrationsMode.FAKE
    api_host: str = "127.0.0.1"
    api_port: int = Field(default=8000, ge=1, le=65535)
    log_level: str = "INFO"

    integration_connect_timeout_seconds: float = Field(default=5, gt=0, le=60)
    integration_request_timeout_seconds: float = Field(default=30, gt=0, le=300)
    integration_transfer_idle_timeout_seconds: float = Field(default=120, gt=0, le=1800)
    integration_transfer_deadline_seconds: float = Field(default=1800, gt=0, le=7200)
    integration_max_http_attempts: int = Field(default=3, ge=1, le=10)

    # Optional only because fake adapters are the default foundation behavior.
    openai_api_key: SecretStr | None = None
    assemblyai_api_key: SecretStr | None = None
    b2_application_key: SecretStr | None = None
    entra_client_secret: SecretStr | None = None
    public_origin: AnyUrl | None = None

    @model_validator(mode="after")
    def validate_runtime_mode(self) -> Settings:
        if (
            self.environment is Environment.PRODUCTION
            and self.integrations_mode is IntegrationsMode.FAKE
        ):
            raise ValueError("production cannot use fake integrations")
        return self


def get_settings() -> Settings:
    """Build settings on demand so tests can control environment variables."""

    return Settings()
