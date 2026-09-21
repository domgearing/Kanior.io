# Recall Desktop Recording SDK

Documentation verified: **2026-09-16**. Live smoke test / **R1 gate: NOT RUN**. Authority: architecture §17. Production connector implementation depends on R1; isolated feasibility code is permitted.

## API, operations and official references

Selected: Recall REST `/api/v1` and `@recallai/desktop-sdk` in Electron. Exact stable SDK/Electron/OS versions are OPEN until the R1 build is pinned and tested; no nightly/floating dependency is approved. [Desktop lifecycle](https://docs.recall.ai/docs/desktop-sdk) documents server-created SDK uploads, desktop upload tokens and completion. [Audio-only configuration](https://docs.recall.ai/docs/audio-only) documents `recording_config.audio_mixed_mp3 = {}` with `video_mixed_mp4 = null`; platform permissions differ.

Use `POST /api/v1/sdk_upload/`, SDK recording controls, signed completion/failure webhooks, and [Retrieve Recording](https://docs.recall.ai/reference/recording_retrieve). Download the completed audio media object, preserve original bytes independently, verify SHA-256 and decoded duration, then allow AssemblyAI submission. Do not enable Recall transcription, bot APIs or video capture as an implicit fallback. [Media objects](https://docs.recall.ai/docs/recordings-and-media) describe provider artifact references; [SDK FAQ](https://docs.recall.ai/docs/desktop-recording-sdk-faq) governs recovery/platform limitations.

The [webhook reference](https://docs.recall.ai/docs/desktop-recording-sdk-webhooks) shows `event=sdk_upload.complete`, recording ID at `data.recording.id` and upload ID at `data.sdk_upload.id`. Use that shape as the test candidate, not the overview's informal `recording_id` wording. Exact audio shortcut/media fields must be captured and verified in R1; do not assume the video's example path works for audio.

## Authentication, permissions and environment

Server-only workspace API key, region-matched base URL; use the endpoint reference's `Authorization: Token …` form and confirm in R1. Desktop receives only the scoped upload credential after app authorization. Verify Svix-signed raw webhook bodies with workspace signing secret, timestamp tolerance and event deduplication; pin the verifier at implementation.

| Name | Kind / setup |
|---|---|
| `RECALL_API_BASE_URL` | Config; approved workspace region, allowlisted server-side |
| `RECALL_API_KEY` | Secret; isolated workspace key |
| `RECALL_WEBHOOK_SECRET` | Secret; workspace webhook verification secret |
| `RECALL_WEBHOOK_URL` | Config; HTTPS callback subscribed to upload completion/failure |
| `RECALL_CAPTURE_MODE` | Config; `audio_only`; verify OS permissions in packaged app |

## Provider-neutral adapter and synthetic response

```text
CaptureProvider.create_session(scope, capture_session_id, operation_key) -> CaptureGrant
CaptureProvider.verify_notification(raw_body, headers) -> CaptureEvent
CaptureProvider.resolve_media(provider_recording_ref) -> PrivateMediaHandle
CaptureProvider.copy_original(media_handle, storage_sink, operation_key) -> StoredCapture
CaptureProvider.delete_capture(provider_recording_ref, operation_key) -> CleanupResult
```

```json
{"capture_session_id":"10000000-0000-4000-8000-000000000010","state":"original_stored","source_asset_id":"10000000-0000-4000-8000-000000000011","duration_ms":60000,"gap_count":0,"audio_provenance":"provider_original"}
```

The storage result also carries computed SHA-256 and byte length. Private media/upload handles never serialize URLs/tokens into public responses or logs. SDK completion alone is not `original_stored`.

## Reliability, data and open approvals

Apply shared metadata/transfer deadlines; capture may run for the configured meeting limit and is not bounded by a 30-second request timer. Duplicate/reordered webhooks schedule one copy by capture/recording identity. After uncertain upload creation, reconcile the persisted intent; don't silently create another session. Refresh an expired download handle through authenticated metadata, revalidate source identity, and resume/restart safely. Never forward Recall Authorization headers to an arbitrary download host. Invalid signatures are rejected; missing audio is `provider_invalid_response`; actual interruptions remain visible gaps.

Recall receives recorded audio and meeting/participant activity metadata. OPEN: approved workspace region/processors, actual artifact TTL, deletion endpoint and its coverage for Desktop-created recordings, local SDK buffer cleanup, offline/restart behavior, and retention terms. Do not borrow a bot retention promise for Desktop SDK artifacts. Keep cleanup pending until evidence exists; independent B2 bytes must survive provider deletion. Company consent and managed-device approvals precede confidential recording.

## Fake behavior and R1 live smoke procedure

Fake: deterministic upload lifecycle, signed/invalid/replayed notifications, delayed media readiness, expired URL, partial transfer, wrong hash, missing remote track and duplicate events. No network or real OS capture in normal CI.

Live R1 (capture engineer + IT, synthetic scripted audio only):

1. Pin exact SDK/Electron build and record target Windows/macOS version plus meeting client. Prove local and remote scripted voices are audible in audio-only mode; test only supported combinations and list unsupported ones.
2. Create authorized upload, capture a one-minute call, stop, verify signed `sdk_upload.complete`, and record sanitized envelope shape. Prove no Recall transcript/video service was enabled.
3. Follow recording-to-audio references. Record exact field path, MIME/container, expiration behavior and any readiness polling required. Copy bytes to private storage; hash/read back, decode, measure duration and inspect both voices. Preserve original MP3 rather than call a re-encoded derivative original.
4. Submit only after durable-copy verification to AssemblyAI, or leave STT explicitly untested if its account is unavailable. Disconnect/restart/duplicate callback and verify visible incomplete/gap states and no duplicate asset. The two-hour acceptance test remains a later gate.
5. Exercise documented deletion for this artifact type, confirm coverage/retention with account settings, and prove independent storage remains readable. Delete only recorded synthetic resources after the test.

PASS requires a reproducible handoff with pinned versions, verified callback, independently playable/hash-verified audio and documented recovery/cleanup behavior. Unknown audio field, missing remote speech, unauthenticated callback, or unverified independent copy blocks connector implementation. Record remaining provider retention approvals separately; R1 PASS never authorizes confidential traffic.
