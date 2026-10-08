"""Resolve Entra sessions through the private enabled-user index under forced RLS.

Revision ID: 0014_entra_session_rls
Revises: 0013_entra_auth_code
"""

from alembic import op

revision = "0014_entra_session_rls"
down_revision = "0013_entra_auth_code"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION verelo_create_entra_session(
          p_entra_tenant uuid,p_entra_oid uuid,p_session_id uuid,
          p_session_sha256 text,p_csrf_token text,p_csrf_sha256 text
        ) RETURNS boolean LANGUAGE plpgsql VOLATILE SECURITY DEFINER
        SET search_path=pg_catalog,public AS $$
        DECLARE account record;
        BEGIN
          SELECT i.tenant_id,i.workspace_id,i.user_id INTO account
          FROM public.tenants t JOIN public.identity_accounts i
            ON i.tenant_id=t.id AND i.provider='entra' AND i.subject=p_entra_oid::text
          JOIN public.user_session_state s ON s.tenant_id=i.tenant_id AND s.user_id=i.user_id
          WHERE t.entra_tenant_id=p_entra_tenant AND i.enabled AND s.enabled
          LIMIT 1;
          IF account.user_id IS NULL THEN RETURN false; END IF;
          INSERT INTO public.sessions
            (id,tenant_id,workspace_id,user_id,token_sha256,csrf_token,csrf_sha256,
             idle_expires_at,absolute_expires_at)
          VALUES (p_session_id,account.tenant_id,account.workspace_id,account.user_id,
            p_session_sha256,p_csrf_token,p_csrf_sha256,
            now()+interval '30 minutes',now()+interval '8 hours');
          RETURN true;
        END $$;
        """
    )


def downgrade() -> None:
    raise RuntimeError("Entra session RLS correction cannot be safely removed")
