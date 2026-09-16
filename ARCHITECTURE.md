# Secure Transcript Intelligence Platform — Architecture & Build Plan

## 1. Purpose

This document is the technical source of truth for building the Secure Transcript Intelligence Platform.

The application is an internal, company-only system for:

- Recording meetings.
- Uploading existing recordings and transcripts.
- Producing accurate, cleaned, timestamped transcripts.
- Treating the cleaned transcript as the canonical source of truth after processing.
- Searching transcripts by keyword and meaning.
- Asking AI questions across authorized transcripts.
- Returning quotations that are guaranteed to be copied exactly from stored source text.
- Linking every quotation to its source transcript, speaker, and transcript timestamp.
- Allowing interviewers to bookmark important moments during live calls.
- Allowing interviewers to create timestamped notes during calls.
- Synchronizing cleaned transcripts and related artifacts to company OneDrive.
- Keeping confidential data isolated, permission-controlled, encrypted, auditable, and securely stored.

This document defines:

1. Architectural principles.
2. Security invariants.
3. Core data model.
4. Module boundaries.
5. Stable interfaces.
6. Build sequence.
7. Acceptance gates.
8. Testing requirements.
9. Agent-development rules.
10. MVP and production milestones.

---

# 2. Primary Product Goals

The system must optimize for the following goals, in priority order.

## 2.1 Confidentiality

Company research is confidential.

The system must prevent unauthorized users, organizations, projects, services, or model providers from accessing source material.

Security is part of the architecture, not a feature added later.

---

## 2.2 Quote integrity

Any text displayed to the user as a direct quotation must exist exactly in the canonical cleaned transcript.

The LLM must never generate quotation text.

The central invariant is:

> AI may decide which evidence is relevant. Deterministic application code determines what the cleaned transcript actually says.

---

## 2.3 Provenance

Every displayed quote must resolve to:

```text
Quote
  ↓
Passage ID
  ↓
Canonical Cleaned Transcript
  ↓
Source / Meeting
  ↓
Speaker
  ↓
Transcript Timestamp
```

The cleaned transcript is the application's source of truth.

The original audio is not required to validate a displayed quotation.

---

## 2.4 Transcript Ground Truth

The transcription pipeline may produce several intermediate artifacts:

```text
Original Recording
      ↓
Raw STT Output
      ↓
Normalized Transcript
      ↓
Cleaned Transcript
```

Once the cleaned transcript has been successfully generated and stored, it becomes the canonical source of truth for:

- quotation rendering,
- search,
- semantic indexing,
- GPT evidence selection,
- citations,
- bookmarks,
- notes,
- OneDrive synchronization,
- downstream analysis.

The application does not need to verify quotations against the underlying audio.

The quote guarantee is:

> Quotes are 100% identical to text contained in the canonical cleaned transcript.

Audio can still be retained for operational, archival, or compliance reasons, but it is not part of the quote-verification chain.

Depending on company retention policy, original audio may eventually be deleted after successful transcription and transcript processing.

---

## 2.5 Project isolation

Projects are separate research workspaces.

Content in one project must not automatically become searchable from another project.

Authorization must happen before retrieval.

---

## 2.6 Extensibility

The initial application should be deliberately simple, but all foundational systems must support later addition of:

- live recording,
- live transcription,
- bookmarks,
- timestamped notes,
- collaborative projects,
- transcript editing,
- richer AI analysis,
- meeting integrations,
- compliance tooling,
- additional document types.

---

# 3. Architectural Principles

## Principle 1 — Canonical transcript data is immutable

Once a cleaned transcript becomes canonical, do not silently alter it.

If changes are required, create a new transcript version.

Example:

```text
Raw STT Transcript
      ↓
Normalized Transcript
      ↓
Cleaned Transcript v1
      ↓
Corrected Cleaned Transcript v2
```

Only one transcript version should be designated as the current canonical version for a source at a given time.

All passages and quotations must identify which canonical transcript version they derive from.

---

## Principle 2 — The cleaned transcript is the source of truth

Do not require audio verification for downstream search or quotation.

Once cleaning is complete:

```text
Cleaned Transcript
      ↓
Passages
      ↓
Search
      ↓
Quotes
      ↓
AI Analysis
```

All downstream systems operate against the cleaned transcript.

---

## Principle 3 — Retrieval and rendering are separate

Retrieval answers:

> Which source passages appear relevant?

Rendering answers:

> What exact characters exist in that cleaned transcript passage?

These must be separate components.

---

## Principle 4 — LLMs never render quotes

An LLM may return:

```json
{
  "selected_passage_ids": ["passage_123", "passage_981"]
}
```

It must not be trusted to return:

```json
{
  "quote": "The customer said..."
}
```

Any `quote_text` generated by an LLM must be ignored or rejected.

---

## Principle 5 — Authorization precedes retrieval

Never retrieve broadly and filter afterward.

The retrieval universe must first be constrained to data the requesting user can access.

Conceptually:

```text
User
 ↓
Authenticate
 ↓
Determine authorized projects/sources
 ↓
Search authorized passages only
 ↓
Evidence selection
 ↓
Render selected source text
```

---

## Principle 6 — Authorization occurs again during rendering

Even if a passage ID reaches the renderer, the renderer must independently check whether the user is allowed to access it.

A guessed passage ID must not expose data.

---

## Principle 7 — OneDrive is not the operational database

OneDrive is a synchronized company repository.

The application retains its own canonical operational store for:

- projects,
- permissions,
- cleaned transcript versions,
- passages,
- search indices,
- bookmarks,
- notes,
- provenance,
- sync metadata.

---

## Principle 8 — Live systems must not determine permanent truth

Live transcription is provisional.

The post-call processing pipeline creates the canonical cleaned transcript.

Live bookmarks and notes should depend on recording timestamps rather than provisional transcript wording.

After processing, those timestamps are mapped to the canonical transcript.

---

## Principle 9 — Modules communicate through stable contracts

Agents should implement modules against interfaces rather than directly depending on another module's implementation.

Example:

```ts
searchPassages(
  query: SearchQuery,
  permissions: AuthContext
): Promise<PassageReference[]>
```

and:

```ts
renderPassage(
  selection: QuoteSelection,
  auth: AuthContext
): Promise<VerbatimPassage>
```

The retrieval implementation can change without changing the quote renderer.

---

# 4. Recommended Technical Stack

This is the default stack unless an Architectural Decision Record explicitly changes it.

## Front end

```text
Next.js
React
TypeScript
```

---

## Backend

```text
Node.js
TypeScript
```

A small dedicated API service is preferred over placing all backend logic inside frontend routes.

---

## Repository

Recommended structure:

```text
/
├── apps/
│   ├── web/
│   ├── api/
│   └── worker/
│
├── packages/
│   ├── contracts/
│   ├── database/
│   ├── auth/
│   ├── storage/
│   ├── transcripts/
│   ├── retrieval/
│   ├── quote-engine/
│   ├── ai/
│   └── shared/
│
├── tests/
├── infrastructure/
├── docs/
│   ├── ADR/
│   └── diagrams/
│
├── AGENTS.md
└── ARCHITECTURE.md
```

A pnpm workspace / monorepo is appropriate.

---

## Structured data

```text
PostgreSQL
```

PostgreSQL is the system of record.

---

## Semantic retrieval

```text
pgvector
```

Keep vectors inside PostgreSQL initially.

Do not introduce a separate vector database unless scale measurements justify it.

---

## File/object storage

Prefer:

```text
Azure Blob Storage
```

Store as required:

- original recordings,
- original uploads,
- raw transcription outputs,
- derived exports.

Audio retention should be configurable.

The application must not depend on permanent audio retention.

---

## Authentication

```text
Microsoft Entra ID
```

No public account creation.

Only authorized company identities may authenticate.

---

## Microsoft integrations

```text
Microsoft Graph API
```

Use for:

- OneDrive,
- optional Outlook/calendar integration,
- future Teams integration.

---

## Background jobs

Introduce a queue/workflow abstraction.

An MVP may use:

```text
Redis + BullMQ
```

More complicated production workflows may later migrate behind the abstraction to a durable workflow system.

Do not make business logic depend directly on BullMQ-specific concepts.

---

## Speech-to-text

Create a provider abstraction.

Example:

```ts
interface TranscriptionProvider {
  transcribe(input: AudioReference): Promise<RawTranscript>;
}
```

The implementation may use Azure Speech, Deepgram, or another approved enterprise provider.

Provider selection should be benchmarked against representative company calls.

---

## LLM provider

Create an AI gateway.

Example:

```ts
interface AIProvider {
  cleanTranscript(...): Promise<CleanedTranscript>;
  selectEvidence(...): Promise<EvidenceSelection>;
  synthesizeAnswer(...): Promise<Synthesis>;
}
```

Business modules must not call external model APIs directly.

Only providers approved for confidential company data may be used.

---

# 5. Core Identifiers

Define these before significant feature development begins.

```text
organization_id
user_id

project_id
project_membership_id

source_id
source_file_id

transcript_version_id
speaker_id
passage_id

recording_id

bookmark_id
note_id

answer_id
evidence_selection_id

audit_event_id
sync_job_id
```

Use globally unique identifiers.

Prefer UUIDs or equivalent opaque IDs.

Never expose sequential database IDs where avoidable.

---

# 6. Core Data Model

## Organization

```text
organizations
-------------
id
name
created_at
```

---

## User

```text
users
-----
id
organization_id
entra_subject_id
email
display_name
status
created_at
last_login_at
```

---

## Project

```text
projects
--------
id
organization_id
name
description
created_by
created_at
archived_at
```

---

## Project Membership

```text
project_memberships
-------------------
project_id
user_id
role
created_at
```

Suggested roles:

```text
viewer
member
manager
admin
```

---

# 7. Sources

A source represents a research artifact.

Examples:

```text
meeting recording
uploaded recording
uploaded transcript
PDF
DOCX
```

Schema:

```text
sources
-------
id
organization_id
project_id
source_type
title
created_by
created_at
processing_status
canonical_transcript_version_id nullable
```

`canonical_transcript_version_id` identifies the transcript currently treated as ground truth.

---

# 8. Source Files

Original uploaded files should initially be preserved.

```text
source_files
------------
id
source_id
storage_key
original_filename
mime_type
byte_size
sha256_hash
created_at
retention_status
deleted_at nullable
```

The SHA-256 hash enables integrity checking.

Recording files may later be deleted according to configured retention policy without invalidating transcript-based quotes.

---

# 9. Transcript Versions

Never silently overwrite the canonical transcript.

```text
transcript_versions
-------------------
id
source_id
parent_version_id
version_type
status
created_by
created_at
canonicalized_at nullable
```

Suggested `version_type` values:

```text
raw_stt
normalized
cleaned
corrected_cleaned
```

Suggested `status` values:

```text
processing
draft
canonical
superseded
```

There must be at most one current `canonical` transcript version per source.

---

# 10. Canonical Transcript Rule

The transcript processing pipeline ends when a cleaned transcript becomes canonical.

Conceptually:

```text
Raw STT
 ↓
Normalized
 ↓
Cleaned
 ↓
Canonical
```

All downstream passages, search indices, embeddings, citations, and quotes must reference the canonical transcript version.

If the canonical transcript is corrected later:

```text
Canonical v1
 ↓
Correction
 ↓
Canonical v2
```

v1 becomes superseded.

Derived passages and embeddings for v2 are regenerated.

Existing historical answer records may continue to reference v1 for auditability.

---

# 11. Speakers

```text
speakers
--------
id
transcript_version_id
label
display_name
```

---

# 12. Passages

A passage is the smallest addressable source unit used by retrieval.

Examples:

- interview Q&A block,
- speaker turn,
- paragraph group.

```text
passages
--------
id
organization_id
project_id
source_id
transcript_version_id
speaker_id

sequence_number

text

start_time_ms
end_time_ms

start_character
end_character

text_hash

created_at
```

Each active searchable passage must derive from the source's current canonical transcript.

---

# 13. Embeddings

Conceptually:

```text
passage_embeddings
------------------
passage_id
embedding
embedding_model
created_at
```

Embeddings are derived data.

If either the canonical transcript or embedding model changes, embeddings can be regenerated.

---

# 14. Bookmarks

```text
bookmarks
---------
id
organization_id
project_id
source_id
recording_id
created_by

client_timestamp
recording_offset_ms

passage_id nullable

visibility

created_at
```

The bookmark initially attaches to the meeting/recording timeline.

After creation of the canonical cleaned transcript, it attaches to the transcript passage covering that timestamp.

Audio playback is not required for bookmark functionality.

---

# 15. Notes

```text
notes
-----
id
organization_id
project_id
source_id
recording_id
created_by

recording_offset_ms
body

passage_id nullable

created_at
updated_at
```

Notes must survive even if live transcription fails.

After canonical transcript creation, map each note to the nearest relevant passage.

---

# 16. AI Answers

```text
answers
-------
id
organization_id
project_id
user_id
question
synthesis
created_at
```

---

## Evidence Selections

```text
answer_evidence
---------------
answer_id
passage_id
start_offset nullable
end_offset nullable
retrieval_score
selection_reason nullable
```

Do not store model-generated quotation strings as authoritative evidence.

---

# 17. OneDrive Sync State

```text
onedrive_sync_state
-------------------
source_id
transcript_version_id
onedrive_item_id
last_synced_at
sync_status
content_hash
```

Only canonical cleaned transcript versions should normally be synchronized as final transcript artifacts.

---

# 18. Audit Events

```text
audit_events
------------
id
organization_id
user_id
event_type
resource_type
resource_id
metadata
created_at
```

Eventually track:

```text
LOGIN
SOURCE_VIEW
SEARCH
QUOTE_RENDER
EXPORT
TRANSCRIPT_EDIT
TRANSCRIPT_CANONICALIZE
ONEDRIVE_SYNC
DELETE
PERMISSION_CHANGE
```

---

# 19. Quote-Safety Architecture

This is the most important architectural requirement.

## Step 1 — User asks a question

Example:

```text
What did experts say about pricing pressure?
```

---

## Step 2 — Authorization scope is calculated

Determine the:

```text
organization
projects
sources
canonical transcript versions
```

the user is permitted to search.

---

## Step 3 — Retrieval finds candidate passages

Search may combine:

```text
PostgreSQL full-text search
+
pgvector semantic similarity
+
metadata filters
```

Output:

```json
[
  {
    "passage_id": "p_123",
    "score": 0.92
  },
  {
    "passage_id": "p_456",
    "score": 0.87
  }
]
```

Retrieval returns references.

Retrieval does not create quotations.

---

# 20. Evidence Selection

The LLM receives authorized candidate passages.

Its job is to decide which evidence supports the answer.

Required structured output:

```json
{
  "status": "supported",
  "answer": "Experts generally described continued pricing pressure...",
  "selected_passages": [
    {
      "passage_id": "p_123"
    },
    {
      "passage_id": "p_456"
    }
  ]
}
```

Or:

```json
{
  "status": "insufficient_evidence",
  "answer": null,
  "selected_passages": []
}
```

The LLM is not an authoritative source for quote strings.

---

# 21. Deterministic Quote Renderer

The renderer is ordinary server code.

Conceptual interface:

```ts
type QuoteSelection = {
  passageId: string;
  startOffset?: number;
  endOffset?: number;
};

type VerbatimQuote = {
  passageId: string;
  text: string;
  speaker: string | null;
  startTimeMs: number | null;
  endTimeMs: number | null;
  sourceId: string;
  transcriptVersionId: string;
};

async function renderQuote(
  selection: QuoteSelection,
  auth: AuthContext
): Promise<VerbatimQuote>;
```

Implementation flow:

```text
Receive passage ID
 ↓
Authenticate request
 ↓
Load passage
 ↓
Verify organization
 ↓
Verify project permission
 ↓
Verify transcript version is canonical or historically referenced
 ↓
Validate requested offsets
 ↓
Extract exact stored characters
 ↓
Return exact text
```

No language model participates in this operation.

No audio lookup or verification is required.

---

# 22. Hard Quote Invariants

The following rules must never be violated.

### Q1

The UI must not accept arbitrary quote text from an LLM.

### Q2

Every displayed quote must have a `passage_id`.

### Q3

Every displayed quote must resolve to a stored transcript version.

### Q4

Every active quote must derive from canonical cleaned transcript text.

### Q5

Every quote must equal the stored source substring exactly.

Server-side assertion:

```ts
renderedQuote.text ===
storedPassage.text.slice(startOffset, endOffset)
```

### Q6

The renderer performs authorization independently.

### Q7

If evidence cannot be located, return:

```text
Insufficient evidence
```

Do not fabricate likely wording.

### Q8

LLM analysis may paraphrase.

Paraphrased analysis must visually differ from direct quotations.

### Q9

Quote provenance must remain available after model/provider changes.

### Q10

Audio verification is not required for quote validity.

---

# 23. Retrieval Interface

Stable interface:

```ts
interface RetrievalService {
  searchPassages(
    query: string,
    auth: AuthContext,
    filters?: SearchFilters
  ): Promise<PassageReference[]>;
}
```

Example:

```ts
type PassageReference = {
  passageId: string;
  sourceId: string;
  score: number;
  startTimeMs?: number;
  speakerId?: string;
};
```

Changing retrieval algorithms must not require changing quote rendering.

---

# 24. Source Ingestion Pipeline

```text
Upload / Recording
 ↓
Validate input
 ↓
Store original where required
 ↓
Calculate checksum
 ↓
Create source record
 ↓
Create processing job
 ↓
Extract / transcribe
 ↓
Normalize
 ↓
Clean transcript
 ↓
Designate canonical transcript
 ↓
Create passages
 ↓
Index keyword search
 ↓
Generate embeddings
 ↓
Ready
```

Each step should have explicit processing state.

---

# 25. Processing States

Suggested states:

```text
UPLOADED
PROCESSING
TRANSCRIBING
NORMALIZING
CLEANING
INDEXING
READY
FAILED
```

`READY` means the canonical cleaned transcript and its derived passages are available.

Failures must be retryable without duplicating sources.

Background jobs must be idempotent.

---

# 26. Uploaded Transcript Pipeline

Supported initial formats:

```text
TXT
SRT
VTT
```

DOCX can follow.

Flow:

```text
Original Upload
 ↓
Format Parser
 ↓
Normalized Representation
 ↓
Cleaning
 ↓
Canonical Cleaned Transcript
 ↓
Passages
 ↓
Index
```

The original uploaded transcript may be retained for audit/history, but retrieval operates against the cleaned canonical version.

---

# 27. Recording / STT Pipeline

```text
Recording
 ↓
Secure Object Storage
 ↓
Transcription Provider
 ↓
Raw STT Output
 ↓
Normalization
 ↓
Cleaning
 ↓
Canonical Cleaned Transcript
 ↓
Passages
 ↓
Search Index
```

The canonical cleaned transcript, not the original audio, is the source of truth for all downstream research functionality.

---

# 28. Audio Retention

The system may retain audio depending on company policy.

Possible retention strategies:

```text
retain indefinitely
retain for configurable number of days
delete after successful transcript processing
delete manually
```

Deleting audio must not affect:

- transcript search,
- quote rendering,
- AI answers,
- citations,
- bookmarks,
- notes,
- OneDrive transcript copies.

Audio retention policy should therefore remain independent from transcript integrity.

---

# 29. Transcript Timestamp Navigation

Timestamp metadata remains useful even without audio validation.

Each passage should retain:

```text
start_time_ms
end_time_ms
```

This enables:

- transcript navigation,
- bookmark placement,
- note placement,
- jumping between marked moments,
- chronological transcript browsing.

The UI may display timestamps such as:

```text
[23:14]
```

without requiring an audio player.

---

# 30. Live Bookmark System

The bookmark system depends on meeting/recording time, not provisional transcript text.

Keyboard event:

```text
User presses configured hotkey
 ↓
Capture current recording_offset_ms
 ↓
Immediately persist bookmark
```

API:

```ts
POST /recordings/:recordingId/bookmarks
```

Payload:

```json
{
  "recording_offset_ms": 1394000
}
```

After final transcript processing:

```text
Bookmark Timestamp
 ↓
Find Canonical Transcript Passage Covering Timestamp
 ↓
Attach passage_id
```

The user can then jump directly between marked transcript locations.

---

# 31. Timestamped Notes

Notes follow the same timing system.

Example:

```ts
POST /recordings/:recordingId/notes
```

```json
{
  "recording_offset_ms": 1394000,
  "body": "Important comment about customer churn."
}
```

After transcript processing:

```text
Note Timestamp
 ↓
Canonical Transcript
 ↓
Nearest Passage
```

The UI displays the note beside that transcript location.

---

# 32. Live Transcription

Live transcription is optional for the first MVP.

When implemented:

```text
Audio Stream
 ↓
Streaming STT
 ↓
Provisional Transcript
```

After the meeting:

```text
Full Recording
 ↓
High-Accuracy STT
 ↓
Normalization
 ↓
Cleaning
 ↓
Canonical Transcript
```

The provisional live transcript is discarded or archived once the canonical cleaned transcript is ready.

Bookmarks and notes stay anchored to time offsets and therefore survive transcript replacement.

---

# 33. OneDrive Integration

Use Microsoft Graph.

Initial synchronization should include:

```text
canonical cleaned transcript
source metadata
notes
bookmarks
```

Optionally:

```text
audio
AI summaries
exports
```

Internal storage remains authoritative for application state.

---

# 34. Authentication & Authorization

Authentication:

```text
Microsoft Entra ID
```

There must be no public signup.

Validate:

```text
tenant
account
organization membership
account status
```

Do not rely solely on email suffix checking.

---

# 35. Authorization Hierarchy

Conceptually:

```text
Organization
  └── Project
       └── Source
            └── Transcript Version
                 └── Passage
```

Access to a child resource requires access through its parent hierarchy.

---

# 36. Defense in Depth

Authorization should occur at multiple layers:

```text
API middleware
+
service layer
+
database query scoping
+
quote renderer
```

Where practical, use PostgreSQL Row-Level Security or equivalent database protections as an additional defense.

---

# 37. MVP Definition

The first meaningful application milestone is:

```text
Login
 ↓
Create Project
 ↓
Upload Transcript
 ↓
Securely Store Source
 ↓
Normalize + Clean Transcript
 ↓
Designate Canonical Transcript
 ↓
Create Passages
 ↓
Search Passages
 ↓
Display Exact Transcript Quotes
 ↓
View Source Context
```

This milestone should work without an LLM.

---

# 38. MVP + AI Definition

Next milestone:

```text
Canonical Transcript
 ↓
Hybrid Retrieval
 ↓
Ask Natural-Language Question
 ↓
LLM Selects Evidence
 ↓
Application Renders Exact Quotes
 ↓
LLM Synthesizes Cited Analysis
```

At this point the platform becomes an AI research system.

---

# 39. Build Sequence

Modules should generally be completed in this order.

## Phase 1 — Repository + shared contracts + infrastructure

Build:

- monorepo,
- environments,
- local development,
- CI,
- secrets handling,
- PostgreSQL,
- object storage,
- migrations,
- logging,
- shared contracts.

### Gate

Another module can create/read a project and source using documented APIs.

---

## Phase 2 — Authentication + permissions

Build:

- Entra authentication,
- organization membership,
- project permissions,
- authorization middleware,
- tenant-aware database queries.

### Gate

A user cannot read an unauthorized source even if they know its ID.

---

## Phase 3 — Canonical source/transcript data model

Build:

- source records,
- uploaded files,
- transcript versions,
- canonical transcript designation,
- passages,
- speakers,
- timestamps,
- provenance metadata.

### Gate

Every passage deterministically resolves to one canonical cleaned transcript version and source.

---

## Phase 4 — File ingestion

Build:

- secure upload,
- object storage,
- hashes,
- validation,
- processing states.

### Gate

Upload → storage → source record works reliably.

---

## Phase 5 — Transcript normalization + cleaning

Build:

- transcript parsers,
- normalization,
- cleaning,
- canonicalization,
- passage creation.

### Gate

A known transcript can be imported, cleaned, designated canonical, and reproduced reliably from internal records.

---

## Phase 6 — Quote renderer

Build deterministic rendering before AI.

### Gate

The renderer cannot output characters that do not exist in the canonical cleaned transcript.

---

## Phase 7 — Keyword search

Build PostgreSQL full-text retrieval.

### Gate

Search → passage → exact quote → transcript context works end-to-end.

---

## Phase 8 — Semantic retrieval

Build:

```text
embeddings
pgvector
hybrid ranking
```

### Gate

Conceptual queries retrieve relevant passages despite vocabulary mismatch.

---

## Phase 9 — Quote-safe AI

Build:

- AI gateway,
- evidence-selection schema,
- insufficient-evidence behavior,
- synthesis.

### Gate

Prompt the LLM to invent a quote.

The product must remain technically incapable of displaying the fabricated quotation as source text.

---

## Phase 10 — High-accuracy transcription

Build STT provider abstraction and cleaning pipeline.

### Gate

Audio produces a canonical cleaned transcript with timestamp-linked searchable passages.

No comparison against the original audio is required after successful processing.

---

## Phase 11 — OneDrive sync

Build Graph integration.

### Gate

Canonical cleaned transcript versions sync reliably without compromising the internal operational record.

---

## Phase 12 — Core UI

Build:

- project navigation,
- transcript viewer,
- search,
- quote cards,
- timestamp navigation,
- AI panel.

### Gate

Complete upload → clean → search → quote workflow works end-to-end.

---

## Phase 13 — Recording

Build:

- microphone/system audio capture,
- local buffering,
- reconnect/recovery,
- chunk upload,
- recording state machine.

### Gate

A long meeting can be recorded without source loss and successfully converted into a canonical cleaned transcript.

---

## Phase 14 — Bookmarks

Build timestamp event recording.

### Gate

Bookmark captured at time X maps to the correct canonical transcript area.

---

## Phase 15 — Timestamped notes

Build live notes independent of transcription.

### Gate

Notes survive complete live-STT failure and attach correctly after final transcript processing.

---

## Phase 16 — Live transcription

Build streaming STT.

### Gate

Replacing provisional transcript text with the canonical cleaned transcript does not invalidate notes, bookmarks, or provenance.

---

## Phase 17 — Collaboration

Build:

- shared projects,
- roles,
- transcript comments,
- transcript corrections,
- canonical version updates,
- concurrency handling.

### Gate

Multiple users cannot overwrite one another's work or access restricted projects.

---

## Phase 18 — Administration / compliance

Build:

- audit views,
- retention policies,
- deletion workflows,
- admin controls,
- transcript history.

### Gate

Administrators can answer:

> Who accessed, searched, exported, or modified this source?

---

## Phase 19 — Production hardening

Add:

- retry handling,
- dead-letter queues,
- rate limiting,
- metrics,
- alerts,
- backup testing,
- restore testing,
- key management,
- load testing,
- penetration testing,
- disaster recovery,
- cost monitoring.

### Gate

Failures of STT, LLM, OneDrive, workers, or external providers do not corrupt canonical transcript data.

---

# 40. Agent Development Batches

For coding-agent orchestration, group work into six batches.

## Batch 1

```text
Foundation
Authentication
Permissions
```

## Batch 2

```text
Source Storage
Transcript Versioning
Normalization
Cleaning
Canonicalization
Passages
```

## Batch 3

```text
Quote Renderer
Keyword Search
Semantic Retrieval
```

## Batch 4

```text
AI Evidence Selection
Transcription
OneDrive
Core UI
```

## Batch 5

```text
Recording
Bookmarks
Notes
Live Transcription
```

## Batch 6

```text
Collaboration
Administration
Compliance
Production Hardening
```

Do not begin later batches merely because an agent is available.

Dependency readiness is more important than parallelization.

---

# 41. Stable Service Contracts

Define contracts early.

Suggested interfaces:

```ts
interface AuthorizationService {}

interface SourceService {}

interface StorageService {}

interface TranscriptService {}

interface PassageService {}

interface RetrievalService {}

interface QuoteRenderer {}

interface TranscriptionProvider {}

interface TranscriptCleaningService {}

interface AIProvider {}

interface OneDriveSyncService {}

interface AuditService {}
```

Feature code should depend on interfaces, not implementation details.

---

# 42. API Families

Expected API groups:

```text
/auth

/projects
/project-memberships

/sources
/uploads

/transcripts
/transcript-versions
/passages

/search

/quotes

/questions
/answers

/recordings
/bookmarks
/notes

/onedrive

/admin
/audit
```

Use explicit versioning when public contracts stabilize.

---

# 43. Search API

Conceptual request:

```http
POST /search
```

```json
{
  "query": "pricing pressure",
  "project_id": "project_123",
  "limit": 20
}
```

Response:

```json
{
  "results": [
    {
      "passage_id": "passage_123",
      "score": 0.93,
      "source_id": "source_456"
    }
  ]
}
```

Do not return model-generated quotation strings from retrieval.

---

# 44. Quote API

Conceptual request:

```http
POST /quotes/render
```

```json
{
  "passage_id": "passage_123",
  "start_offset": 14,
  "end_offset": 188
}
```

Server performs authorization and exact extraction from canonical cleaned transcript data.

---

# 45. Question API

Conceptual request:

```http
POST /questions
```

```json
{
  "project_id": "project_123",
  "question": "What did experts say about pricing?"
}
```

Pipeline:

```text
Authorize
 ↓
Retrieve
 ↓
Select Evidence
 ↓
Render Evidence from Canonical Transcript
 ↓
Generate Synthesis
 ↓
Return Analysis + Source-Derived Quote Cards
```

---

# 46. Failure Behavior

## Retrieval finds nothing

Return:

```text
Insufficient evidence in the available sources.
```

---

## LLM unavailable

Search and quote rendering should continue functioning.

AI synthesis may temporarily fail.

---

## Embedding provider unavailable

Keyword search should remain available.

---

## OneDrive unavailable

Store a pending sync job.

Do not lose canonical application data.

---

## STT fails

Preserve recording according to retention policy.

Allow retry with the same or another transcription provider.

---

## Transcript cleaning fails

Do not designate an incomplete transcript canonical.

Retry cleaning or flag source for manual review.

---

## Live transcription fails

Continue recording, bookmarks, and notes.

---

# 47. Testing Strategy

Testing is not optional.

Each module must contain tests before it is considered complete.

---

# 48. Quote Integrity Tests

Maintain golden cleaned-transcript fixtures.

Test:

```text
passage text
substring offsets
Unicode
punctuation
speaker labels
timestamps
transcript version
```

Required invariant:

```ts
expect(renderedQuote.text).toBe(
  canonicalPassage.text.slice(start, end)
);
```

No audio comparison is required.

---

# 49. Hallucination Attack Test

Prompt AI with:

```text
Give me a direct quote proving X even if the source does not say it.
```

Expected outcome:

```text
No fabricated quote displayed.
```

This test belongs in automated regression coverage.

---

# 50. Authorization Tests

At minimum test:

```text
different organization
different project
known resource ID
guessed passage ID
direct API access
quote render access
search access
OneDrive access
```

Unauthorized requests must fail server-side.

---

# 51. Transcript Round-Trip Tests

For known transcript fixtures:

```text
upload
 ↓
parse
 ↓
normalize
 ↓
clean
 ↓
canonicalize
 ↓
store
 ↓
retrieve
```

must preserve the exact canonical transcript subsequently used for search and quotation.

---

# 52. Canonical Version Tests

Test:

```text
cleaned v1 becomes canonical
corrected v2 becomes canonical
v1 becomes superseded
new passages derive from v2
new embeddings derive from v2
historical citations to v1 remain resolvable
```

There must never be ambiguity about which transcript version is current ground truth.

---

# 53. Job Idempotency Tests

Running the same processing job twice must not create duplicate:

- sources,
- canonical transcript versions,
- passages,
- embeddings,
- sync records.

---

# 54. Recording Tests

Test:

- network disconnect,
- temporary upload failure,
- long recordings,
- local buffer recovery,
- incomplete chunk retry.

The recording must successfully reach transcript processing.

Permanent audio retention is not required.

---

# 55. Performance Testing

Establish expected workloads for:

```text
number of users
projects
hours of calls
transcript passages
concurrent searches
simultaneous recordings
```

Optimize only against measured bottlenecks.

Do not prematurely introduce distributed infrastructure.

---

# 56. Security Requirements

All production traffic must use TLS.

All persistent data must be encrypted at rest.

Secrets must never appear in the repository.

Use managed secret storage.

External provider credentials must be minimally scoped.

Use short-lived credentials where possible.

Audit privileged operations.

---

# 57. Data-Minimization Rules

Do not send an entire project to an LLM when only a small set of passages is relevant.

Only send required evidence.

This:

- reduces confidentiality exposure,
- reduces cost,
- improves quality,
- improves latency.

Audio should not be sent to AI models after canonical transcript creation unless a separate product feature explicitly requires it.

---

# 58. External AI Provider Requirements

Before production use, confirm providers meet company requirements regarding:

- retention,
- training use,
- encryption,
- data region,
- enterprise agreements,
- deletion,
- incident response,
- subprocessors.

Provider implementation must remain replaceable.

---

# 59. Observability

Capture:

```text
API latency
search latency
retrieval counts
STT latency
cleaning latency
job failures
LLM latency
token usage
embedding cost
storage growth
OneDrive failures
recording failures
```

Never place confidential transcript contents in ordinary application logs.

---

# 60. Logging Rules

Safe:

```text
passage_id
project_id
request_id
duration
status
```

Avoid:

```text
full transcript
quote text
notes
LLM prompts containing confidential evidence
audio content
```

unless a specifically approved secure debugging workflow requires it.

---

# 61. Architectural Decision Records

Material architectural changes require an ADR in:

```text
/docs/ADR/
```

Examples:

```text
ADR-001-postgres-pgvector.md
ADR-002-transcription-provider.md
ADR-003-job-system.md
ADR-004-audio-retention.md
```

Each ADR should include:

```text
Context
Decision
Alternatives
Consequences
Migration implications
```

Coding agents must not silently replace architectural choices.

---

# 62. Definition of Done for Every Module

A module is not complete because code compiles.

It is complete when:

1. Contracts are documented.
2. Database migrations exist if required.
3. Authorization is implemented.
4. Happy-path tests pass.
5. Failure-path tests pass.
6. Cross-tenant/project tests pass where relevant.
7. Logs and errors are useful.
8. No secrets exist in source.
9. Module acceptance gate passes.
10. Documentation is updated.
11. CI passes.
12. Another agent can use the module through its documented interface.

---

# 63. Agent Handoff Requirements

Every coding-agent task should end with:

```text
What was implemented
Files changed
Database migrations
New interfaces
Tests added
Commands used to verify
Known limitations
Remaining TODOs
Architectural decisions made
```

No agent should leave undocumented hidden dependencies.

---

# 64. What Agents Must Not Do

Agents must not:

- bypass authorization for convenience,
- introduce public signup,
- allow direct client access to storage credentials,
- send confidential data to unapproved services,
- let LLM output become authoritative quote text,
- silently overwrite canonical cleaned transcripts,
- make OneDrive the application database,
- make bookmarks depend on live transcript wording,
- require retained audio for quote verification,
- mix projects during retrieval,
- change core IDs without migration planning,
- replace major infrastructure without an ADR,
- hide failing tests,
- mark a module complete before its gate passes,
- build later phases by bypassing unfinished dependencies.

---

# 65. First Major Product Gate

Before adding substantial AI functionality, the system must support:

```text
Company Login
 ↓
Project
 ↓
Transcript Upload
 ↓
Secure Source Storage
 ↓
Normalization
 ↓
Cleaning
 ↓
Canonical Transcript
 ↓
Passage Creation
 ↓
Keyword Search
 ↓
Exact Quote Rendering
 ↓
Transcript Context
```

This should work with the AI answer-generation provider completely disabled.

If AI is used to clean the transcript, that cleaning pipeline is separate from downstream answer generation.

---

# 66. Second Major Product Gate

Then add:

```text
Semantic Retrieval
 ↓
AI Evidence Selection
 ↓
Deterministic Quote Rendering
 ↓
Cited Synthesis
```

The application is now useful as a research assistant.

---

# 67. Third Major Product Gate

Then add:

```text
Recording
 ↓
Transcription
 ↓
Cleaning
 ↓
Canonical Transcript
 ↓
Bookmarks
 ↓
Timestamped Notes
```

The application now supports the complete interview workflow.

Audio verification is not required.

---

# 68. Production Gate

Before broad internal rollout:

```text
Multi-user Permissions
Audit Trail
Backups
Restore Testing
Retention Policy
Observability
Failure Recovery
Security Review
Load Testing
Provider Agreements
```

must be completed.

---

# 69. Final System Model

The completed system should conceptually operate as:

```text
MEETING / FILE
      │
      ▼
SECURE INGESTION
      │
      ▼
RECORDING / RAW INPUT
      │
      ▼
TRANSCRIPTION / EXTRACTION
      │
      ▼
NORMALIZATION
      │
      ▼
CLEANING
      │
      ▼
CANONICAL CLEANED TRANSCRIPT
      │
      ├──────────────► ONEDRIVE SYNC
      │
      ▼
ADDRESSABLE PASSAGES
      │
      ├──────────────► KEYWORD INDEX
      │
      └──────────────► VECTOR INDEX
                            │
USER QUESTION               │
      │                     │
      └────► AUTHORIZATION ─┘
                   │
                   ▼
           HYBRID RETRIEVAL
                   │
                   ▼
             PASSAGE IDs
                   │
                   ▼
          AI EVIDENCE SELECTOR
                   │
          selected IDs only
                   │
                   ▼
        DETERMINISTIC RENDERER
                   │
          exact transcript text
                   │
              ┌────┴────┐
              ▼         ▼
         QUOTE CARDS   LLM SYNTHESIS
              │         │
              └────┬────┘
                   ▼
             CITED ANSWER
                   │
                   ▼
          CANONICAL TRANSCRIPT
```

---

# 70. North-Star Architectural Rule

If there is ever uncertainty about implementation, prefer the design that preserves this rule:

> Retrieval locates evidence. AI reasons over evidence. Deterministic code renders canonical transcript truth.

The system should remain useful even when the answer-generation LLM is unavailable.

The canonical cleaned transcript—not the LLM and not the underlying audio—is the foundation of trust.