# Phase 2 ingestion core — synthetic first slice

## Scope

Begin Phase 2 without live credentials by implementing provider-neutral, deterministic transcript
parsing, conservative cleanup validation, hash-bound approval/publication, passage/index intents, and
recording recovery state behavior. Tests use fictional bytes only.

This slice exercises the Phase 2 gate with synthetic data. Phase 1 API/authorization services,
restricted-role RLS, durable job leasing, scoped persistence, local immutable object storage,
authorized ingestion HTTP operations, atomic publication/outbox persistence, and Electron synthetic
capture are included. Recall R1 is not run and live AssemblyAI/provider configuration remains
intentionally absent.

The completed credential-free slice also includes database-backed capture recovery, immutable audio
chunk acknowledgement and reconstruction, quarantine decisions, synthetic provider adapters,
deterministic speaker/timestamp reconciliation, scoped worker/outbox execution, content-free
observability, and an isolated database/object restore smoke exercise.

## Acceptance

- UTF-8 TXT, VTT, SRT, and schema-v1 JSON parse deterministically.
- Unsupported, malformed, or invalid-timing input fails with content-free codes.
- Cleanup permits formatting and the exact versioned meaning-preserving rules in ADR-004; all other
  changes are rejected.
- Approval binds to the canonical byte hash, publication is idempotent, and canonical bytes can be
  reproduced and integrity-checked without audio.
- Passage byte offsets exactly reconstruct Unicode source bytes and index intents have stable keys.
- Recorder interruptions remain visible gaps and chunk acknowledgements reject silent sequence loss.

## Follow-on dependencies

Run live provider adapters only after their gates, complete organization-specific policy decisions,
and exercise confidential pilot traffic only after the security and governance approvals are met.
