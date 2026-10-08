#!/usr/bin/env python3
"""Validate a local Recall test and provision its least-privilege worker scope."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from uuid import uuid4

from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from api.config import Environment, IntegrationsMode, Settings  # noqa: E402


def required_environment(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise SystemExit(f"missing_{name}")
    return value


def main() -> int:
    settings = Settings()
    if settings.environment is not Environment.LOCAL:
        raise SystemExit("live_test_launcher_requires_local_environment")
    if settings.integrations_mode is not IntegrationsMode.LIVE:
        raise SystemExit("VERELO_INTEGRATIONS_MODE_must_be_live")
    if required_environment("VERELO_DESKTOP_CAPTURE_PROVIDER") != "recall_desktop":
        raise SystemExit("VERELO_DESKTOP_CAPTURE_PROVIDER_must_be_recall_desktop")

    if settings.recall_webhook_url is None or settings.recall_webhook_url.scheme != "https":
        raise SystemExit("VERELO_RECALL_WEBHOOK_URL_must_be_public_https")

    required_settings = {
        "VERELO_RECALL_API_BASE_URL": settings.recall_api_base_url,
        "VERELO_RECALL_API_KEY": settings.recall_api_key,
        "VERELO_RECALL_WEBHOOK_SECRET": settings.recall_webhook_secret,
        "VERELO_ASSEMBLYAI_API_KEY": settings.assemblyai_api_key,
        "VERELO_B2_S3_ENDPOINT": settings.b2_s3_endpoint,
        "VERELO_B2_REGION": settings.b2_region,
        "VERELO_B2_BUCKET_NAME": settings.b2_bucket_name,
        "VERELO_B2_APPLICATION_KEY_ID": settings.b2_application_key_id,
        "VERELO_B2_APPLICATION_KEY": settings.b2_application_key,
    }
    missing = [name for name, value in required_settings.items() if value is None]
    if missing:
        raise SystemExit("missing_live_settings:" + ",".join(missing))

    engine = create_engine(
        settings.local_admin_database_url.get_secret_value(),
        pool_pre_ping=True,
        connect_args={"connect_timeout": 3},
    )
    try:
        with engine.begin() as connection:
            local_scopes = (
                connection.execute(
                    text("""SELECT t.id tenant_id,w.id workspace_id
                    FROM tenants t JOIN workspaces w ON w.tenant_id=t.id
                    WHERE t.policy_config_ref='local-magic-link'
                      AND t.entra_tenant_id IS NULL AND w.is_default""")
                )
                .mappings()
                .all()
            )
            if not local_scopes:
                raise SystemExit("provision_a_local_magic_link_employee_first")
            if len(local_scopes) != 1:
                raise SystemExit("local_launcher_found_multiple_magic_link_scopes")
            scope = local_scopes[0]
            scopes = (
                connection.execute(
                    text("""SELECT id project_id FROM projects
                    WHERE tenant_id=:tenant AND workspace_id=:workspace
                      AND state='active' ORDER BY id"""),
                    {"tenant": scope["tenant_id"], "workspace": scope["workspace_id"]},
                )
                .mappings()
                .all()
            )
            service_id = connection.execute(
                text("""SELECT id FROM service_identities
                WHERE tenant_id=:tenant AND name='local-durable-worker'"""),
                {"tenant": scope["tenant_id"]},
            ).scalar_one_or_none()
            if service_id is None:
                service_id = uuid4()
                connection.execute(
                    text("""INSERT INTO service_identities (id,tenant_id,name)
                    VALUES (:id,:tenant,'local-durable-worker')"""),
                    {"id": service_id, "tenant": scope["tenant_id"]},
                )
            for project in scopes:
                for action in ("outbox.dispatch", "jobs.execute"):
                    connection.execute(
                        text("""INSERT INTO service_grants
                        (id,tenant_id,workspace_id,project_id,service_identity_id,action)
                        VALUES (:id,:tenant,:workspace,:project,:service,:action)
                        ON CONFLICT (tenant_id,workspace_id,project_id,service_identity_id,action)
                        DO UPDATE SET enabled=true,revision=service_grants.revision+1,
                          updated_at=now() WHERE service_grants.enabled=false"""),
                        {
                            "id": uuid4(),
                            "tenant": scope["tenant_id"],
                            "workspace": scope["workspace_id"],
                            "project": project["project_id"],
                            "service": service_id,
                            "action": action,
                        },
                    )
        print(f"export VERELO_WORKER_TENANT_ID='{scope['tenant_id']}'")
        print(f"export VERELO_WORKER_WORKSPACE_ID='{scope['workspace_id']}'")
        print(f"export VERELO_WORKER_SERVICE_IDENTITY_ID='{service_id}'")
        project_ids = ",".join(str(project["project_id"]) for project in scopes)
        print(f"export VERELO_WORKER_PROJECT_IDS='{project_ids}'")
        print("export VERELO_WORKER_RUN_ONCE='false'")
        return 0
    finally:
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
