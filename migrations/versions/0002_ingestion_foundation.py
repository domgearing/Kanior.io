"""Durable jobs and synthetic Phase 2 ingestion persistence.

Revision ID: 0002_ingestion_foundation
Revises: 0001_foundation
Create Date: 2026-09-21
"""

from alembic import op

revision = "0002_ingestion_foundation"
down_revision = "0001_foundation"
branch_labels = None
depends_on = None


def _scoped_table(table: str) -> None:
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"""CREATE POLICY {table}_scope_policy ON {table}
        USING (
          verelo_scope_allows(tenant_id, workspace_id)
          AND NULLIF(current_setting('app.project_id', true), '')::uuid = project_id
        )
        WITH CHECK (
          verelo_scope_allows(tenant_id, workspace_id)
          AND NULLIF(current_setting('app.project_id', true), '')::uuid = project_id
        )"""
    )


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE service_identities (
          id uuid PRIMARY KEY, tenant_id uuid NOT NULL, name varchar(200) NOT NULL,
          enabled boolean NOT NULL DEFAULT true, created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now(), UNIQUE (tenant_id, id),
          FOREIGN KEY (tenant_id) REFERENCES tenants(id) ON DELETE RESTRICT
        );
        CREATE TABLE service_grants (
          id uuid PRIMARY KEY, tenant_id uuid NOT NULL, workspace_id uuid NOT NULL,
          project_id uuid NOT NULL, service_identity_id uuid NOT NULL, action varchar(100) NOT NULL,
          enabled boolean NOT NULL DEFAULT true, revision bigint NOT NULL DEFAULT 1 CHECK (revision >= 1),
          created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
          UNIQUE (tenant_id, workspace_id, project_id, service_identity_id, action),
          UNIQUE (tenant_id, workspace_id, project_id, id),
          FOREIGN KEY (tenant_id, workspace_id, project_id)
            REFERENCES projects(tenant_id, workspace_id, id) ON DELETE RESTRICT,
          FOREIGN KEY (tenant_id, service_identity_id)
            REFERENCES service_identities(tenant_id, id) ON DELETE RESTRICT
        )
        """
    )
    op.execute(
        """
        CREATE TABLE jobs (
          id uuid PRIMARY KEY, tenant_id uuid NOT NULL, workspace_id uuid NOT NULL,
          project_id uuid NOT NULL, document_id uuid NULL, job_type varchar(100) NOT NULL,
          operation_key varchar(300) NOT NULL, payload_hash char(64) NOT NULL,
          payload jsonb NOT NULL DEFAULT '{}'::jsonb,
          status text NOT NULL DEFAULT 'pending'
            CHECK (status IN ('pending','leased','retry','succeeded','failed','dead_letter')),
          attempt integer NOT NULL DEFAULT 0 CHECK (attempt >= 0),
          max_attempts integer NOT NULL DEFAULT 8 CHECK (max_attempts > 0),
          lease_owner varchar(200) NULL, lease_until timestamptz NULL,
          next_attempt_at timestamptz NOT NULL DEFAULT now(), provider_ref text NULL,
          outcome_known boolean NOT NULL DEFAULT true, safe_error_code varchar(100) NULL,
          trace_id varchar(128) NOT NULL, created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now(),
          UNIQUE (tenant_id, workspace_id, project_id, operation_key),
          UNIQUE (tenant_id, workspace_id, project_id, id),
          FOREIGN KEY (tenant_id, workspace_id, project_id)
            REFERENCES projects(tenant_id, workspace_id, id) ON DELETE RESTRICT,
          FOREIGN KEY (tenant_id, workspace_id, project_id, document_id)
            REFERENCES documents(tenant_id, workspace_id, project_id, id) ON DELETE RESTRICT
        );
        CREATE INDEX jobs_claim_idx ON jobs (next_attempt_at, created_at, id)
          WHERE status IN ('pending','retry')
        """
    )
    op.execute(
        """
        CREATE TABLE capture_sessions (
          id uuid PRIMARY KEY, tenant_id uuid NOT NULL, workspace_id uuid NOT NULL,
          project_id uuid NOT NULL, document_id uuid NOT NULL, created_by uuid NOT NULL,
          state text NOT NULL DEFAULT 'created'
            CHECK (state IN ('created','recording','paused','interrupted','finalizing','uploading','complete','failed','aborted')),
          acknowledged_chunks integer NOT NULL DEFAULT 0 CHECK (acknowledged_chunks >= 0),
          gaps jsonb NOT NULL DEFAULT '[]'::jsonb, provider_ref text NULL,
          created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
          UNIQUE (tenant_id, workspace_id, project_id, id),
          FOREIGN KEY (tenant_id, workspace_id, project_id, document_id)
            REFERENCES documents(tenant_id, workspace_id, project_id, id) ON DELETE RESTRICT,
          FOREIGN KEY (tenant_id, created_by) REFERENCES users(tenant_id, id) ON DELETE RESTRICT
        );
        CREATE TABLE capture_chunks (
          id uuid PRIMARY KEY, tenant_id uuid NOT NULL, workspace_id uuid NOT NULL,
          project_id uuid NOT NULL, capture_session_id uuid NOT NULL, sequence integer NOT NULL CHECK (sequence > 0),
          object_ref text NOT NULL, byte_length bigint NOT NULL CHECK (byte_length > 0), sha256 char(64) NOT NULL,
          acknowledged_at timestamptz NOT NULL, created_at timestamptz NOT NULL DEFAULT now(),
          UNIQUE (tenant_id, workspace_id, project_id, capture_session_id, sequence),
          UNIQUE (tenant_id, workspace_id, project_id, id),
          FOREIGN KEY (tenant_id, workspace_id, project_id, capture_session_id)
            REFERENCES capture_sessions(tenant_id, workspace_id, project_id, id) ON DELETE RESTRICT
        );
        CREATE TABLE source_assets (
          id uuid PRIMARY KEY, tenant_id uuid NOT NULL, workspace_id uuid NOT NULL,
          project_id uuid NOT NULL, document_id uuid NOT NULL, capture_session_id uuid NULL,
          kind text NOT NULL CHECK (kind IN ('audio','transcript','capture_metadata')),
          original_filename varchar(500) NULL, detected_mime varchar(200) NOT NULL,
          object_ref text NOT NULL, byte_length bigint NOT NULL CHECK (byte_length > 0), sha256 char(64) NOT NULL,
          duration_ms bigint NULL CHECK (duration_ms IS NULL OR duration_ms >= 0),
          provenance varchar(100) NOT NULL, quarantine_state text NOT NULL
            CHECK (quarantine_state IN ('pending','accepted','rejected')),
          created_at timestamptz NOT NULL DEFAULT now(),
          UNIQUE (tenant_id, workspace_id, project_id, id),
          UNIQUE (tenant_id, workspace_id, project_id, document_id, sha256, kind),
          FOREIGN KEY (tenant_id, workspace_id, project_id, document_id)
            REFERENCES documents(tenant_id, workspace_id, project_id, id) ON DELETE RESTRICT,
          FOREIGN KEY (tenant_id, workspace_id, project_id, capture_session_id)
            REFERENCES capture_sessions(tenant_id, workspace_id, project_id, id) ON DELETE RESTRICT
        )
        """
    )
    op.execute(
        """
        CREATE TABLE raw_transcripts (
          id uuid PRIMARY KEY, tenant_id uuid NOT NULL, workspace_id uuid NOT NULL,
          project_id uuid NOT NULL, document_id uuid NOT NULL, source_asset_id uuid NOT NULL,
          provider varchar(100) NOT NULL, model_id varchar(200) NOT NULL,
          raw_object_ref text NOT NULL, raw_sha256 char(64) NOT NULL,
          parsed_object_ref text NOT NULL, parsed_sha256 char(64) NOT NULL,
          parser_version varchar(100) NOT NULL, created_at timestamptz NOT NULL DEFAULT now(),
          UNIQUE (tenant_id, workspace_id, project_id, id),
          UNIQUE (tenant_id, workspace_id, project_id, document_id, raw_sha256),
          FOREIGN KEY (tenant_id, workspace_id, project_id, document_id)
            REFERENCES documents(tenant_id, workspace_id, project_id, id) ON DELETE RESTRICT,
          FOREIGN KEY (tenant_id, workspace_id, project_id, source_asset_id)
            REFERENCES source_assets(tenant_id, workspace_id, project_id, id) ON DELETE RESTRICT
        );
        CREATE TABLE transcript_versions (
          id uuid PRIMARY KEY, tenant_id uuid NOT NULL, workspace_id uuid NOT NULL,
          project_id uuid NOT NULL, document_id uuid NOT NULL, version_number integer NOT NULL CHECK (version_number > 0),
          parent_version_id uuid NULL, raw_transcript_id uuid NOT NULL,
          canonical_object_ref text NOT NULL, content_sha256 char(64) NOT NULL,
          byte_length bigint NOT NULL CHECK (byte_length >= 0),
          cleanup_status text NOT NULL CHECK (cleanup_status IN ('unchanged','accepted','skipped','human_corrected')),
          cleanup_policy_version varchar(100) NOT NULL, cleanup_manifest jsonb NOT NULL DEFAULT '{}'::jsonb,
          state text NOT NULL DEFAULT 'draft' CHECK (state IN ('draft','approved','published','revoked')),
          created_by uuid NOT NULL, created_at timestamptz NOT NULL DEFAULT now(), published_at timestamptz NULL,
          UNIQUE (tenant_id, workspace_id, project_id, document_id, version_number),
          UNIQUE (tenant_id, workspace_id, project_id, id),
          UNIQUE (tenant_id, workspace_id, project_id, document_id, id),
          FOREIGN KEY (tenant_id, workspace_id, project_id, document_id)
            REFERENCES documents(tenant_id, workspace_id, project_id, id) ON DELETE RESTRICT,
          FOREIGN KEY (tenant_id, workspace_id, project_id, raw_transcript_id)
            REFERENCES raw_transcripts(tenant_id, workspace_id, project_id, id) ON DELETE RESTRICT,
          FOREIGN KEY (tenant_id, workspace_id, project_id, document_id, parent_version_id)
            REFERENCES transcript_versions(tenant_id, workspace_id, project_id, document_id, id) ON DELETE RESTRICT,
          FOREIGN KEY (tenant_id, created_by) REFERENCES users(tenant_id, id) ON DELETE RESTRICT
        );
        CREATE TABLE transcript_approvals (
          id uuid PRIMARY KEY, tenant_id uuid NOT NULL, workspace_id uuid NOT NULL,
          project_id uuid NOT NULL, document_id uuid NOT NULL, transcript_version_id uuid NOT NULL,
          content_sha256 char(64) NOT NULL, method text NOT NULL CHECK (method IN ('controlled_cleanup_policy','person')),
          policy_version varchar(100) NOT NULL, approver_kind text NOT NULL CHECK (approver_kind IN ('employee','service')),
          approver_id uuid NOT NULL, approved_at timestamptz NOT NULL, revoked_at timestamptz NULL,
          reason_code varchar(100) NOT NULL, created_at timestamptz NOT NULL DEFAULT now(),
          UNIQUE (tenant_id, workspace_id, project_id, id),
          UNIQUE (tenant_id, workspace_id, project_id, transcript_version_id, content_sha256, method, policy_version),
          FOREIGN KEY (tenant_id, workspace_id, project_id, document_id, transcript_version_id)
            REFERENCES transcript_versions(tenant_id, workspace_id, project_id, document_id, id) ON DELETE RESTRICT
        );
        CREATE TABLE passages (
          id uuid PRIMARY KEY, tenant_id uuid NOT NULL, workspace_id uuid NOT NULL,
          project_id uuid NOT NULL, document_id uuid NOT NULL, transcript_version_id uuid NOT NULL,
          ordinal integer NOT NULL CHECK (ordinal >= 0), start_byte bigint NOT NULL CHECK (start_byte >= 0),
          end_byte bigint NOT NULL CHECK (end_byte > start_byte), span_sha256 char(64) NOT NULL,
          speaker_label varchar(200) NULL, start_ms bigint NULL, end_ms bigint NULL,
          timing_precision text NOT NULL DEFAULT 'unavailable'
            CHECK (timing_precision IN ('exact','approximate','unavailable')),
          created_at timestamptz NOT NULL DEFAULT now(),
          UNIQUE (tenant_id, workspace_id, project_id, id),
          UNIQUE (tenant_id, workspace_id, project_id, transcript_version_id, ordinal),
          FOREIGN KEY (tenant_id, workspace_id, project_id, document_id, transcript_version_id)
            REFERENCES transcript_versions(tenant_id, workspace_id, project_id, document_id, id) ON DELETE RESTRICT,
          CHECK ((start_ms IS NULL) = (end_ms IS NULL)), CHECK (end_ms IS NULL OR end_ms >= start_ms)
        )
        """
    )
    op.execute(
        """
        ALTER TABLE documents ADD COLUMN active_transcript_version_id uuid NULL;
        ALTER TABLE documents ADD CONSTRAINT documents_active_version_fk
          FOREIGN KEY (tenant_id, workspace_id, project_id, id, active_transcript_version_id)
          REFERENCES transcript_versions(tenant_id, workspace_id, project_id, document_id, id)
          ON DELETE RESTRICT
        """
    )
    for table in (
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
        _scoped_table(table)
    op.execute("ALTER TABLE service_identities ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE service_identities FORCE ROW LEVEL SECURITY")
    op.execute(
        """CREATE POLICY service_identities_tenant_policy ON service_identities
        USING (verelo_current_uuid('app.tenant_id') = tenant_id)
        WITH CHECK (verelo_current_uuid('app.tenant_id') = tenant_id)"""
    )
    # Runtime roles are provisioned outside Alembic in deployed environments.
    # Disposable migration validation intentionally has no such roles.
    op.execute(
        """
        DO $grants$
        BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'verelo_api') THEN
            GRANT SELECT, INSERT, UPDATE ON projects, project_memberships, documents TO verelo_api;
            GRANT SELECT ON tenants, workspaces, users TO verelo_api;
            GRANT INSERT, SELECT ON audit_events, outbox_events TO verelo_api;
            GRANT SELECT, INSERT, UPDATE ON capture_sessions TO verelo_api;
            GRANT SELECT, INSERT ON capture_chunks, source_assets, raw_transcripts,
              transcript_versions, transcript_approvals, passages, jobs TO verelo_api;
            GRANT UPDATE (active_transcript_version_id, updated_at) ON documents TO verelo_api;
          END IF;
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'verelo_worker') THEN
            GRANT SELECT ON service_identities, service_grants TO verelo_worker;
            GRANT SELECT, INSERT, UPDATE ON jobs TO verelo_worker;
            GRANT SELECT, UPDATE (dispatched_at) ON outbox_events TO verelo_worker;
            GRANT SELECT ON projects, documents, source_assets, raw_transcripts,
              transcript_versions, transcript_approvals, passages TO verelo_worker;
          END IF;
        END
        $grants$
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE documents DROP CONSTRAINT documents_active_version_fk")
    op.execute("ALTER TABLE documents DROP COLUMN active_transcript_version_id")
    for table in (
        "passages",
        "transcript_approvals",
        "transcript_versions",
        "raw_transcripts",
        "source_assets",
        "capture_chunks",
        "capture_sessions",
        "jobs",
        "service_grants",
        "service_identities",
    ):
        op.execute(f"DROP TABLE {table}")
