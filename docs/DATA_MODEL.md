# Data model contract

Status: Phase 0–2 MVP schema through migration `0009_ingestion_operations`; later entities remain reserved.
Authority: `ARCHITECTURE.md` §§8–12, 20–25, 35 and `PROJECT_SPEC.md` §§8, 12–14. Architecture wins conflicts. API shapes are defined in `contracts/models.py`; database models and migrations must implement this document, not be generated from public DTOs.

## Naming and common rules

- UUID identifiers; PostgreSQL `uuid`, never names/emails as keys. Internal primary keys are `id`; public fields name the entity (`project_id`, `document_id`).
- `tenant_id` is canonical. The spec's `organization_id` denotes the same scope, not a second entity. `documents`/`document_id` replace the spec's `meetings`/`meeting_id`. `source_asset_id` identifies bytes; it is not a document ID. Do not add legacy aliases to new APIs.
- Metadata timestamps are UTC `timestamptz`, serialized as RFC 3339 with a UTC offset. Media times are integer milliseconds; canonical text positions are UTF-8 byte offsets, start inclusive/end exclusive.
- Scope columns are non-null except for explicitly tenant-wide records. Derive scope from authenticated identity and authorized parents. Never accept scope/owner/creator fields in create bodies.
- Every scoped table has `UNIQUE (tenant_id, id)`; workspace-owned tables also have `UNIQUE (tenant_id, workspace_id, id)`; project-owned tables also have `UNIQUE (tenant_id, workspace_id, project_id, id)`. Add referenced composite unique keys before creating composite foreign keys.
- Child FKs include the full parent scope, not just a globally unique ID. UUID uniqueness alone does not stop cross-project association. Index FK columns used for joins and policy lookups.
- All FKs default to `ON DELETE RESTRICT`. No broad cascade from tenant, project, user, or document. Governed purge must explicitly remove dependent records and external copies in order. Do not physically delete referenced users when disabling an employee.
- All text bounds below are initial engineering limits where the spec requires bounded input but gives no number. Keep Python contracts and migrations consistent. Names/titles must contain a non-whitespace character; do not silently trim stored values.

## First implementation slice

This slice creates/reads project and document metadata, resolves current identity, and changes project membership. It does not upload bytes, transcribe, publish evidence, export, or claim the complete architecture Phase 1 gate has passed. Tenant, default workspace, enabled employee records, and project-creation capability are provisioned out of band; there is no public signup/provisioning endpoint.

Common columns: `id uuid PK`, `created_at timestamptz NOT NULL DEFAULT now()`. Mutable tables additionally have `updated_at timestamptz NOT NULL`; repositories update it in the same transaction. UUIDs and ownership scope never change.

Unless explicitly marked nullable, every listed column is NOT NULL. Mutable tables here are tenants, workspaces, users, projects, memberships and documents; audit records are append-only, while outbox dispatch bookkeeping is the only mutable part of its record. All foreign-key scope/actor columns use `uuid`, all counters/revisions use nonnegative `bigint` (membership revision >= 1), and all timestamps use `timestamptz`. Outbox schema version is positive. `actor_kind` is `employee` or `service`; audit outcome is `allowed` or `denied`. For scoped audit/outbox records, document scope requires project/workspace scope and project scope requires workspace scope; enforce composite parent references as above. Service actor IDs refer to provisioned workload identities; employee actor IDs refer to same-tenant users.

Tenant policy configuration stores explicit employee UUID grants for `projects:create` in this slice; it is resolved server-side on each project-creation request. Missing configuration/grant denies creation. This avoids inventing organization-wide creation rights or adding a public capability-management API.

| Table | Required additional columns | Constraints / relationships / indexes |
|---|---|---|
| `tenants` | `entra_tenant_id uuid NULL`, `policy_config_ref text`, `region text` | Entra tenant unique when configured; local magic-link tenants leave it null. Config reference/region provisioned, no credentials or invented company-policy defaults. |
| `workspaces` | `tenant_id uuid`, `name varchar(200)`, `is_default boolean` | FK tenant; partial unique `(tenant_id) WHERE is_default`; provisioning must create exactly one default, transactional service check prevents deleting/disabling it. |
| `users` | `tenant_id uuid`, `entra_object_id uuid NULL`, `display_name varchar(200)`, `email varchar(320)`, `enabled boolean`, `authorization_epoch bigint DEFAULT 0` | Entra object ID is a compatibility field and unique when present; identity accounts are authoritative. Email is display-only here, not a key; epoch >= 0. Tenant FK. |
| `identity_accounts` | `tenant_id`, `workspace_id`, `user_id`, `provider`, immutable `subject`, optional normalized login email, enabled state | Provider-to-internal-user mapping. Magic-link email is a unique mutable locator; internal user UUID is the principal. Entra uses immutable tenant/object identity. |
| `magic_link_challenges`, `authentication_events` | Hashed single-use credential and content-free authentication metadata | Private pre-authentication boundary; no plaintext token, email, cookie, or CSRF value. Ten-minute expiry and atomic consume/session issuance. |
| `projects` | `tenant_id uuid`, `workspace_id uuid`, `name varchar(200)`, `owner_user_id uuid`, `retention_policy_ref text`, `transcript_approval_policy_ref text`, `authorization_epoch bigint DEFAULT 0`, `state text DEFAULT 'active'` | Composite workspace FK; `(tenant_id, owner_user_id)` user FK. State `active` or `tombstoned` in this slice. Owner must be an enabled owner membership in same project. Index `(tenant_id, workspace_id, created_at, id)` for lists. Policy refs come from provisioned configuration. |
| `project_memberships` | `tenant_id uuid`, `workspace_id uuid`, `project_id uuid`, `user_id uuid`, `role text`, `enabled boolean`, `revision bigint DEFAULT 1` | Full-scope project FK; tenant/user FK; unique `(tenant_id, project_id, user_id)`; role `reader`, `contributor`, `project_owner`; revision >= 1. Index `(tenant_id, user_id, enabled, project_id)`. |
| `documents` | `tenant_id uuid`, `workspace_id uuid`, `project_id uuid`, `title varchar(300)`, `meeting_date timestamptz`, `language varchar(35)`, `created_by uuid`, `consent_policy_version varchar(100)`, `consent_acknowledged_by uuid`, `consent_acknowledged_at timestamptz`, `state text DEFAULT 'created'` | Full-scope project FK; tenant/actor FKs. Consent is recorded from authenticated actor and server clock; policy version must match provisioned policy. State `created` or `tombstoned` for this slice. Index `(tenant_id, workspace_id, project_id, created_at, id)`. |
| `audit_events` | tenant, optional workspace/project/document scope, `actor_kind text`, `actor_id uuid`, `action text`, `outcome text`, `request_id varchar(128)`, `authorization_epoch bigint`, `occurred_at timestamptz` | Append-only through restricted writer; no titles, emails, transcript text, request bodies, or credentials. Scope consistency enforced. Index scope/time. Preserve non-content identity references under governed deletion. |
| `outbox_events` | tenant/workspace/project scope, optional document scope, `aggregate_id uuid`, `event_type text`, `schema_version integer`, `payload jsonb`, `created_at`, `dispatched_at timestamptz NULL` | ID is event ID; validated envelope only, IDs/safe metadata. Immutable envelope; dispatcher may update dispatch bookkeeping. Partial index on undispatched rows. Domain mutation and event insert commit together. |

Project creation inserts project and creator's owner membership atomically, after capability check. The owner invariant is checked at transaction commit (a deferred constraint trigger is suitable); partial state must never commit. Membership mutations increment membership revision and project authorization epoch and insert audit plus `access.changed` outbox event in one transaction. In this slice, reject demotion/removal of `owner_user_id`; ownership transfer is a separate deferred API. Additional owner memberships are allowed. Disabled users cannot access content even if their membership remains enabled.

`documents.active_transcript_version_id` is nullable until publication and has a composite FK proving
the version belongs to the same document. Publication changes it only in the atomic publication
transaction; no placeholder version or synthetic published state is inserted.

## Implemented Phase 2 workflow records

`ingestions` is the mutable coordinator record for one immutable source attempt. It carries full
tenant/workspace/project/document scope, creator, source kind/name/media declaration, expected and
uploaded size/hash, acknowledged chunk count, source/draft references, canonical workflow state and
stage, safe failure/retry fields, operation/payload identity, gap count, revision, and timestamps.
The state constraint is the approved state machine in plan 005. Operation key is unique per project.

`ingestion_chunks` is append-only, ordered by ingestion/sequence, with immutable object reference,
byte length, SHA-256, and full scope. Finalization requires a contiguous sequence plus exact aggregate
length/hash before creating an accepted source asset. `capture_sessions.ingestion_id` joins completed
recording recovery to this same workflow. `raw_transcripts.ingestion_id` provides provenance from
attempt to immutable raw provider bytes. Both are nullable only for records predating migration 0008.

`ingestion_operations` durably binds each finalization, provider-stage, publication, retry, or abort
operation key to its scoped ingestion, action, payload hash, and outcome reference. A same-key replay
must have the same payload; a conflicting payload is rejected without changing workflow state.

`source_assets`, `raw_transcripts`, `transcript_versions`, `transcript_approvals`, `passages`, and
`jobs` implement the immutable publication graph. Draft correction creates a new version; it never
updates canonical bytes. Approval binds version and hash. Publication updates version state,
document active pointer, ingestion state, passages, index intents, audit, and outbox in one database
transaction after content-addressed objects have been verified.

## Reserved later entities and constraints

These requirements are extracted from architecture §9 and spec §8.2. Physical columns, indexes, and state enums beyond the stated invariants must be finalized in that phase's contract update before migration code. Do not create all these tables during foundation work.

| Entities | Parent scope and required invariants | Phase |
|---|---|---|
| `speakers`, `word_alignments` | Version scope; ordinal unique within version. Byte bounds fit canonical object and UTF-8 boundaries; nullable speaker/timing. The MVP preserves reconciled segment metadata in the immutable parsed object/manifest; normalized speaker/alignment tables remain a later refinement. | 2 refinement |
| `passage_indexes` | Same-scope passage/version; unique passage/model/generation; embedding dimension and generation pinned. Derived/rebuildable, never quote source. | 2–3 |
| `evidence_runs`, `evidence_candidates` | Principal and project scope; version/index generation/authorization epoch/expiry sealed server-side. Candidate ID unique in run and FK to permitted same-project passage/version. | 3 |
| `source_spans` | Same-scope passage/version, absolute byte bounds/hash; server-issued and immutable, optional audio anchor and origin selection. | 3 |
| `saved_answers`, `quote_collections`, `collection_items` | Project scope; pinned span references, current authorization and approval on read. Collection revisions; no editable quote copies. | 3 / 5 |
| `annotations`, `annotation_revisions` | Document/actor, recording-time anchor, visibility, revision; unique actor/client event ID and annotation/revision. Private notes never become shared evidence. | 5 |
| `jobs` | Scoped service action, aggregate/version, unique operation key, lease owner/expiry, attempts, next attempt, provider job reference, safe error; retry is idempotent. | 1 |
| `export_destinations`, `export_manifests` | Project destination with credential reference and verified ACL fingerprint; unique version/destination/format, hashes/item IDs/ETags/status; no credential values. | 4 |
| `retention_policies`, `holds`, `deletion_requests` | Scoped policy/hold/request, state and per-system completion. Holds prevent purge; deletion ledger survives restore. | 6; configuration refs reserved earlier |
| Transcript restrictions (`transcript_acl` in spec) | Document grants intersect project membership; cannot expand access beyond the project. Exact schema deferred. | 6 |

## Source integrity and deletion

Canonical bytes are UTF-8 without BOM, LF endings, unchanged after hash-bound approval. Publication freezes passages, checks expected active parent/index readiness, and atomically updates active pointer plus outbox. Normal search uses active approved published versions. Saved citations remain pinned; revoked/deleted evidence becomes unavailable, never silently rebound.

Policy deletion is an explicit exception to retention of immutable artifacts, not permission to edit them. Tombstone first and immediately exclude content from retrieval, rendering, playback, workers and exports. Purge only after hold/policy checks; reconcile blobs, database rows, indexes, caches, jobs, providers, exports and backup expiry. No DELETE endpoint is included in foundation. Foundation tests may reset a disposable database; production deletion must not use that mechanism. Company retention durations remain open under architecture §38.

## Required implementation evidence

Migrations must prove composite FK rejection of cross-tenant/workspace/project links, owner invariants, unique memberships, revision/epoch increments, and rollback of audit/outbox with failed mutations. Run RLS tests as non-owner runtime roles, including connection-pool reuse. Schema/DTO tests alone do not prove database isolation.
