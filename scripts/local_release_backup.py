"""Single-user local backup and isolated restore verification.

The manifest is written last: an incomplete prefix is never considered a backup.
No object bytes, database rows, credentials, or provider errors are printed.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import boto3  # type: ignore[import-untyped]
from botocore.config import Config  # type: ignore[import-untyped]
from pydantic import SecretStr
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from api.config import Environment, IntegrationsMode, Settings  # noqa: E402

STATUS = ROOT / ".artifacts" / "local-release" / "backup-status.json"
OBJECT_QUERY = """
SELECT object_ref, sha256, byte_length FROM capture_chunks
UNION ALL SELECT object_ref, sha256, byte_length FROM ingestion_chunks
UNION ALL SELECT object_ref, sha256, byte_length FROM source_assets
UNION ALL SELECT raw_object_ref, raw_sha256, NULL::bigint FROM raw_transcripts
UNION ALL SELECT parsed_object_ref, parsed_sha256, NULL::bigint FROM raw_transcripts
UNION ALL SELECT canonical_object_ref, content_sha256, byte_length FROM transcript_versions
"""


class BackupFailure(Exception):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def _required(value: object | None, code: str) -> str:
    if isinstance(value, SecretStr):
        value = value.get_secret_value()
    if not value:
        raise BackupFailure(code)
    return str(value)


def validate_settings(settings: Settings) -> None:
    if (
        settings.environment is not Environment.LOCAL
        or settings.integrations_mode is not IntegrationsMode.LIVE
    ):
        raise BackupFailure("local_live_mode_required")
    if not settings.b2_bucket_name or not settings.b2_backup_bucket_name:
        raise BackupFailure("backup_bucket_not_configured")
    if settings.b2_bucket_name == settings.b2_backup_bucket_name:
        raise BackupFailure("backup_bucket_must_be_separate")
    for value, code in (
        (settings.b2_s3_endpoint, "b2_endpoint_missing"),
        (settings.b2_region, "b2_region_missing"),
        (settings.b2_application_key_id, "source_key_missing"),
        (settings.b2_application_key, "source_secret_missing"),
        (settings.b2_backup_application_key_id, "backup_key_missing"),
        (settings.b2_backup_application_key, "backup_secret_missing"),
    ):
        _required(value, code)


def _client(settings: Settings, *, backup: bool) -> Any:
    key_id = settings.b2_backup_application_key_id if backup else settings.b2_application_key_id
    secret = settings.b2_backup_application_key if backup else settings.b2_application_key
    return boto3.client(
        "s3",
        endpoint_url=_required(settings.b2_s3_endpoint, "b2_endpoint_missing"),
        region_name=_required(settings.b2_region, "b2_region_missing"),
        aws_access_key_id=_required(key_id, "b2_key_missing"),
        aws_secret_access_key=_required(secret, "b2_secret_missing"),
        config=Config(signature_version="s3v4", retries={"max_attempts": 3, "mode": "standard"}),
    )


def decode_ref(ref: str, bucket: str, prefix: str) -> tuple[str, str]:
    if not ref.startswith("b2v1:"):
        raise BackupFailure("unsupported_object_ref")
    try:
        encoded = ref[5:]
        raw = base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4))
        value = json.loads(raw)
        if not isinstance(value, list) or len(value) != 3:
            raise ValueError
        actual_bucket, key, version = value
        if not all(isinstance(item, str) and item for item in value):
            raise ValueError
    except (ValueError, TypeError, UnicodeError) as error:
        raise BackupFailure("invalid_object_ref") from error
    if actual_bucket != bucket or not key.startswith(prefix.strip("/") + "/"):
        raise BackupFailure("object_ref_outside_source_scope")
    return key, version


def object_rows(rows: Any) -> list[dict[str, Any]]:
    by_ref: dict[str, dict[str, Any]] = {}
    for ref, digest, length in rows:
        ref, digest = str(ref), str(digest).lower()
        if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            raise BackupFailure("invalid_object_hash")
        size = None if length is None else int(length)
        if size is not None and size < 0:
            raise BackupFailure("invalid_object_size")
        existing = by_ref.get(ref)
        if existing and (
            existing["sha256"] != digest
            or (size is not None and existing["size"] not in (None, size))
        ):
            raise BackupFailure("inconsistent_object_reference")
        if existing is None:
            by_ref[ref] = {"ref": ref, "sha256": digest, "size": size}
        elif existing["size"] is None:
            existing["size"] = size
    return [by_ref[ref] for ref in sorted(by_ref)]


def _run(command: list[str], *, input_file: Any = None, output_file: Any = None) -> bytes:
    result = subprocess.run(
        command,
        cwd=ROOT,
        stdin=input_file,
        stdout=output_file if output_file is not None else subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=False,
        timeout=600,
    )
    if result.returncode:
        raise BackupFailure("database_command_failed")
    return result.stdout or b""


def _container() -> str:
    result = (
        _run(
            [
                "docker",
                "compose",
                "--env-file",
                str(ROOT / ".env"),
                "-f",
                str(ROOT / "infra/local/compose.yaml"),
                "ps",
                "-q",
                "postgres",
            ]
        )
        .decode()
        .strip()
    )
    if not result or "\n" in result:
        raise BackupFailure("local_postgres_not_running")
    return result


def _digest_file(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as source:
        while part := source.read(8 * 1024 * 1024):
            digest.update(part)
            size += len(part)
    return digest.hexdigest(), size


def _download(
    client: Any, bucket: str, key: str, path: Path, *, version: str | None = None
) -> tuple[str, int]:
    request: dict[str, str] = {"Bucket": bucket, "Key": key}
    if version is not None:
        request["VersionId"] = version
    body = client.get_object(**request)["Body"]
    digest = hashlib.sha256()
    size = 0
    try:
        with path.open("wb") as target:
            while part := body.read(8 * 1024 * 1024):
                target.write(part)
                digest.update(part)
                size += len(part)
    finally:
        body.close()
    return digest.hexdigest(), size


def _upload(client: Any, bucket: str, key: str, path: Path, digest: str) -> None:
    with path.open("rb") as source:
        client.upload_fileobj(
            source, bucket, key, ExtraArgs={"Metadata": {"verelo-sha256": digest}}
        )


def _write_status(*, success: bool, code: str, snapshot: str | None = None, count: int = 0) -> None:
    STATUS.parent.mkdir(parents=True, exist_ok=True)
    previous: dict[str, Any] = {}
    try:
        previous = json.loads(STATUS.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        pass
    now = datetime.now(UTC).isoformat()
    value = {
        "checked_at": now,
        "last_success_at": now if success else previous.get("last_success_at"),
        "state": "ok" if success else "failed",
        "code": code,
        "snapshot": snapshot if success else previous.get("snapshot"),
        "object_count": count if success else previous.get("object_count", 0),
    }
    temporary = STATUS.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, separators=(",", ":")), encoding="utf-8")
    temporary.replace(STATUS)


@contextmanager
def _lock() -> Iterator[None]:
    STATUS.parent.mkdir(parents=True, exist_ok=True)
    path = STATUS.parent / "backup.lock"
    with path.open("a+b") as handle:
        handle.seek(0)
        handle.write(b"0")
        handle.flush()
        handle.seek(0)
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)  # type: ignore[attr-defined]
        except OSError as error:
            raise BackupFailure("backup_already_running") from error
        try:
            yield
        finally:
            handle.seek(0)
            if os.name == "nt":
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)  # type: ignore[attr-defined]


def create_backup(settings: Settings) -> str:
    validate_settings(settings)
    source = _client(settings, backup=False)
    backup = _client(settings, backup=True)
    backup_bucket = _required(settings.b2_backup_bucket_name, "backup_bucket_missing")
    source_bucket = _required(settings.b2_bucket_name, "source_bucket_missing")
    snapshot = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:8]
    base = settings.b2_backup_key_prefix.strip("/") + "/local-release/" + snapshot
    container = _container()
    admin_url = _required(settings.local_admin_database_url, "admin_db_missing")
    parsed_url = make_url(admin_url)
    if (
        parsed_url.host not in {"127.0.0.1", "localhost"}
        or not parsed_url.username
        or not parsed_url.database
    ):
        raise BackupFailure("local_admin_database_required")
    engine = create_engine(admin_url, isolation_level="REPEATABLE READ")
    try:
        with tempfile.TemporaryDirectory(prefix="verelo-backup-") as directory:
            temporary = Path(directory)
            dump = temporary / "database.dump"
            with engine.connect() as connection:
                snapshot_id = str(
                    connection.execute(text("SELECT pg_export_snapshot()")).scalar_one()
                )
                objects = object_rows(connection.execute(text(OBJECT_QUERY)).all())
                with dump.open("wb") as output:
                    _run(
                        [
                            "docker",
                            "exec",
                            container,
                            "pg_dump",
                            "-U",
                            parsed_url.username,
                            "-d",
                            parsed_url.database,
                            "-Fc",
                            "--no-owner",
                            "--no-privileges",
                            f"--snapshot={snapshot_id}",
                        ],
                        output_file=output,
                    )
            db_sha, db_size = _digest_file(dump)
            db_key = base + "/database.dump"
            _upload(backup, backup_bucket, db_key, dump, db_sha)
            for index, item in enumerate(objects):
                key, version = decode_ref(item["ref"], source_bucket, settings.b2_key_prefix)
                payload = temporary / "object.bin"
                digest, size = _download(source, source_bucket, key, payload, version=version)
                if digest != item["sha256"] or (item["size"] is not None and size != item["size"]):
                    raise BackupFailure("source_object_integrity_failure")
                backup_key = f"{base}/objects/{index:08d}"
                _upload(backup, backup_bucket, backup_key, payload, digest)
                item["backup_key"] = backup_key
                item["size"] = size
                payload.unlink()
            manifest = {
                "format": 1,
                "snapshot": snapshot,
                "created_at": datetime.now(UTC).isoformat(),
                "database": {"key": db_key, "sha256": db_sha, "size": db_size},
                "objects": objects,
            }
            encoded = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
            backup.put_object(
                Bucket=backup_bucket,
                Key=base + "/manifest.json",
                Body=encoded,
                ContentType="application/json",
            )
            return base + "/manifest.json"
    finally:
        engine.dispose()


def verify_backup(settings: Settings, manifest_key: str) -> int:
    validate_settings(settings)
    backup = _client(settings, backup=True)
    bucket = _required(settings.b2_backup_bucket_name, "backup_bucket_missing")
    expected_prefix = settings.b2_backup_key_prefix.strip("/") + "/local-release/"
    if not manifest_key.startswith(expected_prefix) or not manifest_key.endswith("/manifest.json"):
        raise BackupFailure("invalid_manifest_key")
    raw = backup.get_object(Bucket=bucket, Key=manifest_key)["Body"].read()
    manifest = json.loads(raw)
    if manifest.get("format") != 1:
        raise BackupFailure("unsupported_manifest")
    entries = [manifest["database"], *manifest["objects"]]
    with tempfile.TemporaryDirectory(prefix="verelo-verify-") as directory:
        temporary = Path(directory)
        for index, entry in enumerate(entries):
            key = entry.get("key") if index == 0 else entry.get("backup_key")
            if not isinstance(key, str) or not key.startswith(
                manifest_key.removesuffix("manifest.json")
            ):
                raise BackupFailure("invalid_manifest_entry")
            path = temporary / ("database.dump" if index == 0 else "object.bin")
            digest, size = _download(backup, bucket, key, path)
            if digest != entry.get("sha256") or size != entry.get("size"):
                raise BackupFailure("backup_object_integrity_failure")
            if index:
                path.unlink()
        name = "verelo-verify-" + uuid4().hex[:12]
        try:
            _run(
                [
                    "docker",
                    "run",
                    "-d",
                    "--rm",
                    "--name",
                    name,
                    "-e",
                    "POSTGRES_PASSWORD=verelo_verify",
                    "-e",
                    "POSTGRES_DB=verelo_restored",
                    "pgvector/pgvector:0.8.1-pg17",
                ]
            )
            for _ in range(30):
                probe = subprocess.run(
                    [
                        "docker",
                        "exec",
                        name,
                        "pg_isready",
                        "-U",
                        "postgres",
                        "-d",
                        "verelo_restored",
                    ],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                )
                if probe.returncode == 0:
                    break
                import time

                time.sleep(1)
            else:
                raise BackupFailure("isolated_postgres_not_ready")
            _run(
                [
                    "docker",
                    "exec",
                    name,
                    "psql",
                    "-v",
                    "ON_ERROR_STOP=1",
                    "-U",
                    "postgres",
                    "-d",
                    "verelo_restored",
                    "-c",
                    (
                        "CREATE ROLE verelo_migrator; CREATE ROLE verelo_api; "
                        "CREATE ROLE verelo_worker;"
                    ),
                ]
            )
            with (temporary / "database.dump").open("rb") as source:
                _run(
                    [
                        "docker",
                        "exec",
                        "-i",
                        name,
                        "pg_restore",
                        "-U",
                        "postgres",
                        "-d",
                        "verelo_restored",
                        "--no-owner",
                        "--no-privileges",
                    ],
                    input_file=source,
                )
            revision = (
                _run(
                    [
                        "docker",
                        "exec",
                        name,
                        "psql",
                        "-At",
                        "-U",
                        "postgres",
                        "-d",
                        "verelo_restored",
                        "-c",
                        "SELECT version_num FROM alembic_version;",
                    ]
                )
                .decode()
                .strip()
            )
            if not revision:
                raise BackupFailure("restore_revision_missing")
            restored = (
                _run(
                    [
                        "docker",
                        "exec",
                        name,
                        "psql",
                        "-At",
                        "-U",
                        "postgres",
                        "-d",
                        "verelo_restored",
                        "-c",
                        "SELECT object_ref FROM capture_chunks "
                        "UNION SELECT object_ref FROM ingestion_chunks "
                        "UNION SELECT object_ref FROM source_assets "
                        "UNION SELECT raw_object_ref FROM raw_transcripts "
                        "UNION SELECT parsed_object_ref FROM raw_transcripts "
                        "UNION SELECT canonical_object_ref FROM transcript_versions;",
                    ]
                )
                .decode()
                .splitlines()
            )
            if set(restored) != {item["ref"] for item in manifest["objects"]}:
                raise BackupFailure("restore_reference_mismatch")
        finally:
            subprocess.run(
                ["docker", "rm", "-f", name],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
    return len(manifest["objects"])


def main() -> int:
    try:
        with _lock():
            settings = Settings()
            manifest_key = create_backup(settings)
            count = verify_backup(settings, manifest_key)
            _write_status(
                success=True, code="verified", snapshot=manifest_key.rsplit("/", 2)[-2], count=count
            )
            print(f"Local backup verified: {count} objects; isolated database restore passed.")
            return 0
    except Exception as error:
        code = error.code if isinstance(error, BackupFailure) else "backup_unexpected_failure"
        _write_status(success=False, code=code)
        print(f"Local backup failed: {code}. See docs/LOCAL_RELEASE.md.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
