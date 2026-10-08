#!/usr/bin/env python3
"""Bind a pre-approved internal employee to one explicit Entra tenant/object ID."""

from __future__ import annotations

import argparse
import os
from uuid import UUID, uuid4

from sqlalchemy import create_engine, text


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tenant-id", required=True, type=UUID)
    parser.add_argument("--workspace-id", required=True, type=UUID)
    parser.add_argument("--user-id", required=True, type=UUID)
    parser.add_argument("--entra-tenant-id", required=True, type=UUID)
    parser.add_argument("--entra-object-id", required=True, type=UUID)
    args = parser.parse_args()
    if os.environ.get("VERELO_ENVIRONMENT") not in {"staging", "production"}:
        raise SystemExit("Only isolated staging/production identity linking is supported.")
    admin_url = os.environ.get("VERELO_PROVISION_DATABASE_URL")
    if not admin_url:
        raise SystemExit("Inject VERELO_PROVISION_DATABASE_URL into this command only.")
    engine = create_engine(admin_url, pool_pre_ping=True, connect_args={"connect_timeout": 5})
    try:
        with engine.begin() as connection:
            tenant = connection.execute(
                text("SELECT 1 FROM tenants WHERE id=:id AND entra_tenant_id=:entra"),
                {"id": args.tenant_id, "entra": args.entra_tenant_id},
            ).scalar_one_or_none()
            workspace = connection.execute(
                text("SELECT 1 FROM workspaces WHERE id=:id AND tenant_id=:tenant"),
                {"id": args.workspace_id, "tenant": args.tenant_id},
            ).scalar_one_or_none()
            user = connection.execute(
                text("""SELECT entra_object_id FROM users
                WHERE id=:id AND tenant_id=:tenant AND enabled FOR UPDATE"""),
                {"id": args.user_id, "tenant": args.tenant_id},
            ).scalar_one_or_none()
            if tenant is None or workspace is None or user not in (None, args.entra_object_id):
                raise SystemExit("Tenant, workspace, or approved enabled user does not match.")
            # A null user value is allowed only when the explicit enabled user exists.
            exists = connection.execute(
                text("SELECT 1 FROM users WHERE id=:id AND tenant_id=:tenant AND enabled"),
                {"id": args.user_id, "tenant": args.tenant_id},
            ).scalar_one_or_none()
            if exists is None:
                raise SystemExit("The employee must be pre-provisioned and enabled.")
            connection.execute(
                text("""UPDATE users SET entra_object_id=:oid
                WHERE id=:id AND tenant_id=:tenant AND
                  (entra_object_id IS NULL OR entra_object_id=:oid)"""),
                {"oid": args.entra_object_id, "id": args.user_id, "tenant": args.tenant_id},
            )
            connection.execute(
                text("""INSERT INTO identity_accounts
                (id,tenant_id,workspace_id,user_id,provider,subject)
                VALUES (:id,:tenant,:workspace,:user,'entra',:subject)
                ON CONFLICT (provider,subject) DO NOTHING"""),
                {
                    "id": uuid4(),
                    "tenant": args.tenant_id,
                    "workspace": args.workspace_id,
                    "user": args.user_id,
                    "subject": str(args.entra_object_id),
                },
            )
            linked = connection.execute(
                text("""SELECT 1 FROM identity_accounts
                WHERE tenant_id=:tenant AND workspace_id=:workspace AND user_id=:user
                  AND provider='entra' AND subject=:subject AND enabled"""),
                {
                    "tenant": args.tenant_id,
                    "workspace": args.workspace_id,
                    "user": args.user_id,
                    "subject": str(args.entra_object_id),
                },
            ).scalar_one_or_none()
            if linked is None:
                raise SystemExit("Entra subject is already bound to a different identity.")
        print("The approved internal employee is linked to the specified Entra identity.")
        return 0
    finally:
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
