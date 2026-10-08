"""FastAPI application startup and safe shared response boundaries."""

from __future__ import annotations

from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import Engine

from api.capture_routes import create_capture_router
from api.config import IdentityProviderMode, MagicLinkDeliveryMode, get_settings
from api.database import create_database_engine
from api.foundation_routes import create_foundation_router
from api.identity_routes import create_identity_router
from api.ingestion_routes import create_ingestion_router
from api.recall_routes import create_recall_router
from connectors.live_runtime import create_live_storage
from connectors.local_magic_link import LocalMagicLinkDelivery
from connectors.microsoft_entra import EntraAuthorizationCodeAdapter
from connectors.microsoft_graph_mail import MicrosoftGraphMagicLinkDelivery
from connectors.recall import RecallDesktopAdapter
from contracts.models import Error
from domain.capture import CaptureService
from domain.errors import DomainError
from domain.foundation import FoundationService
from domain.identity import IdentityProvider, MagicLinkDelivery, MagicLinkIdentityProvider
from domain.workflow import IngestionWorkflowService


def create_app(
    engine: Engine | None = None, identity_provider: IdentityProvider | None = None
) -> FastAPI:
    """Create the application; tests may supply an isolated database engine."""

    settings = get_settings()
    app = FastAPI(
        title="Verelo API", version="0.1.0", docs_url=None, redoc_url=None, openapi_url=None
    )
    app.state.engine = engine or create_database_engine(settings)
    app.state.public_origin = (
        str(settings.public_origin).rstrip("/") if settings.public_origin else None
    )
    if app.state.public_origin:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=[app.state.public_origin],
            allow_credentials=True,
            allow_methods=["GET", "POST", "PUT"],
            allow_headers=["Content-Type", "X-CSRF-Token"],
        )
    entra_provider: EntraAuthorizationCodeAdapter | None = None
    if identity_provider is None and settings.identity_provider is IdentityProviderMode.ENTRA:
        assert settings.entra_tenant_id is not None
        assert settings.entra_client_id is not None
        assert settings.entra_client_secret is not None
        assert settings.entra_redirect_uri is not None
        assert settings.entra_employee_group_id is not None
        entra_provider = EntraAuthorizationCodeAdapter(
            app.state.engine,
            tenant_id=settings.entra_tenant_id,
            client_id=settings.entra_client_id,
            client_secret=settings.entra_client_secret.get_secret_value(),
            redirect_uri=str(settings.entra_redirect_uri),
            employee_group_id=settings.entra_employee_group_id,
        )
    elif identity_provider is None:
        if settings.magic_link_delivery is MagicLinkDeliveryMode.MICROSOFT_GRAPH:
            assert settings.graph_mail_tenant_id is not None
            assert settings.graph_mail_client_id is not None
            assert settings.graph_mail_client_secret is not None
            assert settings.graph_mail_sender is not None
            delivery: MagicLinkDelivery = MicrosoftGraphMagicLinkDelivery(
                tenant_id=settings.graph_mail_tenant_id,
                client_id=settings.graph_mail_client_id,
                client_secret=settings.graph_mail_client_secret.get_secret_value(),
                sender=settings.graph_mail_sender,
                graph_base_url=str(settings.graph_mail_base_url),
                authority_base_url=str(settings.graph_mail_authority_url),
                connect_timeout_seconds=settings.integration_connect_timeout_seconds,
                request_timeout_seconds=settings.integration_request_timeout_seconds,
                max_attempts=settings.integration_max_http_attempts,
            )
        else:
            delivery = LocalMagicLinkDelivery(settings.development_mailbox_root)
        identity_provider = MagicLinkIdentityProvider(
            app.state.engine,
            delivery,
            str(settings.magic_link_base_url),
        )

    @app.middleware("http")
    async def response_boundaries(request: Request, call_next):  # type: ignore[no-untyped-def]
        request.state.request_id = uuid4()
        response = await call_next(request)
        response.headers["X-Request-ID"] = str(request.state.request_id)
        response.headers["Cache-Control"] = "no-store"
        return response

    def safe_error(request: Request, error: DomainError) -> JSONResponse:
        body = Error(
            code=error.code,  # type: ignore[arg-type]
            message=error.message,
            request_id=str(request.state.request_id),
            retryable=error.retryable,
        )
        return JSONResponse(status_code=error.status_code, content=body.model_dump(mode="json"))

    @app.exception_handler(DomainError)
    async def domain_error(request: Request, error: DomainError) -> JSONResponse:
        return safe_error(request, error)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, error: RequestValidationError) -> JSONResponse:
        del error
        return safe_error(request, DomainError("invalid_input", 422, "The request is invalid."))

    @app.get("/health", include_in_schema=False)
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/ready", include_in_schema=False)
    async def readiness() -> JSONResponse:
        settings = get_settings()
        return JSONResponse(
            status_code=200,
            content={"status": "ready", "environment": settings.environment.value},
        )

    app.include_router(create_foundation_router(FoundationService(app.state.engine)))
    app.include_router(
        create_identity_router(
            identity_provider,
            cookie_secure=settings.session_cookie_secure,
            entra_provider=entra_provider,
        )
    )
    live_storage = (
        create_live_storage(settings) if settings.integrations_mode.value == "live" else None
    )
    workflow = IngestionWorkflowService(
        app.state.engine,
        settings.object_storage_root,
        object_storage=live_storage,
        defer_audio_transcription=settings.integrations_mode.value == "live",
    )
    capture_service = CaptureService(app.state.engine, settings.object_storage_root)
    app.include_router(create_capture_router(capture_service, workflow))
    if settings.integrations_mode.value == "live":
        if not (
            settings.recall_api_base_url
            and settings.recall_api_key
            and settings.recall_webhook_secret
        ):
            raise RuntimeError("Live Recall configuration is incomplete.")
        recall = RecallDesktopAdapter(
            api_base_url=str(settings.recall_api_base_url),
            api_key=settings.recall_api_key.get_secret_value(),
            webhook_secret=settings.recall_webhook_secret.get_secret_value(),
            timeout_seconds=settings.integration_request_timeout_seconds,
        )
        app.include_router(create_recall_router(app.state.engine, capture_service, recall))
    app.include_router(create_ingestion_router(workflow))
    return app


app = create_app()
