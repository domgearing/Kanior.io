"""Durable bridge from verified Recall completion events into ingestion."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from hashlib import sha256
from typing import Protocol
from uuid import UUID, uuid4

from sqlalchemy import Engine, text

from api.database import scoped_transaction
from contracts.models import AuthContext
from domain.providers import ObjectStorage, StoredCapture, TranscriptionProvider
from domain.workflow import IngestionWorkflowService


class RecallCaptureProvider(Protocol):
    def copy_original(
        self, recording_id: str, storage: ObjectStorage, operation_key: str
    ) -> StoredCapture: ...


class RecallIngestionService:
    def __init__(
        self,
        engine: Engine,
        storage: ObjectStorage,
        recall: RecallCaptureProvider,
        transcription: TranscriptionProvider,
        workflow: IngestionWorkflowService,
    ) -> None:
        self._engine = engine
        self._storage = storage
        self._recall = recall
        self._transcription = transcription
        self._workflow = workflow

    def enqueue_completed(self, context: AuthContext, project_id: UUID) -> int:
        """Convert verified, mapped completion events into project-scoped jobs."""

        queued = 0
        with scoped_transaction(self._engine, context, project_id, "jobs.execute") as connection:
            rows = (
                connection.execute(
                    text("""SELECT e.event_id,e.recording_id,u.capture_session_id,cs.document_id
                FROM recall_webhook_events e
                JOIN recall_uploads u ON u.sdk_upload_id=e.sdk_upload_id
                JOIN capture_sessions cs ON cs.id=u.capture_session_id
                WHERE e.event_type='sdk_upload.complete' AND e.recording_id IS NOT NULL
                  AND u.project_id=:project"""),
                    {"project": project_id},
                )
                .mappings()
                .all()
            )
            for row in rows:
                payload = {
                    "event_id": row["event_id"],
                    "recording_id": row["recording_id"],
                    "capture_session_id": str(row["capture_session_id"]),
                    "document_id": str(row["document_id"]),
                    "project_id": str(project_id),
                }
                encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
                result = connection.execute(
                    text("""INSERT INTO jobs
                    (id,tenant_id,workspace_id,project_id,document_id,job_type,operation_key,
                     payload_hash,payload,trace_id,max_attempts)
                    VALUES (:id,:tenant,:workspace,:project,:document,'recall_ingest',:operation,
                     :digest,CAST(:payload AS jsonb),:trace,20)
                    ON CONFLICT (tenant_id,workspace_id,project_id,operation_key) DO NOTHING
                    RETURNING id"""),
                    {
                        "id": uuid4(),
                        "tenant": context.tenant_id,
                        "workspace": context.workspace_id,
                        "project": project_id,
                        "document": row["document_id"],
                        "operation": f"recall-ingest:{row['event_id']}",
                        "digest": sha256(encoded).hexdigest(),
                        "payload": encoded.decode(),
                        "trace": str(row["event_id"])[:128],
                    },
                ).scalar_one_or_none()
                queued += result is not None
        return queued

    def process(self, context: AuthContext, project_id: UUID, payload: dict[str, object]) -> str:
        expected = {"event_id", "recording_id", "capture_session_id", "document_id", "project_id"}
        if set(payload) != expected:
            raise ValueError("unsafe_job_payload")
        capture_id = UUID(str(payload["capture_session_id"]))
        document_id = UUID(str(payload["document_id"]))
        if UUID(str(payload["project_id"])) != project_id:
            raise ValueError("job_scope_mismatch")
        recording_id = str(payload["recording_id"])

        with scoped_transaction(self._engine, context, project_id, "jobs.execute") as connection:
            verified = connection.execute(
                text("""SELECT 1 FROM recall_webhook_events e
                JOIN recall_uploads u ON u.sdk_upload_id=e.sdk_upload_id
                JOIN capture_sessions cs ON cs.id=u.capture_session_id
                WHERE e.event_id=:event AND e.event_type='sdk_upload.complete'
                  AND e.recording_id=:recording AND u.capture_session_id=:capture
                  AND u.project_id=:project AND cs.document_id=:document"""),
                {
                    "event": str(payload["event_id"]),
                    "recording": recording_id,
                    "capture": capture_id,
                    "project": project_id,
                    "document": document_id,
                },
            ).scalar_one_or_none()
        if verified is None:
            raise ValueError("unverified_recall_job")

        copied = self._recall.copy_original(
            recording_id, self._storage, f"recall-copy:{recording_id}"
        )
        stored = copied.stored_object
        source_id = uuid4()
        ingestion_id = uuid4()
        with scoped_transaction(self._engine, context, project_id, "jobs.execute") as connection:
            capture = (
                connection.execute(
                    text("""SELECT * FROM capture_sessions WHERE id=:id FOR UPDATE"""),
                    {"id": capture_id},
                )
                .mappings()
                .one()
            )
            if capture["project_id"] != project_id or capture["document_id"] != document_id:
                raise ValueError("job_scope_mismatch")
            existing = connection.execute(
                text("SELECT ingestion_id FROM capture_sessions WHERE id=:id"), {"id": capture_id}
            ).scalar_one_or_none()
            if existing is not None:
                ingestion_id = existing
            else:
                connection.execute(
                    text("""INSERT INTO source_assets
                    (id,tenant_id,workspace_id,project_id,document_id,capture_session_id,kind,
                     original_filename,detected_mime,object_ref,byte_length,sha256,duration_ms,
                     provenance,quarantine_state)
                    VALUES (:id,:tenant,:workspace,:project,:document,:capture,'audio',
                     'recall-audio.mp3','audio/mpeg',:ref,:length,:digest,:duration,
                     'recall_desktop','accepted')"""),
                    {
                        "id": source_id,
                        "tenant": context.tenant_id,
                        "workspace": context.workspace_id,
                        "project": project_id,
                        "document": document_id,
                        "capture": capture_id,
                        "ref": stored.object_ref,
                        "length": stored.byte_length,
                        "digest": stored.sha256,
                        "duration": copied.duration_ms,
                    },
                )
                operation = f"recall-capture:{capture_id}"
                operation_digest = sha256(
                    f"{document_id}:{source_id}:{stored.sha256}".encode()
                ).hexdigest()
                connection.execute(
                    text("""INSERT INTO ingestions
                    (id,tenant_id,workspace_id,project_id,document_id,created_by,source_kind,
                     original_filename,declared_media_type,expected_byte_length,expected_sha256,
                     uploaded_bytes,acknowledged_chunks,source_asset_id,state,stage,gap_count,
                     operation_key,payload_hash)
                    VALUES (:id,:tenant,:workspace,:project,:document,:actor,'audio',
                     'recall-audio.mp3','audio/mpeg',:length,:digest,:length,1,:source,
                     'transcription_queued','transcription',0,:operation,:payload_hash)"""),
                    {
                        "id": ingestion_id,
                        "tenant": context.tenant_id,
                        "workspace": context.workspace_id,
                        "project": project_id,
                        "document": document_id,
                        "actor": capture["created_by"],
                        "length": stored.byte_length,
                        "digest": stored.sha256,
                        "source": source_id,
                        "operation": operation,
                        "payload_hash": operation_digest,
                    },
                )
                connection.execute(
                    text("""UPDATE capture_sessions SET state='complete',ingestion_id=:ingestion,
                    updated_at=:now WHERE id=:id"""),
                    {"ingestion": ingestion_id, "now": datetime.now(UTC), "id": capture_id},
                )
        self._workflow.process_existing_audio_with_provider(
            context,
            project_id,
            ingestion_id,
            self._transcription,
            provider_name="assemblyai",
        )
        return str(ingestion_id)
