"""Non-recursive private session-resolution index for forced RLS.

Revision ID: 0005_session_resolution_index
Revises: 0004_authorization_indexes
Create Date: 2026-09-21
"""

from alembic import op

revision = "0005_session_resolution_index"
down_revision = "0004_authorization_indexes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE session_resolution_index (
          session_id uuid PRIMARY KEY, tenant_id uuid NOT NULL, workspace_id uuid NOT NULL,
          user_id uuid NOT NULL, token_sha256 char(64) NOT NULL UNIQUE,
          csrf_token varchar(256) NOT NULL, csrf_sha256 char(64) NOT NULL,
          idle_expires_at timestamptz NOT NULL, absolute_expires_at timestamptz NOT NULL,
          revoked_at timestamptz NULL, user_enabled boolean NOT NULL,
          authorization_epoch bigint NOT NULL
        );
        CREATE TABLE user_session_state (
          tenant_id uuid NOT NULL, user_id uuid NOT NULL, enabled boolean NOT NULL,
          authorization_epoch bigint NOT NULL, PRIMARY KEY (tenant_id,user_id)
        );
        REVOKE ALL ON session_resolution_index,user_session_state FROM PUBLIC;
        INSERT INTO user_session_state
          SELECT tenant_id,id,enabled,authorization_epoch FROM users;

        CREATE OR REPLACE FUNCTION verelo_sync_user_session_state() RETURNS trigger
        LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, public AS $$
        BEGIN
          INSERT INTO public.user_session_state (tenant_id,user_id,enabled,authorization_epoch)
          VALUES (NEW.tenant_id,NEW.id,NEW.enabled,NEW.authorization_epoch)
          ON CONFLICT (tenant_id,user_id) DO UPDATE SET enabled=EXCLUDED.enabled,
            authorization_epoch=EXCLUDED.authorization_epoch;
          RETURN NEW;
        END $$;
        CREATE TRIGGER users_sync_private_session_state
          AFTER INSERT OR UPDATE OF enabled,authorization_epoch ON users
          FOR EACH ROW EXECUTE FUNCTION verelo_sync_user_session_state();

        CREATE OR REPLACE FUNCTION verelo_sync_session_resolution() RETURNS trigger
        LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, public AS $$
        DECLARE resolved_enabled boolean; resolved_epoch bigint;
        BEGIN
          IF TG_OP = 'DELETE' THEN
            DELETE FROM public.session_resolution_index WHERE session_id=OLD.id;
            RETURN OLD;
          END IF;
          SELECT enabled,authorization_epoch INTO resolved_enabled,resolved_epoch
            FROM public.user_session_state WHERE tenant_id=NEW.tenant_id AND user_id=NEW.user_id;
          INSERT INTO public.session_resolution_index
            (session_id,tenant_id,workspace_id,user_id,token_sha256,csrf_token,csrf_sha256,
             idle_expires_at,absolute_expires_at,revoked_at,user_enabled,authorization_epoch)
          VALUES (NEW.id,NEW.tenant_id,NEW.workspace_id,NEW.user_id,NEW.token_sha256,
             NEW.csrf_token,NEW.csrf_sha256,NEW.idle_expires_at,NEW.absolute_expires_at,
             NEW.revoked_at,resolved_enabled,resolved_epoch)
          ON CONFLICT (session_id) DO UPDATE SET
            token_sha256=EXCLUDED.token_sha256,csrf_token=EXCLUDED.csrf_token,
            csrf_sha256=EXCLUDED.csrf_sha256,idle_expires_at=EXCLUDED.idle_expires_at,
            absolute_expires_at=EXCLUDED.absolute_expires_at,revoked_at=EXCLUDED.revoked_at,
            user_enabled=EXCLUDED.user_enabled,authorization_epoch=EXCLUDED.authorization_epoch;
          RETURN NEW;
        END $$;
        CREATE TRIGGER sessions_sync_resolution
          AFTER INSERT OR UPDATE OR DELETE ON sessions
          FOR EACH ROW EXECUTE FUNCTION verelo_sync_session_resolution();

        CREATE OR REPLACE FUNCTION verelo_sync_user_sessions() RETURNS trigger
        LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, public AS $$
        BEGIN
          UPDATE public.session_resolution_index SET user_enabled=NEW.enabled,
            authorization_epoch=NEW.authorization_epoch
          WHERE tenant_id=NEW.tenant_id AND user_id=NEW.id;
          RETURN NEW;
        END $$;
        CREATE TRIGGER users_sync_session_resolution
          AFTER UPDATE OF enabled,authorization_epoch ON users
          FOR EACH ROW EXECUTE FUNCTION verelo_sync_user_sessions();

        INSERT INTO session_resolution_index
          SELECT s.id,s.tenant_id,s.workspace_id,s.user_id,s.token_sha256,s.csrf_token,
            s.csrf_sha256,s.idle_expires_at,s.absolute_expires_at,s.revoked_at,
            u.enabled,u.authorization_epoch
          FROM sessions s JOIN users u ON u.tenant_id=s.tenant_id AND u.id=s.user_id;

        CREATE OR REPLACE FUNCTION verelo_resolve_session(p_token_sha256 text)
        RETURNS TABLE (
          session_id uuid, tenant_id uuid, workspace_id uuid, user_id uuid,
          csrf_token varchar(256), csrf_sha256 char(64), authorization_epoch bigint
        ) LANGUAGE sql STABLE SECURITY DEFINER
        SET search_path = pg_catalog, public AS $$
          SELECT s.session_id,s.tenant_id,s.workspace_id,s.user_id,s.csrf_token,s.csrf_sha256,
                 s.authorization_epoch
          FROM public.session_resolution_index s
          WHERE s.token_sha256=p_token_sha256 AND s.revoked_at IS NULL
            AND s.idle_expires_at>now() AND s.absolute_expires_at>now() AND s.user_enabled
          LIMIT 1
        $$;
        REVOKE ALL ON FUNCTION verelo_resolve_session(text) FROM PUBLIC;
        ALTER TABLE sessions NO FORCE ROW LEVEL SECURITY;
        CREATE OR REPLACE FUNCTION verelo_touch_session(p_session_id uuid)
        RETURNS boolean LANGUAGE plpgsql VOLATILE SECURITY DEFINER
        SET search_path = pg_catalog, public AS $$
        DECLARE touched boolean;
        BEGIN
          UPDATE public.sessions SET last_seen_at=now(),
            idle_expires_at=LEAST(now()+interval '30 minutes',absolute_expires_at)
          WHERE id=p_session_id AND revoked_at IS NULL
            AND idle_expires_at>now() AND absolute_expires_at>now()
          RETURNING true INTO touched;
          RETURN COALESCE(touched,false);
        END $$;
        REVOKE ALL ON FUNCTION verelo_touch_session(uuid) FROM PUBLIC;
        DO $grants$
        BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='verelo_api') THEN
            REVOKE UPDATE ON sessions FROM verelo_api;
            GRANT EXECUTE ON FUNCTION verelo_resolve_session(text) TO verelo_api;
            GRANT EXECUTE ON FUNCTION verelo_touch_session(uuid) TO verelo_api;
          END IF;
        END $grants$;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP FUNCTION verelo_touch_session(uuid);
        ALTER TABLE sessions FORCE ROW LEVEL SECURITY;
        DROP TRIGGER users_sync_session_resolution ON users;
        DROP FUNCTION verelo_sync_user_sessions();
        DROP TRIGGER users_sync_private_session_state ON users;
        DROP FUNCTION verelo_sync_user_session_state();
        DROP TRIGGER sessions_sync_resolution ON sessions;
        DROP FUNCTION verelo_sync_session_resolution();
        DROP TABLE session_resolution_index;
        DROP TABLE user_session_state;
        """
    )
