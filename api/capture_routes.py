"""Authorized persistent recording capture operations."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Response

from api.foundation_routes import CsrfSessionDep, SessionDep
from contracts.models import (
    CaptureChunkUpload,
    CaptureCreate,
    CaptureFinalize,
    CaptureSession,
    CaptureTransition,
)
from domain.capture import CaptureService
from domain.workflow import IngestionWorkflowService


def create_capture_router(
    service: CaptureService, workflow: IngestionWorkflowService | None = None
) -> APIRouter:
    router = APIRouter(prefix="/api/v1")

    @router.post("/capture-sessions", response_model=CaptureSession, status_code=201)
    def create_capture_session(
        request: CaptureCreate, response: Response, session: CsrfSessionDep
    ) -> CaptureSession:
        result = service.create(session.context, request)
        response.headers["Location"] = f"/api/v1/capture-sessions/{result.capture_session_id}"
        return result

    @router.get("/capture-sessions/{capture_session_id}", response_model=CaptureSession)
    def get_capture_session(capture_session_id: UUID, session: SessionDep) -> CaptureSession:
        return service.get(session.context, capture_session_id)

    @router.post(
        "/capture-sessions/{capture_session_id}/transitions", response_model=CaptureSession
    )
    def transition_capture_session(
        capture_session_id: UUID, request: CaptureTransition, session: CsrfSessionDep
    ) -> CaptureSession:
        return service.transition(session.context, capture_session_id, request)

    @router.put(
        "/capture-sessions/{capture_session_id}/chunks/{sequence}", response_model=CaptureSession
    )
    def put_capture_chunk(
        capture_session_id: UUID,
        sequence: int,
        request: CaptureChunkUpload,
        session: CsrfSessionDep,
    ) -> CaptureSession:
        return service.put_chunk(session.context, capture_session_id, sequence, request)

    @router.post("/capture-sessions/{capture_session_id}/finalize", response_model=CaptureSession)
    def finalize_capture_session(
        capture_session_id: UUID, request: CaptureFinalize, session: CsrfSessionDep
    ) -> CaptureSession:
        result = service.finalize(session.context, capture_session_id, request)
        if workflow is not None and result.ingestion_id is not None:
            workflow.process_existing_audio(session.context, result.ingestion_id)
        return result

    return router
