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
    str, StringConstraints(min_length=2, max_length=35, pattern=r"^[A-Za-z]{2,8}(-[A-Za-z0-9]{1,8})*$")
]
PolicyVersion = Annotated[str, StringConstraints(min_length=1, max_length=100, pattern=r"\S")]
NonNegative = Annotated[StrictInt, Field(ge=0)]
Positive = Annotated[StrictInt, Field(ge=1)]
RequestId = Annotated[str, StringConstraints(min_length=1, max_length=128)]
Role = Literal["reader", "contributor", "project_owner"]


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
        "unauthenticated", "forbidden", "not_found", "conflict",
        "payload_too_large", "invalid_input", "rate_limited",
        "dependency_unavailable", "internal_error",
    ]
    message: Annotated[str, StringConstraints(min_length=1, max_length=300)]
    request_id: RequestId
    retryable: bool


class MeResponse(Contract):
    user_id: UUID
    tenant_id: UUID
    workspace_id: UUID
    display_name: Name
    capabilities: list[Literal["projects:create"]]
    csrf_token: Annotated[str, StringConstraints(min_length=32, max_length=256)]


class ProjectCreate(Contract):
    name: Name


class Project(Contract):
    project_id: UUID
    tenant_id: UUID
    workspace_id: UUID
    name: Name
    owner_user_id: UUID
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


class DocumentCreate(Contract):
    title: Title
    meeting_date: AwareDatetime
    language: Language
    consent_acknowledged: Literal[True]
    consent_policy_version: PolicyVersion

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
        extra="forbid", strict=True,
        json_schema_extra={
            "anyOf": [
                {"not": {"anyOf": [{"required": ["start_ms"]}, {"required": ["end_ms"]}]}},
                {"required": ["start_ms", "end_ms"], "properties": {"start_ms": {"type": "null"}, "end_ms": {"type": "null"}}},
                {
                    "required": ["start_ms", "end_ms"],
                    "properties": {"start_ms": {"type": "integer"}, "end_ms": {"type": "integer"}},
                },
            ],
            "description": "Times are paired; semantic validation also requires end_ms >= start_ms. Preserve text verbatim.",
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
        if self.start_ms is not None and self.end_ms < self.start_ms:
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


class EvidenceSelection(Contract):
    selected_passages: Annotated[list[UUID], Field(max_length=8, json_schema_extra={"uniqueItems": True})]

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
    selected_spans: Annotated[list[SelectedSpan], Field(max_length=8, json_schema_extra={"uniqueItems": True})]

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
    Error, MeResponse, ProjectCreate, Project, MembershipPut, Membership,
    DocumentCreate, Document, ProjectPage, DocumentPage,
]
RESERVED_MODELS = [
    TranscriptImport, EvidenceSelection, EvidenceSpanSelection,
    AccessChangedEvent, TranscriptPublishedEvent,
]
