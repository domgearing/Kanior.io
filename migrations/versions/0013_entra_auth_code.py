"""Single-use Entra auth-code flows and restricted session issuance.

Revision ID: 0013_entra_auth_code
Revises: 0012_recall_worker_capture_read
"""

from alembic import op

revision = "0013_entra_auth_code"
down_revision = "0012_recall_worker_capture_read"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE entra_auth_flows (
          state_sha256 char(64) PRIMARY KEY,
          browser_sha256 char(64) NOT NULL,
          flow jsonb NOT NULL,
          expires_at timestamptz NOT NULL DEFAULT now() + interval '10 minutes'
        );
        REVOKE ALL ON entra_auth_flows FROM PUBLIC;

        CREATE FUNCTION verelo_begin_entra_flow(
          p_state_sha256 text, p_browser_sha256 text, p_flow jsonb
        ) RETURNS void LANGUAGE plpgsql VOLATILE SECURITY DEFINER
        SET search_path=pg_catalog,public AS $$
        BEGIN
          DELETE FROM public.entra_auth_flows WHERE expires_at <= now();
          INSERT INTO public.entra_auth_flows(state_sha256,browser_sha256,flow)
          VALUES (p_state_sha256,p_browser_sha256,p_flow);
        END $$;

        CREATE FUNCTION verelo_take_entra_flow(
          p_state_sha256 text, p_browser_sha256 text
        ) RETURNS jsonb LANGUAGE plpgsql VOLATILE SECURITY DEFINER
        SET search_path=pg_catalog,public AS $$
        DECLARE saved jsonb;
        BEGIN
          DELETE FROM public.entra_auth_flows
          WHERE state_sha256=p_state_sha256 AND browser_sha256=p_browser_sha256
            AND expires_at>now()
          RETURNING flow INTO saved;
          RETURN saved;
        END $$;

        CREATE FUNCTION verelo_create_entra_session(
          p_entra_tenant uuid,p_entra_oid uuid,p_session_id uuid,
          p_session_sha256 text,p_csrf_token text,p_csrf_sha256 text
        ) RETURNS boolean LANGUAGE plpgsql VOLATILE SECURITY DEFINER
        SET search_path=pg_catalog,public AS $$
        DECLARE account record;
        BEGIN
          SELECT i.tenant_id,i.workspace_id,i.user_id INTO account
          FROM public.tenants t JOIN public.identity_accounts i
            ON i.tenant_id=t.id AND i.provider='entra' AND i.subject=p_entra_oid::text
          JOIN public.users u ON u.tenant_id=i.tenant_id AND u.id=i.user_id
          JOIN public.user_session_state s ON s.tenant_id=u.tenant_id AND s.user_id=u.id
          WHERE t.entra_tenant_id=p_entra_tenant AND i.enabled AND s.enabled
            AND u.entra_object_id=p_entra_oid
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

        REVOKE ALL ON FUNCTION verelo_begin_entra_flow(text,text,jsonb) FROM PUBLIC;
        REVOKE ALL ON FUNCTION verelo_take_entra_flow(text,text) FROM PUBLIC;
        REVOKE ALL ON FUNCTION
          verelo_create_entra_session(uuid,uuid,uuid,text,text,text) FROM PUBLIC;
        DO $grants$ BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='verelo_api') THEN
            GRANT EXECUTE ON FUNCTION verelo_begin_entra_flow(text,text,jsonb) TO verelo_api;
            GRANT EXECUTE ON FUNCTION verelo_take_entra_flow(text,text) TO verelo_api;
            GRANT EXECUTE ON FUNCTION verelo_create_entra_session(uuid,uuid,uuid,text,text,text)
              TO verelo_api;
          END IF;
        END $grants$;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP FUNCTION verelo_create_entra_session(uuid,uuid,uuid,text,text,text);
        DROP FUNCTION verelo_take_entra_flow(text,text);
        DROP FUNCTION verelo_begin_entra_flow(text,text,jsonb);
        DROP TABLE entra_auth_flows;
        """
    )
