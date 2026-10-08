# Security implementation contract

Authority: `ARCHITECTURE.md` §§3, 9, 13–16, 19–22, 35, 38–39 and `PROJECT_SPEC.md` §12. This is an implementation contract, not evidence of deployed security controls.

## Identity and sessions

Identity is provider-neutral under ADR-005. Local/test development may use only the explicitly allowlisted magic-link adapter: neutral request responses, random hashed single-use tokens, ten-minute expiry, hashed email/source rate limits, exact Origin checks, and an enabled internal user are mandatory. Email is a mutable login locator, never a principal or authorization rule. Public signup and domain-only admission are prohibited. The adapter fails startup outside local/test.

Confidential/staging/production identity uses single-tenant Entra authorization-code flow with PKCE. Validate issuer, audience, signature, expiry, nonce/state, exact tenant, enabled employee assignment and enabled internal user. Reject guests, unassigned/disabled employees and other tenants. Stable Entra identity is tenant/object ID. Initial session defaults from spec: 30-minute idle, eight-hour absolute; recording never bypasses disable checks. Emergency disable is immediate; lifecycle propagation target <=5 minutes.

The Entra adapter uses MSAL's authorization-code/PKCE flow with server-held, single-use state bound to a Secure/HttpOnly browser cookie. Because MSAL 1.39 does not verify ID-token signatures for the app, Verelo independently verifies the token against tenant-specific Microsoft signing keys, expiry, issuer, audience, and flow nonce before admission. The app additionally requires the configured tenant, client audience, tenant `acct=0` member claim, and assigned employee group claim; missing or overage claims fail closed. The enterprise app must require assignment and emit `acct` and `groups` in ID tokens. An administrator must separately provision an enabled tenant, workspace, internal user and matching `entra` identity account. `scripts/link_entra_employee.py` binds an explicitly named existing user; it does not create users or grant project membership. On every request the opaque session resolver rechecks the current enabled-user state. IT must connect Entra offboarding and group/assignment removal to internal-user disable; this lifecycle integration and a live tenant negative-test matrix remain confidential-pilot gates.

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
| Approve/revoke/publish transcript | No | No | Yes | No | No |
| Approved project export / request deletion (later) | No | No | Yes | No | No |
| Configure identities/connectors/policies | No | No | No implicit grant | Yes | No |
| Read audit metadata | No implicit grant | No implicit grant | Only separately authorized scope | Only separately authorized scope | Assigned audit scope only |

Project creation uses explicit provisioned `projects:create` capability, not an assumed role inheritance. Creator becomes owner in the same transaction. Foundation cannot demote/disable the designated owner membership; ownership transfer needs a separate contract. An enabled tenant administrator can be separately granted project membership; administrative status alone never admits content access.

Controlled-cleanup service approval is limited to unchanged text or exact edits accepted by the versioned deterministic project policy. ADR-004 permits only its narrow filler-removal and stutter-deduplication rules beyond formatting; protected tokens, punctuation, unlisted wording, and semantic-model judgments fail closed. Transcript ACLs in production intersect project membership; no document grant can admit an outsider. Break-glass access requires explicit time-limited assignment and durable audit.

## Database roles and transaction context

Role names below are initial implementation conventions; credentials are distinct in every environment.

| Role | Allowed | Forbidden |
|---|---|---|
| `verelo_migrator` | Own schema/tables, run reviewed Alembic migrations | API/worker connections; credentials in runtime environment |
| `verelo_api` | Minimum table/service privileges for authorized API work | Table ownership, superuser, BYPASSRLS, DDL, granting roles |
| `verelo_worker` | Only registered scoped job actions and required tables | Migration role, arbitrary principal impersonation, unrestricted evidence reads |
| Restricted audit writer | Insert validated metadata audit records | Content bodies; update/delete existing audit records |

Enable and FORCE RLS on scoped content and policy-bearing tables. Separate tenant-wide user/workspace provisioning from runtime content access. Both USING and WITH CHECK policies must enforce scope and actions; policies cover joins/writes, not just SELECT. Runtime roles must not inherit owner/migration powers. Carefully scoped security-definer helpers, if needed to avoid recursive membership policies, require fixed search_path, restricted EXECUTE, fully qualified tables and dedicated tests; never grant general bypass.

Each API/worker unit of work begins a transaction, validates context, and sets transaction-local parameters with bound values: `app.principal_kind`, `app.principal_id`, `app.tenant_id`, `app.workspace_id`; add server-authorized `app.project_id` for a single-project operation. Project listing leaves project scope unset and policies derive eligible projects from current memberships. Missing/invalid principal, tenant or workspace must deny access, never mean all scopes. Missing project context must not bypass membership checks. Never concatenate input into SQL or session-setting expressions.

Policies consult current enabled user/membership and tombstone state, not just supplied epoch/capabilities. Epoch detects stale state; it is not permission. Composite FKs separately prevent cross-scope associations. Clear context through transaction completion; pooled connections must not carry it to the next request. Tests must alternate tenants/users through the same connection after success, rollback and exception.

RLS protects against accidental application queries, not a fully compromised database administrator or runtime capable of issuing arbitrary trusted-context SQL. Do not expose database credentials or context-setting operations to clients. Test with actual restricted runtime roles, not the migration owner or postgres superuser.

## Workers, storage and external boundaries

Jobs store durable scoped IDs and action-specific service identity. On claim and before side effects, revalidate document/project state, actor permission where the action requires it, and current service grant. Disabled users, revoked approval and tombstones block stale work. Retrying a job does not renew its authority. Lease/operation keys prevent duplicate effects; uncertain provider submissions reconcile before resubmitting. No global worker identity is a blanket grant to all content.

Raw assets enter quarantine and require content validation/limits before use. Private object keys confer no access. No public buckets or source URLs; baseline playback streams through authorized API. Original/published objects cannot be overwritten. External provider access stays behind adapters and approved processor/region configuration. No automatic fallback to unapproved providers. Export requires verified destination readers no broader than source readers; membership removal pauses affected exports pending reconciliation.

The Phase 2 API accepts only WAV, MP3, M4A, and WebM audio and TXT, VTT, SRT, or schema-v1 JSON
transcripts. File extensions and declared MIME are not trusted: exact bytes are hashed, and audio is
opened/decoded with the pinned FFmpeg-backed media stack before release from quarantine. Limits are
2 GiB/four decoded hours for audio and 20 MiB for transcript input. The local MVP uses bounded 5 MiB
JSON chunks; a live object-store transport must stream without buffering production-sized assets.
Electron persists only the capture-session identifier and next sequence in its private application
data. Temporary local session/CSRF configuration is never a packaged credential.

## Development authentication and secrets

Normal local development uses ADR-005's interactive magic-link flow with administrators provisioning allowlisted employees out of band. The default synthetic delivery adapter writes links to the ignored `.artifacts/dev-mailbox` directory and never to logs or API responses. An explicitly configured local/test environment may instead use the Microsoft Graph mail adapter with a dedicated sender mailbox, client-credentials secret injection, and mailbox-scoped Exchange Application RBAC; this does not relax the production identity restriction. Credential-free unit/integration tests may still override the identity dependency inside the test process with fixed fictional AuthContext fixtures; the override exercises real service authorization and RLS. No HTTP header can activate fake identity, and the production entrypoint rejects the magic-link provider outside local/test.

Use synthetic fixtures in the repository/CI; explicitly approved de-identified data outside production follows separate access policy. No real credentials, transcripts, production IDs, audio or provider dumps in git. Environment examples contain placeholders only. Use secret references, server-side storage, separate runtime/migration credentials, and provisioned rotation procedures. Company consent, retention, region and processor approvals remain open decisions until resolved under architecture §38; synthetic implementation may proceed.

For staging, start from `.env.staging.example`, route web/API over distinct HTTPS origins, and inject API/worker/migrator credentials separately. Provision each worker project explicitly with `scripts/provision_deployment_worker.py`; the local dynamic worker supervisor is not a production discovery or authorization mechanism. `scripts/deployment_preflight.py` checks configuration only and cannot attest backup restore, processor approval, employee assignment, security review, or a live Entra sign-in. The public development tunnel and its local magic-link login must not be treated as a coworker deployment.

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
