"""Non-recursive private authorization indexes for forced RLS.

Revision ID: 0004_authorization_indexes
Revises: 0003_identity_authorization
Create Date: 2026-09-21
"""

from alembic import op

revision = "0004_authorization_indexes"
down_revision = "0003_identity_authorization"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE project_access_grants (
          tenant_id uuid NOT NULL, workspace_id uuid NOT NULL, project_id uuid NOT NULL,
          user_id uuid NOT NULL, role text NOT NULL, enabled boolean NOT NULL,
          PRIMARY KEY (tenant_id, workspace_id, project_id, user_id)
        );
        CREATE TABLE service_action_grants (
          tenant_id uuid NOT NULL, workspace_id uuid NOT NULL, project_id uuid NOT NULL,
          service_identity_id uuid NOT NULL, action varchar(100) NOT NULL, enabled boolean NOT NULL,
          PRIMARY KEY (tenant_id, workspace_id, project_id, service_identity_id, action)
        );
        REVOKE ALL ON project_access_grants, service_action_grants FROM PUBLIC;

        CREATE OR REPLACE FUNCTION verelo_sync_project_owner_grant() RETURNS trigger
        LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, public AS $$
        BEGIN
          INSERT INTO public.project_access_grants
            (tenant_id,workspace_id,project_id,user_id,role,enabled)
          VALUES (NEW.tenant_id,NEW.workspace_id,NEW.id,NEW.owner_user_id,'project_owner',NEW.state='active')
          ON CONFLICT (tenant_id,workspace_id,project_id,user_id) DO UPDATE
            SET role='project_owner', enabled=EXCLUDED.enabled;
          RETURN NEW;
        END $$;
        CREATE TRIGGER projects_sync_owner_grant
          AFTER INSERT OR UPDATE OF owner_user_id,state ON projects
          FOR EACH ROW EXECUTE FUNCTION verelo_sync_project_owner_grant();

        CREATE OR REPLACE FUNCTION verelo_sync_membership_grant() RETURNS trigger
        LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, public AS $$
        BEGIN
          IF TG_OP = 'DELETE' THEN
            DELETE FROM public.project_access_grants WHERE tenant_id=OLD.tenant_id
              AND workspace_id=OLD.workspace_id AND project_id=OLD.project_id AND user_id=OLD.user_id;
            RETURN OLD;
          END IF;
          INSERT INTO public.project_access_grants
            (tenant_id,workspace_id,project_id,user_id,role,enabled)
          VALUES (NEW.tenant_id,NEW.workspace_id,NEW.project_id,NEW.user_id,NEW.role,NEW.enabled)
          ON CONFLICT (tenant_id,workspace_id,project_id,user_id) DO UPDATE
            SET role=EXCLUDED.role, enabled=EXCLUDED.enabled;
          RETURN NEW;
        END $$;
        CREATE TRIGGER memberships_sync_grant
          AFTER INSERT OR UPDATE OF role,enabled OR DELETE ON project_memberships
          FOR EACH ROW EXECUTE FUNCTION verelo_sync_membership_grant();

        CREATE OR REPLACE FUNCTION verelo_sync_service_grant() RETURNS trigger
        LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, public AS $$
        BEGIN
          IF TG_OP = 'DELETE' THEN
            DELETE FROM public.service_action_grants WHERE tenant_id=OLD.tenant_id
              AND workspace_id=OLD.workspace_id AND project_id=OLD.project_id
              AND service_identity_id=OLD.service_identity_id AND action=OLD.action;
            RETURN OLD;
          END IF;
          INSERT INTO public.service_action_grants
            (tenant_id,workspace_id,project_id,service_identity_id,action,enabled)
          VALUES (NEW.tenant_id,NEW.workspace_id,NEW.project_id,NEW.service_identity_id,NEW.action,NEW.enabled)
          ON CONFLICT (tenant_id,workspace_id,project_id,service_identity_id,action) DO UPDATE
            SET enabled=EXCLUDED.enabled;
          RETURN NEW;
        END $$;
        CREATE TRIGGER service_grants_sync_index
          AFTER INSERT OR UPDATE OF enabled,action OR DELETE ON service_grants
          FOR EACH ROW EXECUTE FUNCTION verelo_sync_service_grant();

        INSERT INTO project_access_grants
          SELECT tenant_id,workspace_id,project_id,user_id,role,enabled FROM project_memberships;
        INSERT INTO service_action_grants
          SELECT tenant_id,workspace_id,project_id,service_identity_id,action,enabled FROM service_grants;

        CREATE OR REPLACE FUNCTION verelo_project_member(
          row_tenant uuid, row_workspace uuid, row_project uuid
        ) RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER
        SET search_path = pg_catalog, public AS $$
          SELECT verelo_scope_allows(row_tenant, row_workspace)
            AND current_setting('app.principal_kind', true) = 'employee'
            AND EXISTS (SELECT 1 FROM public.users u
              WHERE u.tenant_id=row_tenant AND u.id=verelo_current_uuid('app.principal_id') AND u.enabled)
            AND EXISTS (SELECT 1 FROM public.project_access_grants g
              WHERE g.tenant_id=row_tenant AND g.workspace_id=row_workspace
                AND g.project_id=row_project AND g.user_id=verelo_current_uuid('app.principal_id')
                AND g.enabled)
        $$;
        CREATE OR REPLACE FUNCTION verelo_service_granted(
          row_tenant uuid, row_workspace uuid, row_project uuid
        ) RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER
        SET search_path = pg_catalog, public AS $$
          SELECT verelo_scope_allows(row_tenant, row_workspace)
            AND current_setting('app.principal_kind', true) = 'service'
            AND EXISTS (SELECT 1 FROM public.service_identities s
              WHERE s.tenant_id=row_tenant AND s.id=verelo_current_uuid('app.principal_id') AND s.enabled)
            AND EXISTS (SELECT 1 FROM public.service_action_grants g
              WHERE g.tenant_id=row_tenant AND g.workspace_id=row_workspace
                AND g.project_id=row_project
                AND g.service_identity_id=verelo_current_uuid('app.principal_id')
                AND g.action=current_setting('app.action', true) AND g.enabled)
        $$;
        DO $grants$
        BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='verelo_api') THEN
            GRANT EXECUTE ON FUNCTION verelo_project_member(uuid,uuid,uuid) TO verelo_api;
            GRANT EXECUTE ON FUNCTION verelo_service_granted(uuid,uuid,uuid) TO verelo_api;
          END IF;
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='verelo_worker') THEN
            GRANT EXECUTE ON FUNCTION verelo_project_member(uuid,uuid,uuid) TO verelo_worker;
            GRANT EXECUTE ON FUNCTION verelo_service_granted(uuid,uuid,uuid) TO verelo_worker;
          END IF;
        END $grants$;
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER service_grants_sync_index ON service_grants")
    op.execute("DROP FUNCTION verelo_sync_service_grant()")
    op.execute("DROP TRIGGER memberships_sync_grant ON project_memberships")
    op.execute("DROP FUNCTION verelo_sync_membership_grant()")
    op.execute("DROP TRIGGER projects_sync_owner_grant ON projects")
    op.execute("DROP FUNCTION verelo_sync_project_owner_grant()")
    op.execute("DROP TABLE service_action_grants")
    op.execute("DROP TABLE project_access_grants")
