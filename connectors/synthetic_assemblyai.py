"""Credential-free AssemblyAI lifecycle simulator; never performs network I/O."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from hashlib import sha256

from domain.providers import (
    ObjectStorage,
    RawTranscriptResult,
    Submission,
    TranscriptSegmentResult,
)

from .fakes import FakeProviderError

_MODEL_ID = "universal-3-5-pro"


@dataclass
class SyntheticAssemblyAIAdapter:
    storage: ObjectStorage
    fixture_segments: tuple[TranscriptSegmentResult, ...]
    fault: str | None = None
    _operations: dict[str, tuple[str, Submission]] = field(default_factory=dict)
    _polls: dict[str, int] = field(default_factory=dict)
    _results: dict[str, RawTranscriptResult] = field(default_factory=dict)
    _deleted: set[str] = field(default_factory=set)

    def transcribe(self, audio_handle: str, operation_key: str) -> Submission:
        if self.fault == "auth":
            raise FakeProviderError("provider_auth")
        if self.fault == "throttled":
            raise FakeProviderError("provider_throttled")
        if self.fault == "outcome_unknown":
            raise FakeProviderError("provider_outcome_unknown")
        existing = self._operations.get(operation_key)
        if existing is not None:
            if existing[0] != audio_handle:
                raise FakeProviderError("provider_invalid_input")
            return existing[1]
        submission = Submission(f"synthetic-aai-{len(self._operations) + 1}", "queued")
        self._operations[operation_key] = (audio_handle, submission)
        self._polls[submission.submission_ref] = 0
        return submission

    def get_status(self, submission_ref: str) -> str:
        self._require_submission(submission_ref)
        if self.fault == "failed":
            return "failed"
        count = self._polls[submission_ref]
        self._polls[submission_ref] = count + 1
        return ("queued", "processing", "completed")[min(count, 2)]

    def fetch_result(self, submission_ref: str) -> RawTranscriptResult:
        self._require_submission(submission_ref)
        if self._polls[submission_ref] < 2:
            raise FakeProviderError("provider_unavailable")
        if self.fault == "invalid_response":
            raise FakeProviderError("provider_invalid_response")
        prior = self._results.get(submission_ref)
        if prior is not None:
            return prior
        raw = json.dumps(
            {
                "id": submission_ref,
                "speech_model": _MODEL_ID,
                "status": "completed",
                "utterances": [
                    {
                        "text": item.text,
                        "speaker": item.speaker_label,
                        "start": item.start_ms,
                        "end": item.end_ms,
                    }
                    for item in self.fixture_segments
                ],
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        digest = sha256(raw).hexdigest()
        stored = self.storage.put_immutable(raw, digest, f"aai-raw:{submission_ref}")
        result = RawTranscriptResult(
            "completed", self.fixture_segments, _MODEL_ID, stored.object_ref
        )
        self._results[submission_ref] = result
        return result

    def delete_result(self, submission_ref: str, operation_key: str) -> str:
        del operation_key
        self._require_submission(submission_ref)
        if self.fault == "delete_failed":
            raise FakeProviderError("provider_unavailable")
        self._deleted.add(submission_ref)
        return "deleted"

    def _require_submission(self, submission_ref: str) -> None:
        if submission_ref in self._deleted or submission_ref not in self._polls:
            raise FakeProviderError("provider_not_found")
