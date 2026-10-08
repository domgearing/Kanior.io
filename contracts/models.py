"""Editable contract source. See docs/API_CONTRACTS.md for contextual checks."""

from datetime import datetime, timedelta
from typing import Annotated, Literal
from uuid import UUID

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StrictInt,
    StringConstraints,
    field_validator,
    model_validator,
)

Name = Annotated[str, StringConstraints(min_length=1, max_length=200, pattern=r"\S")]
Title = Annotated[str, StringConstraints(min_length=1, max_length=300, pattern=r"\S")]
Language = Annotated[
    str,
    StringConstraints(min_length=2, max_length=35, pattern=r"^[A-Za-z]{2,8}(-[A-Za-z0-9]{1,8})*$"),
]
PolicyVersion = Annotated[str, StringConstraints(min_length=1, max_length=100, pattern=r"\S")]
NonNegative = Annotated[StrictInt, Field(ge=0)]
Positive = Annotated[StrictInt, Field(ge=1)]
RequestId = Annotated[str, StringConstraints(min_length=1, max_length=128)]
Role = Literal["reader", "contributor", "project_owner"]
EmailAddress = Annotated[str, StringConstraints(min_length=3, max_length=320)]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class AuthContext(Contract):
    """Internal trusted input only, never deserialized from an HTTP body."""

    principal_kind: Literal["employee", "service"]
    principal_id: UUID
    tenant_id: UUID
    workspace_id: UUID
    authorization_epoch: NonNegative
    capabilities: list[Literal["projects:create"]]
    request_id: RequestId


class Error(Contract):
    code: Literal[
        "unauthenticated",
        "forbidden",
        "not_found",
        "conflict",
        "payload_too_large",
        "invalid_input",
        "rate_limited",
        "dependency_unavailable",
        "internal_error",
    ]
    message: Annotated[str, StringConstraints(min_length=1, max_length=300)]
    request_id: RequestId
    retryable: bool


class MeResponse(Contract):
    user_id: UUID
    tenant_id: UUID
    workspace_id: UUID
    display_name: Name
    email: EmailAddress
    capabilities: list[Literal["projects:create"]]
    csrf_token: Annotated[str, StringConstraints(min_length=32, max_length=256)]


class ProfileUpdate(Contract):
    display_name: Name


class MagicLinkRequest(Contract):
    email: EmailAddress

    @field_validator("email")
    @classmethod
    def plausible_email(cls, value: str) -> str:
        candidate = value.strip()
        if candidate.count("@") != 1 or any(character.isspace() for character in candidate):
            raise ValueError("invalid email address")
        local, domain = candidate.rsplit("@", 1)
        if not local or "." not in domain or domain.startswith(".") or domain.endswith("."):
            raise ValueError("invalid email address")
        return candidate


class MagicLinkRequestAccepted(Contract):
    status: Literal["accepted"]
    message: Literal["If the account is eligible, a sign-in link will be sent."]


class MagicLinkConsume(Contract):
    token: Annotated[str, StringConstraints(min_length=32, max_length=256)]


class AuthenticationResult(Contract):
    status: Literal["authenticated"]


class AuthenticationMode(Contract):
    provider: Literal["magic_link", "entra"]


class LogoutResult(Contract):
    status: Literal["signed_out"]


class ProjectCreate(Contract):
    name: Name


class Project(Contract):
    project_id: UUID
    tenant_id: UUID
    workspace_id: UUID
    name: Name
    owner_user_id: UUID
    my_role: Role
    authorization_epoch: NonNegative
    state: Literal["active"]
    created_at: AwareDatetime
    updated_at: AwareDatetime


class MembershipPut(Contract):
    role: Role
    enabled: bool
    expected_revision: NonNegative


class Membership(Contract):
    project_membership_id: UUID
    tenant_id: UUID
    workspace_id: UUID
    project_id: UUID
    user_id: UUID
    role: Role
    enabled: bool
    revision: Positive
    project_authorization_epoch: NonNegative


class MemberSummary(Contract):
    user_id: UUID
    display_name: Name
    email: EmailAddress
    role: Role
    enabled: bool
    revision: Positive


class MemberPage(Contract):
    items: Annotated[list[MemberSummary], Field(max_length=100)]


class MembershipByEmailPut(Contract):
    email: EmailAddress
    role: Role
    enabled: bool = True
    expected_revision: NonNegative = 0

    @field_validator("email")
    @classmethod
    def plausible_email(cls, value: str) -> str:
        return MagicLinkRequest.plausible_email(value)


class DocumentCreate(Contract):
    title: Title
    meeting_date: AwareDatetime
    language: Language
    consent_acknowledged: Literal[True]
    consent_policy_version: PolicyVersion

    @field_validator("meeting_date", mode="before")
    @classmethod
    def parse_json_datetime(cls, value: object) -> object:
        """Accept the RFC 3339 representation JSON necessarily uses for datetimes."""
        if isinstance(value, str):
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        return value

    @field_validator("consent_acknowledged", mode="before")
    @classmethod
    def require_true_boolean(cls, value: object) -> object:
        if value is not True:
            raise ValueError("consent acknowledgement must be true")
        return value


class Document(Contract):
    document_id: UUID
    tenant_id: UUID
    workspace_id: UUID
    project_id: UUID
    title: Title
    meeting_date: AwareDatetime
    language: Language
    created_by: UUID
    consent_policy_version: PolicyVersion
    consent_acknowledged_by: UUID
    consent_acknowledged_at: AwareDatetime
    state: Literal["created"]
    created_at: AwareDatetime
    updated_at: AwareDatetime


Cursor = Annotated[str, StringConstraints(min_length=1, max_length=2048)]


class ProjectPage(Contract):
    items: Annotated[list[Project], Field(max_length=100)]
    next_cursor: Cursor | None


class DocumentPage(Contract):
    items: Annotated[list[Document], Field(max_length=100)]
    next_cursor: Cursor | None


class TranscriptSegment(Contract):
    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        json_schema_extra={
            "anyOf": [
                {"not": {"anyOf": [{"required": ["start_ms"]}, {"required": ["end_ms"]}]}},
                {
                    "required": ["start_ms", "end_ms"],
                    "properties": {"start_ms": {"type": "null"}, "end_ms": {"type": "null"}},
                },
                {
                    "required": ["start_ms", "end_ms"],
                    "properties": {"start_ms": {"type": "integer"}, "end_ms": {"type": "integer"}},
                },
            ],
            "description": (
                "Times are paired; semantic validation also requires end_ms >= start_ms. "
                "Preserve text verbatim."
            ),
        },
    )
    text: Annotated[str, StringConstraints(min_length=1)]
    speaker_label: str | None = None
    start_ms: NonNegative | None = None
    end_ms: NonNegative | None = None

    @model_validator(mode="after")
    def timing(self) -> "TranscriptSegment":
        if ("start_ms" in self.model_fields_set) != ("end_ms" in self.model_fields_set):
            raise ValueError("time fields must be supplied together")
        if (self.start_ms is None) != (self.end_ms is None):
            raise ValueError("times must be paired")
        if self.start_ms is not None and self.end_ms is not None and self.end_ms < self.start_ms:
            raise ValueError("end_ms precedes start_ms")
        return self


class TranscriptImport(Contract):
    schema_version: Literal[1]
    language: Language
    segments: Annotated[list[TranscriptSegment], Field(min_length=1)]

    @field_validator("schema_version", mode="before")
    @classmethod
    def integer_version(cls, value: object) -> object:
        if type(value) is not int:
            raise ValueError("schema_version must be an integer")
        return value


Sha256Digest = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
OperationKey = Annotated[str, StringConstraints(min_length=16, max_length=200, pattern=r"\S")]
IngestionState = Literal[
    "source_pending",
    "quarantined",
    "source_accepted",
    "transcription_queued",
    "transcription_submitted",
    "transcription_processing",
    "raw_transcript_stored",
    "draft_ready",
    "approval_required",
    "approved",
    "publishing",
    "published",
    "failed_retryable",
    "failed_terminal",
    "aborted",
]
IngestionStage = Literal[
    "upload", "quarantine", "transcription", "cleanup", "approval", "publication"
]


class IngestionCreate(Contract):
    source_kind: Literal["audio", "transcript"]
    filename: Annotated[str, StringConstraints(min_length=1, max_length=500, pattern=r"\S")]
    declared_media_type: Literal[
        "audio/wav",
        "audio/mpeg",
        "audio/mp4",
        "audio/webm",
        "text/plain",
        "text/vtt",
        "application/x-subrip",
        "application/json",
    ]
    byte_length: Positive
    sha256: Sha256Digest
    operation_key: OperationKey

    @model_validator(mode="after")
    def matching_kind(self) -> "IngestionCreate":
        is_audio = self.declared_media_type.startswith("audio/")
        if (self.source_kind == "audio") != is_audio:
            raise ValueError("source kind and media type do not match")
        limit = 2 * 1024 * 1024 * 1024 if is_audio else 20 * 1024 * 1024
        if self.byte_length > limit:
            raise ValueError("source exceeds size limit")
        return self


class IngestionChunkPut(Contract):
    sequence: Positive
    content_base64: Annotated[str, StringConstraints(min_length=1, max_length=7_000_000)]
    sha256: Sha256Digest


class IngestionFinalize(Contract):
    operation_key: OperationKey
    expected_byte_length: Positive
    expected_sha256: Sha256Digest


class Ingestion(Contract):
    ingestion_id: UUID
    document_id: UUID
    source_asset_id: UUID | None = None
    source_kind: Literal["audio", "transcript"]
    state: IngestionState
    stage: IngestionStage
    uploaded_bytes: NonNegative
    expected_bytes: Positive
    acknowledged_chunks: NonNegative
    gap_count: NonNegative
    retryable: bool
    safe_error_code: str | None = None
    draft_revision: Positive | None = None
    draft_sha256: Sha256Digest | None = None
    transcript_version_id: UUID | None = None
    can_upload: bool
    can_retry: bool
    can_abort: bool
    can_review: bool
    can_approve: bool
    can_publish: bool
    created_at: AwareDatetime
    updated_at: AwareDatetime


class IngestionPage(Contract):
    items: Annotated[list[Ingestion], Field(max_length=100)]


class CleanupEditManifest(Contract):
    rule: Literal["filler_removal", "stutter_deduplication"]
    start_character: NonNegative
    end_character: NonNegative


class DraftApproval(Contract):
    approval_id: UUID
    method: Literal["controlled_cleanup_policy", "person"]
    content_sha256: Sha256Digest
    approved_at: AwareDatetime


class TranscriptDraft(Contract):
    ingestion_id: UUID
    document_id: UUID
    draft_id: UUID
    revision: Positive
    source_sha256: Sha256Digest
    content_sha256: Sha256Digest
    canonical_text: str
    segments: list[TranscriptSegment]
    cleanup_policy_version: PolicyVersion
    cleanup_status: Literal["unchanged", "accepted", "approval_required", "human_corrected"]
    edit_manifest: list[CleanupEditManifest]
    approval: DraftApproval | None = None


class CorrectedDraftPut(Contract):
    canonical_text: Annotated[str, StringConstraints(min_length=1, max_length=20_000_000)]
    expected_revision: Positive
    expected_content_sha256: Sha256Digest
    reason_code: Literal[
        "transcription_correction", "speaker_correction", "formatting_correction", "other_reviewed"
    ]


class TranscriptApprovalCreate(Contract):
    content_sha256: Sha256Digest
    expected_revision: Positive
    reason_code: Literal["reviewed_transcript", "reviewed_with_audio", "approved_correction"]


class TranscriptPublicationCreate(Contract):
    approved_content_sha256: Sha256Digest
    expected_draft_revision: Positive
    expected_active_transcript_version_id: UUID | None = None
    operation_key: OperationKey


class IngestionAction(Contract):
    operation_key: OperationKey


class TranscriptDownload(Contract):
    format: Literal["txt", "md", "json"]
    filename: Annotated[str, StringConstraints(min_length=1, max_length=520)]
    media_type: Literal[
        "text/plain; charset=utf-8", "text/markdown; charset=utf-8", "application/json"
    ]
    content_base64: str
    sha256: Sha256Digest


class SourceAssetContent(Contract):
    source_asset_id: UUID
    media_type: Annotated[str, StringConstraints(min_length=1, max_length=200)]
    byte_length: Positive
    sha256: Sha256Digest
    content_base64: str


class TranscriptPublication(Contract):
    transcript_version_id: UUID
    document_id: UUID
    source_asset_id: UUID
    content_sha256: Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
    state: Literal["published"]
    approval_method: Literal["controlled_cleanup_policy", "person"]
    passage_count: NonNegative
    index_job_count: NonNegative
    canonical_text: str
    reproduced_sha256: Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]


class CaptureCreate(Contract):
    document_id: UUID

    @field_validator("document_id", mode="before")
    @classmethod
    def parse_json_uuid(cls, value: object) -> object:
        if isinstance(value, str):
            return UUID(value)
        return value


class CaptureGap(Contract):
    start_ms: NonNegative
    end_ms: NonNegative | None
    reason: Annotated[str, StringConstraints(min_length=1, max_length=100)]


class CaptureSession(Contract):
    capture_session_id: UUID
    document_id: UUID
    state: Literal[
        "created",
        "recording",
        "paused",
        "interrupted",
        "finalizing",
        "uploading",
        "complete",
        "failed",
        "aborted",
    ]
    acknowledged_chunks: NonNegative
    gaps: list[CaptureGap]
    source_asset_id: UUID | None = None
    ingestion_id: UUID | None = None


class CaptureTransition(Contract):
    event: Literal["start", "pause", "resume", "interrupt", "recover", "stop", "upload", "fail"]
    at_ms: NonNegative = 0
    reason: Annotated[str, StringConstraints(min_length=1, max_length=100)] = "device_interruption"


class CaptureChunkUpload(Contract):
    sequence: Positive
    content_base64: Annotated[str, StringConstraints(min_length=1, max_length=7_000_000)]
    sha256: Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]


class CaptureFinalize(Contract):
    filename: Annotated[str, StringConstraints(min_length=1, max_length=500, pattern=r"\S")]
    detected_mime: Literal["audio/wav", "audio/mpeg", "audio/mp4", "audio/webm"] = "audio/wav"
    duration_ms: NonNegative


class EvidenceSelection(Contract):
    selected_passages: Annotated[
        list[UUID], Field(max_length=8, json_schema_extra={"uniqueItems": True})
    ]

    @model_validator(mode="after")
    def unique_ids(self) -> "EvidenceSelection":
        if len(set(self.selected_passages)) != len(self.selected_passages):
            raise ValueError("duplicate passage")
        return self


class SelectedSpan(Contract):
    passage_id: UUID
    start_character: NonNegative
    end_character: Positive

    @model_validator(mode="after")
    def increasing(self) -> "SelectedSpan":
        if self.end_character <= self.start_character:
            raise ValueError("span must be increasing")
        return self


class EvidenceSpanSelection(Contract):
    selected_spans: Annotated[
        list[SelectedSpan], Field(max_length=8, json_schema_extra={"uniqueItems": True})
    ]

    @model_validator(mode="after")
    def unique_spans(self) -> "EvidenceSpanSelection":
        keys = [(s.passage_id, s.start_character, s.end_character) for s in self.selected_spans]
        if len(set(keys)) != len(keys):
            raise ValueError("duplicate span")
        return self


class AccessChangedData(Contract):
    project_membership_id: UUID
    user_id: UUID
    membership_revision: Positive
    authorization_epoch: NonNegative


class PublishedData(Contract):
    transcript_version_id: UUID


class EventBase(Contract):
    event_id: UUID
    schema_version: Literal[1]
    tenant_id: UUID
    workspace_id: UUID
    project_id: UUID
    aggregate_id: UUID
    occurred_at: AwareDatetime
    trace_id: RequestId

    @field_validator("schema_version", mode="before")
    @classmethod
    def integer_version(cls, value: object) -> object:
        if type(value) is not int:
            raise ValueError("schema_version must be an integer")
        return value

    @field_validator("occurred_at")
    @classmethod
    def utc_time(cls, value: datetime) -> datetime:
        if value.utcoffset() != timedelta(0):
            raise ValueError("event time must be UTC")
        return value


class AccessChangedEvent(EventBase):
    type: Literal["access.changed"]
    data: AccessChangedData

    @model_validator(mode="after")
    def aggregate(self) -> "AccessChangedEvent":
        if self.aggregate_id != self.project_id:
            raise ValueError("membership event aggregate must be project")
        return self


class TranscriptPublishedEvent(EventBase):
    type: Literal["transcript.published"]
    document_id: UUID
    data: PublishedData

    @model_validator(mode="after")
    def aggregate(self) -> "TranscriptPublishedEvent":
        if self.aggregate_id != self.document_id:
            raise ValueError("publication event aggregate must be document")
        return self


PUBLIC_MODELS = [
    Error,
    MagicLinkRequest,
    MagicLinkRequestAccepted,
    MagicLinkConsume,
    AuthenticationResult,
    AuthenticationMode,
    LogoutResult,
    MeResponse,
    ProfileUpdate,
    ProjectCreate,
    Project,
    MembershipPut,
    Membership,
    MemberSummary,
    MemberPage,
    MembershipByEmailPut,
    DocumentCreate,
    Document,
    ProjectPage,
    DocumentPage,
    TranscriptPublication,
    IngestionCreate,
    IngestionChunkPut,
    IngestionFinalize,
    Ingestion,
    IngestionPage,
    TranscriptDraft,
    CorrectedDraftPut,
    TranscriptApprovalCreate,
    TranscriptPublicationCreate,
    IngestionAction,
    TranscriptDownload,
    SourceAssetContent,
    CaptureCreate,
    CaptureSession,
    CaptureTransition,
    CaptureChunkUpload,
    CaptureFinalize,
]
RESERVED_MODELS = [
    TranscriptImport,
    EvidenceSelection,
    EvidenceSpanSelection,
    AccessChangedEvent,
    TranscriptPublishedEvent,
]
