from __future__ import annotations

import json
import os
from uuid import uuid4

from sqlalchemy import create_engine, text

from contracts.models import AuthContext
from domain.jobs import DurableJobStore
from domain.outbox import OutboxDispatcher


def test_scoped_outbox_and_durable_job_retry_recovery() -> None:
    admin = create_engine(
        os.environ.get(
            "VERELO_TEST_ADMIN_DATABASE_URL",
            "postgresql+psycopg://verelo_admin:verelo_admin@127.0.0.1:5432/verelo",
        )
    )
    worker = create_engine(
        os.environ.get(
            "VERELO_TEST_WORKER_DATABASE_URL",
            "postgresql+psycopg://verelo_worker:verelo_worker@127.0.0.1:5432/verelo",
        )
    )
    tenant, workspace, owner, project = uuid4(), uuid4(), uuid4(), uuid4()
    service, document, event = uuid4(), uuid4(), uuid4()
    context = AuthContext(
        principal_kind="service",
        principal_id=service,
        tenant_id=tenant,
        workspace_id=workspace,
        authorization_epoch=0,
        capabilities=[],
        request_id=str(uuid4()),
    )
    try:
        with admin.begin() as connection:
            connection.execute(
                text(
                    """INSERT INTO tenants (id,entra_tenant_id,policy_config_ref,region)
                    VALUES (:id,:entra,'synthetic','local')"""
                ),
                {"id": tenant, "entra": uuid4()},
            )
            connection.execute(
                text(
                    """INSERT INTO workspaces (id,tenant_id,name,is_default)
                    VALUES (:id,:tenant,'Worker',true)"""
                ),
                {"id": workspace, "tenant": tenant},
            )
            connection.execute(
                text(
                    """INSERT INTO users
                    (id,tenant_id,entra_object_id,display_name,email)
                    VALUES (:id,:tenant,:entra,'Worker Owner','worker-owner.invalid')"""
                ),
                {"id": owner, "tenant": tenant, "entra": uuid4()},
            )
            connection.execute(
                text(
                    """INSERT INTO projects
                    (id,tenant_id,workspace_id,name,owner_user_id,retention_policy_ref,
                     transcript_approval_policy_ref)
                    VALUES (:id,:tenant,:workspace,'Worker project',:owner,'synthetic',
                      'controlled-cleanup-v2')"""
                ),
                {"id": project, "tenant": tenant, "workspace": workspace, "owner": owner},
            )
            connection.execute(
                text(
                    """INSERT INTO project_memberships
                    (id,tenant_id,workspace_id,project_id,user_id,role)
                    VALUES (:id,:tenant,:workspace,:project,:owner,'project_owner')"""
                ),
                {
                    "id": uuid4(),
                    "tenant": tenant,
                    "workspace": workspace,
                    "project": project,
                    "owner": owner,
                },
            )
            connection.execute(
                text(
                    """INSERT INTO documents
                    (id,tenant_id,workspace_id,project_id,title,meeting_date,language,created_by,
                     consent_policy_version,consent_acknowledged_by,consent_acknowledged_at)
                    VALUES (:id,:tenant,:workspace,:project,'Synthetic worker source',now(),'en-US',
                      :owner,'synthetic-v1',:owner,now())"""
                ),
                {
                    "id": document,
                    "tenant": tenant,
                    "workspace": workspace,
                    "project": project,
                    "owner": owner,
                },
            )
            connection.execute(
                text(
                    """INSERT INTO service_identities (id,tenant_id,name)
                    VALUES (:id,:tenant,'worker')"""
                ),
                {"id": service, "tenant": tenant},
            )
            for action in ("outbox.dispatch", "jobs.execute"):
                connection.execute(
                    text(
                        """INSERT INTO service_grants
                        (id,tenant_id,workspace_id,project_id,service_identity_id,action)
                        VALUES (:id,:tenant,:workspace,:project,:service,:action)"""
                    ),
                    {
                        "id": uuid4(),
                        "tenant": tenant,
                        "workspace": workspace,
                        "project": project,
                        "service": service,
                        "action": action,
                    },
                )
            payload = json.dumps({"trace_id": context.request_id})
            connection.execute(
                text(
                    """INSERT INTO outbox_events
                    (id,tenant_id,workspace_id,project_id,document_id,aggregate_id,event_type,
                     schema_version,payload)
                    VALUES (:id,:tenant,:workspace,:project,:document,:document,
                      'transcript.published',1,CAST(:payload AS jsonb))"""
                ),
                {
                    "id": event,
                    "tenant": tenant,
                    "workspace": workspace,
                    "project": project,
                    "document": document,
                    "payload": payload,
                },
            )

        result = OutboxDispatcher(worker).dispatch(context, project, action="outbox.dispatch")
        assert result.dispatched == 1
        assert (
            OutboxDispatcher(worker).dispatch(context, project, action="outbox.dispatch").dispatched
            == 0
        )

        jobs = DurableJobStore(worker)
        leased = jobs.claim(context, project, worker_id="worker-a", action="jobs.execute")
        assert leased is not None
        jobs.fail(
            context,
            project,
            leased.job_id,
            worker_id="worker-a",
            action="jobs.execute",
            safe_error_code="synthetic_retry",
            retry_after_seconds=0,
        )
        retried = jobs.claim(context, project, worker_id="worker-b", action="jobs.execute")
        assert retried is not None and retried.job_id == leased.job_id and retried.attempt == 2
        jobs.complete(
            context,
            project,
            retried.job_id,
            worker_id="worker-b",
            action="jobs.execute",
            provider_ref="synthetic-complete",
        )
        assert jobs.claim(context, project, worker_id="worker-c", action="jobs.execute") is None
    finally:
        worker.dispose()
        with admin.begin() as connection:
            connection.execute(text("DELETE FROM jobs WHERE project_id=:id"), {"id": project})
            connection.execute(
                text("DELETE FROM outbox_events WHERE project_id=:id"), {"id": project}
            )
            connection.execute(
                text("DELETE FROM service_grants WHERE project_id=:id"), {"id": project}
            )
            connection.execute(
                text("DELETE FROM service_action_grants WHERE project_id=:id"), {"id": project}
            )
            connection.execute(text("DELETE FROM service_identities WHERE id=:id"), {"id": service})
            connection.execute(text("DELETE FROM documents WHERE id=:id"), {"id": document})
            connection.execute(
                text("DELETE FROM project_memberships WHERE project_id=:id"), {"id": project}
            )
            connection.execute(
                text("DELETE FROM project_access_grants WHERE project_id=:id"), {"id": project}
            )
            connection.execute(text("DELETE FROM projects WHERE id=:id"), {"id": project})
            connection.execute(text("DELETE FROM users WHERE id=:id"), {"id": owner})
            connection.execute(text("DELETE FROM workspaces WHERE id=:id"), {"id": workspace})
            connection.execute(text("DELETE FROM tenants WHERE id=:id"), {"id": tenant})
        admin.dispose()
