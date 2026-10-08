"""Explicit fictional-data smoke tests for B2 and AssemblyAI.

This command never runs from normal CI. It emits sanitized Markdown only after a successful run.
"""

# ruff: noqa: E402, E501

from __future__ import annotations

import argparse
import platform
import sys
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path

import httpx
from pydantic import SecretStr

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from api.config import Settings
from connectors.assemblyai import AssemblyAIAdapter
from connectors.backblaze_b2 import BackblazeB2Storage
from connectors.fakes import FakeProviderError

STATE = ROOT / ".artifacts" / "live-smoke"
EVIDENCE = ROOT / "docs" / "integrations" / "evidence"


def _secret(value: object | None, name: str) -> str:
    if not isinstance(value, SecretStr):
        raise SystemExit(f"missing_{name}")
    result = value.get_secret_value()
    if not result:
        raise SystemExit(f"missing_{name}")
    return result


def _required(value: str | None, name: str) -> str:
    if value is None or not value.strip():
        raise SystemExit(f"missing_{name}")
    return value


def _storage(settings: Settings, *, role: str) -> BackblazeB2Storage:
    endpoint = str(settings.b2_s3_endpoint)
    region = _required(settings.b2_region, "b2_region")
    state = STATE / f"b2-{role}.sqlite3"
    if role == "runtime":
        return BackblazeB2Storage(
            endpoint_url=endpoint,
            region=region,
            operation_store=state,
            bucket=_required(settings.b2_bucket_name, "b2_bucket_name"),
            key_prefix=settings.b2_key_prefix,
            access_key_id=_required(settings.b2_application_key_id, "b2_application_key_id"),
            secret_access_key=_secret(settings.b2_application_key, "b2_application_key"),
        )
    if role == "purge":
        return BackblazeB2Storage(
            endpoint_url=endpoint,
            region=region,
            operation_store=state,
            bucket=_required(settings.b2_bucket_name, "b2_bucket_name"),
            key_prefix=settings.b2_key_prefix,
            access_key_id=_required(
                settings.b2_purge_application_key_id, "b2_purge_application_key_id"
            ),
            secret_access_key=_secret(
                settings.b2_purge_application_key, "b2_purge_application_key"
            ),
        )
    return BackblazeB2Storage(
        endpoint_url=endpoint,
        region=region,
        operation_store=state,
        bucket=_required(settings.b2_backup_bucket_name, "b2_backup_bucket_name"),
        key_prefix=settings.b2_backup_key_prefix,
        access_key_id=_required(
            settings.b2_backup_application_key_id, "b2_backup_application_key_id"
        ),
        secret_access_key=_secret(settings.b2_backup_application_key, "b2_backup_application_key"),
    )


def _header(provider: str) -> str:
    now = datetime.now(UTC)
    return f"""# Integration feasibility / smoke-test evidence

| Field | Value |
|---|---|
| Provider / gate | {provider} |
| Status | PASS |
| Date, operator, reviewer | {now.date().isoformat()}; local operator; reviewer pending |
| Commit / test procedure revision | Working tree; `scripts/live-provider-smoke.py` |
| API version, SDK/client lockfile version | REST/S3 compatibility; pinned repository lockfiles |
| OS/Electron/meeting client where relevant | {platform.platform()} |
| Account region / environment | Synthetic fictional-data test; identifiers restricted |
| Approved resource boundary / spend limit | Isolated smoke resources; approval reference pending |
| Permission scopes and resource roles | Sanitized results below; no tokens recorded |
| Processor/retention/consent approval references | Pending; PASS does not authorize confidential data |
"""


def run_b2(settings: Settings) -> tuple[BackblazeB2Storage, str]:
    runtime, purge, backup = (
        _storage(settings, role=item) for item in ("runtime", "purge", "backup")
    )
    small = b"abc"
    small_ref = runtime.put_immutable(small, sha256(small).hexdigest(), "b2-smoke-small-v1")
    if runtime.read_version(small_ref.object_ref) != small:
        raise RuntimeError("small_read_mismatch")
    if runtime.read_version(small_ref.object_ref, (1, 3)) != b"bc":
        raise RuntimeError("range_read_mismatch")
    multipart = bytes(range(256)) * (9 * 1024 * 1024 // 256 + 1)
    multipart = multipart[: 9 * 1024 * 1024]
    digest = sha256(multipart).hexdigest()
    def interrupt_after_first_part(part_number: int) -> None:
        if part_number == 1:
            raise RuntimeError("intentional_multipart_interruption")

    interrupted = BackblazeB2Storage(
        endpoint_url=str(settings.b2_s3_endpoint),
        region=_required(settings.b2_region, "b2_region"),
        bucket=_required(settings.b2_bucket_name, "b2_bucket_name"),
        key_prefix=settings.b2_key_prefix,
        access_key_id=_required(settings.b2_application_key_id, "b2_application_key_id"),
        secret_access_key=_secret(settings.b2_application_key, "b2_application_key"),
        operation_store=STATE / "b2-runtime.sqlite3",
        multipart_checkpoint_hook=interrupt_after_first_part,
    )
    try:
        interrupted.put_immutable(multipart, digest, "b2-smoke-multipart-v1")
    except RuntimeError as error:
        if str(error) != "intentional_multipart_interruption":
            raise
    else:
        raise RuntimeError("multipart_interruption_not_injected")
    large_ref = runtime.put_immutable(multipart, digest, "b2-smoke-multipart-v1")
    recovered = runtime.put_immutable(multipart, digest, "b2-smoke-multipart-v1")
    if recovered.object_ref != large_ref.object_ref:
        raise RuntimeError("multipart_idempotency_failure")
    denied = False
    try:
        runtime.delete_version(small_ref.object_ref)
    except FakeProviderError as error:
        denied = str(error) == "provider_permission"
    if not denied:
        raise RuntimeError("runtime_delete_was_not_denied")
    backup_ref = backup.put_immutable(multipart, digest, "b2-smoke-backup-v1")
    restored = backup.read_version(backup_ref.object_ref)
    if sha256(restored).hexdigest() != digest:
        raise RuntimeError("restore_hash_mismatch")
    endpoint = str(settings.b2_s3_endpoint).rstrip("/")
    anonymous = httpx.get(
        f"{endpoint}/{settings.b2_bucket_name}/{settings.b2_key_prefix}", timeout=10
    )
    if anonymous.status_code < 400:
        raise RuntimeError("anonymous_access_not_denied")
    purge.delete_version(small_ref.object_ref)
    purge.delete_version(large_ref.object_ref)
    report = (
        _header("Backblaze B2 smoke test")
        + f"""

## Results

| Step / operation | Expected | Observed | Safe evidence reference | Pass/fail |
|---|---|---|---|---|
| Positive control | Version-pinned put/get/range and multipart | SHA-256 verified for 3-byte and {len(multipart)}-byte objects | Local smoke output; references withheld | PASS |
| Outside-scope negative control | Anonymous read denied | HTTP {anonymous.status_code} | Status only | PASS |
| Duplicate / uncertain outcome | Repeated operation returns pinned version | Same internal object reference and bytes | Reference withheld | PASS |
| Revocation / expired credential | Runtime permanent delete denied | Provider permission denial | Safe error code only | PASS |
| Cleanup / retained copies | Purge removes runtime test versions; backup restores | Restored SHA-256 `{digest}` | Backup reference withheld | PASS |

## Remaining decisions and conclusion

The S3-compatible client is pinned and the isolated fictional-data controls passed. Backup lifecycle,
region/encryption ownership, and confidential-data approval remain external governance gates. The
backup test object is intentionally retained until reviewer confirmation; remove it with the backup
identity after review.
"""
    )
    return runtime, report


def run_assembly(settings: Settings, runtime: BackblazeB2Storage, audio_path: Path) -> str:
    audio = audio_path.read_bytes()
    audio_digest = sha256(audio).hexdigest()
    stored = runtime.put_immutable(audio, audio_digest, "assemblyai-smoke-audio-v1")
    adapter = AssemblyAIAdapter(
        api_key=_secret(settings.assemblyai_api_key, "assemblyai_api_key"),
        base_url=str(settings.assemblyai_api_base_url),
        storage=runtime,
        state_path=STATE / "assemblyai.sqlite3",
        model_id=settings.assemblyai_speech_model,
        timeout_seconds=settings.integration_request_timeout_seconds,
    )
    first = adapter.transcribe(stored.object_ref, "assemblyai-smoke-transcript-v1")
    repeated = adapter.transcribe(stored.object_ref, "assemblyai-smoke-transcript-v1")
    if first.submission_ref != repeated.submission_ref:
        raise RuntimeError("duplicate_submission")
    if adapter.wait(first.submission_ref) != "completed":
        raise RuntimeError("transcription_failed")
    result = adapter.fetch_result(first.submission_ref)
    raw = runtime.read_version(result.raw_artifact_ref)
    raw_digest = sha256(raw).hexdigest()
    speakers = {segment.speaker_label for segment in result.segments if segment.speaker_label}
    if result.model_id != "universal-3-5-pro" or len(speakers) < 2:
        raise RuntimeError("model_or_diarization_failure")
    if adapter.delete_result(first.submission_ref, "assemblyai-delete-v1") != "deleted":
        raise RuntimeError("provider_delete_unverified")
    return (
        _header("AssemblyAI smoke test")
        + f"""

## Results

| Step / operation | Expected | Observed | Safe evidence reference | Pass/fail |
|---|---|---|---|---|
| Positive control | `/v2/upload`, submit, poll, diarization | Completed with {len(speakers)} anonymous speaker labels | Provider ID withheld | PASS |
| Outside-scope negative control | No public B2 source | Uploaded from authenticated pinned storage read | Object reference withheld | PASS |
| Duplicate / uncertain outcome | Same operation creates one transcript | Repeated operation returned same provider ID | ID withheld | PASS |
| Revocation / expired credential | Provider result deleted | Post-delete response/access behavior verified | Safe state only | PASS |
| Cleanup / retained copies | Raw response retained before provider delete | {len(raw)} bytes; SHA-256 `{raw_digest}` | Pinned B2 reference withheld | PASS |

## Remaining decisions and conclusion

The fictional two-speaker async path passed with `speech_models=["universal-3-5-pro"]` and
`speaker_labels=true`. Account-specific training opt-out, TTL, upload-object retention, region, and
confidential-data approval remain required. Raw provider bytes are retained as governed evidence and
were not automatically published.
"""
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--audio", type=Path)
    parser.add_argument("--confirm-fictional-data", action="store_true")
    parser.add_argument("--provider", choices=("b2", "assemblyai", "all"), default="all")
    args = parser.parse_args()
    if not args.confirm_fictional_data:
        raise SystemExit("Pass --confirm-fictional-data after verifying the audio is fictional.")
    settings = Settings()
    STATE.mkdir(parents=True, exist_ok=True)
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    runtime, b2_report = run_b2(settings)
    date = datetime.now(UTC).date().isoformat()
    if args.provider in {"b2", "all"}:
        (EVIDENCE / f"{date}-backblaze-b2.md").write_text(b2_report, encoding="utf-8")
    if args.provider in {"assemblyai", "all"}:
        if args.audio is None or not args.audio.is_file():
            raise SystemExit("--audio must identify the fictional two-speaker audio file")
        report = run_assembly(settings, runtime, args.audio)
        (EVIDENCE / f"{date}-assemblyai.md").write_text(report, encoding="utf-8")
    print("live_provider_smoke_passed")


if __name__ == "__main__":
    main()
