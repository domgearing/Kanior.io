"""Provider-neutral identities and development magic-link authentication.

Revision ID: 0006_magic_link_identity
Revises: 0005_session_resolution_index
Create Date: 2026-09-21
"""

from alembic import op

revision = "0006_magic_link_identity"
down_revision = "0005_session_resolution_index"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE tenants ALTER COLUMN entra_tenant_id DROP NOT NULL;
        ALTER TABLE users ALTER COLUMN entra_object_id DROP NOT NULL;

        CREATE TABLE identity_accounts (
          id uuid PRIMARY KEY, tenant_id uuid NOT NULL, workspace_id uuid NOT NULL,
          user_id uuid NOT NULL,
          provider varchar(40) NOT NULL CHECK (provider IN ('magic_link','entra')),
          subject varchar(320) NOT NULL, login_email_normalized varchar(320) NULL,
          enabled boolean NOT NULL DEFAULT true,
          created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
          UNIQUE (provider, subject), UNIQUE (tenant_id, id),
          FOREIGN KEY (tenant_id, workspace_id) REFERENCES workspaces(tenant_id, id) ON DELETE RESTRICT,
          FOREIGN KEY (tenant_id, user_id) REFERENCES users(tenant_id, id) ON DELETE RESTRICT,
          CHECK ((provider='magic_link' AND login_email_normalized IS NOT NULL)
              OR (provider='entra' AND login_email_normalized IS NULL))
        );
        CREATE UNIQUE INDEX identity_accounts_magic_email_unique
          ON identity_accounts (login_email_normalized) WHERE provider='magic_link';

        INSERT INTO identity_accounts (id,tenant_id,workspace_id,user_id,provider,subject)
          SELECT u.id,u.tenant_id,w.id,u.id,'entra',u.entra_object_id::text
          FROM users u JOIN workspaces w ON w.tenant_id=u.tenant_id AND w.is_default
          WHERE u.entra_object_id IS NOT NULL;

        CREATE TABLE magic_link_challenges (
          id uuid PRIMARY KEY, identity_account_id uuid NOT NULL, tenant_id uuid NOT NULL,
          user_id uuid NOT NULL, token_sha256 char(64) NOT NULL UNIQUE,
          email_sha256 char(64) NOT NULL,
          requested_at timestamptz NOT NULL, expires_at timestamptz NOT NULL,
          consumed_at timestamptz NULL, request_id varchar(128) NOT NULL,
          CHECK (expires_at > requested_at),
          FOREIGN KEY (tenant_id, identity_account_id)
            REFERENCES identity_accounts(tenant_id, id) ON DELETE RESTRICT,
          FOREIGN KEY (tenant_id, user_id) REFERENCES users(tenant_id, id) ON DELETE RESTRICT
        );
        CREATE INDEX magic_link_challenges_active_idx ON magic_link_challenges(token_sha256)
          WHERE consumed_at IS NULL;

        CREATE TABLE authentication_events (
          id uuid PRIMARY KEY, tenant_id uuid NULL, user_id uuid NULL,
          email_sha256 char(64) NOT NULL, source_sha256 char(64) NOT NULL,
          action varchar(40) NOT NULL CHECK (action IN ('magic_link_requested','magic_link_consumed','logout')),
          outcome varchar(40) NOT NULL CHECK (outcome IN ('accepted','delivered','denied','rate_limited')),
          request_id varchar(128) NOT NULL, occurred_at timestamptz NOT NULL DEFAULT now(),
          CHECK ((tenant_id IS NULL) = (user_id IS NULL)),
          FOREIGN KEY (tenant_id, user_id) REFERENCES users(tenant_id, id) ON DELETE RESTRICT
        );
        CREATE INDEX authentication_events_email_rate_idx
          ON authentication_events(email_sha256,occurred_at);
        CREATE INDEX authentication_events_source_rate_idx
          ON authentication_events(source_sha256,occurred_at);

        REVOKE ALL ON identity_accounts,magic_link_challenges,authentication_events FROM PUBLIC;

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
          ) OR (
            SELECT count(*) >= 20 FROM public.authentication_events
            WHERE source_sha256=p_source_sha256 AND occurred_at>now()-interval '15 minutes'
          );
          SELECT i.id AS identity_id,i.tenant_id,i.user_id INTO account
          FROM public.identity_accounts i JOIN public.user_session_state u
            ON u.tenant_id=i.tenant_id AND u.user_id=i.user_id
          WHERE i.provider='magic_link' AND i.login_email_normalized=p_email_normalized
            AND i.enabled AND u.enabled LIMIT 1;

          INSERT INTO public.authentication_events
            (id,tenant_id,user_id,email_sha256,source_sha256,action,outcome,request_id)
          VALUES (gen_random_uuid(),account.tenant_id,account.user_id,p_email_sha256,p_source_sha256,
            'magic_link_requested',CASE WHEN limited THEN 'rate_limited' ELSE 'accepted' END,p_request_id);

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

        CREATE OR REPLACE FUNCTION verelo_consume_magic_link(
          p_token_sha256 text, p_session_id uuid, p_session_sha256 text,
          p_csrf_token text, p_csrf_sha256 text, p_source_sha256 text, p_request_id text
        ) RETURNS TABLE (tenant_id uuid,workspace_id uuid,user_id uuid)
        LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path=pg_catalog,public AS $$
        DECLARE challenge record; default_workspace uuid;
        BEGIN
          SELECT c.tenant_id,c.user_id,c.email_sha256 INTO challenge
          FROM public.magic_link_challenges c
          JOIN public.identity_accounts i ON i.tenant_id=c.tenant_id AND i.id=c.identity_account_id
          JOIN public.user_session_state u ON u.tenant_id=c.tenant_id AND u.user_id=c.user_id
          WHERE c.token_sha256=p_token_sha256 AND c.consumed_at IS NULL
            AND c.expires_at>now() AND i.enabled AND u.enabled
          FOR UPDATE OF c;
          IF challenge.user_id IS NULL THEN
            RETURN;
          END IF;
          SELECT i.workspace_id INTO default_workspace FROM public.identity_accounts i
            JOIN public.magic_link_challenges c ON c.identity_account_id=i.id
            WHERE c.token_sha256=p_token_sha256;
          IF default_workspace IS NULL THEN
            RETURN;
          END IF;
          UPDATE public.magic_link_challenges SET consumed_at=now()
            WHERE token_sha256=p_token_sha256;
          INSERT INTO public.sessions
            (id,tenant_id,workspace_id,user_id,token_sha256,csrf_token,csrf_sha256,
             idle_expires_at,absolute_expires_at)
          VALUES (p_session_id,challenge.tenant_id,default_workspace,challenge.user_id,
            p_session_sha256,p_csrf_token,p_csrf_sha256,now()+interval '30 minutes',now()+interval '8 hours');
          INSERT INTO public.authentication_events
            (id,tenant_id,user_id,email_sha256,source_sha256,action,outcome,request_id)
          VALUES (gen_random_uuid(),challenge.tenant_id,challenge.user_id,
            challenge.email_sha256,p_source_sha256,'magic_link_consumed','accepted',p_request_id);
          RETURN QUERY SELECT challenge.tenant_id,default_workspace,challenge.user_id;
        END $$;

        CREATE OR REPLACE FUNCTION verelo_logout_session(
          p_session_sha256 text,p_source_sha256 text,p_request_id text
        ) RETURNS boolean LANGUAGE plpgsql VOLATILE SECURITY DEFINER
        SET search_path=pg_catalog,public AS $$
        DECLARE resolved record;
        BEGIN
          SELECT tenant_id,user_id INTO resolved FROM public.sessions
            WHERE token_sha256=p_session_sha256 AND revoked_at IS NULL FOR UPDATE;
          IF resolved.user_id IS NULL THEN RETURN false; END IF;
          UPDATE public.sessions SET revoked_at=now() WHERE token_sha256=p_session_sha256;
          INSERT INTO public.authentication_events
            (id,tenant_id,user_id,email_sha256,source_sha256,action,outcome,request_id)
          VALUES (gen_random_uuid(),resolved.tenant_id,resolved.user_id,repeat('0',64),
            p_source_sha256,'logout','accepted',p_request_id);
          RETURN true;
        END $$;

        REVOKE ALL ON FUNCTION verelo_request_magic_link(uuid,text,text,text,text,text) FROM PUBLIC;
        REVOKE ALL ON FUNCTION verelo_consume_magic_link(text,uuid,text,text,text,text,text) FROM PUBLIC;
        REVOKE ALL ON FUNCTION verelo_logout_session(text,text,text) FROM PUBLIC;
        DO $grants$ BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='verelo_api') THEN
            GRANT EXECUTE ON FUNCTION verelo_request_magic_link(uuid,text,text,text,text,text) TO verelo_api;
            GRANT EXECUTE ON FUNCTION verelo_consume_magic_link(text,uuid,text,text,text,text,text) TO verelo_api;
            GRANT EXECUTE ON FUNCTION verelo_logout_session(text,text,text) TO verelo_api;
          END IF;
        END $grants$;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP FUNCTION verelo_logout_session(text,text,text);
        DROP FUNCTION verelo_consume_magic_link(text,uuid,text,text,text,text,text);
        DROP FUNCTION verelo_request_magic_link(uuid,text,text,text,text,text);
        DROP TABLE authentication_events;
        DROP TABLE magic_link_challenges;
        DROP TABLE identity_accounts;
        ALTER TABLE users ALTER COLUMN entra_object_id SET NOT NULL;
        ALTER TABLE tenants ALTER COLUMN entra_tenant_id SET NOT NULL;
        """
    )
