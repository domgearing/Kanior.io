"""Authorized durable source-to-publication workflow for the Phase 2 MVP."""

from __future__ import annotations

import base64
import binascii
import json
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any, cast
from uuid import UUID, uuid4

from sqlalchemy import Connection, Engine, text

from api.database import scoped_transaction
from connectors.local_storage import LocalObjectStorage
from connectors.synthetic_assemblyai import SyntheticAssemblyAIAdapter
from contracts.models import (
    AuthContext,
    CleanupEditManifest,
    CorrectedDraftPut,
    DraftApproval,
    Ingestion,
    IngestionAction,
    IngestionChunkPut,
    IngestionCreate,
    IngestionFinalize,
    IngestionPage,
    SegmentWordAlignment,
    SourceAssetContent,
    SourceAssetWaveform,
    TimedWord,
    TranscriptApprovalCreate,
    TranscriptDownload,
    TranscriptDraft,
    TranscriptPublication,
    TranscriptPublicationCreate,
    TranscriptSegment,
    TranscriptWordAlignment,
)
from domain.errors import CONFLICT, FORBIDDEN, NOT_FOUND, DomainError
from domain.ingestion import (
    IngestionError,
    ParsedTranscript,
    Segment,
    construct_passages,
    controlled_cleanup,
    format_segmented_transcript,
    parse_transcript,
    validate_cleanup_with_manifest,
)
from domain.media import MediaValidationError, validate_audio
from domain.providers import ObjectStorage, TranscriptionProvider, TranscriptSegmentResult
from domain.reconciliation import ReconciliationError, reconcile_provider_segments
from domain.transcript_pdf import render_transcript_pdf
from domain.waveform import audio_waveform
from domain.word_alignment import extract_word_alignment

_MAX_CHUNK_BYTES = 5 * 1024 * 1024
_TRANSCRIPT_LIMIT = 20 * 1024 * 1024
_AUDIO_LIMIT = 2 * 1024 * 1024 * 1024
_TERMINAL = {"published", "failed_terminal", "aborted"}


class IngestionWorkflowService:
    """One authoritative workflow over immutable objects and scoped PostgreSQL records."""

    def __init__(
        self,
        engine: Engine,
        object_root: str,
        *,
        object_storage: ObjectStorage | None = None,
        defer_audio_transcription: bool = False,
    ) -> None:
        self._engine = engine
        self._objects = object_storage or LocalObjectStorage(Path(object_root))
        self._defer_audio_transcription = defer_audio_transcription

    def create(
        self, context: AuthContext, document_id: UUID, request: IngestionCreate
    ) -> Ingestion:
        project_id = self._document_project(context, document_id)
        payload_hash = sha256(
            json.dumps(request.model_dump(mode="json"), sort_keys=True).encode()
        ).hexdigest()
        with scoped_transaction(self._engine, context, project_id) as connection:
            self._require_role(connection, project_id, context.principal_id, write=True)
            prior = (
                connection.execute(
                    text("""SELECT id,payload_hash FROM ingestions
                    WHERE operation_key=:key"""),
                    {"key": request.operation_key},
                )
                .mappings()
                .one_or_none()
            )
            if prior is not None:
                if prior["payload_hash"] != payload_hash:
                    raise CONFLICT
                return self._response(connection, prior["id"], context.principal_id)
            ingestion_id = uuid4()
            connection.execute(
                text("""INSERT INTO ingestions
                (id,tenant_id,workspace_id,project_id,document_id,created_by,source_kind,
                 original_filename,declared_media_type,expected_byte_length,expected_sha256,
                 operation_key,payload_hash)
                VALUES (:id,:tenant,:workspace,:project,:document,:actor,:kind,:filename,
                 :mime,:length,:digest,:operation,:payload_hash)"""),
                {
                    "id": ingestion_id,
                    "tenant": context.tenant_id,
                    "workspace": context.workspace_id,
                    "project": project_id,
                    "document": document_id,
                    "actor": context.principal_id,
                    "kind": request.source_kind,
                    "filename": request.filename,
                    "mime": request.declared_media_type,
                    "length": request.byte_length,
                    "digest": request.sha256,
                    "operation": request.operation_key,
                    "payload_hash": payload_hash,
                },
            )
            return self._response(connection, ingestion_id, context.principal_id)

    def put_chunk(
        self,
        context: AuthContext,
        ingestion_id: UUID,
        path_sequence: int,
        request: IngestionChunkPut,
    ) -> Ingestion:
        if request.sequence != path_sequence:
            raise DomainError("invalid_input", 422, "The chunk sequence is invalid.")
        try:
            data = base64.b64decode(request.content_base64, validate=True)
        except (ValueError, binascii.Error) as error:
            raise DomainError("invalid_input", 422, "The source chunk is invalid.") from error
        if not data or len(data) > _MAX_CHUNK_BYTES or sha256(data).hexdigest() != request.sha256:
            raise DomainError("invalid_input", 422, "The source chunk is invalid.")
        project_id = self._ingestion_project(context, ingestion_id)
        stored = self._objects.put_immutable(
            data, request.sha256, f"ingestion:{ingestion_id}:{path_sequence}"
        )
        with scoped_transaction(self._engine, context, project_id) as connection:
            self._require_role(connection, project_id, context.principal_id, write=True)
            row = (
                connection.execute(
                    text("SELECT * FROM ingestions WHERE id=:id FOR UPDATE"), {"id": ingestion_id}
                )
                .mappings()
                .one_or_none()
            )
            if row is None:
                raise NOT_FOUND
            existing = connection.execute(
                text("""SELECT sha256 FROM ingestion_chunks
                WHERE ingestion_id=:id AND sequence=:sequence"""),
                {"id": ingestion_id, "sequence": path_sequence},
            ).scalar_one_or_none()
            if existing is not None:
                if existing != request.sha256:
                    raise CONFLICT
                return self._response(connection, ingestion_id, context.principal_id)
            if row["state"] != "source_pending" or path_sequence != row["acknowledged_chunks"] + 1:
                raise CONFLICT
            if row["uploaded_bytes"] + len(data) > row["expected_byte_length"]:
                raise DomainError("payload_too_large", 413, "The source exceeds its declared size.")
            connection.execute(
                text("""INSERT INTO ingestion_chunks
                (id,tenant_id,workspace_id,project_id,ingestion_id,sequence,object_ref,
                 byte_length,sha256) VALUES
                (:id,:tenant,:workspace,:project,:ingestion,:sequence,:ref,:length,:digest)"""),
                {
                    "id": uuid4(),
                    "tenant": context.tenant_id,
                    "workspace": context.workspace_id,
                    "project": project_id,
                    "ingestion": ingestion_id,
                    "sequence": path_sequence,
                    "ref": stored.object_ref,
                    "length": stored.byte_length,
                    "digest": stored.sha256,
                },
            )
            connection.execute(
                text("""UPDATE ingestions SET uploaded_bytes=uploaded_bytes+:length,
                acknowledged_chunks=:sequence,revision=revision+1,updated_at=:now WHERE id=:id"""),
                {
                    "length": len(data),
                    "sequence": path_sequence,
                    "now": datetime.now(UTC),
                    "id": ingestion_id,
                },
            )
            return self._response(connection, ingestion_id, context.principal_id)

    def finalize(
        self, context: AuthContext, ingestion_id: UUID, request: IngestionFinalize
    ) -> Ingestion:
        project_id = self._ingestion_project(context, ingestion_id)
        with scoped_transaction(self._engine, context, project_id) as connection:
            self._require_role(connection, project_id, context.principal_id, write=True)
            row = (
                connection.execute(
                    text("SELECT * FROM ingestions WHERE id=:id FOR UPDATE"), {"id": ingestion_id}
                )
                .mappings()
                .one_or_none()
            )
            if row is None:
                raise NOT_FOUND
            operation_replay = self._claim_operation(
                connection,
                context,
                project_id,
                ingestion_id,
                "upload_finalize",
                request.operation_key,
                request.model_dump(mode="json"),
            )
            if row["state"] not in {"source_pending", "quarantined"}:
                if operation_replay and row["source_asset_id"] is not None:
                    return self._response(connection, ingestion_id, context.principal_id)
                raise CONFLICT
            if (
                request.expected_byte_length != row["expected_byte_length"]
                or request.expected_sha256 != row["expected_sha256"]
                or row["uploaded_bytes"] != row["expected_byte_length"]
            ):
                raise CONFLICT
            chunks = (
                connection.execute(
                    text("""SELECT sequence,object_ref FROM ingestion_chunks
                    WHERE ingestion_id=:id ORDER BY sequence"""),
                    {"id": ingestion_id},
                )
                .mappings()
                .all()
            )
            if [item["sequence"] for item in chunks] != list(
                range(1, row["acknowledged_chunks"] + 1)
            ):
                raise CONFLICT
            data = b"".join(self._objects.read_version(item["object_ref"]) for item in chunks)
            if sha256(data).hexdigest() != row["expected_sha256"]:
                self._fail(connection, ingestion_id, "integrity_failure", retryable=False)
                raise DomainError("invalid_input", 422, "The source failed integrity validation.")
            detected_mime, duration_ms = self._validate_source(
                row["source_kind"], row["original_filename"], data
            )
            stored = self._objects.put_immutable(
                data, row["expected_sha256"], request.operation_key
            )
            source_id = uuid4()
            connection.execute(
                text("""UPDATE ingestions SET state='quarantined',stage='quarantine',
                revision=revision+1,updated_at=:now WHERE id=:id"""),
                {"now": datetime.now(UTC), "id": ingestion_id},
            )
            connection.execute(
                text("""INSERT INTO source_assets
                (id,tenant_id,workspace_id,project_id,document_id,kind,original_filename,
                 detected_mime,object_ref,byte_length,sha256,duration_ms,provenance,quarantine_state)
                 VALUES (:id,:tenant,:workspace,:project,:document,:kind,:filename,:mime,
                  :ref,:length,:digest,:duration,'user_upload','accepted')"""),
                {
                    "id": source_id,
                    "tenant": context.tenant_id,
                    "workspace": context.workspace_id,
                    "project": project_id,
                    "document": row["document_id"],
                    "kind": row["source_kind"],
                    "filename": row["original_filename"],
                    "mime": detected_mime,
                    "ref": stored.object_ref,
                    "length": stored.byte_length,
                    "digest": stored.sha256,
                    "duration": duration_ms,
                },
            )
            connection.execute(
                text("""UPDATE ingestions SET source_asset_id=:source,state='source_accepted',
                stage=:stage,revision=revision+1,updated_at=:now WHERE id=:id"""),
                {
                    "source": source_id,
                    "stage": "cleanup" if row["source_kind"] == "transcript" else "transcription",
                    "now": datetime.now(UTC),
                    "id": ingestion_id,
                },
            )
            self._complete_operation(
                connection, "upload_finalize", request.operation_key, str(source_id)
            )
            if row["source_kind"] == "transcript":
                parsed = self._parse_transcript(row["original_filename"], data)
                self._create_draft(
                    connection,
                    context,
                    cast(dict[str, Any], row),
                    ingestion_id,
                    source_id,
                    parsed,
                    data,
                    provider="upload",
                    model_id="none",
                    raw_object_ref=stored.object_ref,
                )
            else:
                if self._defer_audio_transcription:
                    self._queue_audio_transcription(
                        connection, context, cast(dict[str, Any], row), ingestion_id
                    )
                else:
                    self._process_synthetic_audio(
                        connection,
                        context,
                        cast(dict[str, Any], row),
                        ingestion_id,
                        source_id,
                        stored.object_ref,
                    )
            return self._response(connection, ingestion_id, context.principal_id)

    def get(self, context: AuthContext, ingestion_id: UUID) -> Ingestion:
        project_id = self._ingestion_project(context, ingestion_id)
        with scoped_transaction(self._engine, context, project_id) as connection:
            return self._response(connection, ingestion_id, context.principal_id)

    def process_existing_audio(self, context: AuthContext, ingestion_id: UUID) -> Ingestion:
        """Run the deterministic local transcription adapter for a finalized capture."""

        project_id = self._ingestion_project(context, ingestion_id)
        with scoped_transaction(self._engine, context, project_id) as connection:
            row = (
                connection.execute(
                    text("""SELECT i.*,sa.object_ref FROM ingestions i
                    JOIN source_assets sa ON sa.id=i.source_asset_id
                    WHERE i.id=:id FOR UPDATE OF i"""),
                    {"id": ingestion_id},
                )
                .mappings()
                .one_or_none()
            )
            if row is None:
                raise NOT_FOUND
            if row["draft_version_id"] is not None:
                return self._response(connection, ingestion_id, context.principal_id)
            if row["source_kind"] != "audio" or row["state"] not in {
                "source_accepted",
                "transcription_queued",
                "transcription_processing",
            }:
                raise CONFLICT
            if self._defer_audio_transcription:
                self._queue_audio_transcription(
                    connection, context, cast(dict[str, Any], row), ingestion_id
                )
            else:
                self._process_synthetic_audio(
                    connection,
                    context,
                    cast(dict[str, Any], row),
                    ingestion_id,
                    row["source_asset_id"],
                    row["object_ref"],
                )
            return self._response(connection, ingestion_id, context.principal_id)

    @staticmethod
    def _queue_audio_transcription(
        connection: Connection,
        context: AuthContext,
        ingestion: dict[str, Any],
        ingestion_id: UUID,
    ) -> None:
        payload = {
            "ingestion_id": str(ingestion_id),
            "project_id": str(ingestion["project_id"]),
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        connection.execute(
            text("""INSERT INTO jobs
            (id,tenant_id,workspace_id,project_id,document_id,job_type,operation_key,
             payload_hash,payload,trace_id,max_attempts)
            VALUES (:id,:tenant,:workspace,:project,:document,'transcribe_audio',:operation,
             :digest,CAST(:payload AS jsonb),:trace,20)
            ON CONFLICT (tenant_id,workspace_id,project_id,operation_key) DO NOTHING"""),
            {
                "id": uuid4(),
                "tenant": context.tenant_id,
                "workspace": context.workspace_id,
                "project": ingestion["project_id"],
                "document": ingestion["document_id"],
                "operation": f"transcribe-audio:{ingestion_id}",
                "digest": sha256(encoded).hexdigest(),
                "payload": encoded.decode(),
                "trace": str(ingestion_id),
            },
        )
        connection.execute(
            text("""UPDATE ingestions SET state='transcription_queued',stage='transcription',
            revision=revision+1,updated_at=:now WHERE id=:id"""),
            {"now": datetime.now(UTC), "id": ingestion_id},
        )

    def process_existing_audio_with_provider(
        self,
        context: AuthContext,
        project_id: UUID,
        ingestion_id: UUID,
        provider: TranscriptionProvider,
        *,
        provider_name: str,
    ) -> None:
        """Idempotently submit stored audio and attach a completed provider result."""

        with scoped_transaction(self._engine, context, project_id, "jobs.execute") as connection:
            row = (
                connection.execute(
                    text("""SELECT i.*,sa.object_ref FROM ingestions i
                    JOIN source_assets sa ON sa.id=i.source_asset_id
                    WHERE i.id=:id FOR UPDATE OF i"""),
                    {"id": ingestion_id},
                )
                .mappings()
                .one_or_none()
            )
            if row is None:
                raise NOT_FOUND
            if row["draft_version_id"] is not None:
                return
            if row["source_kind"] != "audio" or row["state"] not in {
                "source_accepted",
                "transcription_queued",
                "transcription_submitted",
                "transcription_processing",
                "failed_retryable",
            }:
                raise CONFLICT
            self._process_provider_audio(
                connection,
                context,
                cast(dict[str, Any], row),
                ingestion_id,
                row["source_asset_id"],
                row["object_ref"],
                provider,
                provider_name,
            )

    def list(self, context: AuthContext, document_id: UUID) -> IngestionPage:
        project_id = self._document_project(context, document_id)
        with scoped_transaction(self._engine, context, project_id) as connection:
            ids = connection.execute(
                text(
                    """SELECT id FROM ingestions WHERE document_id=:id
                    ORDER BY created_at DESC LIMIT 100"""
                ),
                {"id": document_id},
            ).scalars()
            return IngestionPage(
                items=[self._response(connection, item, context.principal_id) for item in ids]
            )

    def get_draft(self, context: AuthContext, ingestion_id: UUID) -> TranscriptDraft:
        project_id = self._ingestion_project(context, ingestion_id)
        with scoped_transaction(self._engine, context, project_id) as connection:
            return self._draft_response(connection, ingestion_id)

    def word_alignment(self, context: AuthContext, ingestion_id: UUID) -> TranscriptWordAlignment:
        project_id = self._ingestion_project(context, ingestion_id)
        with scoped_transaction(self._engine, context, project_id) as connection:
            draft = self._draft_row(connection, ingestion_id)
            raw = (
                connection.execute(
                    text(
                        """SELECT provider,raw_object_ref,raw_sha256,parsed_object_ref,parsed_sha256
                        FROM raw_transcripts WHERE id=:id"""
                    ),
                    {"id": draft["raw_transcript_id"]},
                )
                .mappings()
                .one()
            )
        if raw["provider"] != "assemblyai":
            return TranscriptWordAlignment(
                draft_id=draft["draft_id"],
                available=False,
                matches_current_draft=False,
                source_segments=[],
                segments=[],
            )
        raw_bytes = self._objects.read_version(raw["raw_object_ref"])
        parsed_bytes = self._objects.read_version(raw["parsed_object_ref"])
        canonical = self._objects.read_version(draft["canonical_object_ref"])
        if (
            sha256(raw_bytes).hexdigest() != raw["raw_sha256"]
            or sha256(parsed_bytes).hexdigest() != raw["parsed_sha256"]
            or sha256(canonical).hexdigest() != draft["content_sha256"]
        ):
            raise DomainError(
                "internal_error", 500, "Stored transcript integrity verification failed."
            )
        source_segments = [
            TranscriptSegment(**item) for item in json.loads(parsed_bytes)["segments"]
        ]
        segment_texts = tuple(item.text for item in source_segments)
        aligned = extract_word_alignment(raw_bytes, segment_texts)
        return TranscriptWordAlignment(
            draft_id=draft["draft_id"],
            available=bool(aligned),
            matches_current_draft="\n".join(segment_texts) == canonical.decode("utf-8"),
            source_segments=source_segments,
            segments=[
                SegmentWordAlignment(
                    index=item.index,
                    words=[TimedWord(**vars(word)) for word in item.words],
                )
                for item in aligned
            ],
        )

    def correct(
        self, context: AuthContext, ingestion_id: UUID, request: CorrectedDraftPut
    ) -> TranscriptDraft:
        project_id = self._ingestion_project(context, ingestion_id)
        with scoped_transaction(self._engine, context, project_id) as connection:
            self._require_role(connection, project_id, context.principal_id, owner=True)
            current = self._draft_row(connection, ingestion_id, lock=True)
            if (
                current["revision"] != request.expected_revision
                or current["content_sha256"] != request.expected_content_sha256
                or current["ingestion_state"] in _TERMINAL
            ):
                raise CONFLICT
            canonical = request.canonical_text.replace("\r\n", "\n").replace("\r", "\n")
            data = canonical.encode("utf-8")
            digest = sha256(data).hexdigest()
            stored = self._objects.put_immutable(data, digest, f"corrected:{ingestion_id}:{digest}")
            version_id = uuid4()
            revision = current["revision"] + 1
            manifest = {
                "source_sha256": current["source_sha256"],
                "segments": [
                    {"text": canonical, "speaker_label": None, "start_ms": None, "end_ms": None}
                ],
                "edits": [],
                "reason_code": request.reason_code,
            }
            connection.execute(
                text("""INSERT INTO transcript_versions
                (id,tenant_id,workspace_id,project_id,document_id,version_number,parent_version_id,
                 raw_transcript_id,canonical_object_ref,content_sha256,byte_length,cleanup_status,
                 cleanup_policy_version,cleanup_manifest,state,created_by)
                VALUES (:id,:tenant,:workspace,:project,:document,:number,:parent,:raw,:ref,
                 :digest,:length,'human_corrected','controlled-cleanup-v2',CAST(:manifest AS jsonb),
                 'draft',:actor)"""),
                {
                    "id": version_id,
                    "tenant": context.tenant_id,
                    "workspace": context.workspace_id,
                    "project": project_id,
                    "document": current["document_id"],
                    "number": revision,
                    "parent": current["draft_id"],
                    "raw": current["raw_transcript_id"],
                    "ref": stored.object_ref,
                    "digest": digest,
                    "length": len(data),
                    "manifest": json.dumps(manifest),
                    "actor": context.principal_id,
                },
            )
            connection.execute(
                text("""UPDATE ingestions SET draft_version_id=:draft,state='approval_required',
                stage='approval',revision=revision+1,updated_at=:now WHERE id=:id"""),
                {"draft": version_id, "now": datetime.now(UTC), "id": ingestion_id},
            )
            return self._draft_response(connection, ingestion_id)

    def approve(
        self, context: AuthContext, ingestion_id: UUID, request: TranscriptApprovalCreate
    ) -> TranscriptDraft:
        project_id = self._ingestion_project(context, ingestion_id)
        with scoped_transaction(self._engine, context, project_id) as connection:
            self._require_role(connection, project_id, context.principal_id, owner=True)
            current = self._draft_row(connection, ingestion_id, lock=True)
            if (
                current["revision"] != request.expected_revision
                or current["content_sha256"] != request.content_sha256
                or current["ingestion_state"]
                not in {"draft_ready", "approval_required", "approved"}
            ):
                raise CONFLICT
            self._insert_approval(
                connection,
                context,
                current,
                method="person",
                reason=request.reason_code,
            )
            connection.execute(
                text("""UPDATE transcript_versions SET state='approved' WHERE id=:id"""),
                {"id": current["draft_id"]},
            )
            connection.execute(
                text("""UPDATE ingestions SET state='approved',stage='publication',
                revision=revision+1,updated_at=:now WHERE id=:id"""),
                {"now": datetime.now(UTC), "id": ingestion_id},
            )
            return self._draft_response(connection, ingestion_id)

    def publish(
        self, context: AuthContext, ingestion_id: UUID, request: TranscriptPublicationCreate
    ) -> TranscriptPublication:
        project_id = self._ingestion_project(context, ingestion_id)
        with scoped_transaction(self._engine, context, project_id) as connection:
            self._require_role(connection, project_id, context.principal_id, owner=True)
            current = self._draft_row(connection, ingestion_id, lock=True)
            operation_replay = self._claim_operation(
                connection,
                context,
                project_id,
                ingestion_id,
                "publication",
                request.operation_key,
                request.model_dump(mode="json"),
            )
            if current["ingestion_state"] == "published":
                if not operation_replay:
                    raise CONFLICT
                return self._publication_response(
                    connection,
                    current["document_id"],
                    current["draft_id"],
                    current["source_asset_id"],
                )
            if (
                current["ingestion_state"] != "approved"
                or current["revision"] != request.expected_draft_revision
                or current["content_sha256"] != request.approved_content_sha256
            ):
                raise CONFLICT
            active = connection.execute(
                text("SELECT active_transcript_version_id FROM documents WHERE id=:id FOR UPDATE"),
                {"id": current["document_id"]},
            ).scalar_one()
            if active != request.expected_active_transcript_version_id:
                raise CONFLICT
            approval = connection.execute(
                text("""SELECT method FROM transcript_approvals WHERE transcript_version_id=:id
                AND content_sha256=:digest AND revoked_at IS NULL
                ORDER BY approved_at DESC LIMIT 1"""),
                {"id": current["draft_id"], "digest": current["content_sha256"]},
            ).scalar_one_or_none()
            if approval is None:
                raise CONFLICT
            connection.execute(
                text("""UPDATE ingestions SET state='publishing',stage='publication',
                revision=revision+1,updated_at=:now WHERE id=:id"""),
                {"now": datetime.now(UTC), "id": ingestion_id},
            )
            canonical = self._objects.read_version(current["canonical_object_ref"])
            passages = construct_passages(current["draft_id"], canonical.decode("utf-8"))
            for passage in passages:
                span = canonical[passage.start_byte : passage.end_byte]
                connection.execute(
                    text("""INSERT INTO passages
                    (id,tenant_id,workspace_id,project_id,document_id,transcript_version_id,
                     ordinal,start_byte,end_byte,span_sha256) VALUES
                    (:id,:tenant,:workspace,:project,:document,:version,:ordinal,:start,:end,:digest)
                    ON CONFLICT (tenant_id,workspace_id,project_id,transcript_version_id,ordinal)
                    DO NOTHING"""),
                    {
                        "id": passage.passage_id,
                        "tenant": context.tenant_id,
                        "workspace": context.workspace_id,
                        "project": project_id,
                        "document": current["document_id"],
                        "version": current["draft_id"],
                        "ordinal": passage.ordinal,
                        "start": passage.start_byte,
                        "end": passage.end_byte,
                        "digest": sha256(span).hexdigest(),
                    },
                )
                payload = json.dumps(
                    {
                        "transcript_version_id": str(current["draft_id"]),
                        "passage_id": str(passage.passage_id),
                    },
                    sort_keys=True,
                )
                connection.execute(
                    text("""INSERT INTO jobs
                    (id,tenant_id,workspace_id,project_id,document_id,job_type,operation_key,
                     payload_hash,payload,trace_id) VALUES
                    (:id,:tenant,:workspace,:project,:document,'index_passage',:key,:hash,
                     CAST(:payload AS jsonb),:trace)
                    ON CONFLICT (tenant_id,workspace_id,project_id,operation_key) DO NOTHING"""),
                    {
                        "id": uuid4(),
                        "tenant": context.tenant_id,
                        "workspace": context.workspace_id,
                        "project": project_id,
                        "document": current["document_id"],
                        "key": f"index:{current['draft_id']}:{passage.passage_id}",
                        "hash": sha256(payload.encode()).hexdigest(),
                        "payload": payload,
                        "trace": context.request_id,
                    },
                )
            now = datetime.now(UTC)
            event_id = uuid4()
            event_payload = json.dumps(
                {
                    "event_id": str(event_id),
                    "schema_version": 1,
                    "tenant_id": str(context.tenant_id),
                    "workspace_id": str(context.workspace_id),
                    "project_id": str(project_id),
                    "aggregate_id": str(current["document_id"]),
                    "occurred_at": now.isoformat(),
                    "trace_id": context.request_id,
                    "data": {"transcript_version_id": str(current["draft_id"])},
                }
            )
            connection.execute(
                text("""INSERT INTO outbox_events
                (id,tenant_id,workspace_id,project_id,document_id,aggregate_id,event_type,
                 schema_version,payload) VALUES (:id,:tenant,:workspace,:project,:document,
                 :document,'TranscriptPublished',1,CAST(:payload AS jsonb))"""),
                {
                    "id": event_id,
                    "tenant": context.tenant_id,
                    "workspace": context.workspace_id,
                    "project": project_id,
                    "document": current["document_id"],
                    "payload": event_payload,
                },
            )
            connection.execute(
                text("""UPDATE transcript_versions SET state='published',published_at=:now
                WHERE id=:id"""),
                {"now": now, "id": current["draft_id"]},
            )
            connection.execute(
                text("""UPDATE documents SET active_transcript_version_id=:version,
                updated_at=:now WHERE id=:document"""),
                {"version": current["draft_id"], "now": now, "document": current["document_id"]},
            )
            connection.execute(
                text("""UPDATE ingestions SET state='published',stage='publication',retryable=false,
                safe_error_code=NULL,revision=revision+1,updated_at=:now WHERE id=:id"""),
                {"now": now, "id": ingestion_id},
            )
            self._complete_operation(
                connection, "publication", request.operation_key, str(current["draft_id"])
            )
            connection.execute(
                text("""INSERT INTO audit_events
                (id,tenant_id,workspace_id,project_id,document_id,actor_kind,actor_id,
                 action,outcome,request_id,authorization_epoch,occurred_at) VALUES
                (:id,:tenant,:workspace,:project,:document,:kind,:actor,
                 'transcript.published','allowed',:request,:epoch,:now)"""),
                {
                    "id": uuid4(),
                    "tenant": context.tenant_id,
                    "workspace": context.workspace_id,
                    "project": project_id,
                    "document": current["document_id"],
                    "kind": context.principal_kind,
                    "actor": context.principal_id,
                    "request": context.request_id,
                    "epoch": context.authorization_epoch,
                    "now": now,
                },
            )
            return self._publication_response(
                connection, current["document_id"], current["draft_id"], current["source_asset_id"]
            )

    def retry(
        self, context: AuthContext, ingestion_id: UUID, request: IngestionAction
    ) -> Ingestion:
        project_id = self._ingestion_project(context, ingestion_id)
        with scoped_transaction(self._engine, context, project_id) as connection:
            self._require_role(connection, project_id, context.principal_id, write=True)
            state = connection.execute(
                text("SELECT state FROM ingestions WHERE id=:id FOR UPDATE"), {"id": ingestion_id}
            ).scalar_one_or_none()
            operation_replay = self._claim_operation(
                connection,
                context,
                project_id,
                ingestion_id,
                "retry",
                request.operation_key,
                request.model_dump(mode="json"),
            )
            if operation_replay and state != "failed_retryable":
                return self._response(connection, ingestion_id, context.principal_id)
            if state != "failed_retryable":
                raise CONFLICT
            connection.execute(
                text("""UPDATE ingestions SET state='source_accepted',retryable=false,
                safe_error_code=NULL,revision=revision+1,updated_at=:now WHERE id=:id"""),
                {"now": datetime.now(UTC), "id": ingestion_id},
            )
            self._complete_operation(connection, "retry", request.operation_key, str(ingestion_id))
            return self._response(connection, ingestion_id, context.principal_id)

    def abort(
        self, context: AuthContext, ingestion_id: UUID, request: IngestionAction
    ) -> Ingestion:
        project_id = self._ingestion_project(context, ingestion_id)
        with scoped_transaction(self._engine, context, project_id) as connection:
            self._require_role(connection, project_id, context.principal_id, write=True)
            state = connection.execute(
                text("SELECT state FROM ingestions WHERE id=:id FOR UPDATE"), {"id": ingestion_id}
            ).scalar_one_or_none()
            if state is None:
                raise NOT_FOUND
            if state == "published":
                raise CONFLICT
            operation_replay = self._claim_operation(
                connection,
                context,
                project_id,
                ingestion_id,
                "abort",
                request.operation_key,
                request.model_dump(mode="json"),
            )
            if state == "aborted" and not operation_replay:
                raise CONFLICT
            if state != "aborted":
                connection.execute(
                    text("""UPDATE ingestions SET state='aborted',retryable=false,
                    revision=revision+1,updated_at=:now WHERE id=:id"""),
                    {"now": datetime.now(UTC), "id": ingestion_id},
                )
            self._complete_operation(connection, "abort", request.operation_key, str(ingestion_id))
            return self._response(connection, ingestion_id, context.principal_id)

    @staticmethod
    def _claim_operation(
        connection: Connection,
        context: AuthContext,
        project_id: UUID,
        ingestion_id: UUID,
        action: str,
        operation_key: str,
        payload: dict[str, Any],
    ) -> bool:
        payload_hash = sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        existing = (
            connection.execute(
                text("""SELECT payload_hash FROM ingestion_operations
                WHERE action=:action AND operation_key=:key"""),
                {"action": action, "key": operation_key},
            )
            .mappings()
            .one_or_none()
        )
        if existing is not None:
            if existing["payload_hash"] != payload_hash:
                raise CONFLICT
            return True
        connection.execute(
            text("""INSERT INTO ingestion_operations
            (id,tenant_id,workspace_id,project_id,ingestion_id,action,operation_key,payload_hash)
            VALUES (:id,:tenant,:workspace,:project,:ingestion,:action,:key,:hash)"""),
            {
                "id": uuid4(),
                "tenant": context.tenant_id,
                "workspace": context.workspace_id,
                "project": project_id,
                "ingestion": ingestion_id,
                "action": action,
                "key": operation_key,
                "hash": payload_hash,
            },
        )
        return False

    @staticmethod
    def _complete_operation(
        connection: Connection, action: str, operation_key: str, outcome_ref: str
    ) -> None:
        connection.execute(
            text("""UPDATE ingestion_operations SET outcome_ref=:outcome
            WHERE action=:action AND operation_key=:key"""),
            {"outcome": outcome_ref, "action": action, "key": operation_key},
        )

    def download(
        self, context: AuthContext, document_id: UUID, format_name: str
    ) -> TranscriptDownload:
        publication = self.get_publication(context, document_id)
        if format_name not in {"txt", "md", "json", "pdf"}:
            raise NOT_FOUND
        with scoped_transaction(self._engine, context) as initial:
            project_id = initial.execute(
                text("SELECT project_id FROM documents WHERE id=:id"), {"id": document_id}
            ).scalar_one_or_none()
        if project_id is None:
            raise NOT_FOUND
        with scoped_transaction(self._engine, context, project_id) as connection:
            version = (
                connection.execute(
                    text("""SELECT tv.*,d.title FROM transcript_versions tv
                    JOIN documents d ON d.id=tv.document_id WHERE tv.id=:id"""),
                    {"id": publication.transcript_version_id},
                )
                .mappings()
                .one()
            )
        manifest = version["cleanup_manifest"] or {}
        segments = tuple(
            Segment(
                text=item["text"],
                speaker_label=item.get("speaker_label"),
                start_ms=item.get("start_ms"),
                end_ms=item.get("end_ms"),
            )
            for item in manifest.get("segments", [])
        )
        faithful_segments = (
            segments
            if "\n".join(item.text for item in segments) == publication.canonical_text
            else ()
        )
        if format_name == "txt":
            organized = format_segmented_transcript(faithful_segments) or publication.canonical_text
            data = organized.encode("utf-8")
            media = "text/plain; charset=utf-8"
        elif format_name == "md":
            organized = (
                format_segmented_transcript(faithful_segments, markdown=True)
                or publication.canonical_text
            )
            data = f"# {version['title']}\n\n{organized}\n".encode()
            media = "text/markdown; charset=utf-8"
        elif format_name == "pdf":
            try:
                data = render_transcript_pdf(
                    version["title"],
                    publication.canonical_text,
                    faithful_segments,
                    str(publication.transcript_version_id),
                    publication.content_sha256,
                )
            except ValueError as error:
                raise DomainError(
                    "invalid_input",
                    422,
                    "This transcript contains characters the PDF font cannot render.",
                ) from error
            media = "application/pdf"
        else:
            data = json.dumps(
                {
                    "schema_version": 1,
                    "document_id": str(document_id),
                    "transcript_version_id": str(publication.transcript_version_id),
                    "source_asset_id": str(publication.source_asset_id),
                    "content_sha256": publication.content_sha256,
                    "canonical_text": publication.canonical_text,
                    "segments": [self._segment_json(item) for item in segments],
                    "approval_method": publication.approval_method,
                },
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
            media = "application/json"
        return TranscriptDownload(
            format=format_name,  # type: ignore[arg-type]
            filename=f"transcript.{format_name}",
            media_type=media,  # type: ignore[arg-type]
            content_base64=base64.b64encode(data).decode("ascii"),
            sha256=sha256(data).hexdigest(),
        )

    def _source_asset_data(self, context: AuthContext, source_asset_id: UUID) -> tuple[Any, bytes]:
        with scoped_transaction(self._engine, context) as initial:
            project_id = initial.execute(
                text("SELECT project_id FROM source_assets WHERE id=:id"), {"id": source_asset_id}
            ).scalar_one_or_none()
        if project_id is None:
            raise NOT_FOUND
        with scoped_transaction(self._engine, context, project_id) as connection:
            row = (
                connection.execute(
                    text("SELECT * FROM source_assets WHERE id=:id"), {"id": source_asset_id}
                )
                .mappings()
                .one_or_none()
            )
            if row is None:
                raise NOT_FOUND
        data = self._objects.read_version(row["object_ref"])
        if sha256(data).hexdigest() != row["sha256"]:
            raise DomainError("internal_error", 500, "Stored source integrity verification failed.")
        return row, data

    def source_content(self, context: AuthContext, source_asset_id: UUID) -> SourceAssetContent:
        row, data = self._source_asset_data(context, source_asset_id)
        return SourceAssetContent(
            source_asset_id=source_asset_id,
            media_type=row["detected_mime"],
            byte_length=len(data),
            sha256=row["sha256"],
            content_base64=base64.b64encode(data).decode("ascii"),
        )

    def source_waveform(self, context: AuthContext, source_asset_id: UUID) -> SourceAssetWaveform:
        row, data = self._source_asset_data(context, source_asset_id)
        if row["kind"] != "audio":
            raise NOT_FOUND
        try:
            peaks = audio_waveform(data, row["duration_ms"] or 0)
        except MediaValidationError as error:
            raise DomainError(
                "internal_error", 500, "Stored audio could not be decoded."
            ) from error
        return SourceAssetWaveform(
            source_asset_id=source_asset_id,
            duration_ms=row["duration_ms"],
            peaks=list(peaks),
        )

    def get_publication(self, context: AuthContext, document_id: UUID) -> TranscriptPublication:
        with scoped_transaction(self._engine, context) as connection:
            row = (
                connection.execute(
                    text("""SELECT d.project_id,d.active_transcript_version_id,rt.source_asset_id
                    FROM documents d LEFT JOIN transcript_versions tv
                      ON tv.id=d.active_transcript_version_id
                    LEFT JOIN raw_transcripts rt ON rt.id=tv.raw_transcript_id WHERE d.id=:id"""),
                    {"id": document_id},
                )
                .mappings()
                .one_or_none()
            )
        if row is None or row["active_transcript_version_id"] is None:
            raise NOT_FOUND
        with scoped_transaction(self._engine, context, row["project_id"]) as connection:
            return self._publication_response(
                connection, document_id, row["active_transcript_version_id"], row["source_asset_id"]
            )

    def _create_draft(
        self,
        connection: Connection,
        context: AuthContext,
        ingestion: dict[str, Any],
        ingestion_id: UUID,
        source_id: UUID,
        parsed: ParsedTranscript,
        raw_bytes: bytes,
        *,
        provider: str,
        model_id: str,
        raw_object_ref: str,
    ) -> None:
        original = parsed.canonical_text
        raw_digest = sha256(raw_bytes).hexdigest()
        raw_key = f"raw-result:{ingestion_id}:{raw_digest}"
        self._claim_operation(
            connection,
            context,
            ingestion["project_id"],
            ingestion_id,
            "raw_result_store",
            raw_key,
            {"sha256": raw_digest, "provider": provider, "model_id": model_id},
        )
        proposed, _ = controlled_cleanup(original)
        validation = validate_cleanup_with_manifest(original, proposed)
        if not validation.accepted:
            raise DomainError("internal_error", 500, "Cleanup validation failed.")
        parsed_data = json.dumps(
            {
                "format": parsed.format,
                "language": parsed.language,
                "segments": [self._segment_json(item) for item in parsed.segments],
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        parsed_digest = sha256(parsed_data).hexdigest()
        parsed_object = self._objects.put_immutable(
            parsed_data, parsed_digest, f"parsed:{ingestion_id}:{parsed_digest}"
        )
        canonical = proposed.encode("utf-8")
        canonical_digest = sha256(canonical).hexdigest()
        cleanup_key = f"cleanup:{ingestion_id}:{canonical_digest}"
        self._claim_operation(
            connection,
            context,
            ingestion["project_id"],
            ingestion_id,
            "cleanup_generate",
            cleanup_key,
            {"source_sha256": raw_digest, "canonical_sha256": canonical_digest},
        )
        canonical_object = self._objects.put_immutable(
            canonical, canonical_digest, f"canonical:{ingestion_id}:{canonical_digest}"
        )
        raw_id, version_id = uuid4(), uuid4()
        connection.execute(
            text("""INSERT INTO raw_transcripts
            (id,tenant_id,workspace_id,project_id,document_id,source_asset_id,ingestion_id,
             provider,model_id,raw_object_ref,raw_sha256,parsed_object_ref,parsed_sha256,parser_version)
            VALUES (:id,:tenant,:workspace,:project,:document,:source,:ingestion,:provider,:model,
             :raw_ref,:raw_digest,:parsed_ref,:parsed_digest,'deterministic-parser-v1')"""),
            {
                "id": raw_id,
                "tenant": context.tenant_id,
                "workspace": context.workspace_id,
                "project": ingestion["project_id"],
                "document": ingestion["document_id"],
                "source": source_id,
                "ingestion": ingestion_id,
                "provider": provider,
                "model": model_id,
                "raw_ref": raw_object_ref,
                "raw_digest": raw_digest,
                "parsed_ref": parsed_object.object_ref,
                "parsed_digest": parsed_digest,
            },
        )
        self._complete_operation(connection, "raw_result_store", raw_key, str(raw_id))
        self._complete_operation(connection, "cleanup_generate", cleanup_key, str(version_id))
        version_number = connection.execute(
            text(
                """SELECT COALESCE(MAX(version_number),0)+1
                FROM transcript_versions WHERE document_id=:id"""
            ),
            {"id": ingestion["document_id"]},
        ).scalar_one()
        manifest = {
            "source_sha256": ingestion["expected_sha256"],
            "segments": [self._segment_json(item) for item in parsed.segments],
            "edits": [
                {
                    "rule": edit.rule,
                    "start_character": edit.start_character,
                    "end_character": edit.end_character,
                }
                for edit in validation.edits
            ],
        }
        connection.execute(
            text("""INSERT INTO transcript_versions
            (id,tenant_id,workspace_id,project_id,document_id,version_number,raw_transcript_id,
             canonical_object_ref,content_sha256,byte_length,cleanup_status,
             cleanup_policy_version,cleanup_manifest,state,created_by)
            VALUES (:id,:tenant,:workspace,:project,:document,:number,:raw,:ref,:digest,:length,
             :status,:policy,CAST(:manifest AS jsonb),'approved',:actor)"""),
            {
                "id": version_id,
                "tenant": context.tenant_id,
                "workspace": context.workspace_id,
                "project": ingestion["project_id"],
                "document": ingestion["document_id"],
                "number": version_number,
                "raw": raw_id,
                "ref": canonical_object.object_ref,
                "digest": canonical_digest,
                "length": len(canonical),
                "status": "unchanged" if proposed == original else "accepted",
                "policy": validation.policy_version,
                "manifest": json.dumps(manifest),
                "actor": ingestion["created_by"],
            },
        )
        approval_row = {
            "draft_id": version_id,
            "content_sha256": canonical_digest,
            "document_id": ingestion["document_id"],
            "project_id": ingestion["project_id"],
        }
        self._insert_approval(
            connection,
            context,
            approval_row,
            method="controlled_cleanup_policy",
            reason="policy_validated",
        )
        approval_key = f"automatic-approval:{version_id}:{canonical_digest}"
        self._claim_operation(
            connection,
            context,
            ingestion["project_id"],
            ingestion_id,
            "automatic_approval",
            approval_key,
            {"transcript_version_id": str(version_id), "content_sha256": canonical_digest},
        )
        self._complete_operation(connection, "automatic_approval", approval_key, str(version_id))
        connection.execute(
            text("""UPDATE ingestions SET draft_version_id=:draft,state='approved',
            stage='publication',retryable=false,safe_error_code=NULL,revision=revision+1,
            updated_at=:now WHERE id=:id"""),
            {"draft": version_id, "now": datetime.now(UTC), "id": ingestion_id},
        )

    def _process_synthetic_audio(
        self,
        connection: Connection,
        context: AuthContext,
        ingestion: dict[str, Any],
        ingestion_id: UUID,
        source_id: UUID,
        audio_object_ref: str,
    ) -> None:
        fixture = (
            TranscriptSegmentResult("Welcome to the fictional project meeting.", "A", 0, 2500),
            TranscriptSegmentResult("We approved the blue launch plan.", "B", 2600, 5200),
        )
        adapter = SyntheticAssemblyAIAdapter(self._objects, fixture)
        self._process_provider_audio(
            connection,
            context,
            ingestion,
            ingestion_id,
            source_id,
            audio_object_ref,
            adapter,
            "synthetic_assemblyai",
        )

    def _process_provider_audio(
        self,
        connection: Connection,
        context: AuthContext,
        ingestion: dict[str, Any],
        ingestion_id: UUID,
        source_id: UUID,
        audio_object_ref: str,
        adapter: TranscriptionProvider,
        provider_name: str,
    ) -> None:
        submission_key = f"transcription-submit:{ingestion_id}"
        self._claim_operation(
            connection,
            context,
            ingestion["project_id"],
            ingestion_id,
            "transcription_submit",
            submission_key,
            {"source_asset_id": str(source_id), "audio_object_ref": audio_object_ref},
        )
        connection.execute(
            text("""UPDATE ingestions SET state='transcription_processing',stage='transcription',
            revision=revision+1,updated_at=:now WHERE id=:id"""),
            {"now": datetime.now(UTC), "id": ingestion_id},
        )
        submission = adapter.transcribe(audio_object_ref, f"transcribe:{ingestion_id}")
        self._complete_operation(
            connection, "transcription_submit", submission_key, submission.submission_ref
        )
        status = adapter.get_status(submission.submission_ref)
        if provider_name == "synthetic_assemblyai":
            for _ in range(2):
                if status == "completed":
                    break
                status = adapter.get_status(submission.submission_ref)
        if status == "failed":
            raise DomainError("provider_unavailable", 503, "Transcription failed.")
        if status != "completed":
            self._fail(connection, ingestion_id, "provider_processing", retryable=True)
            raise DomainError(
                "provider_unavailable", 503, "Transcription is still processing.", True
            )
        result = adapter.fetch_result(submission.submission_ref)
        try:
            reconciled = reconcile_provider_segments(result.segments, language="en")
        except ReconciliationError as error:
            self._fail(connection, ingestion_id, "provider_invalid_response", retryable=False)
            raise DomainError(
                "invalid_input", 422, "The transcription result is invalid."
            ) from error
        raw = self._objects.read_version(result.raw_artifact_ref)
        self._create_draft(
            connection,
            context,
            ingestion,
            ingestion_id,
            source_id,
            reconciled.transcript,
            raw,
            provider=provider_name,
            model_id=result.model_id,
            raw_object_ref=result.raw_artifact_ref,
        )

    def _insert_approval(
        self,
        connection: Connection,
        context: AuthContext,
        row: dict[str, Any],
        *,
        method: str,
        reason: str,
    ) -> None:
        connection.execute(
            text("""INSERT INTO transcript_approvals
            (id,tenant_id,workspace_id,project_id,document_id,transcript_version_id,
             content_sha256,method,policy_version,approver_kind,approver_id,approved_at,reason_code)
            VALUES (:id,:tenant,:workspace,:project,:document,:version,:digest,:method,
             'controlled-cleanup-v2',:kind,:actor,:now,:reason)
            ON CONFLICT (tenant_id,workspace_id,project_id,transcript_version_id,
                         content_sha256,method,policy_version) DO NOTHING"""),
            {
                "id": uuid4(),
                "tenant": context.tenant_id,
                "workspace": context.workspace_id,
                "project": row["project_id"],
                "document": row["document_id"],
                "version": row["draft_id"],
                "digest": row["content_sha256"],
                "method": method,
                "kind": "service"
                if method == "controlled_cleanup_policy"
                else context.principal_kind,
                "actor": context.principal_id,
                "now": datetime.now(UTC),
                "reason": reason,
            },
        )

    def _draft_row(self, connection: Connection, ingestion_id: UUID, *, lock: bool = False) -> Any:
        suffix = " FOR UPDATE OF i,tv" if lock else ""
        row = (
            connection.execute(
                text(
                    """SELECT i.document_id,i.project_id,i.source_asset_id,i.state ingestion_state,
                    i.revision,tv.id draft_id,tv.raw_transcript_id,tv.canonical_object_ref,
                    tv.content_sha256,tv.cleanup_status,tv.cleanup_policy_version,tv.cleanup_manifest,
                    sa.sha256 source_sha256 FROM ingestions i
                    JOIN transcript_versions tv ON tv.id=i.draft_version_id
                    JOIN source_assets sa ON sa.id=i.source_asset_id WHERE i.id=:id"""
                    + suffix
                ),
                {"id": ingestion_id},
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise NOT_FOUND
        return row

    def _draft_response(self, connection: Connection, ingestion_id: UUID) -> TranscriptDraft:
        row = self._draft_row(connection, ingestion_id)
        canonical = self._objects.read_version(row["canonical_object_ref"])
        if sha256(canonical).hexdigest() != row["content_sha256"]:
            raise DomainError(
                "internal_error", 500, "Stored transcript integrity verification failed."
            )
        approval = (
            connection.execute(
                text("""SELECT id,method,content_sha256,approved_at FROM transcript_approvals
                WHERE transcript_version_id=:id AND revoked_at IS NULL
                ORDER BY approved_at DESC LIMIT 1"""),
                {"id": row["draft_id"]},
            )
            .mappings()
            .one_or_none()
        )
        manifest = row["cleanup_manifest"]
        status = row["cleanup_status"]
        if status == "skipped":
            status = "approval_required"
        return TranscriptDraft(
            ingestion_id=ingestion_id,
            document_id=row["document_id"],
            draft_id=row["draft_id"],
            revision=row["revision"],
            source_sha256=row["source_sha256"],
            content_sha256=row["content_sha256"],
            canonical_text=canonical.decode("utf-8"),
            segments=[TranscriptSegment(**item) for item in manifest.get("segments", [])],
            cleanup_policy_version=row["cleanup_policy_version"],
            cleanup_status=status,
            edit_manifest=[CleanupEditManifest(**item) for item in manifest.get("edits", [])],
            approval=None
            if approval is None
            else DraftApproval(
                approval_id=approval["id"],
                method=approval["method"],
                content_sha256=approval["content_sha256"],
                approved_at=approval["approved_at"],
            ),
        )

    def _response(
        self, connection: Connection, ingestion_id: UUID, principal_id: UUID
    ) -> Ingestion:
        row = (
            connection.execute(
                text("""SELECT i.*,tv.content_sha256 draft_sha256,
                d.active_transcript_version_id transcript_version_id,
                COALESCE(pm.role,CASE WHEN p.owner_user_id=:user THEN 'project_owner' END) my_role
                FROM ingestions i JOIN documents d ON d.id=i.document_id
                JOIN projects p ON p.id=i.project_id
                LEFT JOIN transcript_versions tv ON tv.id=i.draft_version_id
                LEFT JOIN project_memberships pm ON pm.project_id=i.project_id
                  AND pm.user_id=:user AND pm.enabled WHERE i.id=:id"""),
                {"id": ingestion_id, "user": principal_id},
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise NOT_FOUND
        role = row["my_role"]
        owner = role == "project_owner"
        writable = role in {"contributor", "project_owner"}
        state = row["state"]
        return Ingestion(
            ingestion_id=row["id"],
            document_id=row["document_id"],
            source_asset_id=row["source_asset_id"],
            source_kind=row["source_kind"],
            state=state,
            stage=row["stage"],
            uploaded_bytes=row["uploaded_bytes"],
            expected_bytes=row["expected_byte_length"],
            acknowledged_chunks=row["acknowledged_chunks"],
            gap_count=row["gap_count"],
            retryable=row["retryable"],
            safe_error_code=row["safe_error_code"],
            draft_revision=row["revision"] if row["draft_version_id"] else None,
            draft_sha256=row["draft_sha256"],
            transcript_version_id=row["transcript_version_id"] if state == "published" else None,
            can_upload=writable and state == "source_pending",
            can_retry=writable and state == "failed_retryable",
            can_abort=writable and state not in _TERMINAL,
            can_review=owner and row["draft_version_id"] is not None and state != "published",
            can_approve=owner and state in {"draft_ready", "approval_required"},
            can_publish=owner and state == "approved",
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def _publication_response(
        self, connection: Connection, document_id: UUID, version_id: UUID, source_id: UUID
    ) -> TranscriptPublication:
        row = (
            connection.execute(
                text("""SELECT tv.canonical_object_ref,tv.content_sha256,
                (SELECT method FROM transcript_approvals WHERE transcript_version_id=tv.id
                 AND revoked_at IS NULL ORDER BY approved_at DESC LIMIT 1) approval_method,
                (SELECT count(*) FROM passages WHERE transcript_version_id=tv.id) passage_count,
                (SELECT count(*) FROM jobs
                 WHERE payload->>'transcript_version_id'=CAST(tv.id AS text)) job_count
                FROM transcript_versions tv WHERE tv.id=:id AND tv.state='published'"""),
                {"id": version_id},
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise NOT_FOUND
        canonical = self._objects.read_version(row["canonical_object_ref"])
        digest = sha256(canonical).hexdigest()
        if digest != row["content_sha256"]:
            raise DomainError(
                "internal_error", 500, "Stored transcript integrity verification failed."
            )
        return TranscriptPublication(
            transcript_version_id=version_id,
            document_id=document_id,
            source_asset_id=source_id,
            content_sha256=digest,
            state="published",
            approval_method=row["approval_method"],
            passage_count=row["passage_count"],
            index_job_count=row["job_count"],
            canonical_text=canonical.decode("utf-8"),
            reproduced_sha256=digest,
        )

    def _document_project(self, context: AuthContext, document_id: UUID) -> UUID:
        with scoped_transaction(self._engine, context) as connection:
            project_id = connection.execute(
                text("SELECT project_id FROM documents WHERE id=:id AND state='created'"),
                {"id": document_id},
            ).scalar_one_or_none()
        if project_id is None:
            raise NOT_FOUND
        return cast(UUID, project_id)

    def _ingestion_project(self, context: AuthContext, ingestion_id: UUID) -> UUID:
        with scoped_transaction(self._engine, context) as connection:
            project_id = connection.execute(
                text("SELECT project_id FROM ingestions WHERE id=:id"), {"id": ingestion_id}
            ).scalar_one_or_none()
        if project_id is None:
            raise NOT_FOUND
        return cast(UUID, project_id)

    @staticmethod
    def _require_role(
        connection: Connection,
        project_id: UUID,
        principal_id: UUID,
        *,
        write: bool = False,
        owner: bool = False,
    ) -> str:
        role = connection.execute(
            text("""SELECT role FROM project_memberships
            WHERE project_id=:project AND user_id=:user AND enabled"""),
            {"project": project_id, "user": principal_id},
        ).scalar_one_or_none()
        allowed = (
            {"project_owner"}
            if owner
            else {"contributor", "project_owner"}
            if write
            else {"reader", "contributor", "project_owner"}
        )
        if role not in allowed:
            raise FORBIDDEN
        return cast(str, role)

    @staticmethod
    def _parse_transcript(filename: str, data: bytes) -> ParsedTranscript:
        try:
            return parse_transcript(filename, data)
        except IngestionError as error:
            raise DomainError("invalid_input", 422, "The transcript upload is invalid.") from error

    @staticmethod
    def _validate_source(kind: str, filename: str, data: bytes) -> tuple[str, int | None]:
        suffix = Path(filename).suffix.lower()
        if kind == "transcript":
            mime = {
                ".txt": "text/plain",
                ".vtt": "text/vtt",
                ".srt": "application/x-subrip",
                ".json": "application/json",
            }.get(suffix)
            if mime is None or len(data) > _TRANSCRIPT_LIMIT:
                raise DomainError("invalid_input", 422, "The transcript format is unsupported.")
            return mime, None
        if len(data) > _AUDIO_LIMIT:
            raise DomainError("payload_too_large", 413, "The audio source is too large.")
        try:
            metadata = validate_audio(filename, data)
        except MediaValidationError as error:
            raise DomainError(
                "invalid_input", 422, "The audio source failed quarantine validation."
            ) from error
        return metadata.media_type, metadata.duration_ms

    @staticmethod
    def _segment_json(segment: Segment) -> dict[str, Any]:
        return {
            "text": segment.text,
            "speaker_label": segment.speaker_label,
            "start_ms": segment.start_ms,
            "end_ms": segment.end_ms,
        }

    @staticmethod
    def _fail(connection: Connection, ingestion_id: UUID, code: str, *, retryable: bool) -> None:
        connection.execute(
            text("""UPDATE ingestions SET state=:state,retryable=:retryable,safe_error_code=:code,
            revision=revision+1,updated_at=:now WHERE id=:id"""),
            {
                "state": "failed_retryable" if retryable else "failed_terminal",
                "retryable": retryable,
                "code": code,
                "now": datetime.now(UTC),
                "id": ingestion_id,
            },
        )
