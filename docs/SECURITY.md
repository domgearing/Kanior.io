# Security implementation contract

Authority: `ARCHITECTURE.md` §§3, 9, 13–16, 19–22, 35, 38–39 and `PROJECT_SPEC.md` §12. This is an implementation contract, not evidence of deployed security controls.

## Identity and sessions

Single-tenant Entra authorization-code flow with PKCE. Validate issuer, audience, signature, expiry, nonce/state, exact tenant, enabled employee assignment and enabled internal user. Reject guests, unassigned/disabled employees and other tenants. Email suffix is only a secondary check; stable identity is Entra tenant/object ID. Initial session defaults from spec: 30-minute idle, eight-hour absolute; recording never bypasses disable checks. Emergency disable is immediate; lifecycle propagation target <=5 minutes.

Use server-held opaque sessions and the cookie/CSRF conventions in API_CONTRACTS.md. Recheck enabled user and resource access each request and again before quote delivery. Never trust client-selected principal/scope, cached session roles, or a guessed ID. No public signup, consumer-account fallback or provider secrets in browser/Electron bundles.

## Role/action matrix

Rights apply only to active same-scope resources and enabled memberships. Tenant administrator/auditor capabilities are separate from project membership; roles do not implicitly override each other.

| Action | Reader | Contributor | Project owner | Tenant administrator without membership | Compliance auditor without content grant |
|---|---|---|---|---|---|
| Read/list project/document, search/replay | Yes | Yes | Yes | No | No |
| Create document, record/upload, propose correction | No | Yes | Yes | No | No |
| Personal notes/collections (later) | Yes | Yes | Yes | No | No |
| Shared annotations (later) | No | Yes | Yes | No | No |
| Change project membership | No | No | Yes | No | No |
| Approve/revoke/publish transcript (later) | Explicit reviewer capability for approval only | Explicit reviewer capability for approval only | Yes | No | No |
| Approved project export / request deletion (later) | No | No | Yes | No | No |
| Configure identities/connectors/policies | No | No | No implicit grant | Yes | No |
| Read audit metadata | No implicit grant | No implicit grant | Only separately authorized scope | Only separately authorized scope | Assigned audit scope only |

Project creation uses explicit provisioned `projects:create` capability, not an assumed role inheritance. Creator becomes owner in the same transaction. Foundation cannot demote/disable the designated owner membership; ownership transfer needs a separate contract. An enabled tenant administrator can be separately granted project membership; administrative status alone never admits content access.

Controlled-cleanup service approval is limited to unchanged text or validated allowlisted edits under versioned project policy. It cannot approve wording corrections. Transcript ACLs in production intersect project membership; no document grant can admit an outsider. Break-glass access requires explicit time-limited assignment and durable audit.

## Database roles and transaction context

Role names below are initial implementation conventions; credentials are distinct in every environment.

| Role | Allowed | Forbidden |
|---|---|---|
| `kanior_migrator` | Own schema/tables, run reviewed Alembic migrations | API/worker connections; credentials in runtime environment |
| `kanior_api` | Minimum table/service privileges for authorized API work | Table ownership, superuser, BYPASSRLS, DDL, granting roles |
| `kanior_worker` | Only registered scoped job actions and required tables | Migration role, arbitrary principal impersonation, unrestricted evidence reads |
| Restricted audit writer | Insert validated metadata audit records | Content bodies; update/delete existing audit records |

Enable and FORCE RLS on scoped content and policy-bearing tables. Separate tenant-wide user/workspace provisioning from runtime content access. Both USING and WITH CHECK policies must enforce scope and actions; policies cover joins/writes, not just SELECT. Runtime roles must not inherit owner/migration powers. Carefully scoped security-definer helpers, if needed to avoid recursive membership policies, require fixed search_path, restricted EXECUTE, fully qualified tables and dedicated tests; never grant general bypass.

Each API/worker unit of work begins a transaction, validates context, and sets transaction-local parameters with bound values: `app.principal_kind`, `app.principal_id`, `app.tenant_id`, `app.workspace_id`; add server-authorized `app.project_id` for a single-project operation. Project listing leaves project scope unset and policies derive eligible projects from current memberships. Missing/invalid principal, tenant or workspace must deny access, never mean all scopes. Missing project context must not bypass membership checks. Never concatenate input into SQL or session-setting expressions.

Policies consult current enabled user/membership and tombstone state, not just supplied epoch/capabilities. Epoch detects stale state; it is not permission. Composite FKs separately prevent cross-scope associations. Clear context through transaction completion; pooled connections must not carry it to the next request. Tests must alternate tenants/users through the same connection after success, rollback and exception.

RLS protects against accidental application queries, not a fully compromised database administrator or runtime capable of issuing arbitrary trusted-context SQL. Do not expose database credentials or context-setting operations to clients. Test with actual restricted runtime roles, not the migration owner or postgres superuser.

## Workers, storage and external boundaries

Jobs store durable scoped IDs and action-specific service identity. On claim and before side effects, revalidate document/project state, actor permission where the action requires it, and current service grant. Disabled users, revoked approval and tombstones block stale work. Retrying a job does not renew its authority. Lease/operation keys prevent duplicate effects; uncertain provider submissions reconcile before resubmitting. No global worker identity is a blanket grant to all content.

Raw assets enter quarantine and require content validation/limits before use. Private object keys confer no access. No public buckets or source URLs; baseline playback streams through authorized API. Original/published objects cannot be overwritten. External provider access stays behind adapters and approved processor/region configuration. No automatic fallback to unapproved providers. Export requires verified destination readers no broader than source readers; membership removal pauses affected exports pending reconciliation.

## Development authentication and secrets

Normal local development uses Entra test configuration when exercising login. Credential-free unit/integration tests may override the identity dependency inside the test process with fixed fictional AuthContext fixtures. The override must still exercise real service authorization and RLS, never bypass them. No HTTP header/query/body can activate fake identity; no unauthenticated dev-login route. Test overrides must not be registered by the production entrypoint. A future interactive local fake-login mode requires its own explicit contract and startup restrictions; it is not authorized by this document.

Use synthetic fixtures in the repository/CI; explicitly approved de-identified data outside production follows separate access policy. No real credentials, transcripts, production IDs, audio or provider dumps in git. Environment examples contain placeholders only. Use secret references, server-side storage, separate runtime/migration credentials, and provisioned rotation procedures. Company consent, retention, region and processor approvals remain open decisions until resolved under architecture §38; synthetic implementation may proceed.

## Error disclosure, telemetry and untrusted content

Treat transcript instructions as untrusted data; selector has no arbitrary tools or network/storage access. Require sealed candidates and reject extra model fields. Reauthorize in evidence loader before model context and renderer before delivery. The renderer alone constructs source-equal quotes; synthesis is labeled generated analysis and cannot impersonate quote cards.

Return 401 without valid identity, 404 for inaccessible IDs, and 403 only for action/CSRF denial that does not reveal hidden resources. API errors use the common safe shape, including validation errors. Never log raw audio, transcript/note/query text, prompts, model evidence responses, tokens, cookies, CSRF tokens or signed URLs. Trace identifiers/counts/timings/state only. Audit writes are append-only metadata and commit with protected mutations; fail closed when mandatory audit cannot persist.

## Required implementation tests

- Entra other-tenant, guest, unassigned, disabled and expired identities; CSRF and session limits (AT-01).
- Cross-tenant/workspace/project IDs and FK writes; reader mutation denial; admin without membership cannot read; missing RLS context; pooled-context reuse (AT-02).
- Membership revision races, immediate revocation, cached permissions, worker revalidation and no subsequent unauthorized delivery (AT-12/13).
- Same error behavior for absent/inaccessible IDs; no unauthorized counts, scores, snippets or model inputs (AT-02/23).
- Confidential sentinel strings and secrets absent from logs/traces/errors/audit; validation must not echo input (AT-15).
- Quote bytes/hash/version/approval, prompt injection, precise spans, synthesis rejection when those phases arrive (AT-03/04/19–24).
- Governed purge/hold and isolated restore reapply deletion ledger and current authorization before exports/traffic resume (AT-14/17).

Schema tests are necessary but do not satisfy these runtime gates. Add each applicable security test with the feature it protects.
