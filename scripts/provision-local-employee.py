#!/usr/bin/env python3
"""Provision an explicitly allowlisted employee for local magic-link development."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from uuid import uuid4

from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from api.config import Environment, Settings  # noqa: E402
from domain.identity import normalize_email  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--email", required=True)
    parser.add_argument("--display-name", required=True)
    parser.add_argument("--allow-project-creation", action="store_true")
    args = parser.parse_args()
    settings = Settings()
    if settings.environment is not Environment.LOCAL:
        raise SystemExit("This provisioning command is restricted to VERELO_ENVIRONMENT=local.")

    email = normalize_email(args.email)
    tenant_id, workspace_id, user_id, identity_id = uuid4(), uuid4(), uuid4(), uuid4()
    engine = create_engine(settings.local_admin_database_url.get_secret_value())
    try:
        with engine.begin() as connection:
            existing = connection.execute(
                text(
                    """SELECT tenant_id,user_id FROM identity_accounts
                    WHERE provider='magic_link' AND login_email_normalized=:email"""
                ),
                {"email": email},
            ).one_or_none()
            if existing is not None:
                print(f"Already provisioned: user_id={existing.user_id}")
                return 0

            tenant = connection.execute(
                text(
                    """SELECT id FROM tenants
                    WHERE entra_tenant_id IS NULL AND policy_config_ref='local-magic-link'
                    ORDER BY created_at LIMIT 1"""
                )
            ).scalar_one_or_none()
            if tenant is None:
                connection.execute(
                    text(
                        """INSERT INTO tenants (id,policy_config_ref,region)
                        VALUES (:id,'local-magic-link','local')"""
                    ),
                    {"id": tenant_id},
                )
                connection.execute(
                    text(
                        """INSERT INTO workspaces (id,tenant_id,name,is_default)
                        VALUES (:id,:tenant,'Verelo local development',true)"""
                    ),
                    {"id": workspace_id, "tenant": tenant_id},
                )
            else:
                tenant_id = tenant
                workspace_id = connection.execute(
                    text("SELECT id FROM workspaces WHERE tenant_id=:tenant AND is_default"),
                    {"tenant": tenant_id},
                ).scalar_one()

            connection.execute(
                text(
                    """INSERT INTO users (id,tenant_id,display_name,email)
                    VALUES (:id,:tenant,:display_name,:email)"""
                ),
                {
                    "id": user_id,
                    "tenant": tenant_id,
                    "display_name": args.display_name,
                    "email": email,
                },
            )
            connection.execute(
                text(
                    """INSERT INTO identity_accounts
                    (id,tenant_id,workspace_id,user_id,provider,subject,login_email_normalized)
                    VALUES (:id,:tenant,:workspace,:user,'magic_link',:subject,:email)"""
                ),
                {
                    "id": identity_id,
                    "tenant": tenant_id,
                    "workspace": workspace_id,
                    "user": user_id,
                    "subject": str(uuid4()),
                    "email": email,
                },
            )
            if args.allow_project_creation:
                connection.execute(
                    text(
                        """INSERT INTO user_capabilities
                        (id,tenant_id,user_id,capability)
                        VALUES (:id,:tenant,:user,'projects:create')"""
                    ),
                    {"id": uuid4(), "tenant": tenant_id, "user": user_id},
                )
        print(f"Provisioned local employee: user_id={user_id}, tenant_id={tenant_id}")
        return 0
    finally:
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
