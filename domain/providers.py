"""Provider-neutral contracts used by future domain services.

These data types are intentionally internal. They do not expose provider SDK
objects, credentials, URLs, or raw response bodies.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class ProviderFailure:
    code: str
    retryable: bool
    outcome_known: bool
    retry_after_seconds: int | None = None


@dataclass(frozen=True)
class StoredObject:
    object_ref: str
    byte_length: int
    sha256: str
    immutable: bool = True


@dataclass(frozen=True)
class TranscriptSegmentResult:
    text: str
    speaker_label: str | None
    start_ms: int | None
    end_ms: int | None


@dataclass(frozen=True)
class RawTranscriptResult:
    state: str
    segments: tuple[TranscriptSegmentResult, ...]
    model_id: str
    raw_artifact_ref: str


@dataclass(frozen=True)
class Submission:
    submission_ref: str
    state: str


@dataclass(frozen=True)
class EvidenceSelectionResult:
    selected_passages: tuple[str, ...]


@dataclass(frozen=True)
class EmbeddingBatch:
    vectors: tuple[tuple[float, ...], ...]
    dimension: int
    model_id: str


class ObjectStorage(Protocol):
    def put_immutable(
        self, data: bytes, expected_sha256: str, operation_key: str
    ) -> StoredObject: ...

    def read_version(self, object_ref: str, byte_range: tuple[int, int] | None = None) -> bytes: ...

    def stat_version(self, object_ref: str) -> StoredObject: ...


class TranscriptionProvider(Protocol):
    def transcribe(self, audio_handle: str, operation_key: str) -> Submission: ...

    def get_status(self, submission_ref: str) -> str: ...

    def fetch_result(self, submission_ref: str) -> RawTranscriptResult: ...


class ModelProvider(Protocol):
    def select_evidence(
        self, authorized_candidate_ids: tuple[str, ...], operation_key: str
    ) -> EvidenceSelectionResult: ...


class EmbeddingProvider(Protocol):
    def embed(self, texts: tuple[str, ...], operation_key: str) -> EmbeddingBatch: ...
