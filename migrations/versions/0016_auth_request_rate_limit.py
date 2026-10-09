"""Count issued development challenges, not all authentication events.

Revision ID: 0016_auth_request_rate_limit
Revises: 0015_recorder_remote_control
"""

from alembic import op

revision = "0016_auth_request_rate_limit"
down_revision = "0015_recorder_remote_control"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION verelo_request_magic_link(
          p_challenge_id uuid, p_token_sha256 text, p_email_normalized text,
          p_email_sha256 text, p_source_sha256 text, p_request_id text
        ) RETURNS TABLE (deliver boolean, expires_at timestamptz)
        LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,public AS $$
        DECLARE account record; limited boolean; expiry timestamptz := now()+interval '10 minutes';
        BEGIN
          limited := (
            SELECT count(*) >= 5 FROM public.authentication_events
            WHERE email_sha256=p_email_sha256 AND occurred_at>now()-interval '15 minutes'
              AND action='magic_link_requested' AND outcome='accepted'
          ) OR (
            SELECT count(*) >= 20 FROM public.authentication_events
            WHERE source_sha256=p_source_sha256 AND occurred_at>now()-interval '15 minutes'
              AND action='magic_link_requested' AND outcome='accepted'
          );
          SELECT i.id AS identity_id,i.tenant_id,i.user_id INTO account
          FROM public.identity_accounts i JOIN public.user_session_state u
            ON u.tenant_id=i.tenant_id AND u.user_id=i.user_id
          WHERE i.provider='magic_link' AND i.login_email_normalized=p_email_normalized
            AND i.enabled AND u.enabled LIMIT 1;

          INSERT INTO public.authentication_events
            (id,tenant_id,user_id,email_sha256,source_sha256,action,outcome,request_id)
          VALUES (gen_random_uuid(),account.tenant_id,account.user_id,p_email_sha256,
            p_source_sha256,'magic_link_requested',
            CASE WHEN limited THEN 'rate_limited' ELSE 'accepted' END,p_request_id);

          IF limited OR account.identity_id IS NULL THEN
            RETURN QUERY SELECT false,NULL::timestamptz;
            RETURN;
          END IF;
          INSERT INTO public.magic_link_challenges
            (id,identity_account_id,tenant_id,user_id,token_sha256,email_sha256,
             requested_at,expires_at,request_id)
          VALUES (p_challenge_id,account.identity_id,account.tenant_id,account.user_id,
            p_token_sha256,p_email_sha256,now(),expiry,p_request_id);
          RETURN QUERY SELECT true,expiry;
        END $$;
        """
    )


def downgrade() -> None:
    raise RuntimeError("Do not restore a rate limit that counts sign-ins and rejected requests")
