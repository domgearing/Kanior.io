from __future__ import annotations

from hashlib import sha256

import pytest

from connectors.fakes import (
    FakeEmbeddingProvider,
    FakeObjectStorage,
    FakeProviderError,
    FakeTranscriptionProvider,
)


def test_fake_storage_is_idempotent_and_version_pinned() -> None:
    storage = FakeObjectStorage()
    digest = sha256(b"abc").hexdigest()
    first = storage.put_immutable(b"abc", digest, "store:1")
    second = storage.put_immutable(b"abc", digest, "store:1")
    assert first == second
    assert storage.read_version(first.object_ref, (0, 2)) == b"ab"


def test_fake_storage_rejects_wrong_hash() -> None:
    with pytest.raises(FakeProviderError, match="integrity_failure"):
        FakeObjectStorage().put_immutable(b"abc", "not-a-hash", "store:1")


def test_fake_transcription_is_deterministic_and_asynchronous() -> None:
    provider = FakeTranscriptionProvider()
    submission = provider.transcribe("synthetic-audio-1", "transcribe:1")
    assert provider.transcribe("synthetic-audio-1", "transcribe:1") == submission
    assert provider.get_status(submission.submission_ref) == "completed"
    assert (
        provider.fetch_result(submission.submission_ref).segments[0].text
        == "We said fifteen, not fifty."
    )


def test_fake_embeddings_are_deterministic() -> None:
    provider = FakeEmbeddingProvider()
    assert provider.embed(("fictional",), "embed:1") == provider.embed(("fictional",), "embed:2")
