# Phase 2 contract checkpoint — product-owner confirmation required

## Purpose

This is the mandatory Batch 0 checkpoint from
`004-phase-0-2-mvp-completion.md`. It records the verified gap ledger and proposes the exact public
workflow before generated HTTP contracts, migrations, routes, or live connectors change.

Status: **APPROVED — 2026-09-25**

Product-owner approval received in the implementation thread on 2026-09-25. This authorizes the
proposed HTTP contracts and migrations. It does not authorize live-provider activation or
confidential-data processing; the R1, provider smoke, and Gate C requirements remain in force.

## Baseline evidence

- Local PostgreSQL is healthy.
- `./scripts/pr-ready.sh` passed immediately before this checkpoint was prepared.
- `./scripts/backup-restore-smoke.sh` passed, including migration-to-head, database restore, and two
  authoritative-object hash checks.
- Current migration head is `0007_account_profiles`.
- Graph analysis was attempted first as required, but the repository index predates the Phase 2
  symbols and its Windows FTS runtime is unavailable. Direct source inspection confirmed the paths
  below.

## Phase 0–2 gap ledger

| Architecture item | Status | Evidence / remaining action |
| --- | --- | --- |
| Repository, toolchain, local PostgreSQL, CI gate | Implemented | Local PR gate and clean migrations pass. |
| Provider-neutral identity and local/test magic links | Implemented | Production Entra remains an external/configuration gate. |
| Project membership, authorization, RLS | Implemented | Extend restricted-role tests to every new ingestion entity/action. |
| Private object-storage abstraction | Partial | Immutable local adapter works; live private B2 adapter and evidence are absent. |
| Upload quarantine/source assets | Partial | Transcript parsing and minimal WAV checks exist; general chunked audio upload and decoder validation are absent. |
| Durable jobs/outbox | Partial | Persistence/lease/dispatch primitives exist; ingestion handlers and the worker host are not connected. |
| Electron capture application | Partial | UI/IPC state model exists; running app still uses the in-memory synthetic adapter. |
| Recall Desktop SDK | External gate | Synthetic adapter only; R1 is NOT RUN and blocks live connector implementation. |
| Original-audio storage | Partial | Synthetic WAV chunks can be assembled locally; production streaming/B2 path is absent. |
| Transcript/text import | Implemented at service/API level | Not exposed through the connected product workflow. |
| AssemblyAI adapter | External gate / partial | Synthetic lifecycle exists; live connector and account evidence are absent. |
| Immutable raw provider output | Partial | Synthetic adapter writes an object, but no durable coordinator connects it to database lineage. |
| Speaker/timestamp reconciliation | Implemented as a deterministic module | Not connected to a durable ingestion pipeline. |
| Cleanup adapter/validator | Partial | Deterministic policy-v2 exists; no durable draft/review lifecycle or model proposal adapter is connected. |
| Transcript approval | Partial | Approval row is created inside combined publication; no separate human review/hash-CAS operation. |
| Immutable publication | Implemented for direct transcript upload | Must be refactored behind the shared ingestion workflow. |
| Passage/index job generation | Implemented | Index jobs are generated; no active indexing handler is required until Phase 3 but job execution must be safe. |
| Recording recovery states | Partial | Domain/API persistence exists; Electron restart/reconciliation is not wired end to end. |
| Web ingestion/review/product UI | Missing | Current connected UI lists documents and memberships only. |
| End-to-end audio → transcript → publication | Missing | Components exist independently; no coordinator or product journey. |
| Backup/restore baseline | Implemented for synthetic database/objects | Production B2/backup/RPO/RTO approval remains external. |
| Operational observability | Partial | Content-free primitives exist; pipeline signals/readiness/alerts are incomplete. |

## Proposed locked MVP behavior

Approval of this checkpoint would authorize these implementation choices:

1. Audio upload formats are exactly WAV, MP3, M4A, and WebM, matching `PROJECT_SPEC.md` FR-05.
   “Any audio format” will not mean arbitrary codecs; unsupported formats fail safely. Provider output
   may add a format only after validation and a contract revision.
2. Transcript upload formats are UTF-8 TXT, VTT, SRT, and transcript JSON schema v1.
3. Initial limits are 2 GiB per audio file, four decoded hours per meeting, and 20 MiB per transcript,
   matching FR-06. Configuration may tighten but not silently exceed them.
4. Contributors and project owners may create documents and submit sources. Readers may only read
   authorized published results.
5. Deterministically valid policy-v2 cleanup may be service-approved automatically. Project owners
   may perform required human approval and publication. A separate reviewer capability is deferred;
   contributors cannot human-approve merely because they uploaded the source.
6. Manual correction is included because FR-09 is MVP-required. Each correction creates a new
   immutable draft/version and requires project-owner human approval.
7. Graph-delivered magic links remain local/test only. Confidential production uses Entra as required
   by ADR-005.
8. Zoom, Teams, browser calls, and other desktop-call sources use Recall's system-audio/Desktop SDK
   capture path after R1. Verelo will not add separate Zoom/Teams bot or OAuth connectors in Phase 2.
9. Uploaded recordings exported from Zoom, Teams, a browser, a phone, or another recorder are treated
   identically when their actual bytes validate as one of the supported formats.
10. Published transcript downloads are UTF-8 TXT, readable Markdown, and JSON provenance manifest,
    matching architecture §19. VTT/SRT remain supported input formats; generating new subtitle timing
    where timing is absent is prohibited.

## Proposed canonical state machine

`Ingestion.state` is one of:

```text
source_pending
quarantined
source_accepted
transcription_queued
transcription_submitted
transcription_processing
raw_transcript_stored
draft_ready
approval_required
approved
publishing
published
failed_retryable
failed_terminal
aborted
```

Rules:

- Transcript imports skip transcription only after quarantine and immutable preservation.
- Audio never reaches transcription before independent storage and quarantine acceptance.
- Recording completion creates/finalizes an ingestion; it does not imply transcription completion.
- Only `failed_retryable` can be retried by the public retry operation.
- Only the automatic policy service or project owner can create an approval.
- Only an approved exact hash can transition through `publishing` to `published`.
- `aborted`, `failed_terminal`, and `published` are terminal for that ingestion attempt.
- A correction creates a new immutable draft/version lineage rather than reopening published bytes.

## Proposed public operations

All paths use `/api/v1`. Every mutation requires the existing session, exact allowed Origin, and
session-bound CSRF token. Every operation reauthorizes current user/project/document state.

| Method and path | Operation ID | Purpose / authorization |
| --- | --- | --- |
| `POST /documents/{document_id}/ingestions` | `create_ingestion` | Contributor/owner creates a source intent with kind, filename, declared media type, byte length, SHA-256, and operation key. |
| `PUT /ingestions/{ingestion_id}/chunks/{sequence}` | `put_ingestion_chunk` | Creator or authorized contributor uploads the next bounded base64 chunk with its SHA-256. Duplicate same-hash chunk is idempotent. |
| `POST /ingestions/{ingestion_id}/finalize` | `finalize_ingestion` | Contributor/owner verifies total bytes/hash, seals original, quarantines, and schedules the next durable stage. |
| `GET /ingestions/{ingestion_id}` | `get_ingestion` | Project member reads safe stage/state, progress counters, retryability, gap count, and authorized action flags. No provider body/reference. |
| `GET /documents/{document_id}/ingestions` | `list_ingestions` | Project member lists authorized attempts for the document without source text or provider secrets. |
| `GET /ingestions/{ingestion_id}/draft` | `get_transcript_draft` | Project member reads parsed/draft segments, validation state, exact draft hash, revision, and approval requirement. |
| `PUT /ingestions/{ingestion_id}/draft` | `create_corrected_draft` | Project owner creates a new immutable corrected draft using expected revision/hash and a bounded reason code. |
| `POST /ingestions/{ingestion_id}/approvals` | `approve_transcript_draft` | Project owner approves an exact current draft hash/revision. Automatic service approval uses an internal service operation, not this employee route. |
| `POST /ingestions/{ingestion_id}/publication` | `publish_approved_transcript` | Project owner publishes the currently approved exact hash with idempotency and active-version compare-and-swap. |
| `POST /ingestions/{ingestion_id}/retry` | `retry_ingestion` | Contributor/owner schedules only the server-declared retryable stage using a new operation key. |
| `POST /ingestions/{ingestion_id}/abort` | `abort_ingestion` | Contributor/owner stops non-published work; governed stored artifacts remain subject to retention. |
| `GET /documents/{document_id}/transcript-publication` | `get_transcript_publication` | Existing authorized active canonical transcript read/reproduction. |
| `GET /documents/{document_id}/transcript-downloads/{format}` | `download_transcript` | Project member downloads `txt`, `md`, or `json` generated deterministically from the pinned published version. |
| `GET /source-assets/{source_asset_id}/content` | `stream_source_asset` | Authorized bounded/range source playback/download; object references remain private. |

Capture operations remain under `/capture-sessions`. `CaptureFinalize` will return the resulting
`source_asset_id` and `ingestion_id`; Electron then follows `GET /ingestions/{id}` like the web UI.

## Proposed request/response model outlines

### IngestionCreate

```text
source_kind: audio | transcript
filename: 1..500 characters
declared_media_type:
  audio/wav | audio/mpeg | audio/mp4 | audio/webm |
  text/plain | text/vtt | application/x-subrip | application/json
byte_length: positive integer within kind limit
sha256: 64 lowercase hexadecimal characters
operation_key: 16..200 characters
```

The server derives tenant/workspace/project/document/actor and never accepts them here.

### IngestionChunkPut

```text
sequence: positive integer equal to the path value
content_base64: bounded to a decoded 5 MiB maximum
sha256: decoded chunk SHA-256
```

### IngestionFinalize

```text
operation_key: 16..200 characters
expected_byte_length: positive integer
expected_sha256: 64 lowercase hexadecimal characters
```

### Ingestion

```text
ingestion_id
document_id
source_asset_id nullable
source_kind
state
stage: upload | quarantine | transcription | cleanup | approval | publication
uploaded_bytes
expected_bytes
acknowledged_chunks
gap_count
retryable
safe_error_code nullable
draft_revision nullable
draft_sha256 nullable
transcript_version_id nullable
can_upload / can_retry / can_abort / can_review / can_approve / can_publish
created_at / updated_at
```

No provider ID, object key, signed URL, raw error, transcript body, or credential appears here.

### TranscriptDraft

```text
ingestion_id
document_id
draft_id
revision
source_sha256
content_sha256
canonical_text
segments[]: exact text, nullable speaker, paired nullable start/end milliseconds
cleanup_policy_version
cleanup_status: unchanged | accepted | approval_required
edit_manifest[]: rule and source/destination character bounds; no invented explanation
approval nullable: approval ID, method, approved hash, approver display metadata, time
```

### CorrectedDraftPut

```text
canonical_text
expected_revision
expected_content_sha256
reason_code: transcription_correction | speaker_correction | formatting_correction | other_reviewed
```

The server constructs a new immutable draft, never updates the prior object.

### TranscriptApprovalCreate

```text
content_sha256
expected_revision
reason_code: reviewed_transcript | reviewed_with_audio | approved_correction
```

### TranscriptPublicationCreate

```text
approved_content_sha256
expected_draft_revision
expected_active_transcript_version_id nullable
operation_key
```

### TranscriptDownload

- `txt`: exact canonical UTF-8 bytes with LF endings.
- `md`: deterministic readable headings/segments; quoted transcript text is copied from canonical
  bytes without rewriting.
- `json`: versioned provenance manifest containing identifiers, hashes, approval metadata, speakers,
  nullable timestamps, and exact canonical text. It contains no provider credentials/object keys.

## Existing-operation migration

The current `POST /documents/{document_id}/transcript-publications` combined shortcut will be removed
from the public registry before Gate S because there are no external clients yet. Its parsing,
cleanup, approval, publication, passage, and hash-verification logic will be decomposed into the
shared services above. Tests must prove there is only one authoritative publication path.

## Live-provider boundary

Approval of this contract checkpoint does **not** approve a live connector. Implementation order
remains:

1. Complete Gate S with synthetic adapters.
2. Run Recall R1 with fictional audio and record PASS evidence.
3. Implement/pin the Recall connector only after R1 PASS.
4. Configure and smoke-test private B2 storage with fictional objects.
5. Configure and smoke-test AssemblyAI with fictional two-speaker audio.
6. Configure/test Entra and obtain organizational Gate C approval before confidential traffic.

## Product-owner confirmation requested

Approval should explicitly confirm:

- the supported input/output formats and limits above;
- contributor upload versus project-owner human approval/publication;
- manual correction in the MVP;
- replacement of the combined publication shortcut;
- Graph magic links remaining test-only and Entra remaining production identity;
- Recall Desktop SDK as the single live path for Zoom, Teams, browser, and computer-audio capture;
- authorization to publish the proposed HTTP contracts and migrations.

No live provider will be enabled by this approval; each provider still requires its own documented
credentials, administrator configuration, and feasibility/smoke gate.
