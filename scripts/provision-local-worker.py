#!/usr/bin/env python3
"""Provision a least-privilege local worker for one existing project."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from uuid import UUID, uuid4

from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from api.config import Environment, Settings  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-id", required=True, type=UUID)
    args = parser.parse_args()
    settings = Settings()
    if settings.environment is not Environment.LOCAL:
        raise SystemExit("This provisioning command is restricted to VERELO_ENVIRONMENT=local.")
    engine = create_engine(settings.local_admin_database_url.get_secret_value())
    try:
        with engine.begin() as connection:
            project = connection.execute(
                text("SELECT tenant_id,workspace_id FROM projects WHERE id=:id"),
                {"id": args.project_id},
            ).one_or_none()
            if project is None:
                raise SystemExit("Project not found.")
            service_id = connection.execute(
                text("""SELECT id FROM service_identities
                WHERE tenant_id=:tenant AND name='local-durable-worker'"""),
                {"tenant": project.tenant_id},
            ).scalar_one_or_none()
            if service_id is None:
                service_id = uuid4()
                connection.execute(
                    text("""INSERT INTO service_identities (id,tenant_id,name)
                    VALUES (:id,:tenant,'local-durable-worker')"""),
                    {"id": service_id, "tenant": project.tenant_id},
                )
            for action in ("outbox.dispatch", "jobs.execute"):
                connection.execute(
                    text("""INSERT INTO service_grants
                    (id,tenant_id,workspace_id,project_id,service_identity_id,action)
                    VALUES (:id,:tenant,:workspace,:project,:service,:action)
                    ON CONFLICT (tenant_id,workspace_id,project_id,service_identity_id,action)
                    DO UPDATE SET enabled=true,
                      revision=service_grants.revision+1,updated_at=now()"""),
                    {
                        "id": uuid4(),
                        "tenant": project.tenant_id,
                        "workspace": project.workspace_id,
                        "project": args.project_id,
                        "service": service_id,
                        "action": action,
                    },
                )
        print(f"VERELO_WORKER_TENANT_ID={project.tenant_id}")
        print(f"VERELO_WORKER_WORKSPACE_ID={project.workspace_id}")
        print(f"VERELO_WORKER_SERVICE_IDENTITY_ID={service_id}")
        print(f"VERELO_WORKER_PROJECT_IDS={args.project_id}")
        return 0
    finally:
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
