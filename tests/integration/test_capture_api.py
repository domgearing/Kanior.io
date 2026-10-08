from __future__ import annotations

import base64
import os
from datetime import UTC, datetime
from hashlib import sha256
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from api.auth import resolve_session, synthetic_session
from api.config import Settings
from api.main import create_app

CSRF = "synthetic-csrf-token-value-00000000"


def test_persistent_capture_recovery_audio_integrity_and_quarantine(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("VERELO_PUBLIC_ORIGIN", "http://127.0.0.1:5173")
    monkeypatch.setenv("VERELO_SESSION_COOKIE_SECURE", "false")
    monkeypatch.setenv("VERELO_INTEGRATIONS_MODE", "fake")
    settings = Settings()
    admin = create_engine(
        os.environ.get(
            "VERELO_TEST_ADMIN_DATABASE_URL",
            "postgresql+psycopg://verelo_admin:verelo_admin@127.0.0.1:5432/verelo",
        )
    )
    api_engine = create_engine(settings.database_url)
    tenant, workspace, owner, stranger = uuid4(), uuid4(), uuid4(), uuid4()
    project_id = document_id = None
    captures: list[str] = []
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
                VALUES (:id,:tenant,'Capture',true)"""
            ),
            {"id": workspace, "tenant": tenant},
        )
        for user, name in ((owner, "Owner"), (stranger, "Stranger")):
            connection.execute(
                text(
                    """INSERT INTO users
                    (id,tenant_id,entra_object_id,display_name,email)
                    VALUES (:id,:tenant,:entra,:name,:email)"""
                ),
                {
                    "id": user,
                    "tenant": tenant,
                    "entra": uuid4(),
                    "name": name,
                    "email": f"{name.lower()}.invalid",
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
    headers = {"X-CSRF-Token": CSRF, "Origin": "http://127.0.0.1:5173"}
    try:
        with TestClient(app) as client:
            project = client.post(
                "/api/v1/projects", headers=headers, json={"name": "Audio integrity"}
            )
            assert project.status_code == 201
            project_id = project.json()["project_id"]
            document = client.post(
                f"/api/v1/projects/{project_id}/documents",
                headers=headers,
                json={
                    "title": "Synthetic recording",
                    "meeting_date": datetime.now(UTC).isoformat(),
                    "language": "en-US",
                    "consent_acknowledged": True,
                    "consent_policy_version": "synthetic-consent-v1",
                },
            )
            assert document.status_code == 201
            document_id = document.json()["document_id"]
            created = client.post(
                "/api/v1/capture-sessions", headers=headers, json={"document_id": document_id}
            )
            assert created.status_code == 201
            capture_id = created.json()["capture_session_id"]
            captures.append(capture_id)
            assert (
                client.post(
                    f"/api/v1/capture-sessions/{capture_id}/transitions",
                    headers=headers,
                    json={"event": "start"},
                ).json()["state"]
                == "recording"
            )
            assert (
                client.post(
                    f"/api/v1/capture-sessions/{capture_id}/transitions",
                    headers=headers,
                    json={"event": "interrupt", "at_ms": 1200},
                ).status_code
                == 200
            )
            recovered = client.post(
                f"/api/v1/capture-sessions/{capture_id}/transitions",
                headers=headers,
                json={"event": "recover", "at_ms": 1800},
            )
            assert recovered.json()["gaps"] == [
                {"start_ms": 1200, "end_ms": 1800, "reason": "device_interruption"}
            ]

            wav = (
                b"RIFF"
                + (36).to_bytes(4, "little")
                + b"WAVE"
                + b"fmt "
                + (16).to_bytes(4, "little")
                + b"\x01\x00\x01\x00"
                + (8000).to_bytes(4, "little")
                + (8000).to_bytes(4, "little")
                + b"\x01\x00\x08\x00"
                + b"data"
                + (0).to_bytes(4, "little")
            )
            chunks = (wav[:22], wav[22:])
            bad = client.put(
                f"/api/v1/capture-sessions/{capture_id}/chunks/1",
                headers=headers,
                json={
                    "sequence": 1,
                    "content_base64": base64.b64encode(chunks[0]).decode(),
                    "sha256": "0" * 64,
                },
            )
            assert bad.status_code == 422
            for sequence, chunk in enumerate(chunks, 1):
                payload = {
                    "sequence": sequence,
                    "content_base64": base64.b64encode(chunk).decode(),
                    "sha256": sha256(chunk).hexdigest(),
                }
                uploaded = client.put(
                    f"/api/v1/capture-sessions/{capture_id}/chunks/{sequence}",
                    headers=headers,
                    json=payload,
                )
                assert uploaded.status_code == 200
                assert uploaded.json()["acknowledged_chunks"] == sequence
                assert (
                    client.put(
                        f"/api/v1/capture-sessions/{capture_id}/chunks/{sequence}",
                        headers=headers,
                        json=payload,
                    ).status_code
                    == 200
                )
            assert (
                client.get(f"/api/v1/capture-sessions/{capture_id}").json()["acknowledged_chunks"]
                == 2
            )
            assert (
                client.put(
                    f"/api/v1/capture-sessions/{capture_id}/chunks/4",
                    headers=headers,
                    json={
                        "sequence": 4,
                        "content_base64": "eA==",
                        "sha256": sha256(b"x").hexdigest(),
                    },
                ).status_code
                == 409
            )
            client.post(
                f"/api/v1/capture-sessions/{capture_id}/transitions",
                headers=headers,
                json={"event": "stop"},
            )
            finalized = client.post(
                f"/api/v1/capture-sessions/{capture_id}/finalize",
                headers=headers,
                json={"filename": "synthetic.wav", "duration_ms": 0},
            )
            assert finalized.status_code == 200
            assert finalized.json()["state"] == "complete"
            assert finalized.json()["source_asset_id"]
            assert finalized.json()["ingestion_id"]
            audio_ingestion = client.get(f"/api/v1/ingestions/{finalized.json()['ingestion_id']}")
            assert audio_ingestion.status_code == 200
            assert audio_ingestion.json()["state"] == "approved"
            audio_draft = client.get(f"/api/v1/ingestions/{finalized.json()['ingestion_id']}/draft")
            assert audio_draft.status_code == 200
            assert "fictional project meeting" in audio_draft.json()["canonical_text"]
            with admin.connect() as connection:
                asset = (
                    connection.execute(
                        text(
                            """SELECT byte_length,sha256,quarantine_state
                            FROM source_assets WHERE id=:id"""
                        ),
                        {"id": finalized.json()["source_asset_id"]},
                    )
                    .mappings()
                    .one()
                )
                assert dict(asset) == {
                    "byte_length": len(wav),
                    "sha256": sha256(wav).hexdigest(),
                    "quarantine_state": "accepted",
                }

            current["session"] = synthetic_session(
                principal_id=stranger,
                tenant_id=tenant,
                workspace_id=workspace,
                request_id=str(uuid4()),
            )
            assert client.get(f"/api/v1/capture-sessions/{capture_id}").status_code == 404
    finally:
        api_engine.dispose()
        with admin.begin() as connection:
            if document_id:
                connection.execute(
                    text("UPDATE documents SET active_transcript_version_id=NULL WHERE id=:id"),
                    {"id": document_id},
                )
                connection.execute(
                    text("DELETE FROM audit_events WHERE document_id=:id"),
                    {"id": document_id},
                )
                for table in ("outbox_events", "jobs", "passages", "transcript_approvals"):
                    connection.execute(
                        text(f"DELETE FROM {table} WHERE document_id=:id"), {"id": document_id}
                    )
                connection.execute(
                    text("""UPDATE ingestions SET source_asset_id=NULL,draft_version_id=NULL
                    WHERE document_id=:id"""),
                    {"id": document_id},
                )
                connection.execute(
                    text("DELETE FROM transcript_versions WHERE document_id=:id"),
                    {"id": document_id},
                )
                connection.execute(
                    text("DELETE FROM raw_transcripts WHERE document_id=:id"),
                    {"id": document_id},
                )
                connection.execute(
                    text("""DELETE FROM ingestion_chunks WHERE ingestion_id IN
                    (SELECT id FROM ingestions WHERE document_id=:id)"""),
                    {"id": document_id},
                )
                connection.execute(
                    text("""DELETE FROM ingestion_operations WHERE ingestion_id IN
                    (SELECT id FROM ingestions WHERE document_id=:id)"""),
                    {"id": document_id},
                )
                connection.execute(
                    text("UPDATE capture_sessions SET ingestion_id=NULL WHERE document_id=:id"),
                    {"id": document_id},
                )
                connection.execute(
                    text("DELETE FROM ingestions WHERE document_id=:id"), {"id": document_id}
                )
                connection.execute(
                    text("DELETE FROM source_assets WHERE document_id=:id"), {"id": document_id}
                )
                for capture_id in captures:
                    connection.execute(
                        text("DELETE FROM capture_chunks WHERE capture_session_id=:id"),
                        {"id": capture_id},
                    )
                connection.execute(
                    text("DELETE FROM capture_sessions WHERE document_id=:id"), {"id": document_id}
                )
                connection.execute(text("DELETE FROM documents WHERE id=:id"), {"id": document_id})
            if project_id:
                connection.execute(
                    text("DELETE FROM audit_events WHERE project_id=:id"), {"id": project_id}
                )
                connection.execute(
                    text("DELETE FROM project_memberships WHERE project_id=:id"), {"id": project_id}
                )
                connection.execute(
                    text("DELETE FROM project_access_grants WHERE project_id=:id"),
                    {"id": project_id},
                )
                connection.execute(text("DELETE FROM projects WHERE id=:id"), {"id": project_id})
            connection.execute(
                text("DELETE FROM users WHERE id IN (:a,:b)"), {"a": owner, "b": stranger}
            )
            connection.execute(text("DELETE FROM workspaces WHERE id=:id"), {"id": workspace})
            connection.execute(text("DELETE FROM tenants WHERE id=:id"), {"id": tenant})
        admin.dispose()
