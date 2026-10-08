"""Run scoped durable outbox and job execution."""

from __future__ import annotations

import logging
import signal
import time
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import create_engine

from api.config import get_settings
from connectors.live_runtime import create_live_storage, create_live_transcription
from connectors.recall import RecallDesktopAdapter
from contracts.models import AuthContext
from domain.jobs import DurableJobStore, LeasedJob
from domain.observability import StructuredLogSink
from domain.outbox import OutboxDispatcher
from domain.recall_ingestion import RecallIngestionService
from domain.workflow import IngestionWorkflowService
from workers.runtime import DurableWorker, JobHandler, WorkerScope


def _identifier_only_handler(job: LeasedJob) -> str | None:
    """Acknowledge foundation events and Phase 3-deferred index intents safely."""

    allowed = {
        "index_passage": {"transcript_version_id", "passage_id"},
        "observe_transcript_publication": {
            "event_id",
            "event_type",
            "schema_version",
            "aggregate_id",
            "document_id",
            "trace_id",
        },
        "reconcile_access": {
            "event_id",
            "event_type",
            "schema_version",
            "aggregate_id",
            "document_id",
            "trace_id",
        },
    }[job.job_type]
    if not set(job.payload).issubset(allowed):
        raise ValueError("unsafe_job_payload")
    for key, value in job.payload.items():
        if key.endswith("_id") and value is not None:
            UUID(str(value))
    return "phase3-deferred" if job.job_type == "index_passage" else None


def _uuid(value: str | None, name: str) -> UUID:
    if value is None:
        raise RuntimeError(f"{name} is required for the durable worker")
    try:
        return UUID(value)
    except ValueError as error:
        raise RuntimeError(f"{name} must be a UUID") from error


def main() -> None:
    settings = get_settings()
    logging.basicConfig(level=settings.log_level)
    # httpx includes complete signed media URLs in INFO request lines.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logger = logging.getLogger(__name__)
    tenant_id = _uuid(settings.worker_tenant_id, "VERELO_WORKER_TENANT_ID")
    workspace_id = _uuid(settings.worker_workspace_id, "VERELO_WORKER_WORKSPACE_ID")
    service_id = _uuid(settings.worker_service_identity_id, "VERELO_WORKER_SERVICE_IDENTITY_ID")
    try:
        project_ids = [
            UUID(value.strip()) for value in settings.worker_project_ids.split(",") if value.strip()
        ]
    except ValueError as error:
        raise RuntimeError("VERELO_WORKER_PROJECT_IDS must contain UUIDs") from error
    if not project_ids:
        raise RuntimeError("VERELO_WORKER_PROJECT_IDS must contain at least one project")

    engine = create_engine(settings.worker_database_url, pool_pre_ping=True, future=True)
    context = AuthContext(
        principal_kind="service",
        principal_id=service_id,
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        authorization_epoch=0,
        capabilities=[],
        request_id=str(uuid4()),
    )
    scopes = [WorkerScope(context, project_id) for project_id in project_ids]
    handlers: dict[str, JobHandler] = {
        "index_passage": _identifier_only_handler,
        "observe_transcript_publication": _identifier_only_handler,
        "reconcile_access": _identifier_only_handler,
    }
    recall_ingestion = None
    if settings.integrations_mode.value == "live":
        if (
            not settings.recall_api_base_url
            or not settings.recall_api_key
            or not settings.recall_webhook_secret
        ):
            raise RuntimeError("Live Recall configuration is incomplete.")
        storage = create_live_storage(settings)
        recall = RecallDesktopAdapter(
            api_base_url=str(settings.recall_api_base_url),
            api_key=settings.recall_api_key.get_secret_value(),
            webhook_secret=settings.recall_webhook_secret.get_secret_value(),
            timeout_seconds=settings.integration_request_timeout_seconds,
        )
        workflow = IngestionWorkflowService(
            engine, settings.object_storage_root, object_storage=storage
        )
        transcription = create_live_transcription(settings, storage)
        recall_ingestion = RecallIngestionService(engine, storage, recall, transcription, workflow)

        def handle_recall(job: LeasedJob) -> str:
            assert recall_ingestion is not None
            return recall_ingestion.process(
                context, UUID(str(job.payload["project_id"])), job.payload
            )

        handlers["recall_ingest"] = handle_recall

        def handle_audio_transcription(job: LeasedJob) -> str:
            if set(job.payload) != {"ingestion_id", "project_id"}:
                raise ValueError("unsafe_job_payload")
            project_id = UUID(str(job.payload["project_id"]))
            ingestion_id = UUID(str(job.payload["ingestion_id"]))
            workflow.process_existing_audio_with_provider(
                context,
                project_id,
                ingestion_id,
                transcription,
                provider_name="assemblyai",
            )
            return str(ingestion_id)

        handlers["transcribe_audio"] = handle_audio_transcription

    worker = DurableWorker(
        DurableJobStore(engine),
        OutboxDispatcher(engine),
        handlers,
        StructuredLogSink(),
        worker_id=f"worker-{uuid4()}",
    )
    stopping = False

    def stop(_signum: int, _frame: Any) -> None:
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    logger.info("durable worker started", extra={"project_scope_count": len(scopes)})
    try:
        if settings.worker_run_once:
            for scope in scopes:
                if recall_ingestion is not None:
                    recall_ingestion.enqueue_completed(scope.context, scope.project_id)
                worker.run_once(scope)
        else:

            def refreshed_scopes():  # type: ignore[no-untyped-def]
                if recall_ingestion is not None:
                    for scope in scopes:
                        recall_ingestion.enqueue_completed(scope.context, scope.project_id)
                return scopes

            worker.run_until_stopped(
                refreshed_scopes,
                should_stop=lambda: stopping,
                wait=time.sleep,
            )
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
