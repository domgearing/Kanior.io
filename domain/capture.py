"""Persistent, provider-neutral recording capture and recovery service."""

from __future__ import annotations

import base64
import binascii
import json
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import cast
from uuid import UUID, uuid4

from sqlalchemy import Engine, text

from api.database import scoped_transaction
from connectors.local_storage import LocalObjectStorage
from contracts.models import (
    AuthContext,
    CaptureChunkUpload,
    CaptureCreate,
    CaptureFinalize,
    CaptureGap,
    CaptureSession,
    CaptureTransition,
)
from domain.errors import CONFLICT, FORBIDDEN, NOT_FOUND, DomainError
from domain.media import MediaValidationError, validate_audio
from domain.recorder import RecorderState, RecorderTransitionError, RecordingGap, RecordingSession

_MAX_CHUNK_BYTES = 5 * 1024 * 1024


class CaptureService:
    def __init__(self, engine: Engine, object_root: str) -> None:
        self._engine = engine
        self._objects = LocalObjectStorage(Path(object_root))

    def create(self, context: AuthContext, request: CaptureCreate) -> CaptureSession:
        with scoped_transaction(self._engine, context) as connection:
            project_id = connection.execute(
                text("SELECT project_id FROM documents WHERE id=:id AND state='created'"),
                {"id": request.document_id},
            ).scalar_one_or_none()
        if project_id is None:
            raise NOT_FOUND
        capture_id = uuid4()
        with scoped_transaction(self._engine, context, project_id) as connection:
            role = connection.execute(
                text("""SELECT role FROM project_memberships
                WHERE project_id=:project AND user_id=:user AND enabled"""),
                {"project": project_id, "user": context.principal_id},
            ).scalar_one_or_none()
            if role not in {"contributor", "project_owner"}:
                raise FORBIDDEN
            connection.execute(
                text("""INSERT INTO capture_sessions
                (id,tenant_id,workspace_id,project_id,document_id,created_by,state)
                VALUES (:id,:tenant,:workspace,:project,:document,:actor,'created')"""),
                {
                    "id": capture_id,
                    "tenant": context.tenant_id,
                    "workspace": context.workspace_id,
                    "project": project_id,
                    "document": request.document_id,
                    "actor": context.principal_id,
                },
            )
            return self._response(connection, capture_id)

    def get(self, context: AuthContext, capture_id: UUID) -> CaptureSession:
        project_id = self._resolve_project(context, capture_id)
        with scoped_transaction(self._engine, context, project_id) as connection:
            return self._response(connection, capture_id)

    def transition(
        self, context: AuthContext, capture_id: UUID, request: CaptureTransition
    ) -> CaptureSession:
        project_id = self._resolve_project(context, capture_id)
        with scoped_transaction(self._engine, context, project_id) as connection:
            role = connection.execute(
                text("""SELECT role FROM project_memberships
                  WHERE project_id=:project AND user_id=:actor AND enabled"""),
                {"project": project_id, "actor": context.principal_id},
            ).scalar_one_or_none()
            if role not in {"contributor", "project_owner"}:
                raise FORBIDDEN
            row = (
                connection.execute(
                    text("SELECT * FROM capture_sessions WHERE id=:id FOR UPDATE"),
                    {"id": capture_id},
                )
                .mappings()
                .one_or_none()
            )
            if row is None:
                raise NOT_FOUND
            if row["state"] == "aborted":
                raise CONFLICT
            state = cast(RecorderState, "idle" if row["state"] == "created" else row["state"])
            gaps = tuple(
                RecordingGap(gap["start_ms"], gap.get("end_ms"), gap["reason"])
                for gap in row["gaps"]
            )
            recorder = RecordingSession(state, row["acknowledged_chunks"], gaps)
            try:
                updated = recorder.transition(
                    request.event, at_ms=request.at_ms, reason=request.reason
                )
            except RecorderTransitionError as error:
                raise CONFLICT from error
            serialized = [
                {"start_ms": gap.start_ms, "end_ms": gap.end_ms, "reason": gap.reason}
                for gap in updated.gaps
            ]
            connection.execute(
                text("""UPDATE capture_sessions SET state=:state,gaps=CAST(:gaps AS jsonb),
                updated_at=:now WHERE id=:id"""),
                {
                    "state": updated.state,
                    "gaps": json.dumps(serialized),
                    "now": datetime.now(UTC),
                    "id": capture_id,
                },
            )
            return self._response(connection, capture_id)

    def put_chunk(
        self,
        context: AuthContext,
        capture_id: UUID,
        path_sequence: int,
        request: CaptureChunkUpload,
    ) -> CaptureSession:
        if request.sequence != path_sequence:
            raise DomainError("invalid_input", 422, "The chunk sequence is invalid.")
        try:
            data = base64.b64decode(request.content_base64, validate=True)
        except (ValueError, binascii.Error) as error:
            raise DomainError("invalid_input", 422, "The audio chunk is invalid.") from error
        if not data or len(data) > _MAX_CHUNK_BYTES or sha256(data).hexdigest() != request.sha256:
            raise DomainError("invalid_input", 422, "The audio chunk is invalid.")
        project_id = self._resolve_project(context, capture_id)
        stored = self._objects.put_immutable(
            data, request.sha256, f"capture:{capture_id}:{path_sequence}"
        )
        with scoped_transaction(self._engine, context, project_id) as connection:
            session = (
                connection.execute(
                    text("SELECT * FROM capture_sessions WHERE id=:id FOR UPDATE"),
                    {"id": capture_id},
                )
                .mappings()
                .one_or_none()
            )
            if session is None:
                raise NOT_FOUND
            existing = connection.execute(
                text("""SELECT sha256 FROM capture_chunks
                WHERE capture_session_id=:capture AND sequence=:sequence"""),
                {"capture": capture_id, "sequence": path_sequence},
            ).scalar_one_or_none()
            if existing is not None:
                if existing != request.sha256:
                    raise CONFLICT
                return self._response(connection, capture_id)
            if session["state"] not in {
                "recording",
                "paused",
                "interrupted",
                "finalizing",
                "uploading",
            }:
                raise CONFLICT
            if path_sequence != session["acknowledged_chunks"] + 1:
                raise CONFLICT
            connection.execute(
                text("""INSERT INTO capture_chunks
                (id,tenant_id,workspace_id,project_id,capture_session_id,sequence,object_ref,
                 byte_length,sha256,acknowledged_at)
                VALUES (:id,:tenant,:workspace,:project,:capture,:sequence,:ref,:length,
                 :digest,:now)"""),
                {
                    "id": uuid4(),
                    "tenant": context.tenant_id,
                    "workspace": context.workspace_id,
                    "project": project_id,
                    "capture": capture_id,
                    "sequence": path_sequence,
                    "ref": stored.object_ref,
                    "length": stored.byte_length,
                    "digest": stored.sha256,
                    "now": datetime.now(UTC),
                },
            )
            connection.execute(
                text(
                    """UPDATE capture_sessions SET acknowledged_chunks=:sequence,
                    updated_at=:now WHERE id=:id"""
                ),
                {"sequence": path_sequence, "now": datetime.now(UTC), "id": capture_id},
            )
            return self._response(connection, capture_id)

    def finalize(
        self, context: AuthContext, capture_id: UUID, request: CaptureFinalize
    ) -> CaptureSession:
        project_id = self._resolve_project(context, capture_id)
        with scoped_transaction(self._engine, context, project_id) as connection:
            session = (
                connection.execute(
                    text("SELECT * FROM capture_sessions WHERE id=:id FOR UPDATE"),
                    {"id": capture_id},
                )
                .mappings()
                .one_or_none()
            )
            if session is None:
                raise NOT_FOUND
            existing = (
                connection.execute(
                    text("""SELECT sa.id,cs.ingestion_id FROM source_assets sa
                JOIN capture_sessions cs ON cs.id=sa.capture_session_id
                WHERE sa.capture_session_id=:id AND sa.kind='audio'"""),
                    {"id": capture_id},
                )
                .mappings()
                .one_or_none()
            )
            if existing is not None:
                return self._response(connection, capture_id)
            if (
                session["state"] not in {"finalizing", "uploading"}
                or session["acknowledged_chunks"] == 0
            ):
                raise CONFLICT
            chunks = (
                connection.execute(
                    text("""SELECT sequence,object_ref FROM capture_chunks
                WHERE capture_session_id=:id ORDER BY sequence"""),
                    {"id": capture_id},
                )
                .mappings()
                .all()
            )
            if [row["sequence"] for row in chunks] != list(
                range(1, session["acknowledged_chunks"] + 1)
            ):
                raise CONFLICT
            audio = b"".join(self._objects.read_version(row["object_ref"]) for row in chunks)
            digest = sha256(audio).hexdigest()
            stored = self._objects.put_immutable(audio, digest, f"audio:{capture_id}")
            try:
                metadata = validate_audio(request.filename, audio)
                accepted = metadata.media_type == request.detected_mime
            except MediaValidationError:
                metadata = None
                accepted = False
            source_id = uuid4()
            connection.execute(
                text("""INSERT INTO source_assets
                (id,tenant_id,workspace_id,project_id,document_id,capture_session_id,kind,
                 original_filename,detected_mime,object_ref,byte_length,sha256,duration_ms,
                 provenance,quarantine_state)
                VALUES (:id,:tenant,:workspace,:project,:document,:capture,'audio',:filename,
                 :mime,:ref,:length,:digest,:duration,'synthetic_capture',:quarantine)"""),
                {
                    "id": source_id,
                    "tenant": context.tenant_id,
                    "workspace": context.workspace_id,
                    "project": project_id,
                    "document": session["document_id"],
                    "capture": capture_id,
                    "filename": request.filename,
                    "mime": request.detected_mime,
                    "ref": stored.object_ref,
                    "length": stored.byte_length,
                    "digest": digest,
                    "duration": metadata.duration_ms
                    if metadata is not None
                    else request.duration_ms,
                    "quarantine": "accepted" if accepted else "rejected",
                },
            )
            connection.execute(
                text("UPDATE capture_sessions SET state=:state,updated_at=:now WHERE id=:id"),
                {
                    "state": "complete" if accepted else "failed",
                    "now": datetime.now(UTC),
                    "id": capture_id,
                },
            )
            if accepted:
                ingestion_id = uuid4()
                operation_key = f"capture-finalize:{capture_id}"
                payload_hash = sha256(
                    f"{session['document_id']}:{source_id}:{digest}".encode()
                ).hexdigest()
                connection.execute(
                    text("""INSERT INTO ingestions
                    (id,tenant_id,workspace_id,project_id,document_id,created_by,source_kind,
                     original_filename,declared_media_type,expected_byte_length,expected_sha256,
                     uploaded_bytes,acknowledged_chunks,source_asset_id,state,stage,
                     gap_count,operation_key,payload_hash)
                    VALUES (:id,:tenant,:workspace,:project,:document,:actor,'audio',:filename,
                     :mime,:length,:digest,:length,:chunks,:source,'transcription_queued',
                     'transcription',:gaps,:operation,:payload_hash)"""),
                    {
                        "id": ingestion_id,
                        "tenant": context.tenant_id,
                        "workspace": context.workspace_id,
                        "project": project_id,
                        "document": session["document_id"],
                        "actor": context.principal_id,
                        "filename": request.filename,
                        "mime": request.detected_mime,
                        "length": stored.byte_length,
                        "digest": digest,
                        "chunks": session["acknowledged_chunks"],
                        "source": source_id,
                        "gaps": len(session["gaps"]),
                        "operation": operation_key,
                        "payload_hash": payload_hash,
                    },
                )
                connection.execute(
                    text("""UPDATE capture_sessions SET ingestion_id=:ingestion,updated_at=:now
                    WHERE id=:id"""),
                    {"ingestion": ingestion_id, "now": datetime.now(UTC), "id": capture_id},
                )
            result = self._response(connection, capture_id)
        if not accepted:
            raise DomainError(
                "invalid_input", 422, "The assembled audio failed quarantine validation."
            )
        return result

    def _resolve_project(self, context: AuthContext, capture_id: UUID) -> UUID:
        with scoped_transaction(self._engine, context) as connection:
            project_id = connection.execute(
                text("SELECT project_id FROM capture_sessions WHERE id=:id"), {"id": capture_id}
            ).scalar_one_or_none()
        if project_id is None:
            raise NOT_FOUND
        return cast(UUID, project_id)

    def _response(self, connection, capture_id: UUID) -> CaptureSession:  # type: ignore[no-untyped-def]
        row = (
            connection.execute(
                text("""SELECT cs.*,
            (SELECT id FROM source_assets WHERE capture_session_id=cs.id AND kind='audio'
             ORDER BY created_at DESC LIMIT 1) AS source_asset_id
            FROM capture_sessions cs WHERE cs.id=:id"""),
                {"id": capture_id},
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise NOT_FOUND
        return CaptureSession(
            capture_session_id=row["id"],
            document_id=row["document_id"],
            state=row["state"],
            acknowledged_chunks=row["acknowledged_chunks"],
            gaps=[CaptureGap(**gap) for gap in row["gaps"]],
            source_asset_id=row["source_asset_id"],
            ingestion_id=row["ingestion_id"],
        )

    def project_id(self, context: AuthContext, capture_id: UUID) -> UUID:
        """Resolve an authorized capture to its project for scoped integrations."""

        return self._resolve_project(context, capture_id)
