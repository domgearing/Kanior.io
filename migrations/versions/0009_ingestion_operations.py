"""Durable idempotency records for ingestion workflow operations.

Revision ID: 0009_ingestion_operations
Revises: 0008_ingestion_workflow
Create Date: 2026-09-25
"""

from alembic import op

revision = "0009_ingestion_operations"
down_revision = "0008_ingestion_workflow"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE ingestion_operations (
          id uuid PRIMARY KEY,
          tenant_id uuid NOT NULL,
          workspace_id uuid NOT NULL,
          project_id uuid NOT NULL,
          ingestion_id uuid NOT NULL,
          action varchar(64) NOT NULL CHECK (action IN (
            'upload_finalize','transcription_submit','raw_result_store','cleanup_generate',
            'automatic_approval','publication','retry','abort')),
          operation_key varchar(200) NOT NULL,
          payload_hash char(64) NOT NULL CHECK (payload_hash ~ '^[0-9a-f]{64}$'),
          outcome_ref text NULL,
          created_at timestamptz NOT NULL DEFAULT now(),
          UNIQUE (tenant_id,workspace_id,project_id,action,operation_key),
          UNIQUE (tenant_id,workspace_id,project_id,id),
          FOREIGN KEY (tenant_id,workspace_id,project_id,ingestion_id)
            REFERENCES ingestions(tenant_id,workspace_id,project_id,id) ON DELETE RESTRICT
        );
        CREATE INDEX ingestion_operations_ingestion_idx
          ON ingestion_operations (ingestion_id,created_at,id);
        ALTER TABLE ingestion_operations ENABLE ROW LEVEL SECURITY;
        ALTER TABLE ingestion_operations FORCE ROW LEVEL SECURITY;
        CREATE POLICY ingestion_operations_access_policy ON ingestion_operations
        USING (
          verelo_project_member(tenant_id,workspace_id,project_id)
          OR verelo_service_granted(tenant_id,workspace_id,project_id)
        )
        WITH CHECK (
          verelo_project_member(tenant_id,workspace_id,project_id)
          OR verelo_service_granted(tenant_id,workspace_id,project_id)
        );
        DO $grants$ BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='verelo_api') THEN
            GRANT SELECT,INSERT,UPDATE (outcome_ref) ON ingestion_operations TO verelo_api;
          END IF;
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='verelo_worker') THEN
            GRANT SELECT,INSERT,UPDATE (outcome_ref) ON ingestion_operations TO verelo_worker;
          END IF;
        END $grants$;
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE ingestion_operations")
