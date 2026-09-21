# Coding Agent Instructions

## Read First

Before modifying this repository, read:

```text
ARCHITECTURE.md
```

`ARCHITECTURE.md` is the source of truth for architecture, module boundaries, security rules, build order, and acceptance gates.

This file defines agent workflow and summarizes architectural requirements. If a summary or instruction here conflicts with `ARCHITECTURE.md`, follow `ARCHITECTURE.md` and reconcile the stale instruction. Agent workflow rules and task plans do not override the architecture.

Read the relevant architecture sections, `PROJECT_SPEC.md`, approved ADRs under `docs/decisions/`, and the active task plan before implementation. Use the repository layout in architecture §5 and canonical identifiers in §8; do not introduce competing layouts or names.

For foundation implementation, read `docs/DATA_MODEL.md`, `docs/API_CONTRACTS.md`, and `docs/SECURITY.md`. Follow `schemas/README.md` for the single contract-generation workflow; edit the Python contract sources, not generated OpenAPI, JSON schemas, or TypeScript declarations.

Before connector work, read `docs/INTEGRATIONS.md` and the relevant provider guide. Complete the Recall R1 and Graph G1 feasibility gates before their production connector implementations; documentation verification and fake-adapter tests are not live integration evidence.

If your task conflicts with it, do not silently change the architecture. Document the conflict and create an ADR if a material design change is required.

An agent MUST NOT create, submit, or mark a pull request
ready for review until:

    ./scripts/pr-ready.sh

exits with code 0.

---

## Model Routing

KaniorAI uses explicit model routing to control cost and match model capability
to task difficulty.

The authoritative routing policy is:

    docs/MODEL_ROUTING.md

Unless a task plan explicitly specifies otherwise:

- Terra: routine implementation, mechanical and deterministic edits
- Sol: default model for substantial engineering work
- Astra: high-complexity, high-risk, architectural, or unresolved work

Default model: Sol.

Use the cheapest model reasonably expected to complete the task correctly.

Escalation order:

   Terra → Sol → Astra

Escalate when:

- the task crosses multiple architectural boundaries;
- significant ambiguity exists;
- security, authorization, data integrity, or reliability is involved;
- the task requires architectural decisions;
- an implementation approach has failed repeatedly;
- debugging requires system-wide reasoning;
- acceptance tests cannot be made to pass despite reasonable attempts.

Do not use Astra for routine implementation merely because it is available.

After Astra diagnoses or plans a difficult problem, routine implementation SHOULD
be delegated back to Sol or Terra when practical.

Task-specific model assignments in an approved active plan override the default
routing guidance.

# Core Mission

Build a secure internal transcript-intelligence system that:

1. records or imports confidential research calls,
2. preserves raw artifacts and publishes approved, immutable transcript versions,
3. retrieves relevant evidence,
4. guarantees verified quotations are exact contiguous spans of approved, published transcript text,
5. links quotes to pinned transcript versions and audio provenance where available,
6. isolates tenants, workspaces, projects, and restricted documents correctly,
7. supports one-way versioned OneDrive export,
8. later supports live bookmarks, timestamped notes, and collaboration.

---

# Non-Negotiable Invariants

## 1. LLMs never author authoritative quote text

Follow architecture §§3, 14–16. The default selector returns allowed passage IDs from a server-sealed retrieval run. A separately validated precise-span mode may select:

```text
passage_id
start_character
end_character
```

Selector character positions are zero-based Unicode code-point offsets within the exact supplied passage text, start inclusive/end exclusive. Deterministic server code validates them, converts them to absolute UTF-8 byte offsets, and issues a `source_span_id`. Browser UTF-16 indexes are never canonical source offsets.

The server must fetch quote text from the pinned, approved, published transcript. Reject model-provided quote text, provenance, hashes, versions, source span IDs, unexpected fields, and selections outside the sealed run.

---

## 2. Every quote has provenance

Every quote must retain its pinned source and approval provenance under architecture §§8–9 and 15, including:

```text
source_span_id
passage_id
document_id
transcript_version_id
approval reference
source and span hashes
absolute byte offsets
```

Speaker, original audio references, and timing are nullable when unavailable. Never invent them. Audio review is optional; quote validity does not require audio comparison or retained audio.

---

## 3. Authorization happens before retrieval

Never search unauthorized content and filter afterward.

Apply tenant/workspace/project scope, document restrictions, publication/approval state, retention state, and current user permissions before ranking or limiting. Do not leak unauthorized counts, scores, snippets, or metadata. The evidence loader reauthorizes before sending candidate text to the selector.

---

## 4. Quote rendering re-checks authorization

Knowing or guessing a passage/span ID, possessing a stale candidate set, or reopening a saved answer must not grant access. Recheck current authorization and approval before delivery or export.

---

## 5. Source data is versioned

Never silently overwrite:

```text
original audio
raw transcript
normalized transcript
corrected transcript
approved transcript
```

Create versions. Only approved, published versions enter normal evidence search. Approval binds to the exact content hash; corrections require a new version and approval. Revocation blocks subsequent retrieval and quote delivery for the affected version.

Follow architecture §§10–12 for cleanup, approval, and publication. Automatic cleanup may only apply deterministically validated policy-allowed formatting edits. Invalid cleanup preserves unchanged parsed text and still passes through approval. Do not silently broaden cleanup to wording changes. Publish the active version pointer and outbox event atomically after the required lineage, approval, passage, index, and concurrency checks.

---

## 6. OneDrive is a one-way versioned export destination

Do not use OneDrive as the operational database.

Follow architecture §19 for immutable version exports, destination permission validation, retries, and drift reconciliation. Destination readers must not exceed authorized source readers.

---

## 7. Live transcription is provisional

Bookmarks and notes attach to recording timestamps, not transient transcript wording.

---

## 8. Confidential data stays out of logs

Do not put transcript text, note bodies, raw audio, confidential prompts/model responses, access tokens, or signed URLs in standard logs, traces, metrics, or error events. Query text requires an explicitly approved diagnostic policy. Use identifiers, timings, counts, states, and safe error codes instead.

---

# Required Development Order

Follow the authoritative build sequence and phase gates in architecture §29 and agent batches in §30:

0. Foundation decisions.
1. Secure source foundation.
2. Ingestion and recorder.
3. Evidence product.
4. MVP completion.
5. Live and collaborative features.
6. Production reliability and governance.

Do not implement a later phase by bypassing an unfinished foundational interface.

Parallel work requires stable dependencies and shared contracts. Synthetic-data implementation may proceed while the company-policy decisions in architecture §38 remain open; confidential pilot traffic must wait for the required approvals. Agents must not invent unresolved company policy.

---

# Stable Interface Rule

Depend on contracts, not implementation details.

Use the conceptual interfaces in architecture §7 and the task's documented contracts. Examples:

```text
RetrievalService.search_passages(...)
EvidenceSelector.select(...)
QuoteRenderer.render(...)
TranscriptionProvider.transcribe(...)
TranscriptApprovalService.approve(...)
TranscriptPublisher.publish(...)
ExportService.export(...)
AuthorizationService.authorize(...)
```

Do not reach directly into another package's database tables when a service contract exists.

Keep provider access behind connector/adapter boundaries; provider SDK types must not leak into domain contracts. The retriever cannot construct verified quotes, the selector cannot mutate source records, and the renderer cannot import model clients. Frontend code must use generated/shared contracts and cannot construct verified quotes from arbitrary strings.

---

# Before Starting a Task

1. Identify the architecture phase.
2. Identify dependencies.
3. Read relevant interfaces and tests.
4. Confirm prerequisite phase gates are satisfied, respecting the synthetic-data allowance in Phase 0.
5. Reuse existing contracts.
6. Avoid unrelated refactoring.

---

# While Implementing

Prefer:

```text
simple
explicit
typed
testable
idempotent
deterministic
```

over clever abstractions.

Do not introduce infrastructure merely because it might be useful later.

---

# Required Security Behavior

All resource access must be scoped by:

```text
tenant
workspace
project
document restrictions where applicable
current resource/action permission
```

Test access using direct API calls, not merely UI behavior.

Any endpoint receiving an ID must assume that ID may have been guessed.

Follow architecture §§20–21 for Entra employee assignment, server sessions, roles, and defense in depth. Enforce API/service checks, PostgreSQL RLS, scoped queries, worker revalidation, and delivery authorization. Administrative access does not automatically grant transcript-read access. Private object keys do not grant access; baseline audio playback uses an authorized API.

Keep provider credentials out of browser/desktop bundles. Use separate development, staging, and production resources/identities, with synthetic or explicitly approved de-identified data outside production.

---

# Quote Renderer Rule

The quote renderer is a trusted boundary.

Follow the complete trusted rendering path in architecture §15:

```text
principal + validated passage/span reference
 ↓
load sealed/pinned records
 ↓
reauthorize current access
 ↓
verify published state and current approval
 ↓
load exact immutable source and verify content hash
 ↓
validate bounds and UTF-8 boundaries
 ↓
slice exact bytes, verify span hash, and decode strictly
 ↓
reauthorize before delivery and write durable render audit
 ↓
return VerifiedQuote with provenance
```

No LLM call belongs inside the quote renderer.

Never substitute indexed text, model text, a newer version, or normalized search text. Integrity failures suppress the affected quote and raise an integrity event.

---

# AI Failure Rule

Follow architecture §§16 and 26. If no permitted relevant evidence is found, return a scoped no-evidence state; do not claim the information is absent globally. Keep provider/service failures distinct from lack of evidence.

Do not fill gaps using general model knowledge.

Synthesis consumes successfully rendered evidence only. Every claim must cite delivered source span IDs. Never stream unchecked model text or place generated prose in verified-quote fields/styling. If synthesis fails while evidence is available, return evidence with `analysis_unavailable`. Preserve deterministic search and quote functionality when model services are unavailable.

Jobs and external side effects must be idempotent under architecture §22. Use durable leases, bounded retries, provider-state reconciliation, and transactional outbox events; do not assume exactly-once external execution.

---

# Testing Requirements

Every feature must include relevant tests.

At minimum consider:

```text
happy path
invalid input
unauthorized user
wrong project
wrong tenant/workspace
missing resource
duplicate job
provider failure
retry behavior
```

Follow architecture §§27–28 for the applicable test suites and evaluation targets. Quote-related work must test exact approved-source byte equality, Unicode/emoji/combining marks, subspan boundaries, wrong versions, revoked approval, missing source bytes, and adversarial fabrication. No audio-comparison gate is required.

Test revocation during retrieval/delivery, unauthorized counts/metadata, and idempotent retries. Enforce module dependency boundaries with architecture tests. Activate relevant product evals alongside the protected behavior, following `docs/EVALS.md`.

---

# Module Completion Gate

Follow architecture §31. Before declaring completion, verify as applicable:

```text
implementation works
tests pass
authorization is tested
cross-tenant/project isolation is tested
failure behavior is tested
idempotency is tested
contracts are documented
migrations are included
logs contain no confidential content
architecture dependency checks pass
relevant evals and acceptance gates pass
CI passes
ARCHITECTURE.md remains accurate
```

---

# Handoff Format

At completion, report:

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

---

# Architectural Changes

Material architecture changes require an ADR under:

```text
docs/decisions/
```

Follow architecture §37 for ADR contents and §4 for locked implementation choices. Do not silently replace:

- FastAPI/Python API strategy,
- PostgreSQL/pgvector,
- Entra identity strategy,
- transcript approval/version model,
- deterministic quote renderer,
- baseline storage provider,
- Recall capture integration,
- AssemblyAI transcription integration,
- project-isolation strategy,
- provider abstraction boundaries,
- OneDrive one-way export model,
- PostgreSQL jobs/outbox baseline.

Update the architecture when an approved material decision changes it. Pin provider, model, runtime, and API versions as required by the architecture.

---

# Optimization Rule

Optimize only after measuring.

The first objective is correctness and source integrity.

The preferred MVP is a simple modular monolith rather than unnecessary microservices.

---

# Source-of-Truth Rule

When code, prompts, or product behavior conflict with source integrity, preserve source integrity.

The north-star rule is:

> Retrieval locates authorized evidence. AI reasons over permitted evidence. Deterministic code renders approved transcript truth.

The approved, published transcript is the quote source of truth. Apply the complete prohibitions in architecture §39; summaries here do not relax them.

<!-- gitnexus:start -->
# GitNexus — Code Intelligence

This project is indexed by GitNexus as **Kanior.io** (56170 symbols, 176209 relationships, 689 execution flows).

> Index stale? Run `node .gitnexus/run.cjs analyze --index-only` from the project root — it auto-selects an available runner. No `.gitnexus/run.cjs` yet? Bootstrap with `npx`, `bunx`, or `pnpm dlx` — e.g. `bunx gitnexus@latest analyze` (npm 11 npx crash; #1939).

## Always Do

- **MUST run impact before editing.** Use `impact({target: "symbolName", direction: "upstream"})` or `node .gitnexus/run.cjs impact "symbolName" --direction upstream --repo .`; report callers, processes, and risk. Never substitute grep for graph analysis.
- **MUST analyze graph changes before committing.** Use `detect_changes({scope: "all"})` (MCP) or `node .gitnexus/run.cjs detect-changes --scope all --repo .` (CLI fallback). `partial: true` or `truncated: true` is not a clean check — a zero means unseen, not unaffected; re-run it. For regression review: `detect_changes({scope: "compare", base_ref: "main"})` or `node .gitnexus/run.cjs detect-changes --scope compare --base-ref "main" --repo .`.
- MUST warn on HIGH/CRITICAL `risk` pre-edit; never use `riskSharedAxes` to waive a HIGH/CRITICAL `risk` warning. Compare File/symbol: MCP File omits axes; Graph-RAG expands File.
- **MUST treat `risk: UNKNOWN` as unresolved, not as low.** An empty caller set is not evidence the symbol is unused — it can also mean the callers are not resolvable by the index (plain-object property access, dynamic dispatch, cross-language calls). `impact` pairs `UNKNOWN` with a `riskNote` saying so. Confirm with a text search before treating the symbol as safe to change or delete; do not proceed on the strength of a zero.
- **MUST use `query({search_query: "concept"})` for concepts/flows, `context({name: "symbolName"})` for a named symbol, or `impact` for blast radius, on read-only callers, dependencies, imports, or execution flow.** Graph first; text search only for empty/`UNKNOWN`/literals.
- For security review, `explain({target: "fileOrSymbol"})` lists taint findings (source→sink flows; needs `analyze --pdg`).

## Never Do

- NEVER edit a function, class, or method before MCP/CLI impact analysis.
- NEVER ignore HIGH or CRITICAL risk warnings from impact analysis, and never read `UNKNOWN` as an all-clear — it means the walk could not answer, which is the one verdict that requires confirming by other means.
- NEVER rename symbols with find-and-replace — use `rename` which understands the call graph.
- NEVER commit before MCP/CLI graph change analysis.

## Resources

| Resource | Use for |
| --- | --- |
| `gitnexus://repo/Kanior.io/context` | Codebase overview, check index freshness |
| `gitnexus://repo/Kanior.io/clusters` | All functional areas |
| `gitnexus://repo/Kanior.io/processes` | All execution flows |
| `gitnexus://repo/Kanior.io/process/{name}` | Step-by-step execution trace |

## CLI

| Task | Read this skill file |
| --- | --- |
| Understand architecture / "How does X work?" | `.claude/skills/gitnexus-exploring/SKILL.md` |
| Blast radius / "What breaks if I change X?" | `.claude/skills/gitnexus-impact-analysis/SKILL.md` |
| Trace bugs / "Why is X failing?" | `.claude/skills/gitnexus-debugging/SKILL.md` |
| Rename / extract / split / refactor | `.claude/skills/gitnexus-refactoring/SKILL.md` |
| Tools, resources, schema reference | `.claude/skills/gitnexus-guide/SKILL.md` |
| Index, status, clean, wiki CLI commands | `.claude/skills/gitnexus-cli/SKILL.md` |

<!-- gitnexus:end -->
