# API and service contracts

Authority: `ARCHITECTURE.md` §§7–16, 20–26, 29; `PROJECT_SPEC.md` §§8–10, 12. Architecture governs names and boundaries. This document specifies foundation v1 only; no endpoint is implemented by publishing its schema.

## One generation workflow

Hand-edit `contracts/models.py` for wire models and semantic validators, and `contracts/http.py` for the initial operation registry. Run `python scripts/generate-contracts.py` to emit OpenAPI 3.1, JSON Schema 2020-12, and TypeScript. Generated files carry notices; never edit them. See `schemas/README.md` for setup/check commands and `docs/decisions/ADR-002-contract-generation.md` for the decision.

Future FastAPI routes must import these models directly, use the registered operation IDs/statuses, and expose an OpenAPI surface tested against this registry. Do not create a second set of request/response Pydantic models. A runtime conformance test becomes mandatory in the PR introducing routes. TypeScript types describe shape, not authorization, cross-field validation, or evidence authenticity; the server remains authoritative.

## Scope and refinements

The first slice supports an authenticated enabled employee, projects, membership and document metadata. It needs real authorization/RLS before any externally accessible deployment; tests may inject identities under SECURITY.md. It is a subset of Phase 1, not its completion gate.

The spec leaves pagination encoding, length limits, project-creation entitlement, and membership revision mechanics unspecified. The concrete conventions below are engineering refinements, not new product features. Project creation requires explicit server-provisioned `projects:create`; provisioning policy remains with the company. New project creator becomes its owner. Tenant/workspace/user provisioning and capability administration have no public endpoint in this slice.

Use `/documents` and `document_id`, per architecture §§8, 24, rather than the spec's older `/meetings` routes. There are no aliases or duplicate IDs. Foundation adds read/list metadata routes to make the documented create/read/list slice usable.

## Trusted authentication context

`AuthContext` is internal, never a request body or trusted header. It contains `principal_kind`, `principal_id`, `tenant_id`, `workspace_id`, `authorization_epoch`, `capabilities`, and `request_id`. An employee principal ID is the internal user UUID; service IDs are provisioned workload identities. Identity/session resolution validates Entra and derives scope server-side. Services cannot call employee-only foundation HTTP endpoints.

Workspace is the provisioned default workspace in this slice. Current user enabled state, membership, project epoch, and resource state are checked per operation, not trusted from an old session snapshot. Clients cannot choose tenant/workspace/creator/owner through body, query, cookie contents, or arbitrary headers.

Cookie: `kanior_session`, opaque server-side session, Secure/HttpOnly/SameSite=Lax. Mutations require `X-CSRF-Token` bound to session and an allowed Origin; strict CORS. `/me` supplies a CSRF token over the authenticated no-store response. It is not an access token and never enters telemetry. Login/callback/logout transport is deferred to identity implementation; it must satisfy Entra/PKCE/session rules, not create public signup.

## Foundation operations

All paths below have `/api/v1` prefix. Request/response field definitions and exact limits are generated in `schemas/openapi/foundation-v1.json`.

| Operation ID / method and path | Input → success | Required authorization / effects |
|---|---|---|
| `get_me` / `GET /me` | Session → 200 `MeResponse` | Enabled assigned employee. Identity, server-provisioned capabilities, default workspace and CSRF token; no project content or global admin content grant. |
| `list_projects` / `GET /projects` | `limit`, `cursor` → 200 `ProjectPage` | Only active projects with current enabled membership in tenant/workspace. No unauthorized totals. |
| `create_project` / `POST /projects` | `ProjectCreate` → 201 `Project` | Explicit `projects:create`; default configured workspace/policies. Insert creator owner membership atomically, audit; return Location. |
| `get_project` / `GET /projects/{project_id}` | UUID → 200 `Project` | Current project member. |
| `get_project_member` / `GET /projects/{project_id}/members/{user_id}` | UUIDs → 200 `Membership` | Current owner; read revision for CAS/retry reconciliation. Missing membership or inaccessible target returns 404. |
| `set_project_member` / `PUT /projects/{project_id}/members/{user_id}` | `MembershipPut` → 200 `Membership` | Current owner; target is enabled same-tenant employee. Revision compare-and-swap, audit, epoch increment, outbox `access.changed`. Owner-user demotion/removal rejected. |
| `list_documents` / `GET /projects/{project_id}/documents` | UUID, page → 200 `DocumentPage` | Project reader or higher; active/non-tombstoned metadata only. |
| `create_document` / `POST /projects/{project_id}/documents` | `DocumentCreate` → 201 `Document` | Contributor or owner. Consent acknowledged true, current configured policy version, server actor/time; audit and Location. No upload or external job. |
| `get_document` / `GET /documents/{document_id}` | UUID → 200 `Document` | Derive project from row and require current membership. Never load globally then return metadata before authorization. |

Membership `expected_revision=0` means insert only if absent. Existing rows require their exact revision; success increments it, including enable/disable changes. Concurrency conflicts return 409. `enabled=false` keeps the record and blocks access. Creation of another owner membership is permitted; changing the designated owner is deferred. After an uncertain response, read current membership before retrying; no public member-list endpoint is promised yet.

## Errors, pagination, retries and tracing

All errors use exactly `{code, message, request_id, retryable}`, including framework validation errors. Stable codes: `unauthenticated` (401), `forbidden` (403 action/CSRF denial without resource disclosure), `not_found` (404 missing or inaccessible ID), `conflict` (409 revision/state), `payload_too_large` (413), `invalid_input` (422), `rate_limited` (429), `dependency_unavailable` (503), `internal_error` (500). Unexpected errors are generic and non-retryable until reconciled. Never echo provider bodies, validation input values, tokens, document titles or signed URLs. 429/503 retryable responses include `Retry-After` seconds. Authenticate before protected resource lookup; inaccessible parent/resource/target user returns the same 404 shape. Authorization to see a resource is checked before action-specific 403.

All responses include server-generated `X-Request-ID` (UUID string) matching context/error body and `Cache-Control: no-store`. Accept no client-controlled authority through tracing. Propagate request ID as trace ID into audit, outbox and scoped jobs; do not log confidential request bodies.

Lists return `{items, next_cursor}`; null cursor means end. Default limit 50, minimum 1, maximum 100. Order ascending by immutable `(created_at, id)`; use keyset comparison, never offset pagination. Cursor is opaque, authenticated, bound to principal, tenant/workspace, route/project, sort/filter context and original upper `(created_at, id)` watermark. Reject malformed/tampered/wrong-context cursors with 422. Refresh authorization on every page; watermark prevents later-created rows entering this traversal but is not an authorization snapshot. No total counts. Return a cursor only if an extra authorized row exists beyond the page.

Foundation POST creation is deliberately not automatically retryable: a lost response requires reconciliation, not blind re-submit. No `Idempotency-Key` support is advertised on these metadata endpoints. Membership uses revision CAS. The spec mandates scoped durable keys for upload finalization, transcription submission, publication, export and annotation creation; those future operations must persist `(principal, action, resource, key)`, payload fingerprint, outcome and retry-window expiry atomically with their effect. Same key/different payload returns 409, replay reauthorizes, concurrent duplicates cannot double-apply. Retry-window durations must be finalized with those contracts; no guessed TTL is committed here.

## Internal foundation services

These signatures are conceptual Python interfaces, not additional HTTP endpoints. Methods use the same DTOs and typed failure codes; repositories receive trusted context and never infer it from DTO fields.

```text
IdentityService.resolve_session(opaque_session) -> AuthContext
AuthorizationService.authorize(context, action, resource_ref) -> allow or typed denial
ProjectService.create(context, ProjectCreate) -> Project
ProjectService.get(context, project_id) -> Project
ProjectService.list(context, limit, cursor) -> ProjectPage
MembershipService.get(context, project_id, user_id) -> Membership  # owner-only
MembershipService.set(context, project_id, user_id, MembershipPut) -> Membership
DocumentService.create(context, project_id, DocumentCreate) -> Document
DocumentService.get(context, document_id) -> Document
DocumentService.list(context, project_id, limit, cursor) -> DocumentPage
```

Service layer owns transaction, authorization and audit/outbox atomicity; route handlers do not commit intermediate state. Read DTOs contain scoped metadata, never storage keys or secret configuration. Mutation fails if required audit cannot persist. Business validation includes active project, same-scope target, configured consent policy, owner preservation and current membership; schema acceptance alone cannot authorize a call.

## Imports, selection and events: reserved contracts

`transcript-v1.schema.json` extracts spec §8.4: nonempty ordered segments, exact text, optional nullable speaker/timing, paired nonnegative times with end >= start. Unknown fields/versions rejected. Join text with exactly one LF; no trimming, quote offsets or URLs accepted. Timing overlap is allowed. Schema handles shapes/pairing; Python semantic validator handles ordering of time values. Language follows the bounded tag syntax in the model; provider language support remains adapter-specific.

Selection schemas extract spec §9.5 and architecture §14. ID mode is zero to eight unique UUIDs. Precise mode is separate, zero to eight unique selection objects; validate increasing code-point bounds, then require sealed-run membership, current authorization/approval, exact supplied passage length, word/sentence/grapheme boundaries and UTF-8 conversion at runtime. No generated quote text, attribution or span IDs accepted from model. These files reserve Phase 3 boundaries; they do not implement retrieval or rendering.

Events are identifiers-only envelopes with event/schema version, tenant/workspace/project scope, optional document (required for document events), aggregate ID, UTC time, trace ID and a closed typed `data` object. `access.changed` is defined now for membership mutations. `transcript.published` is reserved for Phase 2. Aggregate ID must match project or document respectively. JSON Schema cannot prove referential ownership; consumers verify scope and current aggregate state. Consumers deduplicate by event ID and operation key, use revision/epoch to reject stale work, and never assume global ordering. Other event names in spec §10.1 remain provisional, not an open arbitrary payload escape hatch.

Later upload, jobs, approval/publication, quote response, synthesis, export, annotations and governance APIs remain provisional. Finalize each before implementation using the existing spec; do not generate permissive placeholder endpoints now.

## Foundation acceptance gate

Contract validation and generated-artifact drift checks must pass. Implementation must additionally demonstrate project/document create-read-list, membership CAS and revocation, direct API cross-tenant/workspace/project denial, non-disclosing errors, CSRF, bounded pagination, composite FK/RLS enforcement as runtime role, no secret/content logging, and atomic audit/outbox rollback. See spec AT-01/02/12/15 and architecture §29. Schemas alone do not establish those runtime guarantees.
