"""Map Recall uploads to captures and durably queue completed recordings.

Revision ID: 0011_recall_ingestion
Revises: 0010_recall_webhook_events
Create Date: 2026-10-08
"""

from alembic import op

revision = "0011_recall_ingestion"
down_revision = "0010_recall_webhook_events"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE recall_uploads (
          sdk_upload_id text PRIMARY KEY,
          tenant_id uuid NOT NULL,
          workspace_id uuid NOT NULL,
          project_id uuid NOT NULL,
          capture_session_id uuid NOT NULL,
          operation_key varchar(200) NOT NULL,
          created_at timestamptz NOT NULL DEFAULT now(),
          UNIQUE (tenant_id, workspace_id, project_id, capture_session_id),
          UNIQUE (tenant_id, workspace_id, project_id, operation_key),
          FOREIGN KEY (tenant_id, workspace_id, project_id, capture_session_id)
            REFERENCES capture_sessions(tenant_id, workspace_id, project_id, id)
            ON DELETE RESTRICT
        );
        ALTER TABLE recall_uploads ENABLE ROW LEVEL SECURITY;
        ALTER TABLE recall_uploads FORCE ROW LEVEL SECURITY;
        CREATE POLICY recall_uploads_access_policy ON recall_uploads
        USING (
          verelo_project_member(tenant_id, workspace_id, project_id)
          OR verelo_service_granted(tenant_id, workspace_id, project_id)
        )
        WITH CHECK (
          verelo_project_member(tenant_id, workspace_id, project_id)
          OR verelo_service_granted(tenant_id, workspace_id, project_id)
        );
        DO $grants$ BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='verelo_api') THEN
            GRANT SELECT,INSERT ON recall_uploads TO verelo_api;
          END IF;
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='verelo_worker') THEN
            GRANT SELECT ON recall_uploads TO verelo_worker;
            GRANT INSERT ON source_assets,ingestions TO verelo_worker;
            GRANT UPDATE (state,ingestion_id,updated_at) ON capture_sessions TO verelo_worker;
          END IF;
        END $grants$;
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE recall_uploads")
