# Coding Agent Instructions

## Read First

Before modifying this repository, read:

```text
ARCHITECTURE.md
```

`ARCHITECTURE.md` is the source of truth for architecture, module boundaries, security rules, build order, and acceptance gates.

If your task conflicts with it, do not silently change the architecture. Document the conflict and create an ADR if a material design change is required.

An agent MUST NOT create, submit, or mark a pull request
ready for review until:

    ./scripts/pr-ready.sh

exits with code 0.

---

# Core Mission

Build a secure internal transcript-intelligence system that:

1. records or imports confidential research calls,
2. creates searchable timestamped transcripts,
3. retrieves relevant evidence,
4. guarantees displayed quotations are exact source text,
5. links quotes to transcript/audio provenance,
6. isolates users/projects correctly,
7. supports OneDrive synchronization,
8. later supports live bookmarks, timestamped notes, and collaboration.

---

# Non-Negotiable Invariants

## 1. LLMs never author authoritative quote text

The LLM may select:

```text
passage_id
start_offset
end_offset
```

The server must fetch quote text from the stored transcript.

Never trust a model-provided `quote_text` field.

---

## 2. Every quote has provenance

Every quote must map to:

```text
passage_id
source_id
transcript_version_id
speaker
timestamp
```

where available.

---

## 3. Authorization happens before retrieval

Never search unauthorized content and filter afterward.

---

## 4. Quote rendering re-checks authorization

Knowing or guessing a passage ID must not grant access.

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

Create versions.

---

## 6. OneDrive is a sync destination

Do not use OneDrive as the operational database.

---

## 7. Live transcription is provisional

Bookmarks and notes attach to recording timestamps, not transient transcript wording.

---

## 8. Confidential data stays out of logs

Do not log transcript text, note bodies, raw audio, or full confidential prompts in standard application logging.

---

# Required Development Order

Respect dependency order.

```text
Foundation
 ↓
Authentication / Permissions
 ↓
Source Data Model
 ↓
Upload / Storage
 ↓
Transcript Normalization
 ↓
Exact Quote Renderer
 ↓
Keyword Search
 ↓
Semantic Retrieval
 ↓
AI Evidence Selection
 ↓
Transcription
 ↓
Audio Alignment
 ↓
OneDrive
 ↓
Core UI
 ↓
Recording
 ↓
Bookmarks
 ↓
Notes
 ↓
Live Transcription
 ↓
Collaboration
 ↓
Admin / Compliance
 ↓
Production Hardening
```

Do not implement a later phase by bypassing an unfinished foundational interface.

---

# Stable Interface Rule

Depend on contracts, not implementation details.

Examples:

```ts
RetrievalService.searchPassages(...)
QuoteRenderer.renderQuote(...)
TranscriptionProvider.transcribe(...)
AIProvider.selectEvidence(...)
OneDriveSyncService.sync(...)
AuthorizationService.authorize(...)
```

Do not reach directly into another package's database tables when a service contract exists.

---

# Before Starting a Task

1. Identify the architecture phase.
2. Identify dependencies.
3. Read relevant interfaces and tests.
4. Confirm the previous phase's gate is satisfied.
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
organization
project
resource permission
```

Test access using direct API calls, not merely UI behavior.

Any endpoint receiving an ID must assume that ID may have been guessed.

---

# Quote Renderer Rule

The quote renderer is a trusted boundary.

Its basic operation is:

```text
passage ID
 ↓
authorization
 ↓
load canonical passage
 ↓
validate offsets
 ↓
extract exact substring
 ↓
return source metadata
```

No LLM call belongs inside the quote renderer.

---

# AI Failure Rule

If evidence is insufficient, return an insufficient-evidence state.

Do not fill gaps using general model knowledge.

---

# Testing Requirements

Every feature must include relevant tests.

At minimum consider:

```text
happy path
invalid input
unauthorized user
wrong project
wrong organization
missing resource
duplicate job
provider failure
retry behavior
```

Quote-related work must include adversarial hallucination tests.

---

# Module Completion Gate

Do not declare a task complete until:

```text
implementation works
tests pass
authorization is tested
failure behavior is tested
contracts are documented
migrations are included
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
docs/ADR/
```

Do not silently replace:

- PostgreSQL,
- pgvector,
- authentication strategy,
- transcript version model,
- quote rendering model,
- storage model,
- project-isolation strategy,
- external provider abstraction.

---

# Optimization Rule

Optimize only after measuring.

The first objective is correctness and source integrity.

The preferred MVP is a simple modular monolith rather than unnecessary microservices.

---

# Source-of-Truth Rule

When code, prompts, or product behavior conflict with source integrity, preserve source integrity.

The north-star rule is:

> Retrieval locates evidence. AI reasons over evidence. Deterministic code renders source truth.