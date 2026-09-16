# Secure Transcript Intelligence Platform - Architecture & Build Plan

**Implementation baseline:** PROJECT_SPEC.md v1.2, 16 September 2026  
**Role of this document:** Technical source of truth for architecture, module boundaries, implementation choices, build order, security invariants, and acceptance gates.

---

## 1. Purpose

Build an internal, company-only transcript intelligence platform that can:

- record or import confidential research calls and internal meetings,
- preserve original source artifacts and provenance,
- produce readable timestamped transcripts,
- approve and publish immutable transcript versions as canonical evidence,
- search authorized transcripts by exact phrase and semantic meaning,
- answer questions using authorized source evidence,
- guarantee that user-visible quotations are exact stored source spans,
- link each quote to its approved transcript version, source, speaker, and timestamp where available,
- export published transcript artifacts to an approved company OneDrive destination,
- later support bookmarks, timestamped notes, collaboration, granular governance, and production-scale operations.

The platform must remain useful when the answer-generation model is unavailable. Keyword search, transcript viewing, and deterministic quote rendering are core application functions, not AI-dependent features.

---

## 2. Source-of-Truth Hierarchy

When project documents conflict, use this hierarchy:

1. `AGENTS.md` - coding-agent operating rules and handoff behavior.
2. `ARCHITECTURE.md` - authoritative technical architecture and build order.
3. `PROJECT_SPEC.md` - detailed engineering/product requirements and acceptance criteria.
4. ADRs under `docs/decisions/` - approved changes to architecture.
5. Machine-readable contracts and schemas - executable interface definitions.
6. Active implementation plan - scope of the current coding task.

If an implementation task conflicts with this architecture:

- do not silently improvise,
- document the conflict,
- create or update an ADR when the design choice is material,
- update this document when the approved architecture changes.

`PROJECT_SPEC.md` v1.2 is the implementation baseline used by this revision of `ARCHITECTURE.md`.

---

# 3. Non-Negotiable Architectural Invariants

## 3.1 Approved transcript text is the source of truth

The system preserves distinct artifacts:

```text
Original recording / imported file
        ↓
Raw provider output or raw imported transcript
        ↓
Parsed transcript
        ↓
Cleaned / corrected draft
        ↓
Approval bound to exact content hash
        ↓
Published immutable canonical transcript version
```

Only an approved, published transcript version may become normal searchable evidence.

Human audio review is optional. Approval does not imply that a person listened to every word.

The quote guarantee is:

> A verified quote is exactly equal to a contiguous span of the approved, published transcript version from which it is rendered.

Audio may be retained for provenance, replay, correction, compliance, or investigation, but the application does not need to compare a rendered quote against the audio before displaying it.

---

## 3.2 LLMs never author authoritative quote text

The system is divided into three evidence systems:

```text
Retriever
    ↓
Evidence Selector
    ↓
Deterministic Quote Renderer
```

The Retriever returns authorized passage references.

The Evidence Selector may return:

```text
passage_id
```

or, in a separately validated precise-span mode:

```text
passage_id
start_character
end_character
```

It must not return authoritative quote text.

Only deterministic application code may construct a user-visible verified quotation.

---

## 3.3 Authorization precedes retrieval

Never search globally and remove unauthorized results afterward.

The eligible retrieval set must first be restricted by current:

```text
tenant
workspace
project
document restrictions
published-version state
approval state
retention state
user permissions
```

Only then may keyword or vector ranking occur.

Unauthorized results, counts, scores, snippets, and metadata must not leak through retrieval behavior.

---

## 3.4 Authorization is repeated at quote delivery

A selected passage ID, source span ID, guessed identifier, stale candidate set, or previously saved answer never grants access.

The renderer must independently re-check current authorization and approval before every delivery or export of quote content.

---

## 3.5 Canonical transcript versions are immutable

Do not silently overwrite an approved transcript.

Corrections create a new version:

```text
Published v1
    ↓
Correction draft
    ↓
Approval for exact v2 hash
    ↓
Published v2
```

Historical citations may remain pinned to v1 for auditability while normal search defaults to the active published version.

---

## 3.6 OneDrive is an export destination, not the operational database

The application keeps its own authoritative operational state for:

- projects and permissions,
- source assets,
- raw transcript artifacts,
- transcript versions and approvals,
- passages and indexes,
- evidence runs and source spans,
- annotations,
- jobs and audit state,
- export state.

OneDrive receives versioned exports of published artifacts.

---

## 3.7 Live text is provisional

Live transcription, if added, is never permanent source truth.

Bookmarks and notes bind to the recording timeline rather than provisional transcript wording.

After post-meeting processing, timestamps are mapped to the approved published transcript.

---

## 3.8 Confidential content stays out of ordinary telemetry

Do not place the following in standard application logs, traces, metrics, or error events:

- raw audio,
- raw or canonical transcript text,
- note bodies,
- model responses containing confidential evidence,
- full prompts containing confidential evidence,
- query text unless an explicitly approved diagnostic policy allows it,
- access tokens,
- signed URLs.

Operational telemetry should use identifiers, durations, counts, state, and safe error codes.

---

# 4. Implementation Architecture

Use a modular monolith initially.

A module boundary is a code, contract, and authorization boundary. It does not require a separate network service.

The baseline implementation choices are:

| Concern | MVP implementation | Production evolution |
|---|---|---|
| Web UI | React + TypeScript with Vite | Same UI with live updates |
| Desktop capture | Electron + Recall.ai Desktop Recording SDK | Same capture adapter with signed updates and tested recovery |
| API | Python FastAPI | Scale stateless API replicas independently |
| Validation/contracts | Pydantic | Generated/public contract artifacts remain versioned |
| ORM/migrations | SQLAlchemy + Alembic | Same migration discipline |
| Worker | Python worker | Durable workflow activities behind the same domain contracts |
| MVP jobs | Durable PostgreSQL `jobs` table with leases, retry schedule, idempotency, and transactional outbox | Azure Durable Functions + Service Bus where justified |
| Database/search | PostgreSQL + full-text search + pgvector | Managed PostgreSQL when required |
| Authoritative object storage | Private Backblaze B2 | Private Azure Blob Storage is the managed alternative |
| Budget hosting | One small DigitalOcean VM for web/API/worker plus managed/external dependencies | Azure Container Apps with separate worker pools is the managed alternative |
| Identity | Single-tenant Microsoft Entra ID, authorization-code flow with PKCE, server-side session | Managed employee lifecycle/access review integration |
| Speech recognition | AssemblyAI Universal-3.5 Pro, pinned `universal-3-5-pro`, post-meeting, with diarization | Same provider contract with versioned speaker reconciliation and correction |
| Transcript cleanup | Approved GPT adapter proposing narrowly permitted formatting edits | Same contract with versioned prompts/validators and regression evaluation |
| Evidence selection / synthesis | Approved GPT deployment through an application adapter | Pin model/config versions and evaluate before upgrades |
| Embeddings | Approved embedding deployment; embeddings stored in PostgreSQL/pgvector | Re-index by generation when model changes |
| Microsoft 365 | Microsoft Graph with service-owned export identity and allowlisted destination | Reconciliation and stricter governance |
| Secrets | Server-side restricted secrets; no provider credentials in browser or desktop bundle | Managed vault/workload identities |
| Monitoring | Structured metadata logs and health checks | OpenTelemetry, dashboards, alerts, SLOs |
| Delivery | Containers, migrations, tests, infrastructure as code | Staged rollout, rollback drills, supply-chain controls |
| System-wide hotkeys | Not required for initial MVP | Signed Windows companion; browser foreground shortcut remains available |

Do not silently replace these baseline choices. A material replacement requires an ADR.

Provider, model, runtime, and API versions must be pinned in repository configuration. Do not use unversioned `latest` model identifiers for production behavior.

---

# 5. Repository Structure

The baseline repository should evolve toward:

```text
/
├── AGENTS.md
├── README.md
├── ARCHITECTURE.md
├── PROJECT_SPEC.md
│
├── web/
│   └── React + TypeScript + Vite application
│
├── desktop/
│   └── Electron / Recall desktop capture application
│
├── api/
│   └── FastAPI HTTP application
│
├── workers/
│   └── background job execution
│
├── domain/
│   ├── identity/
│   ├── authorization/
│   ├── ingestion/
│   ├── transcripts/
│   ├── transcript_approval/
│   ├── indexing/
│   ├── retriever/
│   ├── evidence_selector/
│   ├── quote_renderer/
│   ├── annotations/
│   ├── exports/
│   ├── policies/
│   └── audit/
│
├── connectors/
│   ├── recall/
│   ├── assemblyai/
│   ├── openai/
│   ├── microsoft_graph/
│   └── object_storage/
│
├── migrations/
│   └── Alembic migrations
│
├── schemas/
│   ├── openapi/
│   ├── events/
│   ├── imports/
│   └── ai/
│
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── contract/
│   ├── architecture/
│   ├── e2e/
│   └── fixtures/
│
├── evals/
│   ├── datasets/
│   ├── expected/
│   └── results/
│
├── infra/
│   ├── local/
│   └── environments/
│
├── runbooks/
│
├── docs/
│   ├── DATA_MODEL.md
│   ├── API_CONTRACTS.md
│   ├── SECURITY.md
│   ├── EVALS.md
│   ├── decisions/
│   └── plans/
│       ├── active/
│       └── completed/
│
├── scripts/
│
└── .github/
    └── workflows/
```

Frontend code must not duplicate authorization logic or construct verified quote text independently.

Generated/shared API types should be derived from documented contracts rather than redefined separately across clients.

---

# 6. Runtime Architecture

## 6.1 MVP runtime

```text
Employee web / Electron client
          │
          ├──── Microsoft Entra ID
          │
          ├──── Recall Desktop SDK
          │
          ▼
     FastAPI application
          │
          ├──── PostgreSQL
          │       ├─ identity / permissions
          │       ├─ transcript metadata
          │       ├─ approvals
          │       ├─ jobs / outbox
          │       ├─ full-text index
          │       └─ pgvector embeddings
          │
          ├──── Private object storage (Backblaze B2 baseline)
          │       ├─ original assets
          │       ├─ raw provider outputs
          │       ├─ transcript versions
          │       └─ export artifacts
          │
          └──── Python worker
                  ├─ AssemblyAI
                  ├─ approved GPT / embeddings
                  └─ Microsoft Graph
```

Deploy one API and one worker from one repository, one PostgreSQL database, one authoritative object store, and a separate recovery/backup location.

MVP does not require:

- Redis,
- Kubernetes,
- a dedicated vector database,
- an event-streaming platform,
- a meeting bot.

Queued work must survive process restarts through PostgreSQL-backed durable job state.

---

## 6.2 Production runtime

Production may evolve to:

```text
Web / Electron clients
        │
        ▼
API + authorization
        │
        ├──── PostgreSQL
        ├──── private object storage
        ├──── authenticated live gateway
        │
        └──── transactional outbox
                  │
                  ▼
             Service Bus
                  │
                  ▼
        Durable workflow orchestration
             ├─ media/STT workers
             ├─ indexing workers
             ├─ export workers
             └─ governance workers
```

Durable orchestration must carry identifiers and safe metadata, not transcript bodies, audio, access tokens, or signed URLs in replayable orchestration state.

Do not split permission, evidence, and version metadata into separate databases merely to create microservices.

---

# 7. Stable Module Boundaries

Modules depend on contracts, not another module's implementation internals.

Core responsibilities:

| Module | Responsibility |
|---|---|
| Identity/session | Validate Entra authentication and establish server session |
| Authorization | Evaluate current resource/action permission |
| Capture/upload | Accept and validate recording/upload assets |
| Import parser | Parse TXT/VTT/SRT/JSON into stable segments |
| Speech adapter | Call AssemblyAI and preserve raw provider output/timing |
| Transcript cleanup | Produce only validated, policy-allowed cleanup edits |
| Transcript approval | Bind approval/revocation to an exact draft content hash |
| Version publisher | Publish immutable approved transcript version and active pointer |
| Indexer | Build lexical and embedding indexes by version/generation |
| Retriever | Return ranked authorized passage references only |
| Evidence loader | Reauthorize and load candidate text for model context |
| Evidence selector | Select allowed passage IDs or validated subspans |
| Quote renderer | Reauthorize, integrity-check, and return exact source span |
| Analysis composer | Produce paraphrase/analysis only from rendered evidence |
| Annotation service | Persist bookmarks/notes and revision history |
| Export connector | Export published versions and reconcile destination state |
| Governance | Retention, holds, deletion, access-review workflows |
| Audit | Persist content-free security and governance events |
| Operations | Jobs, retries, dead-letter handling, metrics, recovery |

Stable conceptual interfaces include:

```text
AuthorizationService.authorize(...)
CaptureService.finalize(...)
TranscriptParser.parse(...)
TranscriptionProvider.transcribe(...)
TranscriptCleaningService.propose_edits(...)
TranscriptApprovalService.approve(...)
TranscriptPublisher.publish(...)
RetrievalService.search_passages(...)
EvidenceSelector.select(...)
QuoteRenderer.render(...)
AnalysisComposer.compose(...)
AnnotationService.create(...)
ExportService.export(...)
AuditService.record(...)
```

Domain modules must not call external provider APIs directly. Provider access belongs behind connector/adaptor boundaries.

The quote renderer must not import or call an LLM client.

The evidence selector must not mutate transcript/source records.

The retriever must not construct verified quote text.

---

# 8. Core Identifiers and Scope

Implementation contracts should use one consistent naming scheme.

Canonical scope identifiers:

```text
tenant_id
workspace_id
user_id
project_id
document_id
transcript_version_id
passage_id
source_span_id
```

Supporting identifiers include:

```text
project_membership_id
capture_session_id
source_asset_id
raw_transcript_id
transcript_approval_id
speaker_id
annotation_id
evidence_run_id
candidate_id
saved_answer_id
job_id
outbox_event_id
export_destination_id
export_manifest_id
audit_event_id
```

Use opaque globally unique identifiers such as UUIDs.

Legacy terms from earlier documents map conceptually as follows:

```text
organization_id -> tenant scope
meeting_id      -> document_id
source_id       -> document/source scope
```

New implementation contracts should not mix multiple names for the same concept.

Every project-owned resource must be traceable through enforced parent scope.

---

# 9. Canonical Data Model

The exact schema belongs in `docs/DATA_MODEL.md` and Alembic migrations. At architecture level, the required entities are:

```text
tenants
workspaces
users
projects
project_memberships

documents
capture_sessions
capture_chunks
source_assets

raw_transcripts
transcript_versions
transcript_approvals
speakers
passages
word_alignments
passage_indexes

evidence_runs
evidence_candidates
source_spans
saved_answers
quote_collections
collection_items

annotations
annotation_revisions

jobs
outbox_events

export_destinations
export_manifests

audit_events
retention_policies
holds
deletion_requests
```

## 9.1 Scope enforcement

Searchable passages, index records, evidence candidates, and source spans must carry or enforce the full parent scope required to prevent cross-project references.

Use foreign keys, unique constraints, and PostgreSQL Row-Level Security as defense in depth.

Runtime roles must not own protected tables, be database superusers, or have `BYPASSRLS`.

Migration credentials are separate from runtime credentials.

---

## 9.2 Transcript version contract

A transcript version contains or references:

```text
version identity
parent version
raw transcript lineage
canonical immutable object reference
content SHA-256
byte length
cleanup model / prompt / validator versions
cleanup status
correction manifest
approval reference
publication state
created_by / created_at
published_at
```

Approval records contain:

```text
transcript_version_id
approved content SHA-256
approval method
policy version
approver service or user
timestamp
reason / review metadata
```

Approval is hash-bound. Approval of one content hash cannot authorize a changed transcript.

---

## 9.3 Passage contract

Published passages are immutable source spans of one published transcript version.

Canonical transcript offsets use:

```text
zero-based UTF-8 byte offsets
start inclusive
end exclusive
```

Passages retain:

```text
passage_id
transcript_version_id
ordinal
start_byte
end_byte
span_hash
speaker_id nullable
start_ms nullable
end_ms nullable
timing_precision
```

Browser UTF-16 string indexes must never be treated as canonical source offsets.

---

# 10. Transcript Ground-Truth Lifecycle

## 10.1 Imported transcript

```text
TXT / VTT / SRT / JSON
        ↓
quarantine + validation
        ↓
immutable original bytes
        ↓
deterministic parser
        ↓
parsed raw transcript
        ↓
conservative cleanup proposal
        ↓
deterministic cleanup validator
        ↓
cleaned draft or unchanged fallback
        ↓
approval bound to exact content hash
        ↓
index generation
        ↓
atomic publication
```

## 10.2 Recorded meeting

```text
Recall Desktop SDK
        ↓
independently stored original recording
        ↓
AssemblyAI Universal-3.5 Pro + diarization
        ↓
immutable raw provider output
        ↓
speaker reconciliation
        ↓
parsed transcript
        ↓
conservative cleanup proposal
        ↓
validated draft
        ↓
approval
        ↓
published immutable transcript
```

Recall metadata and AssemblyAI anonymous speaker labels may be reconciled using aligned timing, but ambiguous speaker identity remains unknown rather than guessed.

---

# 11. Conservative Transcript Cleanup

Automatic cleanup improves layout/readability without changing source wording.

Initial permitted changes are intentionally narrow:

- leading/trailing horizontal whitespace,
- repeated spaces/tabs between existing tokens,
- paragraph/line-break placement inside an existing speaker segment.

Initial automatic cleanup must not:

- add words,
- remove words,
- reorder words,
- substitute words,
- paraphrase,
- repair grammar,
- remove fillers or repetitions,
- change names or numbers,
- expand contractions,
- translate,
- resolve ambiguity,
- change speaker assignment,
- change punctuation or capitalization under the initial policy.

The model proposes structured edits against stable segment IDs and source offsets.

Application code validates and applies allowed edits deterministically.

If cleanup is invalid, times out, or exceeds policy:

```text
retain unchanged parsed transcript
mark cleanup_status = skipped
continue through the configured approval policy
```

A human wording correction creates a new version and requires authorized approval.

---

# 12. Publication Rules

A transcript version may be published only when:

1. the source asset/raw transcript lineage is durable,
2. the draft content hash is frozen,
3. an approval exists for that exact hash,
4. required passage generation is complete,
5. required search indexes are ready, unless an explicitly labeled degraded lexical-only release is allowed,
6. the expected parent/current active version has not changed concurrently.

Publication updates the active version pointer atomically and writes the corresponding outbox event in the same transaction.

Concurrent publication conflicts return a state conflict rather than overwriting another version.

Approval revocation makes the version non-renderable and removes it from eligible normal retrieval.

---

# 13. Retrieval Architecture

## 13.1 Eligibility first

Construct the authorized eligible passage set before scoring or limiting.

Eligibility includes current:

- user/account state,
- tenant/workspace scope,
- project membership,
- transcript/document restrictions,
- publication state,
- approval state,
- retention/deletion state.

## 13.2 Hybrid retrieval

MVP retrieval may combine:

```text
PostgreSQL full-text search
+
pgvector semantic similarity
+
metadata filters
```

Baseline candidate strategy:

```text
up to 50 lexical candidates
+
up to 50 vector candidates
        ↓
reciprocal-rank fusion
        ↓
deduplicate passage IDs
        ↓
retain up to 20 candidates
```

Candidate counts and thresholds may be tuned through evaluation, but authorization predicates are not tunable.

Search is scoped to one project in MVP.

Cross-project search, if added later, uses a server-derived allowlist of authorized projects.

Exact phrase search verifies the phrase against canonical source text after indexed candidate discovery.

Normalized/indexed text can improve matching but can never become quote source text.

---

# 14. Evidence Selection

A retrieval run is server-created and bound to:

```text
principal
authorized scope
query
version IDs
index generations
expiry
```

The caller cannot submit its own allowed candidate set.

The Evidence Selector receives candidate text only through a trusted evidence loader that rechecks authorization.

Default selector output:

```json
{
  "selected_passages": ["passage_uuid_1", "passage_uuid_2"]
}
```

Rules:

- zero to eight unique passage IDs,
- IDs must belong to the sealed run,
- unexpected fields are rejected,
- model-supplied quote text is rejected,
- model-supplied source paths, speaker names, timestamps, hashes, versions, or source span IDs are rejected.

For precise-excerpt mode, selector offsets are Unicode code-point positions within the exact passage text supplied to the selector.

Server code validates those positions, converts them to absolute UTF-8 byte offsets in canonical source text, computes a span hash, and issues a server-owned `source_span_id`.

Invalid offsets are rejected or explicitly fall back to whole-passage rendering; they are never silently rounded or guessed.

---

# 15. Deterministic Quote Renderer

The quote renderer is a trusted application boundary.

Conceptual flow:

```text
principal + validated passage/span reference
        ↓
load sealed/pinned records
        ↓
reauthorize current access
        ↓
verify transcript is published and currently approved
        ↓
load exact immutable source object
        ↓
verify transcript content hash
        ↓
verify passage/span bounds and UTF-8 boundaries
        ↓
slice exact stored bytes
        ↓
verify span hash
        ↓
decode strictly
        ↓
reauthorize again before delivery
        ↓
write durable render audit
        ↓
return VerifiedQuote
```

No LLM call belongs in this path.

The renderer must never substitute:

- indexed text,
- cached model text,
- a newer transcript version,
- a normalized search representation,
- a model-generated quotation.

If integrity validation fails, the affected quote is unavailable and an integrity event is raised.

---

# 16. Analysis / Synthesis Rules

Optional synthesis happens only after valid evidence has been rendered.

Public responses separate:

```text
status
analysis
quote_cards
```

Analysis is generated paraphrase, not verified quotation.

Every analysis claim must cite delivered source span IDs or the response falls back to evidence-only mode according to the contract.

Generated prose must never be placed into a quotation-bearing field or rendered with verified-quote styling.

Do not stream unchecked model text directly to the user.

If synthesis fails but evidence is available, return verified evidence with `analysis_unavailable` rather than failing the entire research workflow.

If no permitted relevant evidence is found, return a scoped no-evidence state such as:

> No relevant evidence found in the transcripts you can access.

Do not claim the information does not exist globally.

---

# 17. Recording Architecture

The primary MVP capture path is:

```text
Electron application
        ↓
Recall.ai Desktop Recording SDK
        ↓
authenticated upload completion
        ↓
retrieve/copy recording into independent private storage
        ↓
verify hash and duration
        ↓
submit to AssemblyAI
```

Do not enable a second transcription service through Recall when AssemblyAI is the selected transcription provider.

Browser microphone recording may be supported as a fallback, but it must not pretend to capture remote participant audio when the browser/source cannot provide it.

For optional custom/browser uploads, use bounded ordered chunks and idempotent `(session_id, sequence)` behavior.

Recall's SDK upload lifecycle remains Recall-specific; do not force the custom chunk protocol onto the Recall integration.

Recording timestamps use a monotonic media timeline.

Store wall-clock timing separately.

Never silently concatenate around missing media; preserve visible gap mappings.

---

# 18. Bookmarks and Notes

Bookmarks and notes attach to recording/media offsets, not provisional transcript wording.

Bookmark creation captures the current media offset immediately and persists with a client-generated idempotency identifier where appropriate.

After canonical transcript publication:

```text
annotation media offset
        ↓
find approved published transcript passage covering / nearest offset
        ↓
attach passage reference
```

Notes must survive transcription failure.

Private annotations remain readable only by their author and are excluded from shared search, synthesis, and export.

Shared annotations remain subject to current project/document authorization.

---

# 19. OneDrive Export Architecture

OneDrive integration is one-way versioned export.

Each published transcript version should export, according to project policy:

```text
readable Markdown transcript
TXT transcript
JSON provenance manifest
```

Shared notes/bookmarks may be included only when policy allows.

Private notes are excluded.

Audio export is off by default.

Destination configuration uses an allowlisted company drive/folder.

Destination readers must not be broader than authorized source readers.

Store:

```text
destination IDs
Graph item IDs
ETags
export content hashes
status / attempts
reconciliation state
```

External modifications do not change application source truth.

OneDrive outages do not make canonical application data unavailable.

---

# 20. Authentication and Authorization

Authentication uses a single-tenant Microsoft Entra application.

Validate:

- issuer,
- audience,
- signature,
- expiration,
- nonce/state as appropriate,
- expected tenant,
- enabled employee assignment/group,
- active application user record.

Email-domain checking is not a sufficient identity control.

Use the Entra tenant ID plus object ID as stable external identity keys.

Server-side sessions use secure cookies and the OAuth authorization-code flow with PKCE.

Initial application roles:

| Role | Main rights |
|---|---|
| Reader | Read/search/replay permitted transcripts; personal notes/collections |
| Contributor | Reader + record/upload + shared annotations + prepare corrections |
| Project owner | Contributor + publish versions + project membership + approved exports + deletion requests |
| Tenant administrator | Configure identities/connectors/policies; no automatic transcript-read right |
| Compliance auditor | Scoped audit metadata; content only through separately granted access |

Transcript approval rights are separate from merely being able to propose a correction.

The controlled-cleanup service may approve only unchanged text or edits validated under the configured cleanup policy.

---

# 21. Defense in Depth

Authorization is enforced through multiple layers:

```text
API/service checks
+
PostgreSQL RLS
+
scoped joins/queries
+
worker resource revalidation
+
evidence loader checks
+
quote renderer reauthorization
+
audio/export authorization
```

Private object storage has no public access.

Object keys do not constitute authorization.

Baseline audio playback uses an authorized API path.

Never permit overwrite of published immutable transcript objects.

Development, staging, and production use separate resources/identities. Synthetic or explicitly approved de-identified content is used outside production.

---

# 22. Durable Jobs and Outbox

MVP background work uses PostgreSQL-backed durable state.

`jobs` records support:

```text
job ID
type
aggregate/version reference
idempotency key
status
attempt count
lease owner / lease expiry
next attempt time
provider job ID
safe error code
```

Workers use:

- leases,
- heartbeat renewal,
- bounded exponential retry with jitter,
- maximum attempts,
- dead-letter state,
- operator retry,
- provider-state reconciliation after uncertain submissions.

External execution is not assumed exactly-once.

All side effects must be idempotent.

Domain changes that require downstream work write an `outbox_events` record in the same database transaction.

Events carry identifiers and safe metadata, not transcript or note bodies.

Production may migrate workflow coordination to Durable Functions and Service Bus while preserving the domain contracts and idempotency keys.

Do not allow MVP and production workflow owners to process the same operation concurrently during migration.

---

# 23. Processing State Machines

Do not overload one status column with every lifecycle.

Use separate state machines.

## Capture

```text
created
  ↓
recording
  ↓
finalizing
  ↓
complete
```

with explicit:

```text
interrupted
aborted
```

## Ingestion / transcript publication

```text
quarantined
  ↓
validated
  ↓
transcribing / parsing
  ↓
raw_saved
  ↓
cleaning / correcting
  ↓
draft_ready
  ↓
awaiting_approval
  ↓
approved
  ↓
indexing
  ↓
published
```

plus:

```text
retryable_failure
permanent_failure
cancelled
```

Approval state and publication state are distinct.

## Export

```text
pending
  ↓
uploading
  ↓
verified
```

plus:

```text
retryable_failure
permission_blocked
destination_drift
deleted
```

## Deletion

```text
requested
  ↓
tombstoned
  ↓
purging
  ↓
complete
```

or:

```text
held
external_cleanup_pending
```

---

# 24. Application API Families

All application endpoints should live under `/api/v1` once stabilized.

Expected families include:

```text
/me
/projects
/project-memberships
/documents
/uploads
/capture-sessions
/jobs
/transcript-versions
/approvals
/passages
/retrieval-runs
/search
/evidence-runs
/quotes
/answers
/annotations
/collections
/exports
/audit
/deletion-requests
```

Important behavioral contracts:

- callers never supply authoritative quote text,
- protected resource IDs are treated as guessable,
- inaccessible identifiers normally return a non-disclosing not-found response,
- mutating operations use idempotency where retries are expected,
- state conflicts return explicit conflict errors,
- provider error bodies and signed URLs are never exposed directly.

The generated OpenAPI document is an implementation artifact and must stay aligned with these contracts.

---

# 25. Internal Events

Internal events use a versioned envelope containing identifiers only.

Conceptual shape:

```json
{
  "event_id": "uuid",
  "schema_version": 1,
  "type": "transcript.published",
  "tenant_id": "uuid",
  "workspace_id": "uuid",
  "project_id": "uuid",
  "document_id": "uuid",
  "aggregate_id": "uuid",
  "occurred_at": "UTC timestamp",
  "trace_id": "opaque-id",
  "data": {
    "transcript_version_id": "uuid"
  }
}
```

Delivery is at least once.

Consumers deduplicate and verify current aggregate state before side effects.

Do not assume global event ordering.

---

# 26. Failure Behavior

Failure must preserve source integrity.

| Failure | Required behavior |
|---|---|
| Capture/device interruption | Show interrupted state and visible gap; do not claim complete recording |
| Corrupt upload | Reject/quarantine; never fabricate transcript |
| STT timeout | Preserve original asset and retry/reconcile provider job |
| Cleanup violation | Preserve unchanged parsed text; do not silently accept rewrite |
| Missing approval | Version is not normal searchable/renderable evidence |
| Approval revoked | Block subsequent retrieval/render delivery for that version |
| Embedding failure | Keyword/evidence-only functionality may remain available with explicit index health |
| Selector/synthesis outage | Deterministic search/quote cards remain available |
| Invalid model offsets | Reject selection or explicitly fall back to whole passage |
| Missing/bad source hash | Suppress quote and raise integrity event |
| OneDrive failure | Keep application data available; retry export |
| Access revoked mid-request | Reauthorize before delivery and suppress inaccessible output |
| Worker restart | Reclaim durable lease and continue idempotently |
| Audit persistence unavailable for protected operation | Fail closed where required by policy |

No failure mode may cause model-generated text to become source evidence.

---

# 27. Testing Strategy

Testing is part of each module, not a final phase.

Use:

```text
unit tests
integration tests
contract tests
architecture/dependency tests
end-to-end tests
retrieval/evaluation datasets
fault injection
restore tests
```

## 27.1 Mandatory quote tests

Test exact equality for:

- normal ASCII text,
- punctuation,
- Unicode,
- emoji,
- combining marks,
- repeated text,
- passage and precise subspan boundaries,
- wrong versions,
- invalid offsets,
- changed/revoked approval,
- missing source bytes.

Required invariant:

```text
rendered quote bytes == approved source bytes[start:end]
```

No audio comparison is required for quote validity.

## 27.2 Mandatory authorization tests

Test:

- different tenant,
- different workspace,
- different project,
- restricted transcript,
- guessed resource IDs,
- revoked user,
- revoked membership during retrieval/generation,
- quote rendering,
- search,
- audio playback,
- export,
- saved answers/collections.

Unauthorized data must not leak through result counts, scores, candidate prompts, or metadata.

## 27.3 Architecture tests

CI should enforce at least:

```text
quote renderer cannot import model clients
retriever cannot construct verified quote text
evidence selector cannot mutate source data
frontend cannot instantiate VerifiedQuote from arbitrary strings
provider connector code does not leak into domain contracts
```

## 27.4 Job/idempotency tests

Repeating the same operation must not duplicate:

- source assets,
- raw transcripts,
- transcript versions,
- approvals,
- passages,
- embeddings,
- publication events,
- export manifests,
- annotations.

---

# 28. Evaluation Targets

Before pilot release, maintain representative synthetic and approved pilot datasets.

Core targets from the implementation specification include:

```text
Quote fidelity: 100% exact source-span equality in deterministic/adversarial tests
Isolation: zero unauthorized disclosure in access-control suite
Cleanup: 100% published automatic edits pass permitted-edit validator
Retrieval: Recall@20 >= 90% on the agreed labeled MVP corpus
Exact known phrase: found in 100% of healthy indexed fixtures
Abstention: curated unsupported/adversarial cases display no invented quote
```

Targets are measured product acceptance criteria, not provider guarantees.

---

# 29. Build Sequence

This sequence replaces the older architecture's separate 19-phase implementation order and matches `PROJECT_SPEC.md` v1.2.

Do not begin a later phase merely because an agent is available. Dependency readiness is more important than parallelization.

## Phase 0 - Foundation decisions

Resolve or explicitly register:

- Entra tenant/application setup,
- approved processors and regions,
- provider retention behavior,
- OneDrive destination and least-privilege grant,
- recording support matrix,
- retention/consent policy ownership,
- evaluation corpus,
- threat model,
- budget/capacity assumptions,
- recovery targets.

### Gate

Implementation may proceed with synthetic data while some company-policy decisions are pending, but no confidential pilot traffic is allowed until the required configuration decisions are approved.

---

## Phase 1 - Secure source foundation

Build:

- repository/toolchain,
- local development environment,
- CI,
- configuration and secret handling,
- FastAPI skeleton,
- PostgreSQL + pgvector,
- Alembic migrations,
- tenant/workspace/project/user model,
- Entra/session integration,
- project memberships,
- PostgreSQL RLS,
- private object-storage adapter,
- upload quarantine/source assets,
- durable jobs/outbox foundation,
- minimal audit,
- backup/restore baseline,
- shared API/contracts.

### Gate

- permitted users can create/read foundation resources through documented APIs,
- unauthorized IDs cannot expose another project's resource,
- RLS/integration tests pass,
- logs contain no confidential fixtures,
- basic restore smoke test passes,
- CI passes.

---

## Phase 2 - Ingestion and recorder

Build:

- Electron capture application,
- Recall Desktop SDK adapter,
- independent original-audio storage,
- transcript/text upload parsers,
- AssemblyAI adapter,
- immutable raw provider output,
- speaker/timestamp reconciliation,
- conservative cleanup adapter and validator,
- transcript approval,
- immutable version publication,
- passage construction,
- index job generation,
- recording/interruption recovery states.

### Gate

A permitted user can record or upload a representative source and obtain an approved, published transcript whose canonical text can be deterministically reproduced from internal records without mandatory audio comparison.

---

## Phase 3 - Evidence product

Build:

- permission-scoped keyword search,
- embeddings + pgvector,
- hybrid ranking,
- retrieval run/candidate sealing,
- evidence loader,
- evidence selector,
- precise-span validation where enabled,
- deterministic quote renderer,
- quote UI components,
- optional constrained synthesis,
- retrieval eval suite,
- adversarial no-fabricated-quote suite.

### Gate

Attempt to force the model to invent a quote or select unauthorized evidence.

The product must remain technically incapable of displaying fabricated or unauthorized wording as a verified source quotation.

---

## Phase 4 - MVP completion

Build:

- OneDrive versioned export,
- destination permission validation,
- export retries/status,
- transcript correction/version-history flow,
- processing/status UI,
- project/meeting navigation,
- source context/replay where audio exists,
- core operating runbooks,
- pilot acceptance report.

### Gate

A permitted employee can record or upload a meeting, obtain a published transcript, find evidence, copy deterministic verified quotes, and see the transcript exported to the approved OneDrive destination; an unauthorized employee cannot access any of it.

---

## Phase 5 - Live and collaborative features

Build:

- bookmarks,
- timestamped notes,
- speaker mapping/correction,
- annotation visibility,
- concurrent revision handling,
- shared collections,
- live status/invalidation,
- optional provisional live transcript,
- production system-wide hotkey companion if required.

### Gate

Notes/bookmarks survive live-transcription failure, concurrent users cannot silently overwrite each other, and revocation blocks subsequent delivery.

---

## Phase 6 - Production reliability and governance

Build:

- durable orchestration evolution where justified,
- Service Bus / Durable Functions behind existing contracts,
- transcript-level ACLs,
- retention and holds,
- complete audit workflows,
- deletion reconciliation,
- export drift reconciliation,
- monitoring/alerting,
- load testing,
- penetration/security testing,
- backup and restore drills,
- disaster recovery,
- cost monitoring,
- model/provider upgrade evaluation process.

### Gate

The system can detect and recover from tested provider, worker, database, storage, authorization, and export failures without corrupting approved transcript truth or leaking confidential content.

---

# 30. Agent Development Batches

Coding-agent work should follow the build phases.

## Batch 0

```text
Architecture reconciliation
Configuration register
Repository bootstrap plan
Core contracts
Synthetic fixtures
```

## Batch 1

```text
Repository / CI / local infrastructure
Database / migrations
Identity / sessions
Authorization / RLS
Storage foundation
Jobs / outbox
Minimal audit
```

## Batch 2

```text
Capture / upload
Recall connector
AssemblyAI connector
Parsing
Raw transcript preservation
Cleanup validation
Transcript approval
Version publication
Passages / indexing
```

## Batch 3

```text
Keyword retrieval
Semantic retrieval
Evidence runs
Evidence selection
Deterministic quote renderer
Quote UI
Optional synthesis
```

## Batch 4

```text
OneDrive export
Correction/version UI
Processing UI
Core operating runbooks
Pilot acceptance
```

## Batch 5

```text
Bookmarks
Notes
Speaker correction
Collaboration
Collections
Live updates / optional provisional transcript
```

## Batch 6

```text
Retention / holds / deletion
Complete audit
Production orchestration
Monitoring / alerts
Recovery / restore
Load / security hardening
```

Agents may work in parallel only when their dependencies and shared contracts are already stable.

---

# 31. Module Completion Gate

A module is not complete because its code compiles.

Before declaring completion, verify as applicable:

```text
implementation works
public/internal contracts are documented
migrations exist
happy-path tests pass
invalid-input tests pass
authorization tests pass
cross-tenant/project tests pass
failure/retry behavior is tested
idempotency is tested
logs contain no confidential content
architecture dependency tests pass
CI passes
ARCHITECTURE.md remains accurate
```

Another agent should be able to use the module through its documented interface without reading private implementation internals.

---

# 32. Required Agent Handoff

Every implementation task should end with:

```text
IMPLEMENTED
- ...

FILES CHANGED
- ...

INTERFACES ADDED/CHANGED
- ...

DATABASE MIGRATIONS
- ...

TESTS
- ...

EVALS / ACCEPTANCE GATES
- ...

VERIFICATION COMMANDS
- ...

KNOWN LIMITATIONS
- ...

NEXT DEPENDENCIES
- ...

ARCHITECTURAL DECISIONS
- ...
```

No agent should leave undocumented hidden dependencies.

---

# 33. CI Requirements

CI should progressively enforce:

- formatting,
- linting,
- type checking,
- unit tests,
- integration tests against an ephemeral PostgreSQL instance,
- real migration upgrade validation,
- architecture/dependency tests,
- contract/schema validation,
- secret scanning,
- dependency/image vulnerability scanning,
- container builds,
- relevant eval smoke tests.

Production release workflows additionally publish versioned/signed artifacts according to the selected deployment design.

---

# 34. Observability

Track content-free operational signals including:

```text
API latency / error rate
denied access events
upload acknowledgements
recording gaps
job queue age
lease expirations
transcription duration / failures
missing timestamps
index lag
retrieval no-evidence rate
selection rejection rate
quote integrity/hash failures
Graph export lag / ACL drift
deletion backlog
audit backlog
database / storage saturation
model/token spend
cost per audio hour / query
```

Source-integrity mismatches and cross-scope authorization anomalies are high-severity events.

Use trace IDs across API, outbox, worker, and provider jobs.

---

# 35. Backup and Recovery

Backups must cover both:

```text
PostgreSQL metadata/state
+
authoritative source/version objects
```

OneDrive is not a recovery system.

A restore process must:

1. isolate the restore environment,
2. restore database and objects to compatible points,
3. reapply deletion/tombstone state and current authorization,
4. verify manifests and content hashes,
5. rebuild derived indexes where needed,
6. reconcile in-flight jobs/provider state,
7. keep outbound export disabled until reconciliation completes,
8. run quote-integrity and isolation smoke tests,
9. explicitly authorize reopening service.

---

# 36. Required Runbooks

Before pilot/production as applicable, maintain runbooks for:

- employee onboarding/offboarding,
- provider credential rotation,
- recorder recovery,
- stuck transcription,
- duplicate/unknown provider submission,
- index rebuild,
- source-integrity incident,
- Graph permission drift,
- retention/deletion/hold handling,
- compromised account,
- database/object restore,
- rollback,
- model/provider upgrade and evaluation.

Each runbook identifies required permissions, owner, steps, verification, and escalation.

---

# 37. Architectural Decision Records

Material architecture changes require an ADR under:

```text
docs/decisions/
```

Examples:

```text
ADR-001-stack-and-repository-layout.md
ADR-002-storage-provider.md
ADR-003-transcription-provider.md
ADR-004-job-orchestration.md
ADR-005-audio-retention.md
```

Do not silently replace:

- FastAPI/Python API strategy,
- PostgreSQL/pgvector,
- Entra identity strategy,
- transcript approval/version model,
- deterministic quote renderer,
- project-isolation strategy,
- baseline storage provider,
- Recall capture integration,
- AssemblyAI transcription integration,
- provider abstraction boundaries,
- OneDrive one-way export model,
- PostgreSQL jobs/outbox baseline.

An ADR records:

```text
Context
Decision
Alternatives considered
Consequences
Security implications
Migration implications
```

---

# 38. Configuration Decisions Before Confidential-Data Launch

These decisions may remain open while synthetic-data implementation proceeds, but they must be resolved before confidential pilot use.

| Decision | Baseline from PROJECT_SPEC.md | Owner |
|---|---|---|
| Company identity | Entra tenant ID, assigned employee group, corporate domains as secondary check | IT |
| Region/processors | Approved Recall, AssemblyAI, OpenAI, compute/storage regions and retention terms | Security / IT |
| Provider retention | Record actual endpoint/account behavior; do not assume zero retention | Security |
| OneDrive destination | Fixed company OneDrive for Business drive/folder or explicitly selected team library | IT / product owner |
| Export permissions | Destination readers no broader than source readers; external sharing disabled | IT / security |
| Recording environment | Recall Desktop SDK in managed Electron app; tested client/OS support matrix | Product owner |
| Retention/holds | Confirm or replace proposed pilot defaults | Data owner / compliance |
| Consent | Firm-provided acknowledgement text/process | Data owner |
| Ground truth | Approved immutable transcript version; controlled-cleanup approval initially; human approval for wording corrections; audio review optional | Product owner |
| Capacity/budget | Confirm load envelope, provider quota, and spend ceiling | Engineering / finance |
| Recovery | Confirm RPO/RTO and backup region | IT / data owner |

Agents must not invent unresolved company policy.

---

# 39. What Agents Must Not Do

Agents must not:

- bypass authorization for convenience,
- retrieve globally and filter after ranking,
- expose unauthorized result counts or metadata,
- introduce public signup,
- put provider secrets in browser/desktop bundles,
- send confidential data to unapproved services,
- let LLM output become authoritative quote text,
- silently promote an unapproved transcript draft,
- silently overwrite a published transcript version,
- silently broaden cleanup policy,
- treat OneDrive as the application database,
- make bookmarks depend on provisional transcript wording,
- require retained audio to validate a transcript quote,
- invent missing speaker/timestamp metadata,
- make external provider SDK types part of core domain contracts,
- add Redis, Kubernetes, a separate vector database, or another major platform merely because it may be useful later,
- hide failing tests,
- mark a phase complete before its gate passes,
- change a locked implementation choice without an ADR.

---

# 40. Final System Model

```text
MEETING / FILE
      │
      ▼
AUTHENTICATED CAPTURE / UPLOAD
      │
      ▼
QUARANTINE + VALIDATION
      │
      ▼
IMMUTABLE ORIGINAL ASSET
      │
      ├──────────── audio ────────────┐
      │                              ▼
      │                       ASSEMBLYAI STT
      │                              │
      └──────── transcript ──────────┤
                                     ▼
                           IMMUTABLE RAW TRANSCRIPT
                                     │
                                     ▼
                              PARSE / NORMALIZE
                                     │
                                     ▼
                         CONSERVATIVE CLEANUP DRAFT
                                     │
                                     ▼
                           HASH-BOUND APPROVAL
                                     │
                                     ▼
                     PUBLISHED CANONICAL TRANSCRIPT
                                     │
                    ┌────────────────┼─────────────────┐
                    ▼                ▼                 ▼
               PASSAGES        FULL-TEXT INDEX      PGVECTOR
                    │                │                 │
                    └────────────────┴────────┬────────┘
                                             ▼
                                    AUTHORIZED RETRIEVER
                                             │
                                      sealed candidates
                                             │
                                             ▼
                                    EVIDENCE SELECTOR
                                             │
                                    IDs / bounded spans
                                             │
                                             ▼
                                      VALIDATION LAYER
                                             │
                                             ▼
                                  DETERMINISTIC RENDERER
                                             │
                                  exact approved source text
                                      ┌──────┴──────┐
                                      ▼             ▼
                                 QUOTE CARDS    AI ANALYSIS
                                      │             │
                                      └──────┬──────┘
                                             ▼
                                         CITED ANSWER

PUBLISHED TRANSCRIPT ───────────────► VERSIONED ONEDRIVE EXPORT
PUBLISHED TRANSCRIPT + AUDIO TIME ──► BOOKMARK / NOTE MAPPING
```

---

# 41. North-Star Architectural Rule

When there is uncertainty, preserve this separation:

> Retrieval locates authorized evidence. AI reasons over permitted evidence. Deterministic code renders approved transcript truth.

The approved published transcript - not the LLM and not mandatory audio re-verification - is the application's quote source of truth.
