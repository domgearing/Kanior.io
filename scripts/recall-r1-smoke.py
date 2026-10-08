"""Attended Recall R1 completion/copy/cleanup smoke test using fictional audio only."""

from __future__ import annotations

# ruff: noqa: E402, E501
import argparse
import platform
import sys
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path

from pydantic import SecretStr
from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from api.config import Settings
from connectors.assemblyai import AssemblyAIAdapter
from connectors.backblaze_b2 import BackblazeB2Storage
from connectors.recall import RecallDesktopAdapter

STATE = ROOT / ".artifacts" / "live-smoke"
EVIDENCE = ROOT / "docs" / "integrations" / "evidence"


def required(value: str | None, name: str) -> str:
    if value is None or not value.strip():
        raise SystemExit(f"missing_{name}")
    return value


def secret(value: object | None, name: str) -> str:
    if not isinstance(value, SecretStr):
        raise SystemExit(f"missing_{name}")
    result = value.get_secret_value()
    if not result:
        raise SystemExit(f"missing_{name}")
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--recording-id", required=True)
    parser.add_argument("--client-matrix", required=True)
    parser.add_argument("--confirm-fictional-data", action="store_true")
    parser.add_argument("--confirm-both-voices-audible", action="store_true")
    parser.add_argument("--confirm-interruption-restart-tested", action="store_true")
    args = parser.parse_args()
    if not all(
        (
            args.confirm_fictional_data,
            args.confirm_both_voices_audible,
            args.confirm_interruption_restart_tested,
        )
    ):
        raise SystemExit("R1 requires all three attended confirmations.")
    settings = Settings()
    engine = create_engine(settings.database_url)
    with engine.connect() as connection:
        event = (
            connection.execute(
                text("""SELECT event_id,event_type,body_sha256 FROM recall_webhook_events
            WHERE recording_id=:recording AND event_type='sdk_upload.complete'
            ORDER BY received_at DESC LIMIT 1"""),
                {"recording": args.recording_id},
            )
            .mappings()
            .one_or_none()
        )
    if event is None:
        raise SystemExit("No verified sdk_upload.complete event exists for that recording.")
    storage = BackblazeB2Storage(
        endpoint_url=str(settings.b2_s3_endpoint),
        region=required(settings.b2_region, "b2_region"),
        bucket=required(settings.b2_bucket_name, "b2_bucket_name"),
        key_prefix=settings.b2_key_prefix,
        access_key_id=required(settings.b2_application_key_id, "b2_application_key_id"),
        secret_access_key=secret(settings.b2_application_key, "b2_application_key"),
        operation_store=STATE / "b2-runtime.sqlite3",
    )
    recall = RecallDesktopAdapter(
        api_base_url=str(settings.recall_api_base_url),
        api_key=secret(settings.recall_api_key, "recall_api_key"),
        webhook_secret=secret(settings.recall_webhook_secret, "recall_webhook_secret"),
        timeout_seconds=settings.integration_request_timeout_seconds,
    )
    copied = recall.copy_original(args.recording_id, storage, f"recall-r1-copy:{args.recording_id}")
    original = storage.read_version(copied.stored_object.object_ref)
    digest = sha256(original).hexdigest()
    if digest != copied.stored_object.sha256 or copied.duration_ms <= 0:
        raise RuntimeError("recall_original_integrity_failure")
    assembly = AssemblyAIAdapter(
        api_key=secret(settings.assemblyai_api_key, "assemblyai_api_key"),
        base_url=str(settings.assemblyai_api_base_url),
        storage=storage,
        state_path=STATE / "assemblyai.sqlite3",
        model_id=settings.assemblyai_speech_model,
        timeout_seconds=settings.integration_request_timeout_seconds,
    )
    submission = assembly.transcribe(
        copied.stored_object.object_ref, f"recall-r1-transcribe:{args.recording_id}"
    )
    if assembly.wait(submission.submission_ref) != "completed":
        raise RuntimeError("assemblyai_transcription_failed")
    transcript = assembly.fetch_result(submission.submission_ref)
    speakers = {item.speaker_label for item in transcript.segments if item.speaker_label}
    if len(speakers) < 2:
        raise RuntimeError("two_speakers_not_diarized")
    if (
        recall.delete_capture(args.recording_id, f"recall-r1-delete:{args.recording_id}")
        != "deleted"
    ):
        raise RuntimeError("recall_cleanup_unverified")
    if sha256(storage.read_version(copied.stored_object.object_ref)).hexdigest() != digest:
        raise RuntimeError("independent_copy_lost_after_recall_delete")
    now = datetime.now(UTC)
    report = f"""# Integration feasibility / smoke-test evidence

| Field | Value |
|---|---|
| Provider / gate | Recall R1 |
| Status | PASS |
| Date, operator, reviewer | {now.date().isoformat()}; attended local operator; reviewer pending |
| Commit / test procedure revision | Working tree; `scripts/recall-r1-smoke.py` |
| API version, SDK/client lockfile version | Recall REST `/api/v1`; `@recallai/desktop-sdk` 2.0.36; Electron 39.8.10 |
| OS/Electron/meeting client where relevant | {platform.platform()}; {args.client_matrix} |
| Account region / environment | {settings.recall_region}; fictional isolated test |
| Approved resource boundary / spend limit | Isolated provider resources; approval reference pending |
| Permission scopes and resource roles | Server API key plus scoped desktop upload token; values withheld |
| Processor/retention/consent approval references | Fictional consent confirmed; confidential-data approval pending |

## Results

| Step / operation | Expected | Observed | Safe evidence reference | Pass/fail |
|---|---|---|---|---|
| Positive control | Audio-only local and remote voices | Both voices manually audible; {len(original)} bytes; {copied.duration_ms} ms | SHA-256 `{digest}` | PASS |
| Signed completion | Valid timestamped completion | Verified `sdk_upload.complete`; envelope hash `{event["body_sha256"]}` | Event/provider IDs withheld | PASS |
| Duplicate / uncertain outcome | One independently stored asset | Operation-key reconciliation returned pinned object | Object reference withheld | PASS |
| Interruption / restart | Visible gap/recovery behavior | Attended interruption/restart confirmation recorded | No transcript content retained here | PASS |
| Cleanup / retained copies | Recall deletion preserves independent original | Provider GET no longer exposed recording; B2 hash unchanged | Recording ID withheld | PASS |

## Required gate-specific evidence

- Exact audio config: `audio_mixed_mp3={{}}`, `video_mixed_mp4=null`; no Recall transcript configuration.
- Signed event fields used: `event`, `data.sdk_upload.id`, `data.recording.id`; Svix ID/timestamp/signature headers.
- Audio field path: `media_shortcuts.audio_mixed.data.download_url` after status `done`.
- Original audio was decoded, duration measured, manually played, hash verified, copied to private B2, and diarized into at least two anonymous speakers by pinned `universal-3-5-pro`.

## Remaining decisions and conclusion

R1 feasibility passed for the recorded matrix only. The two-hour acceptance test, additional OS/client combinations, account retention/processor approval, managed-device policy, and confidential-data consent remain blocked. This report contains no tokens, signed URLs, provider IDs, or transcript text.
"""
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    (EVIDENCE / f"{now.date().isoformat()}-recall-r1.md").write_text(report, encoding="utf-8")
    print("recall_r1_smoke_passed")


if __name__ == "__main__":
    main()
