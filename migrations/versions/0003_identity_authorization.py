"""Session boundary, capabilities, and membership-aware RLS.

Revision ID: 0003_identity_authorization
Revises: 0002_ingestion_foundation
Create Date: 2026-09-21
"""

from alembic import op

revision = "0003_identity_authorization"
down_revision = "0002_ingestion_foundation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE user_capabilities (
          id uuid PRIMARY KEY, tenant_id uuid NOT NULL, user_id uuid NOT NULL,
          capability varchar(100) NOT NULL, enabled boolean NOT NULL DEFAULT true,
          created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
          UNIQUE (tenant_id, user_id, capability), UNIQUE (tenant_id, id),
          FOREIGN KEY (tenant_id, user_id) REFERENCES users(tenant_id, id) ON DELETE RESTRICT
        );
        CREATE TABLE sessions (
          id uuid PRIMARY KEY, tenant_id uuid NOT NULL, workspace_id uuid NOT NULL, user_id uuid NOT NULL,
          token_sha256 char(64) NOT NULL UNIQUE, csrf_token varchar(256) NOT NULL,
          csrf_sha256 char(64) NOT NULL,
          created_at timestamptz NOT NULL DEFAULT now(), last_seen_at timestamptz NOT NULL DEFAULT now(),
          idle_expires_at timestamptz NOT NULL, absolute_expires_at timestamptz NOT NULL,
          revoked_at timestamptz NULL, UNIQUE (tenant_id, id),
          FOREIGN KEY (tenant_id, workspace_id) REFERENCES workspaces(tenant_id, id) ON DELETE RESTRICT,
          FOREIGN KEY (tenant_id, user_id) REFERENCES users(tenant_id, id) ON DELETE RESTRICT,
          CHECK (idle_expires_at <= absolute_expires_at)
        );
        CREATE INDEX sessions_token_active_idx ON sessions (token_sha256)
          WHERE revoked_at IS NULL;
        """
    )
    for table in ("user_capabilities", "sessions"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"""CREATE POLICY {table}_tenant_policy ON {table}
            USING (verelo_current_uuid('app.tenant_id') = tenant_id)
            WITH CHECK (verelo_current_uuid('app.tenant_id') = tenant_id)"""
        )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION verelo_enabled_employee(row_tenant uuid, row_user uuid)
        RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER
        SET search_path = pg_catalog, public AS $$
          SELECT current_setting('app.principal_kind', true) = 'employee'
            AND verelo_current_uuid('app.tenant_id') = row_tenant
            AND verelo_current_uuid('app.principal_id') = row_user
            AND EXISTS (SELECT 1 FROM public.users u
              WHERE u.tenant_id = row_tenant AND u.id = row_user AND u.enabled)
        $$;
        CREATE OR REPLACE FUNCTION verelo_project_member(
          row_tenant uuid, row_workspace uuid, row_project uuid
        ) RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER
        SET search_path = pg_catalog, public AS $$
          SELECT verelo_scope_allows(row_tenant, row_workspace)
            AND current_setting('app.principal_kind', true) = 'employee'
            AND EXISTS (
              SELECT 1 FROM public.users u
              JOIN public.project_memberships m
                ON m.tenant_id = u.tenant_id AND m.user_id = u.id
              JOIN public.projects p
                ON p.tenant_id = m.tenant_id AND p.workspace_id = m.workspace_id
               AND p.id = m.project_id
              WHERE u.tenant_id = row_tenant
                AND u.id = verelo_current_uuid('app.principal_id') AND u.enabled
                AND m.workspace_id = row_workspace AND m.project_id = row_project AND m.enabled
                AND p.state = 'active'
            )
        $$;
        CREATE OR REPLACE FUNCTION verelo_service_granted(
          row_tenant uuid, row_workspace uuid, row_project uuid
        ) RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER
        SET search_path = pg_catalog, public AS $$
          SELECT verelo_scope_allows(row_tenant, row_workspace)
            AND current_setting('app.principal_kind', true) = 'service'
            AND EXISTS (
              SELECT 1 FROM public.service_identities s
              JOIN public.service_grants g
                ON g.tenant_id = s.tenant_id AND g.service_identity_id = s.id
              WHERE s.tenant_id = row_tenant
                AND s.id = verelo_current_uuid('app.principal_id') AND s.enabled
                AND g.workspace_id = row_workspace AND g.project_id = row_project AND g.enabled
                AND g.action = current_setting('app.action', true)
            )
        $$;
        CREATE OR REPLACE FUNCTION verelo_resolve_session(p_token_sha256 text)
        RETURNS TABLE (
          session_id uuid, tenant_id uuid, workspace_id uuid, user_id uuid,
          csrf_token varchar(256), csrf_sha256 char(64), authorization_epoch bigint
        ) LANGUAGE sql STABLE SECURITY DEFINER
        SET search_path = pg_catalog, public AS $$
          SELECT s.id, s.tenant_id, s.workspace_id, s.user_id, s.csrf_token, s.csrf_sha256,
                 u.authorization_epoch
          FROM public.sessions s
          JOIN public.users u ON u.tenant_id = s.tenant_id AND u.id = s.user_id
          WHERE s.token_sha256 = p_token_sha256 AND s.revoked_at IS NULL
            AND s.idle_expires_at > now() AND s.absolute_expires_at > now()
            AND u.enabled
          LIMIT 1
        $$;
        REVOKE ALL ON FUNCTION verelo_enabled_employee(uuid, uuid) FROM PUBLIC;
        REVOKE ALL ON FUNCTION verelo_project_member(uuid, uuid, uuid) FROM PUBLIC;
        REVOKE ALL ON FUNCTION verelo_service_granted(uuid, uuid, uuid) FROM PUBLIC;
        REVOKE ALL ON FUNCTION verelo_resolve_session(text) FROM PUBLIC;
        """
    )
    # Replace broad workspace-only content policies with current membership or
    # explicitly provisioned worker-action grants. Project INSERT remains
    # possible for the authenticated owner; service code creates membership in
    # the same transaction before subsequent reads.
    op.execute("DROP POLICY projects_scope_policy ON projects")
    op.execute(
        """CREATE POLICY projects_access_policy ON projects
        USING (verelo_project_member(tenant_id, workspace_id, id))
        WITH CHECK (
          verelo_project_member(tenant_id, workspace_id, id)
          OR (verelo_scope_allows(tenant_id, workspace_id)
              AND owner_user_id = verelo_current_uuid('app.principal_id'))
        )"""
    )
    op.execute("DROP POLICY project_memberships_scope_policy ON project_memberships")
    op.execute(
        """CREATE POLICY project_memberships_access_policy ON project_memberships
        USING (verelo_project_member(tenant_id, workspace_id, project_id))
        WITH CHECK (
          verelo_project_member(tenant_id, workspace_id, project_id)
          OR (user_id = verelo_current_uuid('app.principal_id') AND EXISTS (
            SELECT 1 FROM projects p WHERE p.tenant_id = tenant_id
              AND p.workspace_id = workspace_id AND p.id = project_id
              AND p.owner_user_id = user_id
          ))
        )"""
    )
    for table in (
        "documents",
        "audit_events",
        "outbox_events",
        "service_grants",
        "jobs",
        "capture_sessions",
        "capture_chunks",
        "source_assets",
        "raw_transcripts",
        "transcript_versions",
        "transcript_approvals",
        "passages",
    ):
        old = f"{table}_scope_policy"
        op.execute(f"DROP POLICY {old} ON {table}")
        project_expression = "project_id"
        op.execute(
            f"""CREATE POLICY {table}_access_policy ON {table}
            USING (
              verelo_project_member(tenant_id, workspace_id, {project_expression})
              OR verelo_service_granted(tenant_id, workspace_id, {project_expression})
            )
            WITH CHECK (
              verelo_project_member(tenant_id, workspace_id, {project_expression})
              OR verelo_service_granted(tenant_id, workspace_id, {project_expression})
            )"""
        )
    op.execute(
        """
        DO $grants$
        BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'verelo_api') THEN
            GRANT SELECT ON user_capabilities TO verelo_api;
            GRANT UPDATE (last_seen_at, idle_expires_at, revoked_at) ON sessions TO verelo_api;
            GRANT EXECUTE ON FUNCTION verelo_enabled_employee(uuid, uuid) TO verelo_api;
            GRANT EXECUTE ON FUNCTION verelo_project_member(uuid, uuid, uuid) TO verelo_api;
            GRANT EXECUTE ON FUNCTION verelo_resolve_session(text) TO verelo_api;
          END IF;
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'verelo_worker') THEN
            GRANT EXECUTE ON FUNCTION verelo_service_granted(uuid, uuid, uuid) TO verelo_worker;
          END IF;
        END
        $grants$
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY project_memberships_access_policy ON project_memberships")
    op.execute(
        """CREATE POLICY project_memberships_scope_policy ON project_memberships
        USING (verelo_scope_allows(tenant_id, workspace_id))
        WITH CHECK (verelo_scope_allows(tenant_id, workspace_id))"""
    )
    for table in (
        "documents",
        "audit_events",
        "outbox_events",
        "service_grants",
        "jobs",
        "capture_sessions",
        "capture_chunks",
        "source_assets",
        "raw_transcripts",
        "transcript_versions",
        "transcript_approvals",
        "passages",
    ):
        op.execute(f"DROP POLICY {table}_access_policy ON {table}")
        op.execute(
            f"""CREATE POLICY {table}_scope_policy ON {table}
            USING (verelo_scope_allows(tenant_id, workspace_id))
            WITH CHECK (verelo_scope_allows(tenant_id, workspace_id))"""
        )
    op.execute("DROP POLICY projects_access_policy ON projects")
    op.execute(
        """CREATE POLICY projects_scope_policy ON projects
        USING (verelo_scope_allows(tenant_id, workspace_id))
        WITH CHECK (verelo_scope_allows(tenant_id, workspace_id))"""
    )
    op.execute("DROP FUNCTION verelo_service_granted(uuid, uuid, uuid)")
    op.execute("DROP FUNCTION verelo_resolve_session(text)")
    op.execute("DROP FUNCTION verelo_project_member(uuid, uuid, uuid)")
    op.execute("DROP FUNCTION verelo_enabled_employee(uuid, uuid)")
    op.execute("DROP TABLE sessions")
    op.execute("DROP TABLE user_capabilities")
