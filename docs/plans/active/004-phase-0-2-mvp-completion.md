# Phase 0–2 functional MVP completion workplan

## Phase and objective

Architecture Phases 0, 1, and 2. Complete the product as an end-to-end transcript-ingestion MVP:

```text
authorized employee
→ project and document
→ transcript upload, audio upload, or desktop recording
→ independently stored original source
→ transcription when audio is supplied
→ immutable raw transcript
→ deterministic reconciliation and cleanup draft
→ automatic policy approval or explicit human approval
→ immutable publication
→ deterministic canonical-text reproduction
→ passage and index-job creation
```

The first milestone is a complete credential-free vertical slice using fictional fixtures and local
storage. Live Recall, AssemblyAI, Backblaze B2, Microsoft Entra, or Graph calls occur only after their
documented approval and feasibility gates. A passing synthetic slice is not evidence that a live
provider or confidential-data gate passed.

This plan supersedes `002-phase-2-ingestion-core.md` as the active completion plan. That file remains
useful as the record of the first synthetic implementation slice.

## Authoritative inputs

Before changing code, every implementing agent must read in full:

1. `AGENTS.md`.
2. `ARCHITECTURE.md`, especially §§3–13, 17, 20–31, 34–39.
3. `README.md`.
4. `PROJECT_SPEC.md`, especially the ingestion, recording, security, and acceptance sections.
5. `docs/IMPLEMENTATION_DECISIONS.md`.
6. `docs/DATA_MODEL.md`, `docs/API_CONTRACTS.md`, and `docs/SECURITY.md`.
7. ADR-003, ADR-004, and ADR-005 under `docs/decisions/`.
8. `docs/INTEGRATIONS.md` and the provider guide relevant to the current batch.
9. `schemas/README.md`, `docs/EVALS.md`, and `docs/PR_PROCESS.md`.

If a lower-level plan conflicts with these sources, follow the higher authority and reconcile the
stale document. A material architecture change requires an ADR. Never make a product-policy choice
merely to keep implementation moving.

## Current verified baseline

Treat this list as the starting point to verify, not as permission to skip tests:

- FastAPI, PostgreSQL 17/pgvector, Alembic, restricted runtime roles, scoped transactions, forced
  RLS, project membership, CSRF, opaque sessions, and local/test magic-link authentication exist.
- The web application supports login, account profile, project navigation, and project membership.
- Local immutable object storage, durable job/outbox repositories, scoped worker primitives,
  observability primitives, and backup/restore smoke infrastructure exist.
- TXT, VTT, SRT, and canonical JSON parsers exist.
- Deterministic cleanup policy-v2, cleanup validation, passage construction, and canonical hash
  reproduction exist.
- A transcript-upload publication endpoint currently performs parse, cleanup, approval, and
  publication in one synchronous operation.
- Capture session/chunk/finalization APIs and recovery state logic exist.
- Electron still runs its in-memory synthetic capture adapter; its database-backed client is not
  connected to the running application.
- Synthetic Recall and AssemblyAI adapters exist but are not connected to a durable ingestion
  coordinator.
- `workers/__main__.py` does not yet host the durable handlers required for the ingestion pipeline.
- The connected web product does not yet create documents, upload sources, show processing, review
  cleanup, approve drafts, or display the published transcript.
- Recall R1 and all provider live smoke tests remain NOT RUN.

An agent must verify these statements against the current branch before relying on them. Record any
drift in this plan's completion notes.

## Non-negotiable implementation rules

- Use fictional fixtures until the relevant live-provider gate explicitly passes.
- Never put credentials, callback tokens, signed URLs, audio, transcripts, email addresses, or
  provider response bodies in ordinary logs, errors, traces, metrics, or committed fixtures.
- Never expose a public signup path or grant access from an email domain alone.
- Derive tenant, workspace, principal, and project scope from the authenticated server context.
- Authorize before loading source bytes, transcript text, job state, counts, or provider metadata.
- Use the internal user UUID as identity; email is only a login/member-assignment locator.
- Preserve original source, raw provider output, parsed transcript, cleanup draft, and every
  published version independently. Never overwrite any of them.
- Automatic cleanup approval is allowed only when the versioned deterministic validator accepts the
  exact change under ADR-004. An LLM or provider assertion that meaning is preserved cannot expand
  the allowlist.
- Human approval binds to the exact canonical content hash. Any edit after approval creates a new
  draft/version and requires a new approval.
- Publication and its active-version pointer, passages, index intents, audit, and outbox event must
  commit atomically.
- Provider operations use durable operation keys and reconcile uncertain outcomes before retrying.
- Provider SDK types, credentials, raw errors, and URLs do not enter domain or public contracts.
- The runtime API and worker roles never receive table ownership, DDL, superuser, or `BYPASSRLS`.
- Real external contracts and connector enablement require the product owner's confirmation before
  they are published or activated.
- Do not start Phase 3 retrieval, embeddings, answer generation, or OneDrive export in this plan.

## Completion gates

### Gate S — credential-free synthetic Phase 0–2 MVP

A permitted contributor can use the actual web/Electron product to create a document, upload a
fictional transcript or produce a synthetic audio recording, observe processing, resolve any
required approval, and view an immutable published transcript. The transcript can be reproduced
byte-for-byte from internal records without audio comparison. Restart, retry, duplicate submission,
and interrupted recording tests pass. No network provider or secret is required.

### Gate L — live-provider fictional-data MVP

Using isolated approved provider accounts and fictional audio, the packaged Electron application can
capture supported meeting audio through Recall, preserve the original in approved private storage,
transcribe through AssemblyAI, and publish through the same domain workflow. Required negative
controls, deletion/retention observations, and sanitized feasibility evidence pass.

### Gate C — confidential pilot readiness

All Phase 0 company-policy decisions are approved, Entra production identity is verified, regions
and processors are approved, consent and retention policies are configured, backup/recovery targets
are accepted, operational alerts/runbooks exist, and a security review authorizes confidential pilot
traffic. Gate C is a human approval gate and cannot be inferred from tests.

## Delivery strategy and required pull-request slices

Implement the following batches in order. Keep each batch reviewable and leave the repository
passing `./scripts/pr-ready.sh`. Do not combine a live-provider connector with unrelated UI or schema
work.

Recommended PR sequence:

1. Contract/state-machine design and migration.
2. Source upload and quarantine.
3. Durable ingestion coordinator and synthetic handlers.
4. Draft/approval/publication separation.
5. Connected web workflow.
6. Connected Electron synthetic recording.
7. End-to-end reliability, security, observability, and operational gate.
8. Recall R1 evidence and live Recall connector.
9. B2 live storage connector.
10. AssemblyAI live connector and fictional live-provider acceptance.
11. Entra and confidential-pilot governance gate.

Every PR description must identify the plan batch, contracts changed, migrations, restricted roles
tested, fixture version, authorization implications, failure behavior, and `pr-ready` result.

---

# Batch 0 — baseline audit and decision checkpoint

## Objective

Establish a reproducible baseline and identify every open decision that blocks Gate S, Gate L, or
Gate C before modifying interfaces.

## Steps

1. Start PostgreSQL with `./scripts/services.sh up` and verify health.
2. Run `./scripts/pr-ready.sh` on the untouched branch and record the result.
3. Run `./scripts/backup-restore-smoke.sh` and record the result.
4. Inspect current migrations, API operation registry, generated OpenAPI, web application, Electron
   IPC, worker entry point, provider protocols, storage adapter, and all ingestion tests.
5. Trace the existing source-to-publication execution path with GitNexus, then confirm unresolved or
   stale results with `rg`.
6. Produce a short gap ledger mapping every Phase 0–2 architecture item to `implemented`, `partial`,
   `missing`, or `external gate`.
7. Reconcile stale claims in README, active plans, and implementation decisions.
8. Draft the proposed HTTP/internal contracts and state transitions for Batches 1–4.
9. Stop and obtain product-owner confirmation before publishing changed HTTP contracts or committing
   a material architecture decision.

## Required decisions

- Confirm supported synthetic upload formats and limits.
- Confirm initial real audio formats after provider evidence; do not guess before R1.
- Confirm which roles may submit sources, review drafts, approve, publish, retry, and abort.
- Confirm whether project owners automatically possess reviewer/publisher rights or need a separate
  capability. Preserve the current security matrix unless explicitly changed.
- Confirm the visible product states and user-facing failure vocabulary.
- Confirm whether manual corrections are included in the MVP or only approval/rejection of a draft.
- Confirm whether Graph-delivered magic links remain test-only, as ADR-005 currently requires.

## Gate

- Baseline commands pass or every pre-existing failure is recorded.
- The gap ledger is complete.
- Proposed contracts and any ADR are approved before implementation begins.

---

# Batch 1 — workflow contracts and persistence

## Objective

Represent the complete source-to-publication lifecycle durably without overloading publication as a
single synchronous upload request.

## State model

Define and validate one canonical state machine. At minimum it must distinguish:

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

Recording state remains separate and maps to source ingestion only after original-audio finalization.
Do not infer successful transcription or publication from recording completion.

## Steps

1. Extend Python-owned request/response contracts rather than creating route-local DTOs.
2. Define operations for:
   - creating an ingestion/source upload intent;
   - streaming/finalizing an upload;
   - reading processing state without exposing unauthorized metadata;
   - reading a cleanup draft and its validation manifest;
   - submitting a human-approved exact draft hash;
   - publishing an approved draft;
   - retrying an explicitly retryable stage;
   - retrieving the active published transcript.
3. Decide which existing combined publication operation remains as compatibility behavior and which
   path becomes canonical. Do not leave two subtly different publication implementations.
4. Add internal typed commands/results for each worker stage. Provider references remain opaque and
   private.
5. Add a reviewed Alembic migration for missing workflow records/columns. Prefer explicit tables or
   append-only attempts over mutable JSON blobs when state must be queried or reconciled.
6. Persist durable operation keys and payload hashes for upload finalization, transcription
   submission, raw-result ingestion, cleanup generation, approval, and publication.
7. Persist provider submission reference before polling.
8. Persist immutable raw provider response object reference, byte length, SHA-256, provider,
   model/config version, and received time.
9. Persist draft canonical object/hash, cleanup policy version, validation manifest, author/service
   actor, and state.
10. Enforce approval-to-content-hash and publication-to-current-approval relationships with database
    constraints where practical.
11. Ensure active transcript version can point only to an approved published version in the same
    tenant/workspace/project/document.
12. Add/adjust RLS and restricted-role grants for every new table and operation.
13. Regenerate OpenAPI, JSON Schema, and TypeScript artifacts through the documented generator.
14. Update `docs/API_CONTRACTS.md`, `docs/DATA_MODEL.md`, and `docs/SECURITY.md`.

## Required tests

- Every legal and illegal state transition.
- Duplicate operation key with same and different payload.
- Approval hash mismatch and post-approval edit rejection.
- Cross-tenant/workspace/project/document foreign-key rejection.
- Missing RLS context and reader/contributor/owner/reviewer matrix.
- Inaccessible and absent resource responses are indistinguishable.
- Concurrent approve/publish and competing version activation.
- Migration upgrade from zero and downgrade policy where supported.
- Runtime OpenAPI exactly matches generated contracts.

## Gate

The database can represent and authorize every workflow state, and a separate module can use the
documented contracts without relying on private table knowledge.

---

# Batch 2 — source upload, validation, and quarantine

## Objective

Accept transcript and audio sources safely, preserve exact original bytes, and release only validated
assets to downstream processing.

## Steps

1. Implement authorized upload-intent creation for a contributor/owner within one document.
2. Support bounded streaming/chunked upload; never require a production-sized audio file to be held
   fully in API memory.
3. Compute SHA-256 and byte length while streaming.
4. Store each original under a unique immutable key and retain the storage version identifier.
5. Finalize idempotently using scope, source ID, operation key, expected length, and expected hash.
6. Add transcript quarantine:
   - permitted extension/format;
   - UTF-8 validation;
   - parser limits;
   - cue/timestamp ordering;
   - schema version;
   - no executable interpretation.
7. Add audio quarantine:
   - configured format allowlist;
   - magic-byte/container inspection;
   - decoder probe using a pinned tool/library;
   - decoded duration/channel/sample-rate limits;
   - truncated/corrupt file rejection;
   - extension/MIME/container disagreement handling.
8. Keep rejected bytes in the governed quarantine state according to configured policy; do not make
   them available to transcription or playback.
9. Provide authorized, bounded source playback/download through the API; an object key is never an
   authorization credential.
10. Add stale/abandoned multipart cleanup jobs without deleting finalized authoritative versions.
11. Record content-free audit and operational signals for intent, accepted, rejected, failed, and
    abandoned outcomes.

## Required tests

- TXT, VTT, SRT, canonical JSON, and representative synthetic WAV fixtures.
- Empty, oversized, malformed, invalid UTF-8, invalid timestamp, truncated WAV, MIME mismatch, and
  sequence-gap cases.
- Repeated finalization and conflicting operation-key payloads.
- Unauthorized playback/source metadata and guessed object/source IDs.
- Interrupted multipart upload and cleanup recovery.
- Hash mismatch before and after storage.
- Confidential sentinel absent from logs, errors, audit, and metrics.

## Gate

A contributor can upload a fictional transcript or audio source, recover interrupted transfer, and
obtain an immutable accepted asset or a safe terminal quarantine result.

---

# Batch 3 — durable ingestion coordinator and synthetic transcription

## Objective

Join accepted audio to synthetic transcription and downstream draft generation through durable,
restart-safe worker execution.

## Steps

1. Implement an ingestion coordinator service that schedules the next valid job from persisted state.
2. Register concrete worker handlers for:
   - source quarantine;
   - transcription submission;
   - transcription status polling;
   - raw provider result fetch/preservation;
   - speaker/timestamp reconciliation;
   - cleanup draft construction/validation;
   - auto-approval eligibility;
   - publication;
   - passage/index-intent creation;
   - abandoned external-resource cleanup.
3. Replace the logging-only worker entry point with a real host that:
   - loads reviewed service scopes;
   - claims bounded work;
   - renews leases;
   - dispatches outbox events;
   - sleeps when idle;
   - shuts down cleanly;
   - emits content-free health/queue signals.
4. Do not let scope discovery accept arbitrary project IDs from job payloads. Use provisioned service
   grants and revalidate resource state immediately before side effects.
5. Connect `SyntheticAssemblyAIAdapter` to the same provider-neutral transcription boundary intended
   for the live adapter.
6. Persist submission intent before calling the provider and persist its reference immediately after
   a known success.
7. Reconcile an uncertain submission rather than issuing a duplicate paid operation.
8. Poll through durable scheduled jobs; never hold an HTTP request or worker lease for the whole
   transcription duration.
9. Fetch and store exact raw provider bytes before parsing or cleanup.
10. Convert provider segments through the deterministic reconciliation service. Preserve null or
    ambiguous speaker/timestamp fields; never invent them.
11. On provider failure, distinguish retryable, terminal, authentication, throttling, invalid input,
    and outcome-unknown states using safe internal codes.
12. Keep transcript-upload sources on the same workflow after the transcription stage, rather than
    maintaining an unrelated publication implementation.

## Required tests

- Full synthetic queued → processing → completed flow.
- Worker process restart between every stage.
- Lease expiry and reclaim.
- Duplicate jobs/outbox events and repeated callbacks.
- Provider 429, 5xx, invalid response, terminal failure, and outcome unknown.
- Revoked membership/user/service grant before submission and before result delivery.
- Raw result hash mismatch and missing object.
- Overlapping, missing, reversed, and anonymous speaker/timestamp inputs.
- No duplicate source, raw transcript, draft, approval, publication, passage, or index intent.

## Gate

An accepted fictional audio asset reaches a durable cleanup draft through the actual worker process,
survives restart/failure injection, and preserves one immutable raw provider result.

---

# Batch 4 — cleanup, review, approval, and atomic publication

## Objective

Make transcript truth explicit and reviewable while retaining safe automatic approval.

## Steps

1. Produce the parsed transcript as an immutable artifact with parser version and hash.
2. Run deterministic policy-v2 cleanup and persist the proposed canonical bytes and edit manifest.
3. Re-run the independent cleanup validator before any approval decision.
4. If the result is unchanged or every exact edit is allowed by ADR-004, create a service-policy
   approval bound to the canonical hash.
5. If validation fails or a person proposes any other wording change, preserve the draft and enter
   `approval_required`; do not silently fall back and publish without telling the user.
6. Provide an authorized review operation that returns original/parsed/draft text, speakers,
   timestamps, and the content-free validation summary only to permitted reviewers.
7. Implement human approval with optimistic concurrency and an exact expected content hash.
8. If manual correction is in scope, create a new immutable draft from the submitted correction,
   record lineage, validate it, and require human approval. Never mutate the previous draft.
9. Publish only the currently approved hash.
10. In one database transaction:
    - insert the immutable published version metadata;
    - insert approval linkage;
    - construct passages and exact UTF-8 byte offsets;
    - insert stable index jobs;
    - update the active version pointer;
    - insert audit metadata;
    - insert the versioned outbox event.
11. Verify canonical object bytes/hash before returning publication.
12. Make retry/idempotency behavior explicit for lost responses and concurrent publication.
13. Add version history and active-version read operations needed by the UI.

## Required tests

- Formatting-only, allowlisted filler removal, and allowlisted stutter deduplication auto-approve.
- Protected punctuation, numbers, names, negation, speaker boundaries, and unlisted wording do not
  auto-approve.
- Unicode, emoji, combining marks, CRLF/LF, and UTF-8 byte-offset reconstruction.
- Human approval wrong hash, stale revision, revoked reviewer, and edited-after-approval denial.
- Transaction rollback at every publication write boundary.
- Canonical reproduction from stored records with original audio unavailable.
- Published versions are immutable and old versions remain reproducible.
- Index job count and operation keys are stable under retries.

## Gate

A permitted user can obtain an approved published transcript from either transcript input or the
synthetic audio pipeline, and the returned text exactly matches verified immutable canonical bytes.

---

# Batch 5 — connected web product workflow

## Objective

Expose the complete Phase 2 workflow through the authenticated web application without embedding
business rules in React.

## Steps

1. Use generated/shared contract types for new API operations.
2. Add project-level document creation for contributors and owners.
3. Add source selection: transcript upload, audio upload, or desktop recording handoff.
4. Add accessible file pickers, validation messages, progress, cancellation, and safe retry.
5. Add a document processing page showing only authorized stage/state metadata.
6. Poll with bounded backoff or use an approved same-origin update mechanism; stop polling on terminal
   states and component teardown.
7. Display recording gaps and incomplete-source warnings prominently.
8. Add transcript review showing speaker/timestamp rows and a controlled original-versus-cleanup
   comparison.
9. Show why human approval is required without exposing internal provider bodies.
10. Add approve, reject/revise, publish, and retry controls only when the server reports the action is
    authorized.
11. Treat server authorization as authoritative; hiding a button is not access control.
12. Add published transcript view, version number, approval method, publication time, and integrity
    status.
13. Add empty, loading, retryable failure, terminal failure, access revoked, and provider unavailable
    states.
14. Keep visual styling modular so later design changes do not affect domain/data architecture.

## Required tests

- Contributor happy path from document creation to publication.
- Reader sees published content but cannot upload, approve, retry, or publish.
- Owner/reviewer action matrix.
- Session expiry, CSRF rejection, and access revocation while page is open.
- Upload progress/cancel/retry and processing-state transitions.
- Review prevents approving a stale hash.
- UI never derives authoritative publication or quote text independently.
- Keyboard navigation, form labels, focus behavior, and basic responsive layout.

## Gate

The synthetic transcript-upload path can be completed entirely through the visible web application,
with no curl, database manipulation, or filesystem mailbox inspection after login.

---

# Batch 6 — connected Electron synthetic recording

## Objective

Make the packaged desktop application exercise the real authenticated capture persistence boundary
while retaining a deterministic synthetic audio source.

## Steps

1. Define the desktop authentication/session handoff without placing provider or long-lived secrets
   in Electron. Reuse the server-held session model.
2. Add project/document selection based on the signed-in employee's authorized API results.
3. Replace direct renderer access to the in-memory adapter with context-isolated IPC commands.
4. Validate every IPC argument in the main process and return safe state/errors.
5. Connect IPC to `CaptureApiClient` for create, recover, transition, chunk upload, and finalize.
6. Extend the client to support the missing create/chunk/finalize operations with cookies and CSRF.
7. Persist only the minimum local recovery metadata needed to resume a capture. Protect it with OS
   user permissions and never store a Verelo credential in plaintext application logs/config.
8. Feed a deterministic synthetic WAV stream through the same chunking code the future Recall bridge
   will use.
9. Persist monotonic sequence numbers and wait for server acknowledgement before discarding a chunk.
10. On network interruption, retain unacknowledged chunks and expose an interrupted/gap state.
11. On restart, recover the server session state, reconcile acknowledged sequence, and resume or
    explicitly finalize/abort.
12. Finalize into an accepted source asset and schedule the ingestion coordinator.
13. Display recording duration, upload backlog, connection state, gaps, finalization, processing, and
    safe terminal errors.
14. Ensure application close during recording triggers a recoverable interruption, not silent
    completion.

## Required tests

- IPC schema rejection and renderer isolation.
- Ordered chunk acknowledgement and duplicate same-hash acceptance.
- Conflicting duplicate, skipped sequence, and corrupt chunk rejection.
- Offline period, API restart, Electron restart, and finalization retry.
- Authentication expiration and project-access revocation during capture.
- Synthetic WAV reconstructed hash equals the fixture hash.
- Finalized audio enters the same synthetic transcription/publication pipeline.
- Packaged application smoke test on the supported development OS.

## Gate

A permitted user can use the Electron UI to perform a synthetic recording, interrupt/recover it, and
obtain a published transcript through the same API/worker/domain path used by uploads.

---

# Batch 7 — synthetic end-to-end, security, and operations gate

## Objective

Prove Gate S and remove operational gaps before any live provider is connected.

## End-to-end scenarios

1. Provision owner, contributor, reader, and unrelated fictional employees.
2. Owner creates project and assigns roles.
3. Contributor creates a document and acknowledges configured fictional consent.
4. Run transcript-upload publication through the web UI.
5. Run audio-upload publication through the synthetic worker pipeline.
6. Run Electron synthetic recording with an interruption and restart.
7. Verify reader can view only the final authorized publication.
8. Reproduce canonical bytes/hash after removing audio from the test review path.
9. Disable the contributor during processing and prove no subsequent unauthorized action/delivery.
10. Retry every externally modeled side effect and prove no duplicates.

## Security/adversarial suite

- Other tenant, workspace, project, document, source, job, draft, version, and capture IDs.
- Missing/malformed session and CSRF.
- Reader/contributor/owner/reviewer permission boundaries.
- Disabled user/membership and changed authorization epoch.
- Worker with absent/revoked/wrong-project service grant.
- Malicious filenames, Unicode controls, huge metadata, malformed base64, and parser bombs.
- Transcript content containing prompt-like instructions, HTML, script text, SQL-like text, and secret
  sentinels; all remain inert data.
- Provider error bodies containing confidential sentinels never reach logs or clients.
- Pooled database connection reuse after commit, rollback, and exception.

## Reliability/operations suite

- API/worker/database restart at every durable boundary.
- Expired leases, retry exhaustion, dead-letter/operator state, and safe manual retry.
- Outbox duplicate dispatch and unsupported event handling.
- Object present/database missing and database present/object missing reconciliation.
- Backup PostgreSQL and authoritative objects, restore into isolation, verify manifests/hashes,
  reapply current authorization, and keep outbound integrations disabled.
- Queue age, processing duration, failure counts, gap counts, retry counts, and integrity mismatch
  signals contain no content.
- Health/readiness distinguish process health from dependency/configuration readiness.

## Required evals

Activate deterministic blocking evals for:

- transcript import round-trip: 100%;
- canonical version reproduction: 100%;
- job idempotency: 100%;
- unauthorized ingestion/publication access: 0 results;
- cleanup policy conformance: 100%;
- no fabricated speaker/timestamp metadata: 100%.

Do not weaken thresholds to make an implementation pass.

## Gate S checklist

- [ ] Actual web transcript-upload journey passes.
- [ ] Actual web audio-upload journey passes with synthetic transcription.
- [ ] Actual Electron synthetic recording journey passes.
- [ ] Restart/interruption/retry scenarios pass.
- [ ] Restricted-role authorization and RLS suites pass.
- [ ] Canonical bytes reproduce exactly without mandatory audio.
- [ ] Backup/restore smoke passes with database and objects.
- [ ] Logs/errors/audit contain no confidential fixture bodies or secrets.
- [ ] Contract generation has no drift.
- [ ] Clean database migration reaches head.
- [ ] `./scripts/pr-ready.sh` exits 0.
- [ ] README and runbooks accurately describe what is synthetic and what remains gated.

---

# Batch 8 — Recall R1 feasibility gate

## Objective

Establish whether Recall Desktop SDK can supply the required audio-only capture on the intended
managed desktop/meeting-client matrix. This is an experiment and evidence task, not permission to
record confidential calls.

## Required human inputs

- Isolated Recall workspace and region approved for fictional testing.
- Workspace API key and webhook signing secret supplied through secret injection.
- Public HTTPS webhook test endpoint.
- Intended Windows/macOS versions and meeting clients.
- Recording-consent approval for the scripted test participants.

## Steps

Follow `docs/integrations/recall.md` exactly:

1. Pin an exact supported Electron and `@recallai/desktop-sdk` version.
2. Create the server-side SDK upload and obtain only the scoped desktop credential.
3. Record a one-minute scripted fictional two-person call in audio-only mode.
4. Verify local and remote voices, completion callback signature, event shape, and deduplication.
5. Resolve the documented audio media object without assuming a video example field.
6. Copy original bytes to independent private test storage.
7. Re-read/hash/decode the stored audio and verify duration and both voices.
8. Test disconnect, application restart, expired media URL, duplicate callback, delayed readiness,
   and missing audio.
9. Exercise provider deletion and document observed retention/residual behavior.
10. Record sanitized evidence using `docs/integrations/EVIDENCE_TEMPLATE.md`.

## Gate

Do not implement or merge the production Recall connector unless R1 is PASS. If it fails, record the
specific failing requirement and propose alternatives through an ADR; do not silently adopt bots,
video, or Recall transcription.

---

# Batch 9 — live Recall connector

## Objective

Replace the synthetic capture provider with a live Recall adapter without changing domain contracts.

## Steps

1. Implement server-side create-session calls with durable operation identity.
2. Issue only the scoped upload token/grant required by the desktop SDK.
3. Integrate the pinned SDK in Electron behind the existing IPC/capture abstraction.
4. Implement audio-only configuration proven by R1.
5. Implement raw-body webhook signature/timestamp verification with a pinned verifier.
6. Deduplicate webhook events durably.
7. Resolve media only from the allowlisted Recall API/host behavior proven in R1.
8. Never forward a bearer/API token to a provider-supplied arbitrary URL.
9. Stream original audio to private storage, hash/read back, and only then mark `original_stored`.
10. Reconcile unknown create/completion/copy outcomes before retrying.
11. Implement provider cleanup jobs and explicit pending/failed cleanup states.
12. Preserve the synthetic adapter for CI and fault injection.

## Tests and gate

- Contract tests run against synthetic recorded responses.
- Live opt-in smoke repeats R1 positive and negative controls.
- Unauthorized desktop/user/project cannot obtain an upload grant.
- Revocation during capture prevents final delivery while preserving recoverable governed bytes.
- Gate passes only when live fictional audio reaches independently stored accepted source state.

---

# Batch 10 — production object storage adapter

## Objective

Move authoritative source/version objects from local storage to the locked private Backblaze B2
adapter while preserving `ObjectStorage` semantics.

## Required human inputs

- Approved B2 region and private test bucket.
- Scoped runtime key with only required read/write/list capabilities.
- Separate purge identity.
- Independent backup bucket/identity and agreed encryption boundary.

## Steps

1. Pin the selected S3-compatible client.
2. Implement immutable unique-key put, pinned-version stat/read/range-read, multipart resume/abort,
   and version-specific governed purge.
3. Compute application SHA-256 independently of provider ETags.
4. Persist bucket/key/version only in private storage metadata; never expose it publicly.
5. Reconcile uncertain completion by stat/read/hash before another write.
6. Deny anonymous, unrelated-prefix, and unrelated-bucket access.
7. Prove the runtime identity cannot permanently purge authoritative versions.
8. Copy backups across the independent administrative boundary and run hash-verified restore.
9. Keep the local adapter for development and deterministic CI.
10. Record sanitized live smoke evidence per `docs/integrations/backblaze-b2.md`.

## Gate

All source/raw/canonical objects used by a fictional live-provider run are private, version-pinned,
hash-verifiable, independently backed up, and restorable without broad runtime deletion rights.

---

# Batch 11 — live AssemblyAI connector

## Objective

Transcribe independently stored fictional audio through the approved AssemblyAI account using the
same durable pipeline proven synthetically.

## Required human inputs

- Approved account/region and API base URL.
- API key injected into the worker only.
- Confirmed access to `universal-3-5-pro`.
- Training opt-out, TTL, upload/result deletion, quota, and concurrency evidence.

## Steps

1. Implement byte upload from authorized private storage; never make the source public.
2. Submit with the pinned model and `speaker_labels=true`.
3. Persist submission intent and provider ID durably.
4. Poll with scheduled jobs and bounded backoff; honor valid throttling guidance.
5. Store/re-read/hash the complete raw provider response before parsing.
6. Validate provider schema and sanitize failures.
7. Reconcile speaker/timestamp data without invention.
8. Route the result through the same cleanup/approval/publication services as synthetic data.
9. Implement upload/result deletion cleanup and abandoned-resource reconciliation.
10. Prove repeated operation keys cannot create a second paid submission.
11. Preserve synthetic adapter coverage for all fault states.
12. Record sanitized live evidence under the integration guide.

## Gate

A short fictional two-speaker recording travels from independently stored original audio to a
published reproducible transcript, while raw provider bytes, model/config provenance, retries, and
cleanup state remain durable.

---

# Batch 12 — production identity and confidential-pilot gate

## Objective

Complete Phase 0 decisions and Phase 1 production identity/security requirements before allowing
confidential calls.

## Required human decisions

- Entra tenant, app registration, employee assignment mechanism, MFA/Conditional Access, guest
  policy, lifecycle owner, and credential method.
- Approved Recall, AssemblyAI, storage, compute, and backup regions/processors.
- Provider retention/training/deletion findings.
- Recording-consent text and acknowledgement process.
- Audio/transcript retention, deletion, holds, and owner.
- Supported managed-device and meeting-client matrix.
- Capacity, quotas, cost ceiling, RPO, RTO, incident ownership, and escalation.

## Steps

1. Implement the single-tenant Entra authorization-code/PKCE adapter behind `IdentityProvider`.
2. Map exact tenant/object ID to the existing immutable internal user UUID.
3. Require assigned/enabled employees; reject guests, other tenants, unassigned, disabled, expired,
   wrong-audience, wrong-issuer, and replayed callbacks.
4. Verify login, logout, session rotation, CSRF, idle/absolute expiry, internal disable, and directory
   revocation behavior.
5. Ensure administrative identity does not grant project content access.
6. Disable test-only magic-link identity in staging/production. Graph mail may remain only where the
   approved environment policy permits it.
7. Configure consent-policy version and prevent recording/document creation without acknowledgement.
8. Configure approved retention/hold/deletion policy; do not use invented defaults.
9. Configure production secret injection and rotation; no `.env` secrets on deployed hosts.
10. Add dashboards/alerts for API failure, auth denial anomalies, recording gaps, queue age, provider
    failure, index lag, storage saturation, backup failure, and integrity mismatch.
11. Complete and exercise onboarding/offboarding, compromised account, recorder recovery, stuck
    transcription, credential rotation, source-integrity incident, backup/restore, and rollback
    runbooks.
12. Run a full fictional production-like acceptance before requesting confidential-pilot approval.
13. Obtain written owner/security approval for Gate C.

## Gate

Confidential traffic remains prohibited until the complete Gate C checklist has human approval.

---

# Required test matrix across all batches

For each new endpoint, service, job handler, IPC command, and connector, cover as applicable:

| Area | Required cases |
| --- | --- |
| Happy path | Authorized source reaches the expected durable next state |
| Input | Empty, malformed, oversized, unsupported, corrupt, and boundary values |
| Authorization | Reader/contributor/owner/reviewer; disabled user; disabled membership |
| Isolation | Wrong tenant, workspace, project, document, source, job, draft, version, capture |
| Concurrency | Duplicate request, same/different idempotency payload, stale revision/hash |
| Reliability | Timeout before/after side effect, restart, lease loss, retry exhaustion |
| Provider | Authentication, permission, throttling, unavailable, invalid response, unknown outcome |
| Integrity | Wrong source/raw/canonical hash, missing object, UTF-8/offset corruption |
| Privacy | Confidential sentinels absent from logs/errors/audit/metrics |
| Recovery | Interrupted upload/capture, resume, abort, orphan cleanup, backup/restore |

Use restricted database roles in integration tests. A test using the schema owner or administrator
does not prove runtime authorization.

# Verification commands

Run focused tests during each batch. Before every batch is declared complete, run from Git Bash:

```bash
./scripts/setup.sh
./scripts/services.sh up
./scripts/migrate.sh
./scripts/check.sh
./scripts/test-integration.sh
./scripts/check-migrations.sh
./scripts/backup-restore-smoke.sh
./scripts/eval.sh pr
./scripts/pr-ready.sh
```

For Electron batches, also build/package and manually exercise the supported development OS using
fictional audio. For live-provider batches, run only the explicitly documented opt-in smoke command
with isolated credentials and record sanitized evidence outside normal CI.

# Final definition of done

Phase 0–2 may be called a fully functional synthetic MVP only when Gate S passes. It may be called a
live-provider fictional-data MVP only when Gate L passes. It may handle confidential pilot data only
when Gate C is approved.

The final handoff must use the format in `AGENTS.md` and include:

```text
IMPLEMENTED
FILES CHANGED
INTERFACES ADDED/CHANGED
DATABASE MIGRATIONS
TESTS
EVALS / ACCEPTANCE GATES
VERIFICATION COMMANDS
KNOWN LIMITATIONS
NEXT DEPENDENCIES
ARCHITECTURAL DECISIONS
```

The handoff must explicitly say which of Gate S, Gate L, and Gate C passed. It must not describe
documentation review, mocks, or synthetic tests as live-provider evidence.

## Completion notes

Batch 0 baseline verification and the proposed interface/state checkpoint are recorded in
`005-phase-2-contract-checkpoint.md`. Product-owner confirmation was received on 2026-09-25;
Batch 1 contract, migration, and route implementation is authorized. Live-provider and confidential
data gates remain separate and are not approved by this checkpoint.

Credential-free implementation checkpoint, 2026-09-25:

- Batches 1, 2, 4, 5, and the credential-free portions of Batches 6–7 are implemented through the
  approved `foundation-v1` HTTP contract and migrations `0008_ingestion_workflow` and
  `0009_ingestion_operations`.
- The web workflow creates meetings, uploads supported audio/transcript sources, displays durable
  processing/draft state, creates immutable corrections, approves/publishes, and downloads
  deterministic TXT, Markdown, and JSON output.
- Electron uses the persisted capture API when configured, retains restart recovery metadata, mixes
  microphone and desktop audio through `MediaRecorder`, uploads bounded WebM chunks, and retains a
  synthetic fallback. The compiled app launched successfully on Windows with a responsive
  `Verelo Capture` window; an operator must still exercise actual microphone/system-audio consent
  and a real meeting client on each supported OS before treating that client/OS as verified.
- WAV, MP3, M4A, and WebM are decoder-probed through pinned PyAV. TXT, VTT, SRT, and JSON continue to
  use deterministic parsers. Immutable originals, raw provider bytes, parsed artifacts, canonical
  drafts, approvals, publications, passages, jobs, audit, and outbox lineage are retained.
- Durable operation keys/payload hashes cover upload finalization, synthetic transcription
  submission, raw-result storage, cleanup, automatic approval, publication, retry, and abort.
- The durable worker host now runs bounded scoped job claims and outbox dispatch with graceful
  shutdown. Phase 3 passage embedding remains an explicit safe `phase3-deferred` result.
- `./scripts/pr-ready.sh`, `./scripts/check-migrations.sh`, and
  `./scripts/backup-restore-smoke.sh` pass. The suite includes 69 unit/architecture/contract tests,
  127 schema subtests, 9 restricted-role integration tests, 7 web/Electron tests, clean frontend
  builds, and the PR evaluation smoke suite.

Gate status:

- Gate S: implementation and automated acceptance pass; final manual device/client capture matrix is
  pending because microphone/system-audio permission interaction is operator-controlled.
- Gate L: NOT RUN. Recall R1, live private storage, and AssemblyAI fictional-data smoke evidence are
  required before live connectors may be activated.
- Gate C: NOT APPROVED. Company identity, processor/region, consent, retention, recovery, and security
  approvals remain human-owned prerequisites for confidential traffic.
