"""Deterministic, credential-free adapters for tests and local development.

They model immutable object versions and asynchronous transcription without
network calls. Production adapter implementations remain blocked by the
provider feasibility gates in docs/INTEGRATIONS.md.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from hashlib import sha256

from domain.providers import (
    EmbeddingBatch,
    EvidenceSelectionResult,
    RawTranscriptResult,
    StoredObject,
    Submission,
    TranscriptSegmentResult,
)


class FakeProviderError(RuntimeError):
    """Safe fake-adapter failure that deliberately contains no external response."""


@dataclass
class FakeObjectStorage:
    _objects: dict[str, bytes] = field(default_factory=dict)
    _operations: dict[str, StoredObject] = field(default_factory=dict)

    def put_immutable(self, data: bytes, expected_sha256: str, operation_key: str) -> StoredObject:
        digest = sha256(data).hexdigest()
        if digest != expected_sha256:
            raise FakeProviderError("integrity_failure")
        if prior := self._operations.get(operation_key):
            return prior
        object_ref = f"synthetic-object-version-{len(self._objects) + 1}"
        stored = StoredObject(object_ref=object_ref, byte_length=len(data), sha256=digest)
        self._objects[object_ref] = data
        self._operations[operation_key] = stored
        return stored

    def read_version(self, object_ref: str, byte_range: tuple[int, int] | None = None) -> bytes:
        try:
            value = self._objects[object_ref]
        except KeyError as error:
            raise FakeProviderError("provider_not_found") from error
        if byte_range is None:
            return value
        start, end = byte_range
        if start < 0 or end < start or end > len(value):
            raise FakeProviderError("provider_invalid_input")
        return value[start:end]

    def stat_version(self, object_ref: str) -> StoredObject:
        value = self.read_version(object_ref)
        return StoredObject(object_ref, len(value), sha256(value).hexdigest())


@dataclass
class FakeTranscriptionProvider:
    _submissions: dict[str, Submission] = field(default_factory=dict)

    def transcribe(self, audio_handle: str, operation_key: str) -> Submission:
        if existing := self._submissions.get(operation_key):
            return existing
        submission = Submission(f"synthetic-transcript-{len(self._submissions) + 1}", "queued")
        self._submissions[operation_key] = submission
        return submission

    def get_status(self, submission_ref: str) -> str:
        if not any(item.submission_ref == submission_ref for item in self._submissions.values()):
            raise FakeProviderError("provider_not_found")
        return "completed"

    def fetch_result(self, submission_ref: str) -> RawTranscriptResult:
        if self.get_status(submission_ref) != "completed":
            raise FakeProviderError("provider_unavailable")
        return RawTranscriptResult(
            state="completed",
            segments=(
                TranscriptSegmentResult(
                    text="We said fifteen, not fifty.",
                    speaker_label="A",
                    start_ms=0,
                    end_ms=1800,
                ),
            ),
            model_id="synthetic-assemblyai-v1",
            raw_artifact_ref=f"synthetic-raw-{submission_ref}",
        )


class FakeModelProvider:
    def select_evidence(
        self, authorized_candidate_ids: tuple[str, ...], operation_key: str
    ) -> EvidenceSelectionResult:
        del operation_key
        return EvidenceSelectionResult(selected_passages=authorized_candidate_ids[:8])


class FakeEmbeddingProvider:
    """Produces stable three-dimensional synthetic vectors; never use for retrieval quality."""

    def embed(self, texts: tuple[str, ...], operation_key: str) -> EmbeddingBatch:
        del operation_key
        return EmbeddingBatch(
            vectors=tuple(self._vector(text) for text in texts),
            dimension=3,
            model_id="synthetic-embedding-v1",
        )

    @staticmethod
    def _vector(text: str) -> tuple[float, float, float]:
        digest = sha256(text.encode("utf-8")).digest()
        return tuple(round(byte / 255, 6) for byte in digest[:3])  # type: ignore[return-value]


def fake_segment_text(segments: Iterable[TranscriptSegmentResult]) -> str:
    """Join provider segments exactly once with LF, matching transcript-import convention."""

    return "\n".join(segment.text for segment in segments)
