# KaniorAI Repository Readiness Workplan

**Plan ID:** 000-repository-readiness  
**Purpose:** Prepare the KaniorAI GitHub repository and codebase so feature development can begin safely with coding agents.  
**Scope:** Repository architecture alignment, contracts, documentation, local infrastructure, test/eval scaffolding, CI, and developer ergonomics.  
**Out of scope:** Product feature implementation beyond the minimum code required to prove the repository/toolchain/contracts work.

---

## 1. Mission

Bring the repository from its current planning/specification state to a **development-ready, agent-safe baseline**.

When this plan is complete, a new coding agent should be able to:

1. Clone the repository.
2. Know which documents are authoritative.
3. Understand the locked implementation stack and repository layout.
4. Install dependencies using documented commands.
5. Start required local infrastructure.
6. Apply database migrations.
7. Run linting, formatting, type checks, tests, architecture checks, contract checks, and basic evals.
8. Understand the core data model and API/service contracts without inventing new conventions.
9. Use deterministic synthetic fixtures instead of confidential production data.
10. Open a pull request that is automatically judged by CI.
11. Pick up `docs/plans/active/001-foundation.md` and begin Phase 1 implementation without first redesigning the repository.

The final repository should make the **correct path easier than improvisation**.

---

## 2. Execution Rules for the Agent

### 2.1 Do not begin feature development

This plan prepares the repository for development. Do **not** implement ingestion, retrieval, transcript processing, search, AI synthesis, UI workflows, connectors, or other product features except where a minimal stub is required to prove the toolchain or contract is valid.

### 2.2 Audit before modifying

Before changing architecture-related files:

1. Read `AGENTS.md`.
2. Read `ARCHITECTURE.md`.
3. Read `PROJECT_SPEC.md`.
4. Read any existing ADRs.
5. Inspect the current repository tree and package/toolchain files.
6. Identify whether the architecture/specification conflict described in prior planning has already been resolved.

**Important:** The latest intended architecture is expected to align with the detailed project specification. Do not reintroduce an older stack merely because stale references remain elsewhere.

### 2.3 Do not guess across material conflicts

If a stale document conflicts with a newer explicit architecture decision, update the stale document.

If two current authoritative documents still contain a **material unresolved choice** that affects implementation and there is no clear newer decision:

- record it in `docs/IMPLEMENTATION_DECISIONS.md` as `OPEN/BLOCKING`,
- do not silently invent an answer,
- do not implement the affected subsystem,
- continue all independent readiness work.

### 2.4 Prefer simple, explicit infrastructure

Do not introduce orchestration frameworks, agent frameworks, service meshes, unnecessary abstractions, or extra infrastructure unless already required by the architecture.

### 2.5 Preserve architectural boundaries

The repository must support later enforcement of clear boundaries between major domain modules, especially retrieval, evidence selection, quote rendering, connectors, and authorization.

### 2.6 Use synthetic data only

Do not add real customer transcripts, credentials, tokens, production exports, or confidential examples to the repository.

---

## 3. Source-of-Truth Hierarchy

Create or confirm this hierarchy in `docs/IMPLEMENTATION_DECISIONS.md` and reference it from `README.md` and `AGENTS.md` where appropriate.

1. **`AGENTS.md`** — agent behavior, development workflow, verification requirements, and repository operating rules.
2. **`ARCHITECTURE.md`** — authoritative technical architecture and module boundaries.
3. **`PROJECT_SPEC.md`** — authoritative product requirements and detailed system specification.
4. **`docs/decisions/ADR-*.md`** — approved architecture decisions and changes.
5. **`docs/DATA_MODEL.md`, `docs/API_CONTRACTS.md`, `docs/SECURITY.md`, machine-readable schemas** — implementation contracts that must remain consistent with the architecture/specification.
6. **`docs/plans/active/*.md`** — scope and acceptance criteria for the current implementation task; plans may narrow work but may not override higher-level architecture.

If documents conflict, the agent must reconcile the lower-level/stale material to the higher-level/current decision rather than creating a third interpretation.

---

## 4. Expected Locked Technical Baseline

Verify these against the current `ARCHITECTURE.md` and `PROJECT_SPEC.md`. If the architecture has already been reconciled, preserve it.

Expected baseline from the latest project direction:

- **Frontend:** React + TypeScript + Vite
- **Backend API:** Python + FastAPI
- **Workers:** Python
- **Database:** PostgreSQL + pgvector
- **Durable jobs:** PostgreSQL-backed durable job table
- **Object storage baseline:** Backblaze B2-compatible object storage abstraction
- **Speech-to-text baseline:** AssemblyAI Universal-3.5 Pro behind a provider interface
- **Repository layout:** top-level domains such as `web/`, `desktop/`, `api/`, `workers/`, `domain/`
- **ADR location:** `docs/decisions/`

Do not treat this section as permission to overwrite a newer explicit decision found in the repository. Its purpose is to catch accidental regression to the older conflicting architecture.

---

# PHASE A — Repository and Architecture Audit

## A1. Inventory the repository

Produce a concise internal audit while working. Inspect at minimum:

- root documentation
- `.github/`
- application/source directories
- tests
- schemas
- scripts
- infra
- package manifests
- lockfiles
- environment files
- Docker/Compose files
- lint/type/test configuration

Do not create duplicate structures if equivalent files already exist.

## A2. Reconcile architecture references

Search the repository for stale references to old implementation choices, including:

- Next.js where the current frontend is Vite
- Node/TypeScript backend where the current backend is FastAPI/Python
- BullMQ/Redis where durable PostgreSQL jobs are current
- Azure Blob where Backblaze B2 is current
- old ADR paths such as `docs/ADR/`
- old repo layouts such as `apps/` + `packages/` if no longer authoritative

Update stale documentation/configuration so there is one implementation story.

## A3. Create architecture consistency gate

Add an architecture/readiness test or script that fails on known forbidden stale architectural references in normative files.

At minimum, the gate should detect accidental reintroduction of retired stack choices in authoritative documents.

### Acceptance gate A

- `ARCHITECTURE.md` and `PROJECT_SPEC.md` do not materially contradict each other.
- `AGENTS.md` points to the correct authoritative files and ADR path.
- No normative document directs agents to both old and new repository structures.
- Architecture consistency check passes.

---

# PHASE B — Lock Decisions and Repository Structure

## B1. Create `docs/IMPLEMENTATION_DECISIONS.md`

This should be short, operational, and easy for agents to scan.

Required sections:

```md
# Implementation Decisions

## Source-of-truth hierarchy

## Locked decisions
| Area | Decision | Status | Source |

## Open non-blocking decisions
| Area | Question | Default / constraint | Owner / phase |

## Open blocking decisions
| Area | Question | Why blocking | Required before |

## Deferred decisions
| Area | Reason deferred | Revisit in phase |
```

Include at least:

- frontend stack
- API stack
- worker stack
- database/vector extension
- job system
- object storage baseline
- STT provider baseline
- repo layout
- ADR path
- package managers/tooling if already decided
- test runner(s)
- migration framework
- container/local-infra strategy

Unresolved deployment/provider/retention decisions that do not block synthetic-data development should be explicitly marked `OPEN/NON-BLOCKING` rather than guessed.

## B2. Create `docs/decisions/ADR-001-stack-and-repo-layout.md`

Record:

- chosen stack
- chosen top-level layout
- why the architecture is polyglot if applicable
- why jobs use PostgreSQL rather than a separate queue for the baseline
- why provider/storage integrations sit behind interfaces
- consequences/tradeoffs
- which older alternatives are retired

If equivalent ADR(s) already exist, update rather than duplicate.

## B3. Normalize the top-level repository layout

Target structure:

```text
kanior-ai/
├── AGENTS.md
├── README.md
├── ARCHITECTURE.md
├── PROJECT_SPEC.md
│
├── docs/
│   ├── IMPLEMENTATION_DECISIONS.md
│   ├── DATA_MODEL.md
│   ├── API_CONTRACTS.md
│   ├── SECURITY.md
│   ├── EVALS.md
│   ├── decisions/
│   │   └── ADR-001-stack-and-repo-layout.md
│   └── plans/
│       ├── TASK_TEMPLATE.md
│       ├── active/
│       │   └── 001-foundation.md
│       └── completed/
│
├── schemas/
│   ├── openapi.yaml
│   ├── imports/
│   │   └── transcript-v1.schema.json
│   ├── events/
│   └── ai/
│
├── web/
├── desktop/
├── api/
├── workers/
├── domain/
│
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── contract/
│   ├── architecture/
│   ├── e2e/
│   └── fixtures/
│       └── synthetic/
│
├── evals/
│   ├── datasets/
│   ├── expected/
│   └── README.md
│
├── scripts/
├── infra/
│   ├── README.md
│   └── local/
│       └── compose.yaml
│
├── .github/
│   ├── workflows/
│   │   └── ci.yml
│   ├── pull_request_template.md
│   └── dependabot.yml
│
├── .env.example
├── .gitignore
├── .editorconfig
└── [language/package configuration and lockfiles]
```

Only create `desktop/` if it is part of the current architecture. Empty future directories should contain a small README or `.gitkeep` only when necessary.

### Acceptance gate B

- Stack and repo layout are recorded in an ADR.
- `docs/IMPLEMENTATION_DECISIONS.md` exists and distinguishes `LOCKED`, `OPEN`, and `DEFERRED` decisions.
- Repository layout matches the locked architecture.
- No duplicate ADR location exists.

---

# PHASE C — Core Implementation Contracts

## C1. Create `docs/DATA_MODEL.md`

Extract and normalize the existing specification. Do not invent a parallel model.

At minimum define the canonical identifiers and naming rules for entities such as:

- organization / tenant
- user
- workspace if applicable
- project
- source / meeting / document naming convention
- recording
- transcript
- transcript version
- passage
- speaker
- annotation/correction if in scope
- processing job
- evidence run
- source span / quote reference

For each core table/entity include:

- purpose
- canonical name
- identifier
- important columns and types
- primary key
- foreign keys
- unique constraints
- tenant/project ownership
- version semantics
- mutability/immutability rules
- deletion/cascade behavior
- important indexes
- RLS/security scope

Resolve naming collisions such as:

- `tenant_id` vs `organization_id`
- `source_id` vs `meeting_id` vs `document_id`

Pick the canonical term already supported by the latest architecture/specification and document aliases only where migration/backward compatibility requires them.

## C2. Create `docs/API_CONTRACTS.md`

Define Phase 1 interfaces before implementation.

At minimum specify:

- `AuthContext`
- organization/project/source models needed for foundation work
- create/read/list project contract
- create/read/list source contract
- common error shape
- pagination convention
- request ID / trace ID convention
- idempotency convention where applicable
- authorization expectations on every endpoint

Also reserve/describe future domain contracts already defined in architecture where doing so prevents agents from inventing incompatible shapes, for example:

- transcript version
- passage
- passage reference
- evidence selection
- verified quote
- processing job

Do not fully design later feature APIs unless the existing specification already does so.

## C3. Add machine-readable contracts

Create or validate:

### `schemas/openapi.yaml`

Must include the Phase 1 API surface or a generated equivalent committed to the repository.

### `schemas/imports/transcript-v1.schema.json`

Create from the existing transcript import specification if defined. If the detailed import shape is not yet locked, create a clearly marked minimal schema only for what is already specified; do not invent product behavior.

### `schemas/events/`

Add schemas only for events already required by the current architecture. Do not create speculative event sprawl.

### `schemas/ai/`

Add structured-output schemas only for AI boundaries explicitly defined in the architecture/specification, especially evidence selection/synthesis contracts if already specified.

## C4. Add schema validation tests

Add tests that confirm:

- schemas are valid JSON Schema/OpenAPI
- checked-in example fixtures validate
- invalid examples fail where practical

### Acceptance gate C

- Core entity names are canonical and unambiguous.
- Phase 1 endpoints/services have explicit request/response/error contracts.
- Machine-readable schema files parse and validate.
- Contract tests pass.

---

# PHASE D — Security Contract

## D1. Create `docs/SECURITY.md`

Keep this implementation-focused. Extract the security invariants from the main spec rather than duplicating all security prose.

Required sections:

1. Authentication model
2. Authorization model
3. Roles and permission matrix
4. Organization/project/source scoping
5. Row-level security expectations
6. Retrieval authorization rule: unauthorized material must be filtered before ranking/selection
7. Object-storage access rules
8. Secret handling
9. Logging/redaction rules
10. External-provider restrictions
11. Prompt-injection/content trust assumptions
12. Error-disclosure policy
13. Synthetic-data-only rule for repository fixtures
14. Security tests required before merge

## D2. Add security invariants to tests

Create test placeholders or executable tests where the supporting code exists for:

- cross-tenant isolation
- cross-project isolation
- unauthorized nearest-neighbor exclusion
- secret leakage prevention where testable
- no direct public object-storage access unless explicitly intended

Do not fake passing tests against unimplemented features. Mark future tests as skipped/TODO only with a clear phase reference; CI must distinguish intentional pending coverage from accidental absence.

### Acceptance gate D

- Security invariants are documented in one agent-readable location.
- Permission terminology matches the data model and API contracts.
- Test structure exists for authorization isolation.

---

# PHASE E — Evaluation and Test Baseline

## E1. Create `docs/EVALS.md`

Map important requirements to objective checks.

Required columns:

| ID | Requirement | Metric / test | Dataset / fixture | Threshold | Phase |
|---|---|---|---|---|---|

Include at minimum:

- quote fidelity/integrity
- authorization isolation
- transcript import round-trip
- canonical transcript version behavior
- job idempotency
- retrieval quality
- insufficient-evidence behavior
- fabricated-quote/adversarial behavior
- Unicode/source-span handling
- architecture-boundary enforcement

Only set numerical thresholds where already supported by the specification or clearly designated as an initial engineering gate.

## E2. Create test categories

Ensure these exist:

```text
tests/
├── unit/
├── integration/
├── contract/
├── architecture/
├── e2e/
└── fixtures/
```

### Architecture tests

Prepare tests/rules that can enforce boundaries such as:

- quote renderer must not call AI providers
- retriever must not import quote renderer
- frontend must not construct trusted/verified quote objects independently
- domain modules must not import concrete connector implementations directly
- authorization boundaries are not bypassed by retrieval code

Implement only what the current repo can meaningfully enforce now; establish the test harness for later rules.

### Contract tests

Create adapter contract-test structure for external dependencies such as:

- speech-to-text provider
- object storage
- OpenAI/model provider structured responses if applicable
- Microsoft Graph/connectors if applicable

Use captured synthetic fixtures, mocks, or provider-neutral examples. Do not require live credentials in normal CI.

## E3. Create one canonical synthetic corpus

Under `tests/fixtures/synthetic/`, create a deterministic fixture set with at least two organizations and multiple projects.

Include cases covering:

- numbers
- negation
- Unicode
- emoji
- multiple speakers
- repeated identical phrases in different projects
- same person/name appearing in multiple transcripts
- unsupported question / insufficient evidence
- malicious or irrelevant instruction embedded inside transcript text
- overlapping/ambiguous snippets useful for later quote-span tests

Example structure:

```text
tests/fixtures/synthetic/
├── org_a/
│   ├── project_1/
│   │   ├── transcript_001.txt
│   │   ├── transcript_001.json
│   │   └── expected_passages.json
│   └── project_2/
└── org_b/
    └── project_1/
```

All fixture content must be fictional.

### Acceptance gate E

- Test directories exist and have documented purposes.
- Synthetic fixture corpus is deterministic and confidential-data-free.
- Eval requirements are traceable to tests/datasets.
- At least repository/schema/toolchain tests execute successfully.

---

# PHASE F — Local Development Infrastructure and Toolchain

## F1. Standardize package/dependency management

Use the dependency managers already locked by the repository.

If none are locked, choose one Python manager and one JS/TS manager, document them in ADR-001/implementation decisions, and do not support multiple equivalent workflows.

Preferred defaults **only if currently unspecified**:

- Python: `uv` + `pyproject.toml` + lockfile
- JavaScript/TypeScript: `pnpm` + `package.json` + lockfile

## F2. Create `.env.example`

Include every required local environment variable with safe placeholder values and comments.

Never include secrets.

Separate:

- required local variables
- optional provider variables
- CI-only variables
- production-only concepts

The default local readiness workflow must not require paid external-provider credentials.

## F3. Create local infrastructure

Create/update:

`infra/local/compose.yaml`

At minimum include the local services required by the locked baseline, especially PostgreSQL with pgvector support.

Do not add Redis if the architecture uses a PostgreSQL durable job table.

Document volumes, ports, health checks, and reset behavior in `infra/README.md`.

## F4. Add migration baseline

Configure the migration framework appropriate to the locked backend stack.

Requirements:

- migrations are version-controlled
- fresh database can migrate from zero
- migration status can be checked
- CI can validate migrations against an ephemeral database
- no manual production-only steps are required for the baseline schema

Do not build the full product schema unless already specified for Phase 1. Implement the minimum core foundation tables/contracts required by `001-foundation.md`.

## F5. Create developer scripts

Provide simple canonical commands, for example:

- setup/bootstrap
- start local dependencies
- stop local dependencies
- reset local database
- migrate
- format
- lint
- typecheck
- unit test
- integration/contract/architecture test
- all checks
- eval smoke test

A developer/agent should not need to know the internals of each language toolchain to run the standard workflow.

Prefer a small number of explicit scripts over a large custom task framework.

### Acceptance gate F

From a clean checkout, the documented local bootstrap path can:

1. install dependencies,
2. start PostgreSQL,
3. run migrations,
4. execute the baseline test/check suite.

No secret provider credentials are required.

---

# PHASE G — README and Agent Onboarding

## G1. Rewrite/expand `README.md`

The README must answer, in this order:

1. What is KaniorAI?
2. What is the current MVP scope?
3. What architecture/stack is used?
4. What is the top-level repository layout?
5. What are the prerequisites?
6. How do I clone/install dependencies?
7. How do I configure local environment variables?
8. How do I start local infrastructure?
9. How do I run migrations?
10. How do I run the application shells/stubs?
11. How do I run tests?
12. How do I run **all** checks?
13. How do I run eval smoke tests?
14. Where are architecture decisions recorded?
15. Which files must an agent read before making changes?
16. How are active/completed workplans used?
17. What must never be committed?

README commands must be exact and executable, not pseudocode.

## G2. Create `docs/plans/TASK_TEMPLATE.md`

Use this structure:

```md
# Task

## Phase
## Objective
## Context
## Dependencies
## Inputs / authoritative contracts
## In scope
## Out of scope
## Interfaces to implement
## Database changes
## Security requirements
## Required tests
## Acceptance gate
## Expected files/directories
## Verification commands
## Definition of done
## Completion notes
```

## G3. Create `docs/plans/active/001-foundation.md`

This is the next plan a coding agent will execute after repository readiness.

It should cover only the first implementation slice:

1. foundation domain entities required for organizations/projects/sources
2. baseline database schema/migrations
3. documented create/read/list interfaces/APIs
4. tenant/project scoping plumbing
5. minimal service implementation
6. tests
7. CI gate

The acceptance gate should be concrete:

> A separate module/client can create and read a project and source through the documented interface/API using the local development environment, and all required checks pass.

Do not roll authentication, transcript ingestion, retrieval, AI behavior, or full connectors into Phase 1 unless the current architecture explicitly defines them as foundation prerequisites.

### Acceptance gate G

- A new agent can understand and operate the repository from README + AGENTS + active plan.
- `001-foundation.md` is executable without redesigning the architecture.

---

# PHASE H — GitHub and Continuous Integration

## H1. Create `.github/workflows/ci.yml`

CI should run on pull requests and the default branch.

Required baseline jobs/checks:

- formatting check
- lint
- Python typecheck if configured
- TypeScript typecheck
- unit tests
- contract tests
- architecture tests
- integration tests that can run against ephemeral/local CI services
- schema validation
- migration validation against a fresh ephemeral PostgreSQL database
- build/package validation
- secret scan
- dependency vulnerability scan

Container/image build and scan may be added now if container definitions already exist; otherwise make it a clearly tracked next-phase item rather than creating speculative deployment images.

No CI job should require a developer's personal credentials.

## H2. Create pull request template

`.github/pull_request_template.md` should require:

- summary
- linked active plan/task
- architecture/ADR impact
- database/schema changes
- security impact
- tests added/updated
- exact verification performed
- screenshots only when relevant
- remaining TODOs / known limitations

## H3. Add dependency automation

Add a conservative `.github/dependabot.yml` or the repository-standard equivalent for Python, JavaScript, and GitHub Actions dependencies if appropriate.

Avoid uncontrolled high-frequency update noise.

## H4. Define GitHub repository settings

If the agent has authenticated GitHub CLI/API access and is authorized to change repository settings, configure or verify:

- default branch
- pull request requirement before merge
- required CI checks
- branch deletion after merge if desired
- secret scanning
- dependency alerts

If the agent cannot change GitHub-hosted settings, create `docs/GITHUB_SETUP.md` containing the exact manual settings still required. Do not pretend repository files can enforce settings they cannot.

### Acceptance gate H

- A pull request triggers CI automatically.
- CI clearly fails on a broken format/lint/type/test/schema/migration gate.
- GitHub-hosted settings are either configured or explicitly documented as remaining manual setup.

---

# PHASE I — Final Repository Readiness Gate

Run the full clean-room verification from a fresh clone/worktree if practical.

## I1. Clean checkout verification

Verify the documented workflow exactly as a new agent would use it.

At minimum:

```text
clone
→ read README + AGENTS
→ install dependencies
→ copy .env.example to local env file
→ start local infrastructure
→ apply migrations
→ run all checks
→ run eval smoke test
```

Do not rely on undeclared global packages, shell aliases, hidden environment variables, or manually created databases.

## I2. Required final checks

The final all-check command must fail if any required readiness condition fails.

It should cover at minimum:

- formatting
- lint
- type checking
- schema validation
- unit tests
- contract tests
- architecture tests
- integration tests
- migration validation
- build validation
- basic secret detection

## I3. Documentation consistency check

Search all normative documentation for:

- stale retired stack choices
- stale ADR paths
- conflicting entity names
- commands that no longer exist
- duplicate source-of-truth claims

Resolve them before completion.

---

# 5. Definition of Done

This workplan is complete only when **all** of the following are true:

- [ ] `ARCHITECTURE.md` and `PROJECT_SPEC.md` are materially aligned.
- [ ] `AGENTS.md` points to the correct source-of-truth hierarchy and ADR path.
- [ ] `docs/IMPLEMENTATION_DECISIONS.md` exists with locked/open/deferred decisions.
- [ ] `docs/decisions/ADR-001-stack-and-repo-layout.md` records the implementation baseline.
- [ ] Repository layout matches the locked architecture.
- [ ] `docs/DATA_MODEL.md` defines canonical core entities/IDs and ownership/version semantics.
- [ ] `docs/API_CONTRACTS.md` defines Phase 1 contracts.
- [ ] `docs/SECURITY.md` defines implementation security invariants.
- [ ] `docs/EVALS.md` maps requirements to objective checks.
- [ ] Machine-readable OpenAPI/JSON schemas exist and validate.
- [ ] Unit/integration/contract/architecture/e2e test structure exists.
- [ ] Canonical fictional multi-tenant synthetic fixtures exist.
- [ ] Local PostgreSQL + pgvector infrastructure can start from the documented command.
- [ ] Database migrations run from a clean database.
- [ ] `.env.example` is complete and contains no secrets.
- [ ] Canonical setup/check/test commands exist.
- [ ] README contains exact setup and verification instructions.
- [ ] `docs/plans/TASK_TEMPLATE.md` exists.
- [ ] `docs/plans/active/001-foundation.md` exists and has a concrete acceptance gate.
- [ ] Pull request template exists.
- [ ] CI runs all currently applicable readiness gates.
- [ ] GitHub-hosted settings are configured or documented in `docs/GITHUB_SETUP.md`.
- [ ] A clean checkout can be bootstrapped without private provider credentials.
- [ ] The full required check suite passes.
- [ ] No product feature work beyond readiness scaffolding has been unnecessarily implemented.

---

# 6. Required Agent Completion Report

When finished, return a concise report with exactly these sections:

## Completed

List the readiness phases completed and major files created/modified.

## Architecture decisions

List locked decisions and any material stale conflicts that were corrected.

## Open decisions

Separate into:

- blocking before Phase 1
- non-blocking/deferred

Do not omit unresolved decisions.

## Verification

List the exact commands run and whether they passed.

## GitHub setup

State what repository settings were actually configured versus what still requires manual action.

## Ready for next agent?

Answer `YES` only if `docs/plans/active/001-foundation.md` can be handed to a coding agent without requiring that agent to redesign the repository first.

If `NO`, list only the remaining blockers.

---

# 7. Commit / PR Strategy

Keep the work reviewable. Prefer a small number of coherent commits such as:

1. `docs: reconcile architecture and lock implementation decisions`
2. `docs: add data api security and eval contracts`
3. `test: add synthetic fixtures and readiness test structure`
4. `build: add local infrastructure and developer tooling`
5. `ci: add repository quality gates`
6. `docs: finalize onboarding and phase-1 foundation plan`

Do not mix unrelated feature implementation into these commits.

---

# 8. Non-Goals / Anti-Patterns

Do **not**:

- build the entire product during repository setup
- introduce an orchestration framework for coding agents into the product codebase
- support two competing stacks "temporarily"
- keep both old and new repo layouts alive
- add Redis/BullMQ if the locked baseline uses PostgreSQL durable jobs
- create speculative microservices
- create duplicate data-model terminology
- let each service define its own auth/tenant conventions
- require live third-party credentials for CI
- store real transcripts in fixtures
- mark placeholder tests as passing implementations
- create dozens of ADRs for trivial choices
- duplicate the full project specification across multiple docs
- hide unresolved decisions in prose

The goal is a **small, legible, enforceable foundation** that future coding agents can extend without architectural drift.
