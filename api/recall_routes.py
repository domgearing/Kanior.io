"""Authorized Recall upload grants and unauthenticated-but-signed webhook ingress."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import Engine, text

from api.database import scoped_transaction
from api.foundation_routes import CsrfSessionDep
from connectors.fakes import FakeProviderError
from connectors.recall import RecallDesktopAdapter
from domain.capture import CaptureService
from domain.errors import DomainError


class RecallUploadCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    operation_key: str = Field(min_length=1, max_length=200)


class RecallUploadGrantResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    upload_token: str
    sdk_upload_id: str
    capture_mode: str = "audio_only"


def create_recall_router(
    engine: Engine, capture_service: CaptureService, adapter: RecallDesktopAdapter
) -> APIRouter:
    router = APIRouter(prefix="/api/v1")

    @router.post(
        "/capture-sessions/{capture_session_id}/recall-upload",
        response_model=RecallUploadGrantResponse,
        status_code=201,
    )
    def create_recall_upload(
        capture_session_id: UUID, request: RecallUploadCreate, session: CsrfSessionDep
    ) -> RecallUploadGrantResponse:
        capture_service.get(session.context, capture_session_id)
        project_id = capture_service.project_id(session.context, capture_session_id)
        try:
            grant = adapter.create_upload(str(capture_session_id), request.operation_key)
        except FakeProviderError as error:
            raise DomainError(
                "provider_unavailable", 503, "Recall is unavailable.", True
            ) from error
        with scoped_transaction(engine, session.context, project_id) as connection:
            existing = (
                connection.execute(
                    text("""SELECT sdk_upload_id,operation_key FROM recall_uploads
                WHERE capture_session_id=:capture"""),
                    {"capture": capture_session_id},
                )
                .mappings()
                .one_or_none()
            )
            if existing is not None and (
                existing["sdk_upload_id"] != grant.sdk_upload_id
                or existing["operation_key"] != request.operation_key
            ):
                raise DomainError("conflict", 409, "Recall upload identity conflict.")
            connection.execute(
                text("""INSERT INTO recall_uploads
                (sdk_upload_id,tenant_id,workspace_id,project_id,capture_session_id,operation_key)
                SELECT :upload,tenant_id,workspace_id,project_id,id,:operation
                FROM capture_sessions WHERE id=:capture
                ON CONFLICT (sdk_upload_id) DO NOTHING"""),
                {
                    "upload": grant.sdk_upload_id,
                    "capture": capture_session_id,
                    "operation": request.operation_key,
                },
            )
        return RecallUploadGrantResponse(
            upload_token=grant.upload_token, sdk_upload_id=grant.sdk_upload_id
        )

    @router.post("/webhooks/recall", status_code=204, include_in_schema=False)
    async def recall_webhook(request: Request) -> Response:
        raw_body = await request.body()
        headers = {key: value for key, value in request.headers.items()}
        try:
            event = adapter.verify_webhook(raw_body, headers)
        except FakeProviderError as error:
            raise DomainError("unauthenticated", 401, "Webhook authentication failed.") from error
        with engine.begin() as connection:
            existing = connection.execute(
                text("SELECT body_sha256 FROM recall_webhook_events WHERE event_id=:id"),
                {"id": event.event_id},
            ).scalar_one_or_none()
            if existing is not None and existing != event.body_sha256:
                raise DomainError("conflict", 409, "Webhook event identity conflict.")
            connection.execute(
                text("""INSERT INTO recall_webhook_events
                (event_id,event_type,sdk_upload_id,recording_id,body_sha256)
                VALUES (:event_id,:event_type,:sdk_upload_id,:recording_id,:body_sha256)
                ON CONFLICT (event_id) DO NOTHING"""),
                {
                    "event_id": event.event_id,
                    "event_type": event.event_type,
                    "sdk_upload_id": event.sdk_upload_id,
                    "recording_id": event.recording_id,
                    "body_sha256": event.body_sha256,
                },
            )
        return Response(status_code=204)

    return router
