# KaniorAI Eval Policy

## Purpose

Tests answer "does the software behave as implemented?" Evals answer "does KaniorAI still satisfy the product correctness and safety properties we care about?"

Blocking PR eval thresholds are stored in `evals/manifest.toml`. The manifest is normative; prose in this document explains the policy.

## Suites

### `pr`

Runs on every pull request and from `./scripts/pr-ready.sh`.

It must remain deterministic enough to be a reliable merge gate. Prefer synthetic fixtures, recorded provider responses, fixed seeds, and exact source spans over live-model calls.

### `full`

Superset intended for larger or more expensive evaluations. Run it before releases and, once live-model evals exist, on a schedule or for AI-sensitive changes.

The `full` suite must never be weaker than the `pr` suite.

## Threshold classes

### Invariants

These should normally require perfect behavior:

| Eval | Intended threshold |
| --- | ---: |
| Verified quote/source-span fidelity | 100% |
| Unauthorized retrieval results | 0 |
| Cross-tenant/project leakage | 0 |
| Transcript import round-trip | 100% |
| Canonical-version semantics | 100% |
| Job idempotency | 100% |
| Fabricated verified quotes | 0 |

### Statistical quality metrics

These use measured thresholds rather than perfection. Initial examples:

| Eval | Initial target |
| --- | ---: |
| Retrieval Recall@20 | >= 90% |
| Correct insufficient-evidence abstention | >= 95% |

Do not adopt those exact numbers blindly: activate them only with a reviewed gold dataset that reflects the product requirement.

## Activation rule

The repo begins with `harness_self_test` so the gate itself can be committed before product modules exist.

A PR that first introduces behavior protected by one of the product evals must introduce and activate the corresponding eval in the same PR. For example, the first PR that can render a `VerifiedQuote` must not merge with quote-fidelity protection still merely commented in the manifest.

Do not create production behavior first and defer its critical invariant eval to a later PR.

## Eval output contract

Each eval command prints one JSON object as its final non-empty stdout line:

```json
{"metric":"recall_at_20","value":0.934,"details":"optional diagnostic text"}
```

`evals/run.py` compares `value` with the threshold in `evals/manifest.toml` and exits non-zero when a blocking eval fails.

## Changing thresholds or gold expectations

Thresholds and expected outputs are part of the product contract, not a tuning knob for making CI green.

A change is acceptable only when supported by an authoritative specification change, a correction to an invalid existing expectation, or an approved ADR. The PR must explain the reason.

When you have a stable GitHub team/user for architecture ownership, add `CODEOWNERS` protection for at least:

```text
/evals/
/docs/EVALS.md
/docs/decisions/
```

and require Code Owner review for those paths.

## Dataset rules

Use synthetic/non-confidential fixtures in normal CI. Do not put confidential customer transcripts, access tokens, provider payloads containing confidential text, or production identifiers into the repository.

Synthetic fixtures should deliberately cover difficult behavior: negation, numbers, repeated wording across projects, Unicode, speaker boundaries, unsupported questions, and prompt-like text embedded in transcripts.
