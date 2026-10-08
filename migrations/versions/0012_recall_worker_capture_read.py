"""Allow the scoped worker to resolve mapped Recall capture sessions.

Revision ID: 0012_recall_worker_capture_read
Revises: 0011_recall_ingestion
Create Date: 2026-10-08
"""

from alembic import op

revision = "0012_recall_worker_capture_read"
down_revision = "0011_recall_ingestion"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        DO $grants$ BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='verelo_worker') THEN
            GRANT SELECT ON capture_sessions TO verelo_worker;
          END IF;
        END $grants$;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DO $grants$ BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='verelo_worker') THEN
            REVOKE SELECT ON capture_sessions FROM verelo_worker;
          END IF;
        END $grants$;
        """
    )
