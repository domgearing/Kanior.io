"""Direct API checks for same-user device control and meeting authorization."""

from __future__ import annotations

import os
from datetime import UTC, datetime
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from api.auth import resolve_session, synthetic_session
from api.main import create_app

CSRF = "synthetic-csrf-token-value-00000000"
ORIGIN = "http://127.0.0.1:5173"
TOKEN = "a" * 64


def test_web_commands_are_employee_device_and_meeting_scoped(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("VERELO_ENVIRONMENT", "test")
    monkeypatch.setenv("VERELO_INTEGRATIONS_MODE", "fake")
    monkeypatch.setenv("VERELO_IDENTITY_PROVIDER", "magic_link")
    monkeypatch.setenv("VERELO_PUBLIC_ORIGIN", ORIGIN)
    monkeypatch.setenv("VERELO_SESSION_COOKIE_SECURE", "false")
    api_url = os.environ.get(
        "VERELO_TEST_API_DATABASE_URL",
        "postgresql+psycopg://verelo_api:verelo_api@127.0.0.1:5432/verelo",
    )
    admin_url = os.environ.get(
        "VERELO_TEST_ADMIN_DATABASE_URL",
        "postgresql+psycopg://verelo_admin:verelo_admin@127.0.0.1:5432/verelo",
    )
    admin = create_engine(admin_url)
    api_engine = create_engine(api_url)
    tenant, workspace = uuid4(), uuid4()
    other_tenant, other_workspace = uuid4(), uuid4()
    owner, reader, outsider = uuid4(), uuid4(), uuid4()
    device_id, reader_device = uuid4(), uuid4()
    project_id = document_id = None
    with admin.begin() as connection:
        for t, w in ((tenant, workspace), (other_tenant, other_workspace)):
            connection.execute(
                text("""INSERT INTO tenants (id,entra_tenant_id,policy_config_ref,region)
                  VALUES (:id,:entra,'synthetic','local')"""),
                {"id": t, "entra": uuid4()},
            )
            connection.execute(
                text("""INSERT INTO workspaces (id,tenant_id,name,is_default)
                  VALUES (:id,:tenant,'Recorder',true)"""),
                {"id": w, "tenant": t},
            )
        for user, scope, name in (
            (owner, tenant, "Owner"),
            (reader, tenant, "Reader"),
            (outsider, other_tenant, "Outsider"),
        ):
            connection.execute(
                text("""INSERT INTO users (id,tenant_id,entra_object_id,display_name,email)
                  VALUES (:id,:tenant,:entra,:name,:email)"""),
                {
                    "id": user,
                    "tenant": scope,
                    "entra": uuid4(),
                    "name": name,
                    "email": f"{user}@invalid.example",
                },
            )
    current = {
        "session": synthetic_session(
            principal_id=owner,
            tenant_id=tenant,
            workspace_id=workspace,
            request_id=str(uuid4()),
            capabilities=("projects:create",),
        )
    }
    app = create_app(api_engine)
    app.dependency_overrides[resolve_session] = lambda: current["session"]
    headers = {"Origin": ORIGIN, "X-CSRF-Token": CSRF}
    desktop_headers = {**headers, "X-Recorder-Device-Token": TOKEN}
    try:
        with TestClient(app) as client:
            project = client.post(
                "/api/v1/projects", headers=headers, json={"name": "Recorder controls"}
            )
            assert project.status_code == 201
            project_id = project.json()["project_id"]
            document = client.post(
                f"/api/v1/projects/{project_id}/documents",
                headers=headers,
                json={
                    "title": "Synthetic interview",
                    "meeting_date": datetime.now(UTC).isoformat(),
                    "language": "en-US",
                    "consent_acknowledged": True,
                    "consent_policy_version": "synthetic-consent-v1",
                },
            )
            assert document.status_code == 201
            document_id = document.json()["document_id"]
            with admin.begin() as connection:
                connection.execute(
                    text("""INSERT INTO project_memberships
                      (id,tenant_id,workspace_id,project_id,user_id,role)
                      VALUES (:id,:tenant,:workspace,:project,:reader,'reader')"""),
                    {
                        "id": uuid4(),
                        "tenant": tenant,
                        "workspace": workspace,
                        "project": project_id,
                        "reader": reader,
                    },
                )

            heartbeat_url = f"/api/v1/recorder-devices/{device_id}/heartbeat"
            preflight = client.options(
                heartbeat_url,
                headers={
                    "Origin": ORIGIN,
                    "Access-Control-Request-Method": "PUT",
                    "Access-Control-Request-Headers": (
                        "content-type,x-csrf-token,x-recorder-device-token"
                    ),
                },
            )
            assert preflight.status_code == 200
            assert (
                "x-recorder-device-token"
                in preflight.headers["access-control-allow-headers"].lower()
            )
            idle = {"state": "idle", "document_id": None, "capture_session_id": None}
            assert client.put(heartbeat_url, headers=headers, json=idle).status_code == 422
            assert client.put(heartbeat_url, headers=desktop_headers, json=idle).status_code == 200
            assert (
                client.put(
                    heartbeat_url,
                    headers={**headers, "X-Recorder-Device-Token": "b" * 64},
                    json=idle,
                ).status_code
                == 404
            )
            assert len(client.get("/api/v1/recorder-devices").json()["items"]) == 1

            current["session"] = synthetic_session(
                principal_id=reader,
                tenant_id=tenant,
                workspace_id=workspace,
                request_id=str(uuid4()),
            )
            assert client.get("/api/v1/recorder-devices").json()["items"] == []
            assert client.put(heartbeat_url, headers=desktop_headers, json=idle).status_code == 404
            assert (
                client.post(
                    f"/api/v1/recorder-devices/{device_id}/commands",
                    headers=headers,
                    json={
                        "action": "start",
                        "document_id": document_id,
                        "operation_key": str(uuid4()),
                    },
                ).status_code
                == 404
            )
            assert (
                client.put(
                    f"/api/v1/recorder-devices/{reader_device}/heartbeat",
                    headers=desktop_headers,
                    json=idle,
                ).status_code
                == 200
            )
            assert (
                client.post(
                    f"/api/v1/recorder-devices/{reader_device}/commands",
                    headers=headers,
                    json={
                        "action": "start",
                        "document_id": document_id,
                        "operation_key": str(uuid4()),
                    },
                ).status_code
                == 403
            )
            current["session"] = synthetic_session(
                principal_id=outsider,
                tenant_id=other_tenant,
                workspace_id=other_workspace,
                request_id=str(uuid4()),
            )
            assert client.get("/api/v1/recorder-devices").json()["items"] == []
            assert (
                client.post(
                    f"/api/v1/recorder-devices/{device_id}/commands",
                    headers=headers,
                    json={"action": "stop", "document_id": None, "operation_key": str(uuid4())},
                ).status_code
                == 404
            )

            current["session"] = synthetic_session(
                principal_id=owner,
                tenant_id=tenant,
                workspace_id=workspace,
                request_id=str(uuid4()),
                capabilities=("projects:create",),
            )
            command_url = f"/api/v1/recorder-devices/{device_id}/commands"
            assert (
                client.post(
                    command_url,
                    headers=headers,
                    json={
                        "action": "start",
                        "document_id": str(uuid4()),
                        "operation_key": str(uuid4()),
                    },
                ).status_code
                == 404
            )
            payload = {"action": "start", "document_id": document_id, "operation_key": str(uuid4())}
            assert client.post(command_url, json=payload).status_code == 403
            submitted = client.post(command_url, headers=headers, json=payload)
            assert submitted.status_code == 201
            command_id = submitted.json()["command_id"]
            assert (
                client.post(command_url, headers=headers, json=payload).json()["command_id"]
                == command_id
            )
            assert (
                client.post(
                    command_url,
                    headers=headers,
                    json={**payload, "action": "pause", "document_id": None},
                ).status_code
                == 409
            )
            claim_url = f"/api/v1/recorder-devices/{device_id}/commands/claim"
            assert client.post(claim_url, headers=headers).status_code == 422
            claimed = client.post(claim_url, headers=desktop_headers)
            assert claimed.status_code == 200
            assert claimed.json()["command"]["command_id"] == command_id
            assert client.post(claim_url, headers=desktop_headers).json()["command"] is None
            result_url = f"/api/v1/recorder-commands/{command_id}/result"
            created_capture = client.post(
                "/api/v1/capture-sessions",
                headers=headers,
                json={"document_id": document_id},
            )
            assert created_capture.status_code == 201
            capture_id = created_capture.json()["capture_session_id"]
            assert (
                client.post(
                    f"/api/v1/capture-sessions/{capture_id}/transitions",
                    headers=headers,
                    json={"event": "start", "at_ms": 0},
                ).json()["state"]
                == "recording"
            )
            current["session"] = synthetic_session(
                principal_id=reader,
                tenant_id=tenant,
                workspace_id=workspace,
                request_id=str(uuid4()),
            )
            assert (
                client.post(
                    f"/api/v1/capture-sessions/{capture_id}/transitions",
                    headers=headers,
                    json={"event": "pause", "at_ms": 100},
                ).status_code
                == 403
            )
            current["session"] = synthetic_session(
                principal_id=owner,
                tenant_id=tenant,
                workspace_id=workspace,
                request_id=str(uuid4()),
                capabilities=("projects:create",),
            )
            assert (
                client.post(
                    result_url,
                    headers=desktop_headers,
                    json={"status": "completed", "capture_session_id": str(uuid4())},
                ).status_code
                == 409
            )
            assert (
                client.post(
                    result_url,
                    headers=headers,
                    json={"status": "completed", "capture_session_id": capture_id},
                ).status_code
                == 422
            )
            assert (
                client.post(
                    result_url,
                    headers=desktop_headers,
                    json={"status": "completed", "capture_session_id": capture_id},
                ).status_code
                == 200
            )
            assert (
                client.post(
                    result_url,
                    headers=desktop_headers,
                    json={"status": "completed", "capture_session_id": capture_id},
                ).status_code
                == 200
            )
            assert (
                client.get(f"/api/v1/recorder-commands/{command_id}").json()["status"]
                == "completed"
            )

            assert (
                client.put(
                    heartbeat_url,
                    headers=desktop_headers,
                    json={
                        "state": "recording",
                        "document_id": document_id,
                        "capture_session_id": capture_id,
                    },
                ).status_code
                == 200
            )
            stop = client.post(
                command_url,
                headers=headers,
                json={"action": "stop", "document_id": None, "operation_key": str(uuid4())},
            )
            assert stop.status_code == 201
            with admin.begin() as connection:
                connection.execute(
                    text("""UPDATE recorder_commands SET expires_at=now()-interval '1 second'
                      WHERE id=:id"""),
                    {"id": stop.json()["command_id"]},
                )
            assert (
                client.get(f"/api/v1/recorder-commands/{stop.json()['command_id']}").json()[
                    "status"
                ]
                == "expired"
            )

            for action, state, next_state in (
                ("pause", "recording", "paused"),
                ("resume", "paused", "recording"),
                ("stop", "recording", "finalizing"),
            ):
                assert (
                    client.put(
                        heartbeat_url,
                        headers=desktop_headers,
                        json={
                            "state": state,
                            "document_id": document_id,
                            "capture_session_id": capture_id,
                        },
                    ).status_code
                    == 200
                )
                issued = client.post(
                    command_url,
                    headers=headers,
                    json={"action": action, "document_id": None, "operation_key": str(uuid4())},
                )
                assert issued.status_code == 201
                assert (
                    client.post(claim_url, headers=desktop_headers).json()["command"]["action"]
                    == action
                )
                assert (
                    client.post(
                        f"/api/v1/capture-sessions/{capture_id}/transitions",
                        headers=headers,
                        json={"event": action, "at_ms": 1000},
                    ).json()["state"]
                    == next_state
                )
                assert (
                    client.post(
                        f"/api/v1/recorder-commands/{issued.json()['command_id']}/result",
                        headers=desktop_headers,
                        json={"status": "completed", "capture_session_id": capture_id},
                    ).status_code
                    == 200
                )
                assert (
                    client.put(
                        heartbeat_url,
                        headers=desktop_headers,
                        json={
                            "state": next_state,
                            "document_id": document_id,
                            "capture_session_id": capture_id,
                        },
                    ).status_code
                    == 200
                )

            with admin.begin() as connection:
                connection.execute(
                    text("""UPDATE project_memberships SET role='contributor'
                      WHERE project_id=:project AND user_id=:reader"""),
                    {"project": project_id, "reader": reader},
                )
            current["session"] = synthetic_session(
                principal_id=reader,
                tenant_id=tenant,
                workspace_id=workspace,
                request_id=str(uuid4()),
            )
            reader_capture = client.post(
                "/api/v1/capture-sessions",
                headers=headers,
                json={"document_id": document_id},
            )
            assert reader_capture.status_code == 201
            reader_capture_id = reader_capture.json()["capture_session_id"]
            assert (
                client.post(
                    f"/api/v1/capture-sessions/{reader_capture_id}/transitions",
                    headers=headers,
                    json={"event": "start", "at_ms": 0},
                ).status_code
                == 200
            )
            reader_heartbeat = f"/api/v1/recorder-devices/{reader_device}/heartbeat"
            assert (
                client.put(
                    reader_heartbeat,
                    headers=desktop_headers,
                    json={
                        "state": "recording",
                        "document_id": document_id,
                        "capture_session_id": reader_capture_id,
                    },
                ).status_code
                == 200
            )
            reader_commands = f"/api/v1/recorder-devices/{reader_device}/commands"
            pending_pause = client.post(
                reader_commands,
                headers=headers,
                json={"action": "pause", "document_id": None, "operation_key": str(uuid4())},
            )
            assert pending_pause.status_code == 201
            with admin.begin() as connection:
                connection.execute(
                    text("""UPDATE project_memberships SET enabled=false
                      WHERE project_id=:project AND user_id=:reader"""),
                    {"project": project_id, "reader": reader},
                )
            assert (
                client.post(
                    f"/api/v1/recorder-devices/{reader_device}/commands/claim",
                    headers=desktop_headers,
                ).json()["command"]
                is None
            )
            assert (
                client.get(
                    f"/api/v1/recorder-commands/{pending_pause.json()['command_id']}"
                ).json()["safe_error_code"]
                == "permission_revoked"
            )
            assert (
                client.post(
                    reader_commands,
                    headers=headers,
                    json={"action": "pause", "document_id": None, "operation_key": str(uuid4())},
                ).status_code
                == 404
            )
            safety_stop = client.post(
                reader_commands,
                headers=headers,
                json={"action": "stop", "document_id": None, "operation_key": str(uuid4())},
            )
            assert safety_stop.status_code == 201
            assert (
                client.post(
                    f"/api/v1/recorder-devices/{reader_device}/commands/claim",
                    headers=desktop_headers,
                ).json()["command"]["action"]
                == "stop"
            )
            assert (
                client.post(
                    f"/api/v1/recorder-commands/{safety_stop.json()['command_id']}/result",
                    headers=desktop_headers,
                    json={"status": "failed", "safe_error_code": "capture_failed"},
                ).status_code
                == 200
            )
    finally:
        with admin.begin() as connection:
            connection.execute(
                text("DELETE FROM recorder_commands WHERE user_id IN (:a,:b)"),
                {"a": owner, "b": reader},
            )
            connection.execute(
                text("DELETE FROM recorder_devices WHERE user_id IN (:a,:b)"),
                {"a": owner, "b": reader},
            )
            connection.execute(
                text("DELETE FROM audit_events WHERE actor_id IN (:a,:b)"),
                {"a": owner, "b": reader},
            )
            if document_id:
                connection.execute(
                    text("DELETE FROM capture_sessions WHERE document_id=:id"), {"id": document_id}
                )
                connection.execute(text("DELETE FROM documents WHERE id=:id"), {"id": document_id})
            if project_id:
                for table in (
                    "outbox_events",
                    "project_memberships",
                    "project_access_grants",
                    "projects",
                ):
                    connection.execute(
                        text(f"DELETE FROM {table} WHERE project_id=:id")
                        if table != "projects"
                        else text("DELETE FROM projects WHERE id=:id"),
                        {"id": project_id},
                    )
            connection.execute(
                text("DELETE FROM users WHERE id IN (:a,:b,:c)"),
                {"a": owner, "b": reader, "c": outsider},
            )
            connection.execute(
                text("DELETE FROM workspaces WHERE id IN (:a,:b)"),
                {"a": workspace, "b": other_workspace},
            )
            connection.execute(
                text("DELETE FROM tenants WHERE id IN (:a,:b)"), {"a": tenant, "b": other_tenant}
            )
        api_engine.dispose()
        admin.dispose()
