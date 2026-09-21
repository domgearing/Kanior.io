# ADR-001: Stack and repository layout

Status: accepted.

## Context

KaniorAI needs a small initial implementation that preserves strict authorization and source-integrity boundaries while supporting a web client, managed desktop capture, an HTTP API, background work, relational data, and vector search. Future agents need one repository layout and one toolchain path. Supporting multiple equivalent stacks or queues would create drift before product behavior exists.

## Decision

Build a modular monolith in one polyglot repository:

- `web/`: React, TypeScript, and Vite.
- `desktop/`: Electron and TypeScript, with Recall isolated behind a capture adapter.
- `api/`: Python FastAPI HTTP application using Pydantic contracts.
- `domain/`: provider-neutral business and authorization boundaries.
- `workers/`: Python background execution using the same domain contracts.
- `connectors/`: external provider and storage adapters whose SDK types do not enter domain contracts.
- `migrations/`: SQLAlchemy/Alembic database evolution for PostgreSQL 17 and pgvector.
- `schemas/`: generated OpenAPI, JSON Schema, and TypeScript contracts from the Python-owned source defined by ADR-002.
- `tests/`, `evals/`, `infra/`, `docs/`, and `scripts/`: shared verification, local infrastructure, decisions, and canonical commands.

Use `uv` and a checked-in `uv.lock` for Python. Use a root pnpm 12.4.2 workspace and checked-in `pnpm-lock.yaml` for JavaScript/TypeScript. pytest is the Python runner and Vitest is the TypeScript unit runner. Docker Compose supplies local PostgreSQL/pgvector; application processes run from the checkout. On Windows, Git Bash is the supported environment for repository shell scripts, which use LF endings.

The initial durable-work baseline is PostgreSQL: a jobs table uses leases, bounded retries, and operation keys, while transactional outbox records make domain changes and event publication atomic. Do not add Redis or a second queue for the baseline. A managed workflow/queue requires measured need and another ADR.

Provider access uses the interfaces in architecture §7. The MVP choices remain Backblaze B2, AssemblyAI, Recall, approved OpenAI deployments, and Microsoft Graph, but domain and service code receives provider-neutral values. This makes synthetic adapters usable in tests and allows an approved provider evolution without leaking SDK types across modules.

## Alternatives considered

- Separate network microservices were rejected for the baseline because they add deployment and consistency boundaries without a current scaling need.
- A TypeScript API or mixed API stacks were rejected because FastAPI/Pydantic is the locked API and contract source.
- Redis/BullMQ and an in-process-only queue were rejected because PostgreSQL jobs/outbox provide the required durable, transactional MVP behavior.
- OneDrive as operational storage was rejected; it remains a one-way export destination.
- Provider SDK models as domain models were rejected because they couple core behavior and tests to external services.
- Legacy `organizations`/`meetings` names are retired for new code; canonical names are `tenants`/`documents` under architecture §8.

## Consequences

The repository has two language toolchains, so the root scripts and CI gate must run both locked environments. Shared contracts are generated rather than hand-maintained in each language. Module boundaries are code and authorization boundaries inside one deployable system; they do not imply network calls. PostgreSQL carries additional job/outbox responsibility, which requires lease, retry, idempotency, and recovery tests.

The initial layout includes application shells before full features exist. An empty shell does not satisfy a phase gate, and generated schemas do not prove authorization behavior.

## Security implications

Clients never receive provider credentials or database credentials. API and worker roles are separate from the migration owner and cannot use `BYPASSRLS`. Tenant/workspace/project scope, authorization, audit, and RLS remain service and database obligations regardless of the modular-monolith deployment. Synthetic adapters are the default outside explicitly approved live environments. Provider feasibility and company-policy approvals still gate confidential data.

## Migration implications

Alembic is the only database migration path. Changes are version controlled, expand-compatible where possible, and tested from an empty PostgreSQL database with pgvector. Runtime code does not create or alter schema. A later move to managed hosting, Azure Blob, or managed workflow services must preserve contracts and include an ADR plus operational migration plan.
