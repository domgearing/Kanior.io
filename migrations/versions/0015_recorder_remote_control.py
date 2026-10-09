"""User-scoped, expiring desktop recorder command channel.

Revision ID: 0015_recorder_remote_control
Revises: 0014_entra_session_rls
"""

from alembic import op

revision = "0015_recorder_remote_control"
down_revision = "0014_entra_session_rls"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE recorder_devices (
          id uuid PRIMARY KEY,
          tenant_id uuid NOT NULL,
          workspace_id uuid NOT NULL,
          user_id uuid NOT NULL,
          token_sha256 char(64) NOT NULL CHECK (token_sha256 ~ '^[0-9a-f]{64}$'),
          state text NOT NULL CHECK (state IN
            ('idle','created','recording','paused','interrupted','finalizing',
             'uploading','complete','failed','aborted')),
          document_id uuid NULL,
          capture_session_id uuid NULL,
          last_seen_at timestamptz NOT NULL DEFAULT now(),
          created_at timestamptz NOT NULL DEFAULT now(),
          UNIQUE (tenant_id,workspace_id,user_id,id),
          FOREIGN KEY (tenant_id,user_id) REFERENCES users(tenant_id,id) ON DELETE RESTRICT,
          FOREIGN KEY (tenant_id,workspace_id) REFERENCES workspaces(tenant_id,id)
            ON DELETE RESTRICT
        );
        CREATE INDEX recorder_devices_user_idx
          ON recorder_devices (tenant_id,workspace_id,user_id,last_seen_at DESC);
        CREATE TABLE recorder_commands (
          id uuid PRIMARY KEY,
          tenant_id uuid NOT NULL,
          workspace_id uuid NOT NULL,
          user_id uuid NOT NULL,
          device_id uuid NOT NULL,
          document_id uuid NULL,
          project_id uuid NULL,
          capture_session_id uuid NULL,
          action text NOT NULL CHECK (action IN ('start','pause','resume','stop')),
          status text NOT NULL CHECK (status IN
            ('pending','running','completed','failed','expired')),
          safe_error_code text NULL CHECK (safe_error_code IN
            ('capture_failed','session_expired','recorder_unavailable','permission_revoked')),
          operation_key uuid NOT NULL,
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now(),
          expires_at timestamptz NOT NULL,
          CHECK ((action='start' AND document_id IS NOT NULL AND project_id IS NOT NULL)
             OR (action<>'start' AND document_id IS NULL AND project_id IS NULL)),
          UNIQUE (tenant_id,workspace_id,user_id,operation_key),
          FOREIGN KEY (tenant_id,workspace_id,user_id,device_id)
            REFERENCES recorder_devices(tenant_id,workspace_id,user_id,id)
            ON DELETE RESTRICT,
          FOREIGN KEY (tenant_id,workspace_id,project_id,document_id)
            REFERENCES documents(tenant_id,workspace_id,project_id,id)
            ON DELETE RESTRICT
        );
        CREATE UNIQUE INDEX recorder_commands_one_open_idx
          ON recorder_commands (device_id)
          WHERE status IN ('pending','running');
        CREATE INDEX recorder_commands_device_idx
          ON recorder_commands (device_id,created_at DESC);
        ALTER TABLE recorder_devices ENABLE ROW LEVEL SECURITY;
        ALTER TABLE recorder_devices FORCE ROW LEVEL SECURITY;
        CREATE POLICY recorder_devices_owner ON recorder_devices
          USING (verelo_scope_allows(tenant_id,workspace_id)
            AND verelo_enabled_employee(tenant_id,user_id))
          WITH CHECK (verelo_scope_allows(tenant_id,workspace_id)
            AND verelo_enabled_employee(tenant_id,user_id));
        ALTER TABLE recorder_commands ENABLE ROW LEVEL SECURITY;
        ALTER TABLE recorder_commands FORCE ROW LEVEL SECURITY;
        CREATE POLICY recorder_commands_owner ON recorder_commands
          USING (verelo_scope_allows(tenant_id,workspace_id)
            AND verelo_enabled_employee(tenant_id,user_id))
          WITH CHECK (verelo_scope_allows(tenant_id,workspace_id)
            AND verelo_enabled_employee(tenant_id,user_id));
        CREATE POLICY recorder_control_audit_insert ON audit_events FOR INSERT
          WITH CHECK (project_id IS NULL AND document_id IS NULL
            AND verelo_scope_allows(tenant_id,workspace_id)
            AND actor_kind='employee' AND actor_id=verelo_current_uuid('app.principal_id')
            AND verelo_enabled_employee(tenant_id,actor_id)
            AND action IN ('recorder.command.start','recorder.command.pause',
              'recorder.command.resume','recorder.command.stop',
              'recorder.command.completed','recorder.command.failed'));
        DO $grants$ BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='verelo_api') THEN
            GRANT SELECT,INSERT,UPDATE ON recorder_devices TO verelo_api;
            GRANT SELECT,INSERT,UPDATE ON recorder_commands TO verelo_api;
          END IF;
        END $grants$;
        """
    )


def downgrade() -> None:
    raise RuntimeError("Recorder command history cannot be safely discarded")
