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


def test_foundation_api_authorized_flow_and_guessed_id_denial(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("VERELO_PUBLIC_ORIGIN", "http://127.0.0.1:5173")
    monkeypatch.setenv("VERELO_SESSION_COOKIE_SECURE", "false")
    settings = Settings()
    admin = create_engine(
        os.environ.get(
            "VERELO_TEST_ADMIN_DATABASE_URL",
            "postgresql+psycopg://verelo_admin:verelo_admin@127.0.0.1:5432/verelo",
        )
    )
    api_engine = create_engine(settings.database_url)
    tenant, workspace, owner, stranger = uuid4(), uuid4(), uuid4(), uuid4()
    owner_email = f"owner-{owner}@example.invalid"
    stranger_email = f"stranger-{stranger}@example.invalid"
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
                VALUES (:id,:tenant,'Synthetic',true)"""
            ),
            {"id": workspace, "tenant": tenant},
        )
        connection.execute(
            text("""INSERT INTO users (id,tenant_id,entra_object_id,display_name,email)
                VALUES (:id,:tenant,:entra,:name,:email)"""),
            [
                {
                    "id": owner,
                    "tenant": tenant,
                    "entra": uuid4(),
                    "name": "Owner",
                    "email": owner_email,
                },
                {
                    "id": stranger,
                    "tenant": tenant,
                    "entra": uuid4(),
                    "name": "Stranger",
                    "email": stranger_email,
                },
            ],
        )
        connection.execute(
            text(
                """INSERT INTO identity_accounts
                (id,tenant_id,workspace_id,user_id,provider,subject,login_email_normalized)
                VALUES (:id,:tenant,:workspace,:user,'magic_link',:subject,:email)"""
            ),
            {
                "id": uuid4(),
                "tenant": tenant,
                "workspace": workspace,
                "user": stranger,
                "subject": str(uuid4()),
                "email": stranger_email,
            },
        )
    app = create_app(api_engine)
    current = {
        "session": synthetic_session(
            principal_id=owner,
            tenant_id=tenant,
            workspace_id=workspace,
            request_id=str(uuid4()),
            capabilities=("projects:create",),
        )
    }
    app.dependency_overrides[resolve_session] = lambda: current["session"]
    project_id = document_id = None
    try:
        with TestClient(app) as client:
            created = client.post(
                "/api/v1/projects",
                headers={"X-CSRF-Token": CSRF, "Origin": "http://127.0.0.1:5173"},
                json={"name": "Synthetic API project"},
            )
            assert created.status_code == 201, created.text
            project_id = created.json()["project_id"]
            document = client.post(
                f"/api/v1/projects/{project_id}/documents",
                headers={"X-CSRF-Token": CSRF, "Origin": "http://127.0.0.1:5173"},
                json={
                    "title": "Fictional customer interview",
                    "meeting_date": datetime.now(UTC).isoformat(),
                    "language": "en-US",
                    "consent_acknowledged": True,
                    "consent_policy_version": "synthetic-consent-v1",
                },
            )
            assert document.status_code == 201, document.text
            document_id = document.json()["document_id"]
            synthetic_text = b"Host: Um welcome.\nGuest: I I prefer the fictional blue plan."
            digest = sha256(synthetic_text).hexdigest()
            ingestion = client.post(
                f"/api/v1/documents/{document_id}/ingestions",
                headers={"X-CSRF-Token": CSRF, "Origin": "http://127.0.0.1:5173"},
                json={
                    "source_kind": "transcript",
                    "filename": "fictional-interview.txt",
                    "declared_media_type": "text/plain",
                    "byte_length": len(synthetic_text),
                    "sha256": digest,
                    "operation_key": f"create-{uuid4()}",
                },
            )
            assert ingestion.status_code == 201, ingestion.text
            ingestion_id = ingestion.json()["ingestion_id"]
            chunk = client.put(
                f"/api/v1/ingestions/{ingestion_id}/chunks/1",
                headers={"X-CSRF-Token": CSRF, "Origin": "http://127.0.0.1:5173"},
                json={
                    "sequence": 1,
                    "content_base64": base64.b64encode(synthetic_text).decode("ascii"),
                    "sha256": digest,
                },
            )
            assert chunk.status_code == 200, chunk.text
            finalize_key = f"finalize-{uuid4()}"
            finalize_payload = {
                "operation_key": finalize_key,
                "expected_byte_length": len(synthetic_text),
                "expected_sha256": digest,
            }
            finalized = client.post(
                f"/api/v1/ingestions/{ingestion_id}/finalize",
                headers={"X-CSRF-Token": CSRF, "Origin": "http://127.0.0.1:5173"},
                json=finalize_payload,
            )
            assert finalized.status_code == 200, finalized.text
            assert finalized.json()["state"] == "approved"
            replayed_finalize = client.post(
                f"/api/v1/ingestions/{ingestion_id}/finalize",
                headers={"X-CSRF-Token": CSRF, "Origin": "http://127.0.0.1:5173"},
                json=finalize_payload,
            )
            assert replayed_finalize.status_code == 200
            conflicting_finalize = client.post(
                f"/api/v1/ingestions/{ingestion_id}/finalize",
                headers={"X-CSRF-Token": CSRF, "Origin": "http://127.0.0.1:5173"},
                json={**finalize_payload, "expected_byte_length": len(synthetic_text) + 1},
            )
            assert conflicting_finalize.status_code == 409
            draft = client.get(f"/api/v1/ingestions/{ingestion_id}/draft").json()
            corrected_text = draft["canonical_text"] + "\nOwner: Correction reviewed."
            corrected = client.put(
                f"/api/v1/ingestions/{ingestion_id}/draft",
                headers={"X-CSRF-Token": CSRF, "Origin": "http://127.0.0.1:5173"},
                json={
                    "canonical_text": corrected_text,
                    "expected_revision": draft["revision"],
                    "expected_content_sha256": draft["content_sha256"],
                    "reason_code": "transcription_correction",
                },
            )
            assert corrected.status_code == 200, corrected.text
            draft = corrected.json()
            assert draft["approval"] is None
            approved = client.post(
                f"/api/v1/ingestions/{ingestion_id}/approvals",
                headers={"X-CSRF-Token": CSRF, "Origin": "http://127.0.0.1:5173"},
                json={
                    "content_sha256": draft["content_sha256"],
                    "expected_revision": draft["revision"],
                    "reason_code": "approved_correction",
                },
            )
            assert approved.status_code == 201, approved.text
            draft = approved.json()
            publish_key = f"publish-{uuid4()}"
            publish_payload = {
                "approved_content_sha256": draft["content_sha256"],
                "expected_draft_revision": draft["revision"],
                "expected_active_transcript_version_id": None,
                "operation_key": publish_key,
            }
            published = client.post(
                f"/api/v1/ingestions/{ingestion_id}/publication",
                headers={"X-CSRF-Token": CSRF, "Origin": "http://127.0.0.1:5173"},
                json=publish_payload,
            )
            assert published.status_code == 201, published.text
            publication = published.json()
            replayed_publication = client.post(
                f"/api/v1/ingestions/{ingestion_id}/publication",
                headers={"X-CSRF-Token": CSRF, "Origin": "http://127.0.0.1:5173"},
                json=publish_payload,
            )
            assert replayed_publication.status_code == 201
            assert replayed_publication.json() == publication
            assert publication["canonical_text"] == (
                "Host: welcome.\nGuest: I prefer the fictional blue plan.\n"
                "Owner: Correction reviewed."
            )
            assert publication["content_sha256"] == publication["reproduced_sha256"]
            assert publication["passage_count"] > 0
            assert publication["index_job_count"] == publication["passage_count"]
            reproduced = client.get(f"/api/v1/documents/{document_id}/transcript-publication")
            assert reproduced.json() == publication
            assert client.get(f"/api/v1/documents/{document_id}/ingestions").json()["items"]
            source = client.get(f"/api/v1/source-assets/{publication['source_asset_id']}/content")
            assert base64.b64decode(source.json()["content_base64"]) == synthetic_text
            assert (
                client.get(
                    f"/api/v1/source-assets/{publication['source_asset_id']}/waveform"
                ).status_code
                == 404
            )
            alignment = client.get(f"/api/v1/ingestions/{ingestion_id}/word-alignment")
            assert alignment.status_code == 200
            assert alignment.json()["available"] is False
            for format_name in ("txt", "md", "json", "pdf"):
                download = client.get(
                    f"/api/v1/documents/{document_id}/transcript-downloads/{format_name}"
                )
                assert download.status_code == 200
                content = base64.b64decode(download.json()["content_base64"])
                assert content.startswith(b"%PDF-") if format_name == "pdf" else bool(content)
            assert client.get(f"/api/v1/documents/{document_id}").status_code == 200
            assert client.get(f"/api/v1/projects/{project_id}/documents").json()["items"]
            current["session"] = synthetic_session(
                principal_id=stranger,
                tenant_id=tenant,
                workspace_id=workspace,
                request_id=str(uuid4()),
            )
            denied = client.get(f"/api/v1/documents/{document_id}")
            assert denied.status_code == 404
            assert set(denied.json()) == {"code", "message", "request_id", "retryable"}
            assert client.get(f"/api/v1/projects/{project_id}").status_code == 404
            assert (
                client.get(f"/api/v1/documents/{document_id}/transcript-publication").status_code
                == 404
            )
            assert (
                client.get(f"/api/v1/ingestions/{ingestion_id}/word-alignment").status_code == 404
            )
            assert (
                client.get(f"/api/v1/documents/{document_id}/transcript-downloads/pdf").status_code
                == 404
            )
            assert (
                client.get(
                    f"/api/v1/source-assets/{publication['source_asset_id']}/content"
                ).status_code
                == 404
            )
            assert (
                client.get(
                    f"/api/v1/source-assets/{publication['source_asset_id']}/waveform"
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
            granted = client.put(
                f"/api/v1/projects/{project_id}/members/by-email",
                headers={"X-CSRF-Token": CSRF, "Origin": "http://127.0.0.1:5173"},
                json={
                    "email": stranger_email,
                    "role": "reader",
                    "enabled": True,
                    "expected_revision": 0,
                },
            )
            assert granted.status_code == 200, granted.text
            members = client.get(f"/api/v1/projects/{project_id}/members")
            assert {item["email"] for item in members.json()["items"]} == {
                owner_email,
                stranger_email,
            }
            current["session"] = synthetic_session(
                principal_id=stranger,
                tenant_id=tenant,
                workspace_id=workspace,
                request_id=str(uuid4()),
            )
            assert client.get(f"/api/v1/projects/{project_id}").json()["my_role"] == "reader"
            assert len(client.get("/api/v1/projects").json()["items"]) == 1
            assert client.get(f"/api/v1/ingestions/{ingestion_id}").status_code == 200
            reader_ingestion_write = client.post(
                f"/api/v1/documents/{document_id}/ingestions",
                headers={"X-CSRF-Token": CSRF, "Origin": "http://127.0.0.1:5173"},
                json={
                    "source_kind": "transcript",
                    "filename": "denied.txt",
                    "declared_media_type": "text/plain",
                    "byte_length": 1,
                    "sha256": sha256(b"x").hexdigest(),
                    "operation_key": f"reader-denied-{uuid4()}",
                },
            )
            assert reader_ingestion_write.status_code == 403
            reader_correction = client.put(
                f"/api/v1/ingestions/{ingestion_id}/draft",
                headers={"X-CSRF-Token": CSRF, "Origin": "http://127.0.0.1:5173"},
                json={
                    "canonical_text": "Reader cannot replace this.",
                    "expected_revision": draft["revision"],
                    "expected_content_sha256": draft["content_sha256"],
                    "reason_code": "transcription_correction",
                },
            )
            assert reader_correction.status_code == 403
            denied_write = client.post(
                f"/api/v1/projects/{project_id}/documents",
                headers={"X-CSRF-Token": CSRF, "Origin": "http://127.0.0.1:5173"},
                json={
                    "title": "Denied reader write",
                    "meeting_date": datetime.now(UTC).isoformat(),
                    "language": "en-US",
                    "consent_acknowledged": True,
                    "consent_policy_version": "synthetic-consent-v1",
                },
            )
            assert denied_write.status_code == 403
            assert client.get("/api/v1/me").json()["email"] == stranger_email
            updated = client.patch(
                "/api/v1/me",
                headers={"X-CSRF-Token": CSRF, "Origin": "http://127.0.0.1:5173"},
                json={"display_name": "Unique Stranger Profile"},
            )
            assert updated.json()["display_name"] == "Unique Stranger Profile"
    finally:
        api_engine.dispose()
        with admin.begin() as connection:
            if document_id:
                connection.execute(
                    text("UPDATE documents SET active_transcript_version_id=NULL WHERE id=:id"),
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
                    text("UPDATE raw_transcripts SET ingestion_id=NULL WHERE document_id=:id"),
                    {"id": document_id},
                )
                connection.execute(
                    text("""UPDATE ingestions SET source_asset_id=NULL,draft_version_id=NULL
                    WHERE document_id=:id"""),
                    {"id": document_id},
                )
                connection.execute(
                    text("DELETE FROM ingestions WHERE document_id=:id"), {"id": document_id}
                )
                for table in (
                    "audit_events",
                    "outbox_events",
                    "jobs",
                    "passages",
                    "transcript_approvals",
                    "transcript_versions",
                    "raw_transcripts",
                    "source_assets",
                ):
                    connection.execute(
                        text(f"DELETE FROM {table} WHERE document_id=:id"), {"id": document_id}
                    )
                connection.execute(text("DELETE FROM documents WHERE id=:id"), {"id": document_id})
            if project_id:
                connection.execute(
                    text("DELETE FROM outbox_events WHERE project_id=:id"), {"id": project_id}
                )
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
                text("DELETE FROM identity_accounts WHERE user_id IN (:a,:b)"),
                {"a": owner, "b": stranger},
            )
            connection.execute(
                text("DELETE FROM users WHERE id IN (:a,:b)"), {"a": owner, "b": stranger}
            )
            connection.execute(text("DELETE FROM workspaces WHERE id=:id"), {"id": workspace})
            connection.execute(text("DELETE FROM tenants WHERE id=:id"), {"id": tenant})
        admin.dispose()
