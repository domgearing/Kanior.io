"""Durable Recall webhook deduplication and capture provider references.

Revision ID: 0010_recall_webhook_events
Revises: 0009_ingestion_operations
Create Date: 2026-10-08
"""

from alembic import op

revision = "0010_recall_webhook_events"
down_revision = "0009_ingestion_operations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE recall_webhook_events (
          event_id text PRIMARY KEY,
          event_type text NOT NULL CHECK (event_type IN (
            'sdk_upload.complete','sdk_upload.failed','sdk_upload.uploading')),
          sdk_upload_id text NOT NULL,
          recording_id text NULL,
          body_sha256 char(64) NOT NULL CHECK (body_sha256 ~ '^[0-9a-f]{64}$'),
          received_at timestamptz NOT NULL DEFAULT now(),
          UNIQUE (event_id,body_sha256)
        );
        CREATE INDEX recall_webhook_recording_idx
          ON recall_webhook_events (recording_id,received_at)
          WHERE recording_id IS NOT NULL;
        DO $grants$ BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='verelo_api') THEN
            GRANT SELECT,INSERT ON recall_webhook_events TO verelo_api;
          END IF;
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='verelo_worker') THEN
            GRANT SELECT ON recall_webhook_events TO verelo_worker;
          END IF;
        END $grants$;
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE recall_webhook_events")

