"""Authorized Phase 2 ingestion, review, publication, and download operations."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Response

from api.foundation_routes import CsrfSessionDep, SessionDep
from contracts.models import (
    CorrectedDraftPut,
    Ingestion,
    IngestionAction,
    IngestionChunkPut,
    IngestionCreate,
    IngestionFinalize,
    IngestionPage,
    SourceAssetContent,
    TranscriptApprovalCreate,
    TranscriptDownload,
    TranscriptDraft,
    TranscriptPublication,
    TranscriptPublicationCreate,
)
from domain.workflow import IngestionWorkflowService


def create_ingestion_router(service: IngestionWorkflowService) -> APIRouter:
    router = APIRouter(prefix="/api/v1")

    @router.post(
        "/documents/{document_id}/ingestions",
        response_model=Ingestion,
        status_code=201,
        operation_id="create_ingestion",
    )
    def create_ingestion(
        document_id: UUID, request: IngestionCreate, response: Response, session: CsrfSessionDep
    ) -> Ingestion:
        result = service.create(session.context, document_id, request)
        response.headers["Location"] = f"/api/v1/ingestions/{result.ingestion_id}"
        return result

    @router.put(
        "/ingestions/{ingestion_id}/chunks/{sequence}",
        response_model=Ingestion,
        operation_id="put_ingestion_chunk",
    )
    def put_ingestion_chunk(
        ingestion_id: UUID, sequence: int, request: IngestionChunkPut, session: CsrfSessionDep
    ) -> Ingestion:
        return service.put_chunk(session.context, ingestion_id, sequence, request)

    @router.post(
        "/ingestions/{ingestion_id}/finalize",
        response_model=Ingestion,
        operation_id="finalize_ingestion",
    )
    def finalize_ingestion(
        ingestion_id: UUID, request: IngestionFinalize, session: CsrfSessionDep
    ) -> Ingestion:
        return service.finalize(session.context, ingestion_id, request)

    @router.get(
        "/ingestions/{ingestion_id}", response_model=Ingestion, operation_id="get_ingestion"
    )
    def get_ingestion(ingestion_id: UUID, session: SessionDep) -> Ingestion:
        return service.get(session.context, ingestion_id)

    @router.get(
        "/documents/{document_id}/ingestions",
        response_model=IngestionPage,
        operation_id="list_ingestions",
    )
    def list_ingestions(document_id: UUID, session: SessionDep) -> IngestionPage:
        return service.list(session.context, document_id)

    @router.get(
        "/ingestions/{ingestion_id}/draft",
        response_model=TranscriptDraft,
        operation_id="get_transcript_draft",
    )
    def get_transcript_draft(ingestion_id: UUID, session: SessionDep) -> TranscriptDraft:
        return service.get_draft(session.context, ingestion_id)

    @router.put(
        "/ingestions/{ingestion_id}/draft",
        response_model=TranscriptDraft,
        operation_id="create_corrected_draft",
    )
    def create_corrected_draft(
        ingestion_id: UUID, request: CorrectedDraftPut, session: CsrfSessionDep
    ) -> TranscriptDraft:
        return service.correct(session.context, ingestion_id, request)

    @router.post(
        "/ingestions/{ingestion_id}/approvals",
        response_model=TranscriptDraft,
        status_code=201,
        operation_id="approve_transcript_draft",
    )
    def approve_transcript_draft(
        ingestion_id: UUID, request: TranscriptApprovalCreate, session: CsrfSessionDep
    ) -> TranscriptDraft:
        return service.approve(session.context, ingestion_id, request)

    @router.post(
        "/ingestions/{ingestion_id}/publication",
        response_model=TranscriptPublication,
        status_code=201,
        operation_id="publish_approved_transcript",
    )
    def publish_approved_transcript(
        ingestion_id: UUID,
        request: TranscriptPublicationCreate,
        response: Response,
        session: CsrfSessionDep,
    ) -> TranscriptPublication:
        result = service.publish(session.context, ingestion_id, request)
        response.headers["Location"] = (
            f"/api/v1/documents/{result.document_id}/transcript-publication"
        )
        return result

    @router.post(
        "/ingestions/{ingestion_id}/retry",
        response_model=Ingestion,
        operation_id="retry_ingestion",
    )
    def retry_ingestion(
        ingestion_id: UUID, request: IngestionAction, session: CsrfSessionDep
    ) -> Ingestion:
        return service.retry(session.context, ingestion_id, request)

    @router.post(
        "/ingestions/{ingestion_id}/abort",
        response_model=Ingestion,
        operation_id="abort_ingestion",
    )
    def abort_ingestion(
        ingestion_id: UUID, request: IngestionAction, session: CsrfSessionDep
    ) -> Ingestion:
        return service.abort(session.context, ingestion_id, request)

    @router.get(
        "/documents/{document_id}/transcript-publication",
        response_model=TranscriptPublication,
        operation_id="get_transcript_publication",
    )
    def get_transcript_publication(document_id: UUID, session: SessionDep) -> TranscriptPublication:
        return service.get_publication(session.context, document_id)

    @router.get(
        "/documents/{document_id}/transcript-downloads/{format}",
        response_model=TranscriptDownload,
        operation_id="download_transcript",
    )
    def download_transcript(
        document_id: UUID, format: str, session: SessionDep
    ) -> TranscriptDownload:
        return service.download(session.context, document_id, format)

    @router.get(
        "/source-assets/{source_asset_id}/content",
        response_model=SourceAssetContent,
        operation_id="stream_source_asset",
    )
    def stream_source_asset(source_asset_id: UUID, session: SessionDep) -> SourceAssetContent:
        return service.source_content(session.context, source_asset_id)

    return router
