from hashlib import sha256

import pytest

from connectors.fakes import FakeProviderError
from connectors.local_storage import LocalObjectStorage


def test_local_storage_is_immutable_idempotent_and_range_readable(tmp_path) -> None:  # type: ignore[no-untyped-def]
    storage = LocalObjectStorage(tmp_path)
    data = "fictional audio 🌍".encode()
    digest = sha256(data).hexdigest()
    first = storage.put_immutable(data, digest, "upload-1")
    second = storage.put_immutable(data, digest, "upload-2")
    assert first == second
    assert storage.read_version(first.object_ref, (11, 16)) == data[11:16]
    assert storage.stat_version(first.object_ref).sha256 == digest


def test_local_storage_rejects_traversal_and_hash_mismatch(tmp_path) -> None:  # type: ignore[no-untyped-def]
    storage = LocalObjectStorage(tmp_path)
    with pytest.raises(FakeProviderError, match="provider_invalid_input"):
        storage.read_version("../secret")
    with pytest.raises(FakeProviderError, match="integrity_failure"):
        storage.put_immutable(b"bytes", "0" * 64, "upload-1")
