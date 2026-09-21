# OpenAI

Documentation verified: **2026-09-16** using official OpenAI documentation. Live smoke test: **NOT RUN**. Authority: architecture §§4, 11, 14–16, 38. [Shared integration rules](../INTEGRATIONS.md) apply.

## API, operations and official references

Selected transport: direct OpenAI REST `/v1/responses` for cleanup proposals, evidence selection and optional synthesis; `/v1/embeddings` for passage/query embeddings. No hosted vector store, file search, arbitrary tools, background mode or confidential streaming in this baseline. An Azure-hosted alternative requires separate endpoint/region/data-control decisions; no automatic fallback.

Exact approved cleanup, selector, synthesis and embedding model identifiers and embedding dimensions are **OPEN / blocking live use**, not inferred from the coding-agent model-routing policy. Pin returned/configured model identifiers and prompt/schema versions in provenance; avoid floating aliases when a supported approved snapshot exists. No SDK is installed by this guide; select/pin one or use the application's pinned HTTP client during implementation.

[Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs) supports schema-constrained responses but only a supported JSON Schema subset. Adapt transport schemas without weakening the local contract; continue validating local uniqueness, field restrictions, span bounds and sealed candidate membership. Treat refusals and incomplete output as failures, not empty successful selections. [Embeddings documentation](https://developers.openai.com/api/docs/guides/embeddings) describes vector generation; the app must bind each index generation to its model and dimension.

## Authentication, permissions and environment

Server-side project credential with only required endpoint/model access and approved spend limits; never use an employee consumer ChatGPT session. Grant no administrative key-management permissions to runtime.

| Name | Kind / setup |
|---|---|
| `OPENAI_API_KEY` | Secret; isolated approved project service credential |
| `OPENAI_PROJECT_ID`, `OPENAI_API_BASE_URL` | Config; provisioned project/approved endpoint, not user-selected |
| `OPENAI_CLEANUP_MODEL`, `OPENAI_SELECTOR_MODEL`, `OPENAI_SYNTHESIS_MODEL` | Config; required approved versioned model identifiers |
| `OPENAI_EMBEDDING_MODEL`, `OPENAI_EMBEDDING_DIMENSIONS` | Config; approved supported pair; changing either creates a new index generation |
| `OPENAI_INTERACTIVE_BUDGET_SECONDS`, `OPENAI_CLEANUP_BUDGET_SECONDS` | Config; initial interactive budget 12 seconds; cleanup job budget explicitly set |

## Provider-neutral adapters and synthetic responses

```text
ModelProvider.propose_edits(segments, cleanup_policy, operation_key) -> EditProposal
ModelProvider.select_evidence(question, authorized_candidates, mode, operation_key) -> Selection
ModelProvider.compose_analysis(question, rendered_evidence, operation_key) -> Analysis
EmbeddingProvider.embed(texts, model_config, operation_key) -> EmbeddingBatch
```

```json
{"selected_passages":["10000000-0000-4000-8000-000000000021"]}
```

```json
{"vectors":[[0.1,0.2,0.3]],"dimension":3,"model_id":"synthetic-embedding-v1"}
```

Dimension 3 is a fake-only example, not a selected production dimension. Selection uses the existing `schemas/ai/` contracts. Cleanup/synthesis DTOs must be finalized from spec §§8.5/9.5 before their adapters are implemented. The renderer has no dependency on these adapters. Only deterministic code creates verified quote text/source-span IDs.

## Reliability, data and approvals

Apply the shared interactive budget across network attempts; no hidden SDK retry multiplication. The [rate-limit guide](https://developers.openai.com/api/docs/guides/rate-limits) describes limits/backoff; discover actual account limits rather than hard-code provider quotas. 429 capacity may retry within budget; exhausted billing/quota needs configuration intervention. Invalid schema/model is terminal. A timeout may have incurred cost: deduplicate accepted outputs by operation key, never promise provider exactly-once execution. Cleanup failure returns unchanged parsed text through approval; selection/synthesis outage preserves evidence-only functionality; embedding failure exposes index health.

Send only authorized candidate text for selection, successfully rendered evidence for synthesis, necessary parsed segments for cleanup, and authorized text for embeddings. Store embeddings in pgvector. Set `store=false` explicitly for Responses. The [data-controls guide](https://developers.openai.com/api/docs/guides/your-data) distinguishes application state, abuse monitoring and approved retention controls; `store=false` does not prove zero retention. Before confidential traffic, document actual endpoint/model exceptions, training policy, account retention approval, residency and prompt-cache settings. Do not enable retention-changing caching/background features silently. Local deletion covers prompts/results retained under app policy and vector generations; provider cleanup claims must match actual account controls.

## Fake behavior and live smoke procedure

Fake: valid ID-only result, invented/out-of-run UUID, extra quote fields, duplicate IDs, bad Unicode offsets, refusal, truncation, 429/outage, mismatched embedding dimension and malicious transcript instructions. Fake vectors are deterministic and clearly synthetic, not retrieval-quality evidence.

Live: after approved model/config selection, submit fictional candidate text using the exact transported schema and `store=false`; prove the returned selection passes local validation and renderer checks; exercise cleanup preservation separately; embed a small fictional corpus and verify count/dimension/model metadata. Verify rejection of unsafe output with injected responses, cost limits, no raw prompts in logs and evidence-only fallback. Record model IDs, transport schema hash, account data controls and spend; never store keys or full response dumps in git. OPEN: every production model/dimension choice, supported schema transport, account region/retention approval, budget and SDK pin.
