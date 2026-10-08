"""First-class durable ingestion workflow and immutable upload chunks.

Revision ID: 0008_ingestion_workflow
Revises: 0007_account_profiles
Create Date: 2026-09-25
"""

from alembic import op

revision = "0008_ingestion_workflow"
down_revision = "0007_account_profiles"
branch_labels = None
depends_on = None


def _scoped_table(table: str) -> None:
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"""CREATE POLICY {table}_access_policy ON {table}
        USING (
          verelo_project_member(tenant_id, workspace_id, project_id)
          OR verelo_service_granted(tenant_id, workspace_id, project_id)
        )
        WITH CHECK (
          verelo_project_member(tenant_id, workspace_id, project_id)
          OR verelo_service_granted(tenant_id, workspace_id, project_id)
        )"""
    )


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE ingestions (
          id uuid PRIMARY KEY,
          tenant_id uuid NOT NULL,
          workspace_id uuid NOT NULL,
          project_id uuid NOT NULL,
          document_id uuid NOT NULL,
          created_by uuid NOT NULL,
          source_kind text NOT NULL CHECK (source_kind IN ('audio','transcript')),
          original_filename varchar(500) NOT NULL CHECK (original_filename ~ '\\S'),
          declared_media_type varchar(100) NOT NULL,
          expected_byte_length bigint NOT NULL CHECK (expected_byte_length > 0),
          expected_sha256 char(64) NOT NULL CHECK (expected_sha256 ~ '^[0-9a-f]{64}$'),
          uploaded_bytes bigint NOT NULL DEFAULT 0 CHECK (uploaded_bytes >= 0),
          acknowledged_chunks integer NOT NULL DEFAULT 0 CHECK (acknowledged_chunks >= 0),
          source_asset_id uuid NULL,
          draft_version_id uuid NULL,
          state text NOT NULL DEFAULT 'source_pending' CHECK (state IN (
            'source_pending','quarantined','source_accepted','transcription_queued',
            'transcription_submitted','transcription_processing','raw_transcript_stored',
            'draft_ready','approval_required','approved','publishing','published',
            'failed_retryable','failed_terminal','aborted')),
          stage text NOT NULL DEFAULT 'upload' CHECK (stage IN (
            'upload','quarantine','transcription','cleanup','approval','publication')),
          gap_count integer NOT NULL DEFAULT 0 CHECK (gap_count >= 0),
          retryable boolean NOT NULL DEFAULT false,
          safe_error_code varchar(100) NULL,
          operation_key varchar(200) NOT NULL,
          payload_hash char(64) NOT NULL CHECK (payload_hash ~ '^[0-9a-f]{64}$'),
          revision bigint NOT NULL DEFAULT 1 CHECK (revision >= 1),
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now(),
          UNIQUE (tenant_id, workspace_id, project_id, operation_key),
          UNIQUE (tenant_id, workspace_id, project_id, id),
          FOREIGN KEY (tenant_id, workspace_id, project_id, document_id)
            REFERENCES documents(tenant_id, workspace_id, project_id, id) ON DELETE RESTRICT,
          FOREIGN KEY (tenant_id, created_by) REFERENCES users(tenant_id, id) ON DELETE RESTRICT,
          FOREIGN KEY (tenant_id, workspace_id, project_id, source_asset_id)
            REFERENCES source_assets(tenant_id, workspace_id, project_id, id) ON DELETE RESTRICT,
          FOREIGN KEY (tenant_id, workspace_id, project_id, document_id, draft_version_id)
            REFERENCES transcript_versions(tenant_id, workspace_id, project_id, document_id, id)
            ON DELETE RESTRICT
        );
        CREATE INDEX ingestions_document_created_idx
          ON ingestions (document_id, created_at DESC, id DESC);
        CREATE INDEX ingestions_work_idx
          ON ingestions (state, updated_at, id)
          WHERE state IN ('source_accepted','transcription_queued','transcription_submitted',
                          'transcription_processing','raw_transcript_stored','publishing',
                          'failed_retryable');

        CREATE TABLE ingestion_chunks (
          id uuid PRIMARY KEY,
          tenant_id uuid NOT NULL,
          workspace_id uuid NOT NULL,
          project_id uuid NOT NULL,
          ingestion_id uuid NOT NULL,
          sequence integer NOT NULL CHECK (sequence > 0),
          object_ref text NOT NULL,
          byte_length bigint NOT NULL CHECK (byte_length > 0),
          sha256 char(64) NOT NULL CHECK (sha256 ~ '^[0-9a-f]{64}$'),
          created_at timestamptz NOT NULL DEFAULT now(),
          UNIQUE (tenant_id, workspace_id, project_id, ingestion_id, sequence),
          UNIQUE (tenant_id, workspace_id, project_id, id),
          FOREIGN KEY (tenant_id, workspace_id, project_id, ingestion_id)
            REFERENCES ingestions(tenant_id, workspace_id, project_id, id) ON DELETE RESTRICT
        );

        ALTER TABLE capture_sessions ADD COLUMN ingestion_id uuid NULL;
        ALTER TABLE capture_sessions ADD CONSTRAINT capture_sessions_ingestion_fk
          FOREIGN KEY (tenant_id, workspace_id, project_id, ingestion_id)
          REFERENCES ingestions(tenant_id, workspace_id, project_id, id) ON DELETE RESTRICT;
        ALTER TABLE raw_transcripts ADD COLUMN ingestion_id uuid NULL;
        ALTER TABLE raw_transcripts ADD CONSTRAINT raw_transcripts_ingestion_fk
          FOREIGN KEY (tenant_id, workspace_id, project_id, ingestion_id)
          REFERENCES ingestions(tenant_id, workspace_id, project_id, id) ON DELETE RESTRICT;
        """
    )
    _scoped_table("ingestions")
    _scoped_table("ingestion_chunks")
    op.execute(
        """
        DO $grants$ BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='verelo_api') THEN
            GRANT SELECT, INSERT, UPDATE ON ingestions TO verelo_api;
            GRANT SELECT, INSERT ON ingestion_chunks TO verelo_api;
            GRANT UPDATE (ingestion_id,updated_at) ON capture_sessions TO verelo_api;
            GRANT UPDATE (state,published_at) ON transcript_versions TO verelo_api;
          END IF;
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='verelo_worker') THEN
            GRANT SELECT, INSERT, UPDATE ON ingestions TO verelo_worker;
            GRANT SELECT ON ingestion_chunks TO verelo_worker;
            GRANT INSERT ON source_assets,raw_transcripts,transcript_versions,
              transcript_approvals,passages,outbox_events,jobs,audit_events TO verelo_worker;
            GRANT UPDATE (state,published_at) ON transcript_versions TO verelo_worker;
            GRANT UPDATE (active_transcript_version_id,updated_at) ON documents TO verelo_worker;
          END IF;
        END $grants$;
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE raw_transcripts DROP CONSTRAINT raw_transcripts_ingestion_fk")
    op.execute("ALTER TABLE raw_transcripts DROP COLUMN ingestion_id")
    op.execute("ALTER TABLE capture_sessions DROP CONSTRAINT capture_sessions_ingestion_fk")
    op.execute("ALTER TABLE capture_sessions DROP COLUMN ingestion_id")
    op.execute("DROP TABLE ingestion_chunks")
    op.execute("DROP TABLE ingestions")
