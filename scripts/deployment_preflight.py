#!/usr/bin/env python3
"""Read-only deployment readiness check; never prints configuration secrets."""

from __future__ import annotations

import sys
from pathlib import Path

from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from api.config import Environment, IdentityProviderMode, IntegrationsMode, Settings  # noqa: E402


def blockers(settings: Settings) -> list[str]:
    issues: list[str] = []
    if settings.environment not in {Environment.STAGING, Environment.PRODUCTION}:
        issues.append("Use an isolated staging or production environment, not local/test.")
    if settings.integrations_mode is not IntegrationsMode.LIVE:
        issues.append("Live provider integrations are required.")
    if settings.identity_provider is not IdentityProviderMode.ENTRA:
        issues.append("Team deployment requires Entra employee sign-in.")
    if not settings.session_cookie_secure:
        issues.append("Secure session cookies are required behind HTTPS.")
    if settings.public_origin is None or settings.public_origin.scheme != "https":
        issues.append("VERELO_PUBLIC_ORIGIN must be an HTTPS app origin.")
    if settings.api_public_origin is None or settings.api_public_origin.scheme != "https":
        issues.append("VERELO_API_PUBLIC_ORIGIN must be an HTTPS API origin.")
    if settings.recall_webhook_url is None or settings.recall_webhook_url.scheme != "https":
        issues.append("VERELO_RECALL_WEBHOOK_URL must be a stable HTTPS API endpoint.")
    if any(
        value is None
        for value in (
            settings.recall_api_base_url,
            settings.recall_api_key,
            settings.recall_webhook_secret,
            settings.assemblyai_api_key,
            settings.b2_s3_endpoint,
            settings.b2_region,
            settings.b2_bucket_name,
            settings.b2_application_key_id,
            settings.b2_application_key,
        )
    ):
        issues.append("Recall, AssemblyAI, and private B2 provider settings must be injected.")
    try:
        api_db = make_url(settings.database_url)
        worker_db = make_url(settings.worker_database_url)
        if (
            api_db.host in {"localhost", "127.0.0.1"}
            or worker_db.host in {"localhost", "127.0.0.1"}
            or api_db.username == worker_db.username
        ):
            issues.append("Use isolated, non-local API and worker database roles/resources.")
    except (ValueError, ArgumentError):
        issues.append("API and worker database URLs are invalid.")
    if (
        not settings.worker_tenant_id
        or not settings.worker_workspace_id
        or not settings.worker_service_identity_id
        or not settings.worker_project_ids
    ):
        issues.append("Provision a scoped durable worker for the deployment.")
    return issues


def main() -> int:
    try:
        settings = Settings()
    except ValueError as error:
        print(f"BLOCKED: invalid deployment configuration ({type(error).__name__}).")
        return 1
    print("Deployment preflight (read-only; no secrets displayed):")
    issues = blockers(settings)
    for issue in issues:
        print(f"- {issue}")
    print(
        "Manual release gates remain: isolated resources, secrets, backups/restore, "
        "monitoring, employee assignment, and company policy approvals."
    )
    return 1 if issues else 0


if __name__ == "__main__":
    raise SystemExit(main())
