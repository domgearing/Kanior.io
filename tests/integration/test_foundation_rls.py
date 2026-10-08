from __future__ import annotations

import os
from uuid import UUID, uuid4

from sqlalchemy import create_engine, text

from api.config import Settings
from contracts.models import AuthContext
from domain.foundation import FoundationService


def _context(user: UUID, tenant: UUID, workspace: UUID) -> AuthContext:
    return AuthContext(
        principal_kind="employee",
        principal_id=user,
        tenant_id=tenant,
        workspace_id=workspace,
        authorization_epoch=0,
        capabilities=[],
        request_id=str(uuid4()),
    )


def test_restricted_api_role_enforces_current_membership_and_tenant_scope() -> None:
    settings = Settings()
    admin_url = os.environ.get(
        "VERELO_TEST_ADMIN_DATABASE_URL",
        "postgresql+psycopg://verelo_admin:verelo_admin@127.0.0.1:5432/verelo",
    )
    admin = create_engine(admin_url)
    api = create_engine(settings.database_url)
    tenant_a, tenant_b = uuid4(), uuid4()
    workspace_a, workspace_b = uuid4(), uuid4()
    owner, stranger, foreign_user = uuid4(), uuid4(), uuid4()
    project, membership = uuid4(), uuid4()
    try:
        with admin.begin() as connection:
            connection.execute(
                text(
                    """INSERT INTO tenants (id,entra_tenant_id,policy_config_ref,region)
                    VALUES (:id,:entra,'synthetic','local')"""
                ),
                [{"id": tenant_a, "entra": uuid4()}, {"id": tenant_b, "entra": uuid4()}],
            )
            connection.execute(
                text(
                    """INSERT INTO workspaces (id,tenant_id,name,is_default)
                    VALUES (:id,:tenant,'Synthetic',true)"""
                ),
                [{"id": workspace_a, "tenant": tenant_a}, {"id": workspace_b, "tenant": tenant_b}],
            )
            connection.execute(
                text("""INSERT INTO users
                    (id,tenant_id,entra_object_id,display_name,email) VALUES
                    (:id,:tenant,:entra,:name,:email)"""),
                [
                    {
                        "id": owner,
                        "tenant": tenant_a,
                        "entra": uuid4(),
                        "name": "Owner",
                        "email": "owner.invalid",
                    },
                    {
                        "id": stranger,
                        "tenant": tenant_a,
                        "entra": uuid4(),
                        "name": "Stranger",
                        "email": "stranger.invalid",
                    },
                    {
                        "id": foreign_user,
                        "tenant": tenant_b,
                        "entra": uuid4(),
                        "name": "Foreign",
                        "email": "foreign.invalid",
                    },
                ],
            )
            connection.execute(
                text("""INSERT INTO projects
                (id,tenant_id,workspace_id,name,owner_user_id,retention_policy_ref,transcript_approval_policy_ref)
                VALUES (:id,:tenant,:workspace,'RLS fixture',:owner,'synthetic',
                  'controlled-cleanup-v2')"""),
                {"id": project, "tenant": tenant_a, "workspace": workspace_a, "owner": owner},
            )
            connection.execute(
                text("""INSERT INTO project_memberships
                (id,tenant_id,workspace_id,project_id,user_id,role,enabled)
                VALUES (:id,:tenant,:workspace,:project,:user,'project_owner',true)"""),
                {
                    "id": membership,
                    "tenant": tenant_a,
                    "workspace": workspace_a,
                    "project": project,
                    "user": owner,
                },
            )
        service = FoundationService(api)
        assert [
            item.project_id
            for item in service.list_projects(_context(owner, tenant_a, workspace_a), 50).items
        ] == [project]
        assert service.list_projects(_context(stranger, tenant_a, workspace_a), 50).items == []
        assert service.list_projects(_context(foreign_user, tenant_b, workspace_b), 50).items == []
        with api.begin() as connection:
            assert connection.execute(text("SELECT count(*) FROM projects")).scalar_one() == 0
    finally:
        api.dispose()
        with admin.begin() as connection:
            connection.execute(
                text("DELETE FROM project_memberships WHERE id=:id"), {"id": membership}
            )
            connection.execute(text("DELETE FROM projects WHERE id=:id"), {"id": project})
            connection.execute(
                text("DELETE FROM users WHERE id IN (:a,:b,:c)"),
                {"a": owner, "b": stranger, "c": foreign_user},
            )
            connection.execute(
                text("DELETE FROM workspaces WHERE id IN (:a,:b)"),
                {"a": workspace_a, "b": workspace_b},
            )
            connection.execute(
                text("DELETE FROM tenants WHERE id IN (:a,:b)"), {"a": tenant_a, "b": tenant_b}
            )
        admin.dispose()
