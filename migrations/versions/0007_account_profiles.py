"""Account profile editing permission.

Revision ID: 0007_account_profiles
Revises: 0006_magic_link_identity
Create Date: 2026-09-21
"""

from alembic import op

revision = "0007_account_profiles"
down_revision = "0006_magic_link_identity"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        DO $grants$ BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='verelo_api') THEN
            GRANT UPDATE (display_name,updated_at) ON users TO verelo_api;
          END IF;
        END $grants$;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DO $grants$ BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='verelo_api') THEN
            REVOKE UPDATE (display_name,updated_at) ON users FROM verelo_api;
          END IF;
        END $grants$;
        DROP FUNCTION IF EXISTS verelo_lookup_enabled_magic_user(text);
        """
    )
