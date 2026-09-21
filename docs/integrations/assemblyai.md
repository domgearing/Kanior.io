# AssemblyAI

Documentation verified: **2026-09-16**. Live smoke test: **NOT RUN**. Authority: architecture §§4, 10–12 and [shared integration rules](../INTEGRATIONS.md).

## API, operations and official references

Selected: REST `/v2`; async model explicitly `speech_models: ["universal-3-5-pro"]`, with diarization. The [official pre-recorded model announcement](https://www.assemblyai.com/blog/universal-3-5-pro-code-switching-contextual-prompting) confirms that exact identifier. Do not omit it to follow the provider default, or add a fallback model without approval. No Python SDK is required by this contract; if adopted, pin it before implementation.

Use [upload](https://www.assemblyai.com/docs/pre-recorded-audio/api-reference/files/upload) `POST /v2/upload`, [submit](https://www.assemblyai.com/docs/pre-recorded-audio/api-reference/transcripts/submit) `POST /v2/transcript`, poll `GET /v2/transcript/{id}`, persist complete raw result, then [delete](https://www.assemblyai.com/docs/pre-recorded-audio/delete-transcripts) `DELETE /v2/transcript/{id}` under policy. Set `speaker_labels=true`; preserve word/utterance timing and anonymous labels. No provider-generated summaries, redaction or translation replace source text.

## Authentication, permissions and environment

API key in `Authorization` header, server worker only. Initial handoff uploads bytes from independently verified private storage to AssemblyAI, then uses its upload handle for submission; do not expose B2 publicly. Regional endpoint/account/model availability must be checked together.

| Name | Kind / setup |
|---|---|
| `ASSEMBLYAI_API_KEY` | Secret; approved isolated account |
| `ASSEMBLYAI_API_BASE_URL` | Config; approved region, not caller-controlled |
| `ASSEMBLYAI_SPEECH_MODEL` | Config; fixed `universal-3-5-pro` |
| `ASSEMBLYAI_MAX_CONCURRENT_JOBS` | Config; set below verified account limit |

## Provider-neutral adapter and synthetic response

```text
TranscriptionProvider.transcribe(authorized_audio_handle, options, operation_key) -> Submission
TranscriptionProvider.get_status(submission_ref) -> ProcessingStatus
TranscriptionProvider.fetch_result(submission_ref) -> RawTranscriptResult
TranscriptionProvider.delete_result(submission_ref, operation_key) -> CleanupResult
```

```json
{"state":"completed","segments":[{"text":"We said fifteen, not fifty.","speaker_label":"A","start_ms":0,"end_ms":1800}],"model_id":"universal-3-5-pro","raw_artifact_ref":"synthetic-raw-result-1"}
```

Submission is asynchronous; adapter-neutral states are queued/processing/completed/failed. Internal immutable storage contains the actual raw provider bytes, hash and provider/config provenance. Missing speaker/confidence/timing remains null; this result is not an approved canonical transcript.

## Reliability and data lifecycle

Use shared metadata/transfer defaults. Poll with durable scheduling, initially every 5 seconds then back off to 30 seconds; an HTTP deadline is not a whole-job STT timeout. Track queue age separately and escalate the spec's processing-target breach. Persist provider ID before subsequent polling. Unknown submission outcome does not authorize a duplicate paid transcript; use reconciliation/operator recovery. GET/delete retries follow known state; 429 respects retry guidance, 401/403 stops for configuration, invalid audio is terminal, provider error text is sanitized.

External data includes required audio, locale/options and provider-produced transcript. Raw provider response must be stored and verified before cleanup. The [retention/training policy](https://www.assemblyai.com/docs/data-retention-and-model-training) distinguishes asynchronous storage, TTL and training controls; do not apply streaming zero-retention statements to this async pipeline. Require account-specific training opt-out evidence, approved processor/region, configured TTL, and deletion coverage for uploads plus results. Handle abandoned uploads and failed jobs as cleanup work too. No assumed zero retention or instant erasure of all copies.

## Fake behavior and live smoke procedure

Fake: queued→processing→completed, anonymous/unknown speakers, overlapping/missing times, provider errors, 429, uncertain submission, crash after provider acceptance, and failed deletion. Preserve fixture raw bytes separately; never invent confidence.

Live: upload a short two-speaker fictional recording from private storage; submit the exact pinned model with diarization; record safe model/status fields and timestamps; persist/re-read raw bytes and hashes; confirm no auto-publication; delete the provider result and verify documented response/access behavior. Record uploaded-file cleanup and orphan handling separately. Re-run a known operation through the app to prove it doesn't create a second submission. Fault-inject throttling locally rather than saturating the service. OPEN: account region/model access, training opt-out, TTL/deletion terms, quotas, maximum supported input tested against the app's file/duration limits.
