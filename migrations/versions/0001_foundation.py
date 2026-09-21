"""Foundation tenant, project, document, audit and outbox baseline.

Revision ID: 0001_foundation
Revises:
Create Date: 2026-09-17
"""

from alembic import op

revision = "0001_foundation"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute(
        """
        CREATE TABLE tenants (
            id uuid PRIMARY KEY, created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(), entra_tenant_id uuid NOT NULL UNIQUE,
            policy_config_ref text NOT NULL, region text NOT NULL
        )
        """
    )
    op.execute(
        """
        CREATE TABLE workspaces (
            id uuid PRIMARY KEY, tenant_id uuid NOT NULL, created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(), name varchar(200) NOT NULL CHECK (name ~ '\\S'),
            is_default boolean NOT NULL DEFAULT false, UNIQUE (tenant_id, id),
            FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE RESTRICT
        );
        CREATE UNIQUE INDEX workspaces_one_default_per_tenant ON workspaces (tenant_id) WHERE is_default
        """
    )
    op.execute(
        """
        CREATE TABLE users (
            id uuid PRIMARY KEY, tenant_id uuid NOT NULL, created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(), entra_object_id uuid NOT NULL,
            display_name varchar(200) NOT NULL CHECK (display_name ~ '\\S'), email varchar(320) NOT NULL,
            enabled boolean NOT NULL DEFAULT true, authorization_epoch bigint NOT NULL DEFAULT 0
                CHECK (authorization_epoch >= 0),
            UNIQUE (tenant_id, id), UNIQUE (tenant_id, entra_object_id),
            FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE RESTRICT
        )
        """
    )
    op.execute(
        """
        CREATE TABLE projects (
            id uuid PRIMARY KEY, tenant_id uuid NOT NULL, workspace_id uuid NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
            name varchar(200) NOT NULL CHECK (name ~ '\\S'), owner_user_id uuid NOT NULL,
            retention_policy_ref text NOT NULL, transcript_approval_policy_ref text NOT NULL,
            authorization_epoch bigint NOT NULL DEFAULT 0 CHECK (authorization_epoch >= 0),
            state text NOT NULL DEFAULT 'active' CHECK (state IN ('active', 'tombstoned')),
            UNIQUE (tenant_id, id), UNIQUE (tenant_id, workspace_id, id),
            FOREIGN KEY (tenant_id, workspace_id) REFERENCES workspaces(tenant_id, id) ON DELETE RESTRICT,
            FOREIGN KEY (tenant_id, owner_user_id) REFERENCES users(tenant_id, id) ON DELETE RESTRICT
        );
        CREATE INDEX projects_scope_list_idx ON projects (tenant_id, workspace_id, created_at, id)
        """
    )
    op.execute(
        """
        CREATE TABLE project_memberships (
            id uuid PRIMARY KEY, tenant_id uuid NOT NULL, workspace_id uuid NOT NULL, project_id uuid NOT NULL,
            user_id uuid NOT NULL, created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(), role text NOT NULL
                CHECK (role IN ('reader', 'contributor', 'project_owner')),
            enabled boolean NOT NULL DEFAULT true, revision bigint NOT NULL DEFAULT 1 CHECK (revision >= 1),
            UNIQUE (tenant_id, id), UNIQUE (tenant_id, workspace_id, project_id, id),
            UNIQUE (tenant_id, project_id, user_id),
            FOREIGN KEY (tenant_id, workspace_id, project_id)
                REFERENCES projects(tenant_id, workspace_id, id) ON DELETE RESTRICT,
            FOREIGN KEY (tenant_id, user_id) REFERENCES users(tenant_id, id) ON DELETE RESTRICT
        );
        CREATE INDEX project_memberships_access_idx
            ON project_memberships (tenant_id, user_id, enabled, project_id)
        """
    )
    op.execute(
        """
        CREATE TABLE documents (
            id uuid PRIMARY KEY, tenant_id uuid NOT NULL, workspace_id uuid NOT NULL, project_id uuid NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
            title varchar(300) NOT NULL CHECK (title ~ '\\S'), meeting_date timestamptz NOT NULL,
            language varchar(35) NOT NULL, created_by uuid NOT NULL, consent_policy_version varchar(100) NOT NULL,
            consent_acknowledged_by uuid NOT NULL, consent_acknowledged_at timestamptz NOT NULL,
            state text NOT NULL DEFAULT 'created' CHECK (state IN ('created', 'tombstoned')),
            UNIQUE (tenant_id, id), UNIQUE (tenant_id, workspace_id, project_id, id),
            FOREIGN KEY (tenant_id, workspace_id, project_id)
                REFERENCES projects(tenant_id, workspace_id, id) ON DELETE RESTRICT,
            FOREIGN KEY (tenant_id, created_by) REFERENCES users(tenant_id, id) ON DELETE RESTRICT,
            FOREIGN KEY (tenant_id, consent_acknowledged_by) REFERENCES users(tenant_id, id) ON DELETE RESTRICT
        );
        CREATE INDEX documents_scope_list_idx ON documents (tenant_id, workspace_id, project_id, created_at, id)
        """
    )
    op.execute(
        """
        CREATE TABLE audit_events (
            id uuid PRIMARY KEY, tenant_id uuid NOT NULL, workspace_id uuid NULL, project_id uuid NULL,
            document_id uuid NULL, actor_kind text NOT NULL CHECK (actor_kind IN ('employee', 'service')),
            actor_id uuid NOT NULL, action text NOT NULL, outcome text NOT NULL CHECK (outcome IN ('allowed', 'denied')),
            request_id varchar(128) NOT NULL, authorization_epoch bigint NOT NULL CHECK (authorization_epoch >= 0),
            occurred_at timestamptz NOT NULL, created_at timestamptz NOT NULL DEFAULT now(),
            CHECK ((project_id IS NULL OR workspace_id IS NOT NULL) AND
                   (document_id IS NULL OR (workspace_id IS NOT NULL AND project_id IS NOT NULL))),
            UNIQUE (tenant_id, id),
            FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE RESTRICT,
            FOREIGN KEY (tenant_id, workspace_id) REFERENCES workspaces(tenant_id, id) ON DELETE RESTRICT,
            FOREIGN KEY (tenant_id, workspace_id, project_id)
                REFERENCES projects(tenant_id, workspace_id, id) ON DELETE RESTRICT,
            FOREIGN KEY (tenant_id, workspace_id, project_id, document_id)
                REFERENCES documents(tenant_id, workspace_id, project_id, id) ON DELETE RESTRICT
        );
        CREATE INDEX audit_events_scope_time_idx ON audit_events (tenant_id, workspace_id, project_id, occurred_at)
        """
    )
    op.execute(
        """
        CREATE TABLE outbox_events (
            id uuid PRIMARY KEY, tenant_id uuid NOT NULL, workspace_id uuid NOT NULL, project_id uuid NOT NULL,
            document_id uuid NULL, aggregate_id uuid NOT NULL, event_type text NOT NULL,
            schema_version integer NOT NULL CHECK (schema_version > 0), payload jsonb NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(), dispatched_at timestamptz NULL,
            UNIQUE (tenant_id, id),
            FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE RESTRICT,
            FOREIGN KEY (tenant_id, workspace_id) REFERENCES workspaces(tenant_id, id) ON DELETE RESTRICT,
            FOREIGN KEY (tenant_id, workspace_id, project_id)
                REFERENCES projects(tenant_id, workspace_id, id) ON DELETE RESTRICT,
            FOREIGN KEY (tenant_id, workspace_id, project_id, document_id)
                REFERENCES documents(tenant_id, workspace_id, project_id, id) ON DELETE RESTRICT
        );
        CREATE INDEX outbox_events_pending_idx ON outbox_events (created_at) WHERE dispatched_at IS NULL
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION kanior_current_uuid(setting_name text) RETURNS uuid
        LANGUAGE sql STABLE AS $$ SELECT NULLIF(current_setting(setting_name, true), '')::uuid $$;
        CREATE OR REPLACE FUNCTION kanior_scope_allows(row_tenant uuid, row_workspace uuid) RETURNS boolean
        LANGUAGE sql STABLE AS $$
            SELECT kanior_current_uuid('app.tenant_id') = row_tenant
               AND kanior_current_uuid('app.workspace_id') = row_workspace
        $$;
        """
    )
    for table in ("workspaces", "users", "projects", "project_memberships", "documents", "audit_events", "outbox_events"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        workspace_column = "workspace_id"
        if table in {"users"}:
            policy = "kanior_current_uuid('app.tenant_id') = tenant_id"
        elif table == "workspaces":
            policy = "kanior_current_uuid('app.tenant_id') = tenant_id"
        else:
            policy = f"kanior_scope_allows(tenant_id, {workspace_column})"
        op.execute(f"CREATE POLICY {table}_scope_policy ON {table} USING ({policy}) WITH CHECK ({policy})")


def downgrade() -> None:
    for table in ("outbox_events", "audit_events", "documents", "project_memberships", "projects", "users", "workspaces", "tenants"):
        op.execute(f"DROP TABLE {table}")
    op.execute("DROP FUNCTION IF EXISTS kanior_scope_allows(uuid, uuid)")
    op.execute("DROP FUNCTION IF EXISTS kanior_current_uuid(text)")
