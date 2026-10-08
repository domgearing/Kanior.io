"""Private content-addressed object storage for synthetic local development."""

from __future__ import annotations

import os
from hashlib import sha256
from pathlib import Path

from connectors.fakes import FakeProviderError
from domain.providers import StoredObject


class LocalObjectStorage:
    """Immutable filesystem adapter; object references never contain caller paths."""

    def __init__(self, root: Path) -> None:
        self._root = root.resolve()
        self._root.mkdir(parents=True, exist_ok=True)

    def _path(self, object_ref: str) -> Path:
        if not object_ref.startswith("sha256/") or len(object_ref) != 71:
            raise FakeProviderError("provider_invalid_input")
        digest = object_ref.removeprefix("sha256/")
        if any(character not in "0123456789abcdef" for character in digest):
            raise FakeProviderError("provider_invalid_input")
        return self._root / digest[:2] / digest[2:]

    def put_immutable(self, data: bytes, expected_sha256: str, operation_key: str) -> StoredObject:
        del operation_key  # content addressing makes repeated identical writes idempotent.
        digest = sha256(data).hexdigest()
        if digest != expected_sha256:
            raise FakeProviderError("integrity_failure")
        object_ref = f"sha256/{digest}"
        target = self._path(object_ref)
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            if target.read_bytes() != data:
                raise FakeProviderError("integrity_failure") from None
        else:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
        return StoredObject(object_ref, len(data), digest)

    def read_version(self, object_ref: str, byte_range: tuple[int, int] | None = None) -> bytes:
        try:
            value = self._path(object_ref).read_bytes()
        except FileNotFoundError as error:
            raise FakeProviderError("provider_not_found") from error
        if sha256(value).hexdigest() != object_ref.removeprefix("sha256/"):
            raise FakeProviderError("integrity_failure")
        if byte_range is None:
            return value
        start, end = byte_range
        if start < 0 or end < start or end > len(value):
            raise FakeProviderError("provider_invalid_input")
        return value[start:end]

    def stat_version(self, object_ref: str) -> StoredObject:
        value = self.read_version(object_ref)
        return StoredObject(object_ref, len(value), sha256(value).hexdigest())
