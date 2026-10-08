"""Editable operation registry; contains no handlers or running server."""

from dataclasses import dataclass

from pydantic import BaseModel

from contracts import models as m


@dataclass(frozen=True)
class Operation:
    method: str
    path: str
    operation_id: str
    response: type[BaseModel]
    summary: str
    request: type[BaseModel] | None = None
    success: int = 200
    paginated: bool = False
    csrf: bool = True
    authenticated: bool = True


OPERATIONS = (
    Operation(
        "get",
        "/auth/mode",
        "get_authentication_mode",
        m.AuthenticationMode,
        "Describe the configured interactive sign-in method",
        csrf=False,
        authenticated=False,
    ),
    Operation(
        "post",
        "/auth/magic-link/request",
        "request_magic_link",
        m.MagicLinkRequestAccepted,
        "Request a development sign-in link without disclosing account eligibility",
        m.MagicLinkRequest,
        202,
        csrf=False,
        authenticated=False,
    ),
    Operation(
        "post",
        "/auth/magic-link/consume",
        "consume_magic_link",
        m.AuthenticationResult,
        "Consume a single-use development sign-in link",
        m.MagicLinkConsume,
        csrf=False,
        authenticated=False,
    ),
    Operation(
        "post",
        "/auth/logout",
        "logout",
        m.LogoutResult,
        "Revoke the current server session",
        request=None,
    ),
    Operation("get", "/me", "get_me", m.MeResponse, "Resolve current enabled employee"),
    Operation(
        "patch",
        "/me",
        "update_me",
        m.MeResponse,
        "Update the current employee profile",
        m.ProfileUpdate,
    ),
    Operation(
        "get",
        "/projects",
        "list_projects",
        m.ProjectPage,
        "List permitted projects",
        paginated=True,
    ),
    Operation(
        "post",
        "/projects",
        "create_project",
        m.Project,
        "Create project and creator owner membership",
        m.ProjectCreate,
        201,
    ),
    Operation("get", "/projects/{project_id}", "get_project", m.Project, "Read permitted project"),
    Operation(
        "get",
        "/projects/{project_id}/members/{user_id}",
        "get_project_member",
        m.Membership,
        "Owner reads current membership revision",
    ),
    Operation(
        "get",
        "/projects/{project_id}/members",
        "list_project_members",
        m.MemberPage,
        "Owner lists project members",
    ),
    Operation(
        "put",
        "/projects/{project_id}/members/by-email",
        "set_project_member_by_email",
        m.Membership,
        "Owner grants or updates project membership by allowlisted email",
        m.MembershipByEmailPut,
    ),
    Operation(
        "put",
        "/projects/{project_id}/members/{user_id}",
        "set_project_member",
        m.Membership,
        "Owner changes membership using revision CAS",
        m.MembershipPut,
    ),
    Operation(
        "get",
        "/projects/{project_id}/documents",
        "list_documents",
        m.DocumentPage,
        "List permitted document metadata",
        paginated=True,
    ),
    Operation(
        "post",
        "/projects/{project_id}/documents",
        "create_document",
        m.Document,
        "Contributor creates document metadata with consent",
        m.DocumentCreate,
        201,
    ),
    Operation(
        "get",
        "/documents/{document_id}",
        "get_document",
        m.Document,
        "Read permitted document metadata",
    ),
    Operation(
        "post",
        "/documents/{document_id}/ingestions",
        "create_ingestion",
        m.Ingestion,
        "Create an authorized transcript or audio ingestion intent",
        m.IngestionCreate,
        201,
    ),
    Operation(
        "put",
        "/ingestions/{ingestion_id}/chunks/{sequence}",
        "put_ingestion_chunk",
        m.Ingestion,
        "Store and acknowledge the next immutable source chunk",
        m.IngestionChunkPut,
    ),
    Operation(
        "post",
        "/ingestions/{ingestion_id}/finalize",
        "finalize_ingestion",
        m.Ingestion,
        "Verify and seal the independently stored source",
        m.IngestionFinalize,
    ),
    Operation(
        "get",
        "/ingestions/{ingestion_id}",
        "get_ingestion",
        m.Ingestion,
        "Read safe ingestion state",
    ),
    Operation(
        "get",
        "/documents/{document_id}/ingestions",
        "list_ingestions",
        m.IngestionPage,
        "List authorized ingestion attempts for a document",
    ),
    Operation(
        "get",
        "/ingestions/{ingestion_id}/draft",
        "get_transcript_draft",
        m.TranscriptDraft,
        "Read the immutable current transcript draft",
    ),
    Operation(
        "put",
        "/ingestions/{ingestion_id}/draft",
        "create_corrected_draft",
        m.TranscriptDraft,
        "Create an immutable corrected transcript draft",
        m.CorrectedDraftPut,
    ),
    Operation(
        "post",
        "/ingestions/{ingestion_id}/approvals",
        "approve_transcript_draft",
        m.TranscriptDraft,
        "Approve the exact current transcript draft",
        m.TranscriptApprovalCreate,
        201,
    ),
    Operation(
        "post",
        "/ingestions/{ingestion_id}/publication",
        "publish_approved_transcript",
        m.TranscriptPublication,
        "Atomically publish the exact approved transcript",
        m.TranscriptPublicationCreate,
        201,
    ),
    Operation(
        "post",
        "/ingestions/{ingestion_id}/retry",
        "retry_ingestion",
        m.Ingestion,
        "Retry only the server-declared retryable stage",
        m.IngestionAction,
    ),
    Operation(
        "post",
        "/ingestions/{ingestion_id}/abort",
        "abort_ingestion",
        m.Ingestion,
        "Abort non-published ingestion work",
        m.IngestionAction,
    ),
    Operation(
        "get",
        "/documents/{document_id}/transcript-publication",
        "get_transcript_publication",
        m.TranscriptPublication,
        "Reproduce the active canonical transcript from immutable internal records",
    ),
    Operation(
        "get",
        "/documents/{document_id}/transcript-downloads/{format}",
        "download_transcript",
        m.TranscriptDownload,
        "Render the pinned published transcript deterministically",
    ),
    Operation(
        "get",
        "/source-assets/{source_asset_id}/content",
        "stream_source_asset",
        m.SourceAssetContent,
        "Read an authorized immutable source asset",
    ),
    Operation(
        "post",
        "/capture-sessions",
        "create_capture_session",
        m.CaptureSession,
        "Create a persistent recording session",
        m.CaptureCreate,
        201,
    ),
    Operation(
        "get",
        "/capture-sessions/{capture_session_id}",
        "get_capture_session",
        m.CaptureSession,
        "Recover persistent recording state",
    ),
    Operation(
        "post",
        "/capture-sessions/{capture_session_id}/transitions",
        "transition_capture_session",
        m.CaptureSession,
        "Apply an idempotent-safe recorder state transition",
        m.CaptureTransition,
    ),
    Operation(
        "put",
        "/capture-sessions/{capture_session_id}/chunks/{sequence}",
        "put_capture_chunk",
        m.CaptureSession,
        "Persist and acknowledge the next immutable audio chunk",
        m.CaptureChunkUpload,
    ),
    Operation(
        "post",
        "/capture-sessions/{capture_session_id}/finalize",
        "finalize_capture_session",
        m.CaptureSession,
        "Assemble, quarantine-check, and preserve original synthetic audio",
        m.CaptureFinalize,
    ),
)
