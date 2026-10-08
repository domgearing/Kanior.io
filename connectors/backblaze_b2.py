"""Version-pinned Backblaze B2 storage through the S3-compatible API."""

from __future__ import annotations

import base64
import json
import sqlite3
from collections.abc import Callable
from hashlib import sha256
from pathlib import Path
from threading import Lock
from typing import Any, cast
from uuid import uuid4

import boto3  # type: ignore[import-untyped]
from botocore.config import Config  # type: ignore[import-untyped]
from botocore.exceptions import ClientError  # type: ignore[import-untyped]

from connectors.fakes import FakeProviderError
from domain.providers import StoredObject

_PART_SIZE = 8 * 1024 * 1024


def _encode_ref(bucket: str, key: str, version_id: str) -> str:
    raw = json.dumps([bucket, key, version_id], separators=(",", ":")).encode()
    return "b2v1:" + base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _decode_ref(object_ref: str) -> tuple[str, str, str]:
    if not object_ref.startswith("b2v1:"):
        raise FakeProviderError("provider_invalid_input")
    try:
        value = object_ref.removeprefix("b2v1:")
        raw = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
        bucket, key, version = json.loads(raw)
        if not all(isinstance(item, str) and item for item in (bucket, key, version)):
            raise ValueError
        return bucket, key, version
    except (ValueError, TypeError, json.JSONDecodeError) as error:
        raise FakeProviderError("provider_invalid_input") from error


class _OperationStore:
    """Small durable reconciliation store; it contains references, never credentials or bytes."""

    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(path, check_same_thread=False)
        self._lock = Lock()
        with self._connection:
            self._connection.execute(
                """CREATE TABLE IF NOT EXISTS b2_operations (
                operation_key TEXT PRIMARY KEY, object_key TEXT NOT NULL,
                expected_sha256 TEXT NOT NULL,
                upload_id TEXT NULL, version_id TEXT NULL, byte_length INTEGER NULL)"""
            )

    def get(self, operation_key: str) -> sqlite3.Row | None:
        self._connection.row_factory = sqlite3.Row
        return cast(
            sqlite3.Row | None,
            self._connection.execute(
                "SELECT * FROM b2_operations WHERE operation_key=?", (operation_key,)
            ).fetchone(),
        )

    def begin(self, operation_key: str, object_key: str, expected_sha256: str) -> sqlite3.Row:
        with self._lock, self._connection:
            self._connection.execute(
                """INSERT OR IGNORE INTO b2_operations
                (operation_key,object_key,expected_sha256) VALUES (?,?,?)""",
                (operation_key, object_key, expected_sha256),
            )
        row = self.get(operation_key)
        assert row is not None
        if row["expected_sha256"] != expected_sha256:
            raise FakeProviderError("provider_invalid_input")
        return row

    def set_upload(self, operation_key: str, upload_id: str) -> None:
        with self._connection:
            self._connection.execute(
                "UPDATE b2_operations SET upload_id=? WHERE operation_key=?",
                (upload_id, operation_key),
            )

    def complete(self, operation_key: str, version_id: str, byte_length: int) -> None:
        with self._connection:
            self._connection.execute(
                """UPDATE b2_operations SET version_id=?,byte_length=?,upload_id=NULL
                WHERE operation_key=?""",
                (version_id, byte_length, operation_key),
            )


class BackblazeB2Storage:
    """Immutable/version-aware storage with resumable multipart upload state."""

    def __init__(
        self,
        *,
        endpoint_url: str,
        region: str,
        bucket: str,
        key_prefix: str,
        access_key_id: str,
        secret_access_key: str,
        operation_store: Path,
        multipart_checkpoint_hook: Callable[[int], None] | None = None,
    ) -> None:
        self._bucket = bucket
        self._prefix = key_prefix.strip("/") + "/"
        self._client = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            region_name=region,
            aws_access_key_id=access_key_id,
            aws_secret_access_key=secret_access_key,
            config=Config(
                signature_version="s3v4",
                retries={"max_attempts": 3, "mode": "standard"},
            ),
        )
        self._operations = _OperationStore(operation_store)
        self._multipart_checkpoint_hook = multipart_checkpoint_hook

    def put_immutable(self, data: bytes, expected_sha256: str, operation_key: str) -> StoredObject:
        digest = sha256(data).hexdigest()
        if digest != expected_sha256:
            raise FakeProviderError("integrity_failure")
        object_key = f"{self._prefix}objects/{digest[:2]}/{digest}-{uuid4()}"
        row = self._operations.begin(operation_key, object_key, expected_sha256)
        if row["version_id"]:
            result = StoredObject(
                _encode_ref(self._bucket, row["object_key"], row["version_id"]),
                row["byte_length"],
                expected_sha256,
            )
            self._verify(result)
            return result
        try:
            if len(data) < _PART_SIZE:
                response = self._client.put_object(
                    Bucket=self._bucket,
                    Key=row["object_key"],
                    Body=data,
                    Metadata={"verelo-sha256": digest},
                )
                version_id = response["VersionId"]
            else:
                version_id = self._multipart(data, row, operation_key, digest)
        except ClientError as error:
            raise self._safe_error(error) from error
        self._operations.complete(operation_key, version_id, len(data))
        result = StoredObject(
            _encode_ref(self._bucket, row["object_key"], version_id), len(data), digest
        )
        self._verify(result)
        return result

    def _multipart(self, data: bytes, row: sqlite3.Row, operation_key: str, digest: str) -> str:
        upload_id = row["upload_id"]
        if upload_id is None:
            created = self._client.create_multipart_upload(
                Bucket=self._bucket,
                Key=row["object_key"],
                Metadata={"verelo-sha256": digest},
            )
            upload_id = created["UploadId"]
            self._operations.set_upload(operation_key, upload_id)
        existing = self._client.list_parts(
            Bucket=self._bucket, Key=row["object_key"], UploadId=upload_id
        ).get("Parts", [])
        completed = {int(part["PartNumber"]): part["ETag"] for part in existing}
        parts: list[dict[str, Any]] = []
        for offset in range(0, len(data), _PART_SIZE):
            number = offset // _PART_SIZE + 1
            etag = completed.get(number)
            if etag is None:
                uploaded = self._client.upload_part(
                    Bucket=self._bucket,
                    Key=row["object_key"],
                    UploadId=upload_id,
                    PartNumber=number,
                    Body=data[offset : offset + _PART_SIZE],
                )
                etag = uploaded["ETag"]
                if self._multipart_checkpoint_hook is not None:
                    self._multipart_checkpoint_hook(number)
            parts.append({"ETag": etag, "PartNumber": number})
        result = self._client.complete_multipart_upload(
            Bucket=self._bucket,
            Key=row["object_key"],
            UploadId=upload_id,
            MultipartUpload={"Parts": parts},
        )
        return str(result["VersionId"])

    def read_version(self, object_ref: str, byte_range: tuple[int, int] | None = None) -> bytes:
        bucket, key, version_id = _decode_ref(object_ref)
        if bucket != self._bucket or not key.startswith(self._prefix):
            raise FakeProviderError("provider_permission")
        request: dict[str, Any] = {"Bucket": bucket, "Key": key, "VersionId": version_id}
        if byte_range is not None:
            start, end = byte_range
            if start < 0 or end <= start:
                raise FakeProviderError("provider_invalid_input")
            request["Range"] = f"bytes={start}-{end - 1}"
        try:
            return bytes(self._client.get_object(**request)["Body"].read())
        except ClientError as error:
            raise self._safe_error(error) from error

    def stat_version(self, object_ref: str) -> StoredObject:
        bucket, key, version_id = _decode_ref(object_ref)
        if bucket != self._bucket or not key.startswith(self._prefix):
            raise FakeProviderError("provider_permission")
        try:
            value = self._client.head_object(Bucket=bucket, Key=key, VersionId=version_id)
        except ClientError as error:
            raise self._safe_error(error) from error
        digest = value.get("Metadata", {}).get("verelo-sha256")
        if not isinstance(digest, str) or len(digest) != 64:
            raise FakeProviderError("provider_invalid_response")
        return StoredObject(object_ref, int(value["ContentLength"]), digest)

    def delete_version(self, object_ref: str) -> None:
        bucket, key, version_id = _decode_ref(object_ref)
        self._client.delete_object(Bucket=bucket, Key=key, VersionId=version_id)

    def _verify(self, stored: StoredObject) -> None:
        value = self.read_version(stored.object_ref)
        if len(value) != stored.byte_length or sha256(value).hexdigest() != stored.sha256:
            raise FakeProviderError("integrity_failure")

    @staticmethod
    def _safe_error(error: ClientError) -> FakeProviderError:
        status = error.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
        if status in {401, 403}:
            return FakeProviderError("provider_permission")
        if status == 404:
            return FakeProviderError("provider_not_found")
        return FakeProviderError("provider_unavailable")
