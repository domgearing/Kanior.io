#!/usr/bin/env python3
"""Provision one explicitly named project grant for a staging/production worker."""

from __future__ import annotations

import argparse
import os
from uuid import UUID, uuid4

from sqlalchemy import create_engine, text


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tenant-id", required=True, type=UUID)
    parser.add_argument("--workspace-id", required=True, type=UUID)
    parser.add_argument("--project-id", required=True, type=UUID)
    parser.add_argument("--service-name", default="deployment-durable-worker")
    args = parser.parse_args()
    if os.environ.get("VERELO_ENVIRONMENT") not in {"staging", "production"}:
        raise SystemExit("Only isolated staging/production provisioning is supported.")
    admin_url = os.environ.get("VERELO_PROVISION_DATABASE_URL")
    if not admin_url:
        raise SystemExit("Inject VERELO_PROVISION_DATABASE_URL into this command only.")
    if not args.service_name or len(args.service_name) > 200:
        raise SystemExit("Invalid worker service name.")
    engine = create_engine(admin_url, pool_pre_ping=True, connect_args={"connect_timeout": 5})
    try:
        with engine.begin() as connection:
            project = connection.execute(
                text("""SELECT 1 FROM projects WHERE id=:project AND tenant_id=:tenant
                AND workspace_id=:workspace AND state='active'"""),
                {
                    "project": args.project_id,
                    "tenant": args.tenant_id,
                    "workspace": args.workspace_id,
                },
            ).scalar_one_or_none()
            if project is None:
                raise SystemExit("The named active project does not match that tenant/workspace.")
            service_id = connection.execute(
                text("""SELECT id FROM service_identities
                WHERE tenant_id=:tenant AND name=:name AND enabled"""),
                {"tenant": args.tenant_id, "name": args.service_name},
            ).scalar_one_or_none()
            if service_id is None:
                service_id = uuid4()
                connection.execute(
                    text("""INSERT INTO service_identities(id,tenant_id,name)
                    VALUES (:id,:tenant,:name)"""),
                    {"id": service_id, "tenant": args.tenant_id, "name": args.service_name},
                )
            for action in ("jobs.execute", "outbox.dispatch"):
                connection.execute(
                    text("""INSERT INTO service_grants
                    (id,tenant_id,workspace_id,project_id,service_identity_id,action)
                    VALUES (:id,:tenant,:workspace,:project,:service,:action)
                    ON CONFLICT (tenant_id,workspace_id,project_id,service_identity_id,action)
                    DO UPDATE SET enabled=true,revision=service_grants.revision+1,
                      updated_at=now() WHERE service_grants.enabled=false"""),
                    {
                        "id": uuid4(),
                        "tenant": args.tenant_id,
                        "workspace": args.workspace_id,
                        "project": args.project_id,
                        "service": service_id,
                        "action": action,
                    },
                )
        print(f"VERELO_WORKER_TENANT_ID={args.tenant_id}")
        print(f"VERELO_WORKER_WORKSPACE_ID={args.workspace_id}")
        print(f"VERELO_WORKER_SERVICE_IDENTITY_ID={service_id}")
        print(f"VERELO_WORKER_PROJECT_IDS={args.project_id}")
        print("Provisioning completed for the explicitly named project only.")
        return 0
    finally:
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
