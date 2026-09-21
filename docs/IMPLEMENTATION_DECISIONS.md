# Implementation Decisions

This register is an operational index. `ARCHITECTURE.md` remains authoritative; an accepted ADR records the rationale for a material choice, and the active plan narrows the current implementation slice.

## Source-of-truth hierarchy

1. `AGENTS.md` — coding-agent operating rules and handoff behavior. Its architecture summaries cannot override `ARCHITECTURE.md`.
2. `ARCHITECTURE.md` — authoritative technical architecture, boundaries, security invariants, sequence, and gates.
3. `PROJECT_SPEC.md` — product behavior and acceptance targets where architecture does not refine it.
4. Accepted ADRs in `docs/decisions/` — rationale for material choices consistent with architecture.
5. `docs/DATA_MODEL.md`, `docs/API_CONTRACTS.md`, `docs/SECURITY.md`, and machine-readable schemas — implementable contracts.
6. Active plans in `docs/plans/active/` — bounded work and acceptance criteria; plans cannot override the sources above.

When two sources conflict, follow the higher source and reconcile the stale lower source in the same change or record the conflict for its owner.

## Locked decisions

| Area | Decision | Status | Source |
| --- | --- | --- | --- |
| Application shape | Modular monolith with explicit domain, connector, API, and worker boundaries | LOCKED | Architecture §§4–7; ADR-001 |
| Web | React + TypeScript + Vite | LOCKED | Architecture §4; ADR-001 |
| Desktop | Electron; Recall capture stays behind an adapter | LOCKED | Architecture §4; ADR-001 |
| API and validation | Python FastAPI with Pydantic-owned wire contracts | LOCKED | Architecture §4; ADR-001; ADR-002 |
| Worker | Python worker using domain service contracts | LOCKED | Architecture §4; ADR-001 |
| Database and vectors | PostgreSQL 17 with pgvector | LOCKED | Architecture §4; ADR-001 |
| ORM and migrations | SQLAlchemy and version-controlled Alembic migrations | LOCKED | Architecture §4; ADR-001 |
| Jobs and events | PostgreSQL durable jobs with leases, retries, idempotency, and transactional outbox; no baseline Redis queue | LOCKED | Architecture §§4, 22, 25; ADR-001 |
| Outbox dispatch | Dispatcher operates under a provisioned service identity in explicit tenant/workspace/project scope without `BYPASSRLS` | LOCKED | Architecture §§21–22; ADR-003 |
| Object storage | Private Backblaze B2 behind `ObjectStorage`; private Azure Blob is the managed alternative | LOCKED | Architecture §§4, 7, 13 |
| Speech recognition | AssemblyAI Universal-3.5 Pro, pinned as `universal-3-5-pro`, behind `TranscriptionProvider` | LOCKED | Architecture §§4, 7 |
| Capture | Recall Desktop SDK behind the capture adapter and its feasibility gate | LOCKED | Architecture §§4, 7; `docs/INTEGRATIONS.md` |
| Identity | Single-tenant Microsoft Entra authorization code flow with PKCE and server-held sessions | LOCKED | Architecture §§4, 20 |
| Microsoft 365 | One-way, immutable, versioned Microsoft Graph/OneDrive export behind an adapter | LOCKED | Architecture §19 |
| Contract generation | Edit Python contract sources; generate OpenAPI, JSON Schema, and TypeScript declarations | LOCKED | ADR-002; `schemas/README.md` |
| Repository layout | Top-level `api/`, `domain/`, `workers/`, `connectors/`, `web/`, `desktop/`, `migrations/`, `schemas/`, `tests/`, `evals/`, `infra/`, `docs/`, and `scripts/` | LOCKED | Architecture §5; ADR-001 |
| Package managers | `uv` with `pyproject.toml`/`uv.lock`; pnpm 12.4.2 with root workspace/lockfile | LOCKED | ADR-001; repository manifests |
| Test runners | pytest for Python; Vitest for web/desktop; repository shell gates compose tool-specific checks | LOCKED | ADR-001; repository manifests |
| Local containers | Docker Compose provides PostgreSQL/pgvector only; application processes run from the checkout | LOCKED | ADR-001; `infra/README.md` |
| Supported Windows shell | Git Bash runs repository `.sh` commands with LF line endings | LOCKED | ADR-001; `.gitattributes` |

## Open non-blocking decisions

These items do not block synthetic-data implementation. They must be resolved by their stated gate; this register does not imply provider, security, or company approval.

| Area | Question | Default / constraint | Owner / phase |
| --- | --- | --- | --- |
| Entra configuration | Which tenant, assigned employee group, application registration, and secondary corporate domains are approved? | Exact tenant and assigned enabled employees only | IT; before confidential pilot |
| Regions and processors | Which Recall, AssemblyAI, OpenAI, compute, and storage regions and terms are approved? | Synthetic adapters only until approved | Security / IT; before live provider use |
| Provider retention | What does each approved endpoint/account retain and how is deletion verified? | Record actual behavior; never assume zero retention | Security; before confidential pilot |
| Recall feasibility | Can the supported desktop/OS matrix provide the required audio handoff and recovery behavior? | Complete the documented R1 gate before connector implementation | Product owner; before live capture |
| OneDrive destination | Which business drive/folder or team library and least-privilege grant are approved? | Readers may never be broader than source readers | IT / product owner; complete G1 before connector implementation |
| Retention and holds | Which retention durations, legal holds, and deletion owners replace or confirm proposed defaults? | No invented duration; synthetic data only | Data owner / compliance; before confidential pilot |
| Consent | What acknowledgement text and process does the firm require? | Consent version must be configured, not guessed | Data owner; before confidential pilot |
| Evaluation corpus | Which permission-approved corpus and labeling process measure retrieval quality? | Repository fixtures remain fictional | Product owner / security; before product acceptance |
| Capacity and budget | What load envelope, provider quota, and spend ceiling apply? | Do not infer production capacity from local defaults | Engineering / finance; before pilot sizing |
| Recovery | What RPO, RTO, backup region, and restore approval apply? | Baseline restore work uses synthetic data | IT / data owner; before confidential pilot |

## Open blocking decisions

There are no known company-policy decisions blocking the synthetic-data first implementation slice in `docs/plans/active/001-foundation.md`. The open items above become blocking at their stated live-provider or confidential-data gate. Any newly discovered architecture conflict must be recorded here as `OPEN/BLOCKING` before implementation proceeds through the affected gate.

## Deferred decisions

| Area | Reason deferred | Revisit in phase |
| --- | --- | --- |
| Managed hosting migration | The modular monolith and local/container baseline must work before Azure Container Apps adds value | Production reliability and governance |
| Durable Functions / Service Bus | PostgreSQL jobs/outbox meet the MVP baseline; change only with measured scaling evidence and an ADR | Production reliability and governance |
| Azure Blob migration | B2 is the locked MVP authority and callers use an interface | Production reliability and governance |
| System-wide hotkeys | Initial MVP uses browser/managed desktop behavior without a Windows companion | Live/collaborative features |
| Ownership transfer API | The first slice preserves the designated owner; transfer needs its own authorization and concurrency contract | Later foundation work |
| Interactive fake login | Tests may inject fixed identities in-process; a user-facing fake login needs explicit startup restrictions | Later developer-experience work, if needed |
| Transcript ACL schema | Project membership bounds access initially; document restrictions need a dedicated contract | Governance phase |
