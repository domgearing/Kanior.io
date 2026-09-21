# Foundation API and authorization slice

## Phase

Architecture Phase 1 — Secure source foundation. This plan implements the first bounded API/data slice defined by the existing foundation-v1 contracts. Completing it does not by itself complete every Phase 1 item in architecture §29.

## Objective

Implement the documented project, membership, and document-metadata operations over the baseline PostgreSQL schema. A permitted synthetic test principal must be able to create, list, and read a project and document through the HTTP API. Guessed or cross-scope identifiers must disclose nothing, and service mutations must commit their audit/outbox effects atomically.

## Context

Repository/toolchain scaffolding, contract generation, a FastAPI health shell, local PostgreSQL/pgvector, and an Alembic baseline exist. Treat them as a starting point to verify, not evidence that the behavior or security gate is complete. The first slice intentionally omits transcript bytes, retrieval, AI, capture, and live providers.

## Dependencies

- `./scripts/pr-ready.sh` passes before this work is submitted for review.
- The local database can migrate from zero using the migrator role.
- `ARCHITECTURE.md`, ADR-001, ADR-002, ADR-003, and the foundation contracts remain consistent.
- Generated contract artifacts are current under `schemas/README.md`.
- Tests use only the canonical fictional fixture corpus under `tests/fixtures/synthetic/`.

Open company-policy decisions in `docs/IMPLEMENTATION_DECISIONS.md` do not block this synthetic slice. They still prohibit confidential traffic and unapproved live providers.

## Inputs / authoritative contracts

Read before implementation:

1. `ARCHITECTURE.md`, especially §§3–9, 20–25, 27–31, 35, and 39.
2. `docs/DATA_MODEL.md` for tables, scope keys, ownership, immutability, and deletion behavior.
3. `docs/API_CONTRACTS.md` and `schemas/openapi/foundation-v1.json` for the nine HTTP operations.
4. `docs/SECURITY.md` for trusted identity, role/action rules, RLS context, errors, and logging.
5. `schemas/README.md` and ADR-002 for the single contract-generation workflow.
6. ADR-003 for scoped outbox dispatch; workers receive explicit tenant/workspace scope and never use `BYPASSRLS`.

If implementation requires a material departure, stop and propose an ADR. Do not redesign these contracts inside the feature change.

## In scope

- Persistence/repository and service implementations for tenants, workspaces, users, projects, project memberships, documents, audit events, and outbox events.
- Transaction-local PostgreSQL context for principal, tenant, workspace, and single-project operations.
- The foundation-v1 HTTP operations and common safe error translation.
- Explicit `projects:create` capability checks and atomic creator-owner membership.
- Current membership authorization, membership revision compare-and-swap, project authorization-epoch increments, and owner preservation.
- Keyset pagination with sealed, principal/scope-bound cursors and no total counts.
- Metadata-only audit and transactional `access.changed` outbox writes.
- Synthetic in-process identity dependency overrides in tests only, as allowed by `docs/SECURITY.md`.
- Restricted-role integration tests and architecture/contract checks.

## Out of scope

- Public signup, identity provisioning APIs, interactive fake login, and caller-selected auth headers.
- Production Entra login/session integration beyond the internal `AuthContext` boundary.
- Upload, object bytes, quarantine, capture, transcription, cleanup, approval, publication, indexing, retrieval, quote rendering, synthesis, or export.
- Live Recall, AssemblyAI, OpenAI, Microsoft Graph, Entra, or B2 calls and credentials.
- Project ownership transfer, document deletion, transcript ACLs, and full retention/hold workflows.
- Full durable job execution or an active dispatcher. This slice writes its defined outbox event; later work implements ADR-003's persisted service grants, scoped dispatcher, and registered job actions.

## Interfaces to implement

Implement the exact operation IDs, methods, paths, request/response models, and status codes from `docs/API_CONTRACTS.md`:

| Operation | HTTP interface |
| --- | --- |
| `get_me` | `GET /api/v1/me` |
| `list_projects` | `GET /api/v1/projects` |
| `create_project` | `POST /api/v1/projects` |
| `get_project` | `GET /api/v1/projects/{project_id}` |
| `get_project_member` | `GET /api/v1/projects/{project_id}/members/{user_id}` |
| `set_project_member` | `PUT /api/v1/projects/{project_id}/members/{user_id}` |
| `list_documents` | `GET /api/v1/projects/{project_id}/documents` |
| `create_document` | `POST /api/v1/projects/{project_id}/documents` |
| `get_document` | `GET /api/v1/documents/{document_id}` |

Routes remain thin. Implement and call the `ProjectService`, `MembershipService`, and `DocumentService` operations named in `docs/API_CONTRACTS.md`. Import request/response models from `contracts/`; do not create a second DTO hierarchy. The service layer owns transaction, authorization, audit, and outbox atomicity.

## Database changes

Verify and, where tests expose gaps, revise the initial Alembic migration rather than adding a competing schema baseline. The schema must match the first-slice tables and composite scope rules in `docs/DATA_MODEL.md`.

Required database evidence includes:

- full-scope composite foreign keys reject cross-tenant/workspace/project associations;
- creator owner membership and project creation commit together;
- membership revision and project authorization epoch advance atomically;
- the designated owner cannot be demoted or disabled by this API;
- audit/outbox writes roll back when the protected mutation fails;
- RLS is enabled and forced for scoped tables and denies missing/invalid context;
- runtime API/worker roles do not own tables, migrate, or bypass RLS;
- outbox records carry the required scope, and no runtime role gains `BYPASSRLS`; the dispatcher stays inactive until ADR-003's persisted service-grant contract is implemented.

Do not add reserved later tables from `docs/DATA_MODEL.md` unless this plan is amended through review.

## Security requirements

- Derive tenant/workspace/principal from trusted `AuthContext`; never accept them from request data.
- Resolve a resource inside the authorized scope and return the same 404 shape for missing and inaccessible IDs.
- Authorize before loading or counting protected metadata. Do not return unauthorized totals, titles, membership details, or existence signals.
- Recheck enabled user, current membership, project/resource state, and action on each operation.
- Use transaction-local RLS settings with bound values and clear them through transaction completion, rollback, and pool reuse.
- Enforce the role/action matrix in `docs/SECURITY.md`; tenant administrator status alone grants no project content.
- Require the documented CSRF behavior on state-changing browser requests.
- Log identifiers, states, counts, and safe codes only. Never log request bodies, document titles, emails, credentials, tokens, or provider configuration.
- Fail the protected mutation if mandatory audit persistence fails.

## Required tests

Unit tests:

- service happy paths and invalid transitions;
- project-creation capability denial and owner preservation;
- membership compare-and-swap conflict and epoch increment;
- sealed cursor validation, wrong principal/scope, bounds, and stable ordering;
- safe error mapping without echoed input.

PostgreSQL integration tests using actual restricted roles:

- migrate an empty pgvector database to head;
- permitted project/document create, read, and list;
- reader mutation denial and contributor/owner action matrix;
- wrong tenant, workspace, project, document, and target-user identifiers;
- direct cross-scope insert/update rejection by composite keys and RLS;
- missing RLS context and alternating principals through the same pooled connection after success, rollback, and exception;
- membership revocation takes effect on the next access;
- atomic rollback of project/member/audit and membership/outbox/audit groups;
- API runtime access cannot claim or rewrite outbox envelopes, and no worker test treats caller-set scope UUIDs alone as authority.

Contract/architecture/e2e checks:

- runtime FastAPI OpenAPI conforms to the generated foundation-v1 contract;
- all nine operations use shared models and common error shapes;
- synthetic API flow creates and then reads/lists a project and document;
- confidential sentinel strings and secret-shaped fixture values do not appear in logs, errors, or audit payloads.

No live credential or paid provider is permitted in these tests.

## Acceptance gate

A separate module/client can create and read a project and document through the documented interface/API using the local synthetic development environment, and all required checks pass.

Evidence must show:

- all nine foundation operations conform to the committed contracts;
- authorized create/read/list and membership-CAS behavior works;
- direct API and database tests show zero cross-tenant/workspace/project disclosure;
- restricted runtime roles and pooled RLS context tests pass;
- audit/outbox atomicity, revocation, non-disclosing errors, CSRF, and pagination tests pass;
- logs and audit payloads contain no confidential fixture content or credentials;
- migrations apply from an empty database; and
- `./scripts/pr-ready.sh` exits 0.

## Expected files/directories

Changes should remain within existing boundaries, primarily `api/`, `domain/`, `migrations/`, `tests/unit/`, `tests/integration/`, `tests/e2e/`, and `tests/fixtures/synthetic/`. Update contract sources/generated artifacts only if implementation reveals a reviewed contract defect. Do not add a parallel source tree or dependency manager.

## Verification commands

Run from Git Bash on Windows:

```bash
./scripts/setup.sh
./scripts/services.sh up
./scripts/migrate.sh
./scripts/check.sh
./scripts/test-integration.sh
./scripts/check-migrations.sh
./scripts/eval.sh pr
./scripts/pr-ready.sh
```

The pull request description must identify the synthetic fixture version, the restricted database roles exercised, and the result of each command. If Docker is unavailable, the work is not ready to claim the integration/migration gate locally; use CI or a configured ephemeral PostgreSQL environment and report that evidence.

## Definition of done

- Implementation and tests satisfy every item in the acceptance gate.
- No live provider, confidential data, or secret is required.
- Contracts and generated artifacts have no drift.
- Migrations are reproducible from zero and runtime roles remain least-privileged.
- Relevant architecture and eval checks are active rather than placeholders.
- `ARCHITECTURE.md` remains accurate and no unrecorded material decision was introduced.
- The agent handoff uses the completion format in `AGENTS.md` and names remaining Phase 1 dependencies without claiming the whole phase complete.

## Completion notes

To be filled by the implementing agent with files changed, migration revisions, test/eval evidence, limitations, and next dependencies.
