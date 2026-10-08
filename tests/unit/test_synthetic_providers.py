from __future__ import annotations

from hashlib import sha256

import pytest

from connectors.fakes import FakeObjectStorage, FakeProviderError
from connectors.synthetic_assemblyai import SyntheticAssemblyAIAdapter
from connectors.synthetic_recall import SyntheticRecallAdapter
from domain.providers import TranscriptSegmentResult


def _segments() -> tuple[TranscriptSegmentResult, ...]:
    return (
        TranscriptSegmentResult("Fictional opening.", "A", 0, 900),
        TranscriptSegmentResult("Fictional response.", "B", 850, 1700),
    )


def test_recall_signed_completion_copies_original_once_and_survives_provider_delete() -> None:
    storage = FakeObjectStorage()
    adapter = SyntheticRecallAdapter(b"synthetic-audio", 1700, gap_count=1)
    grant = adapter.create_session("capture-1", "create:1")
    assert adapter.create_session("capture-1", "create:1") == grant
    body, signature = adapter.notification(grant.capture_ref, "event-1")
    assert adapter.verify_notification(body, signature).state == "completed"
    assert adapter.verify_notification(body, signature).state == "duplicate"

    copied = adapter.copy_original(grant.capture_ref, storage, "copy:1")
    assert copied.gap_count == 1
    assert copied.stored_object.sha256 == sha256(b"synthetic-audio").hexdigest()
    adapter.delete_capture(grant.capture_ref, "delete:1")
    assert storage.read_version(copied.stored_object.object_ref) == b"synthetic-audio"


def test_recall_rejects_forged_event_and_operation_key_rebinding() -> None:
    adapter = SyntheticRecallAdapter(b"audio", 1)
    grant = adapter.create_session("capture-1", "create:1")
    body, _ = adapter.notification(grant.capture_ref, "event-1")
    with pytest.raises(FakeProviderError, match="provider_permission"):
        adapter.verify_notification(body, "forged")
    with pytest.raises(FakeProviderError, match="provider_invalid_input"):
        adapter.create_session("capture-2", "create:1")


@pytest.mark.parametrize(
    ("fault", "code"),
    [
        ("media_delayed", "provider_unavailable"),
        ("missing_audio", "provider_invalid_response"),
        ("wrong_hash", "integrity_failure"),
    ],
)
def test_recall_media_faults_are_safe(fault: str, code: str) -> None:
    adapter = SyntheticRecallAdapter(b"audio", 1, fault=fault)
    grant = adapter.create_session("capture-1", "create:1")
    with pytest.raises(FakeProviderError, match=code):
        adapter.copy_original(grant.capture_ref, FakeObjectStorage(), "copy:1")


def test_assemblyai_is_async_idempotent_and_preserves_raw_result() -> None:
    storage = FakeObjectStorage()
    adapter = SyntheticAssemblyAIAdapter(storage, _segments())
    submission = adapter.transcribe("audio-object-1", "transcribe:1")
    assert adapter.transcribe("audio-object-1", "transcribe:1") == submission
    assert adapter.get_status(submission.submission_ref) == "queued"
    assert adapter.get_status(submission.submission_ref) == "processing"
    result = adapter.fetch_result(submission.submission_ref)
    assert result.model_id == "universal-3-5-pro"
    assert storage.stat_version(result.raw_artifact_ref).immutable
    assert adapter.fetch_result(submission.submission_ref) == result


def test_assemblyai_rejects_operation_key_rebinding_and_early_fetch() -> None:
    adapter = SyntheticAssemblyAIAdapter(FakeObjectStorage(), _segments())
    submission = adapter.transcribe("audio-1", "transcribe:1")
    with pytest.raises(FakeProviderError, match="provider_invalid_input"):
        adapter.transcribe("audio-2", "transcribe:1")
    with pytest.raises(FakeProviderError, match="provider_unavailable"):
        adapter.fetch_result(submission.submission_ref)


@pytest.mark.parametrize(
    ("fault", "code"),
    [
        ("auth", "provider_auth"),
        ("throttled", "provider_throttled"),
        ("outcome_unknown", "provider_outcome_unknown"),
    ],
)
def test_assemblyai_submission_faults_are_safe(fault: str, code: str) -> None:
    adapter = SyntheticAssemblyAIAdapter(FakeObjectStorage(), _segments(), fault=fault)
    with pytest.raises(FakeProviderError, match=code):
        adapter.transcribe("audio-1", "transcribe:1")
