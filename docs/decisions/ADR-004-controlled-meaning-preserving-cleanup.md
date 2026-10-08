# ADR-004: Constrained automatic non-formatting cleanup

Status: accepted.

## Context

The original baseline allowed automatic approval only for unchanged text or formatting-only edits.
The product owner approved automatic approval of narrowly constrained non-formatting cleanup when the
application can deterministically prove that every edit belongs to a versioned allowlist intended to
preserve meaning. A model's semantic judgment alone is not proof.

## Decision

`controlled_cleanup_policy` version 2 may automatically approve formatting changes plus only these
deterministic transformations:

- removal of standalone fillers from the policy's exact case-insensitive filler lexicon; and
- collapse of immediately adjacent duplicate tokens from the policy's exact stutter lexicon.

The initial filler lexicon is `um`, `uh`, `erm`, and `ah`. The initial stutter lexicon is limited to
`i`, `we`, `a`, `an`, `the`, `and`, `but`, `so`, `it`, `that`, and `this`. Names, numbers, negation,
modality, attribution, punctuation, and all tokens outside those lists are protected. Each accepted
change produces an exact edit manifest containing policy rule, source text, replacement, and source
character bounds. The proposal must equal a deterministic output accepted by the validator; an LLM
claim that meaning is preserved cannot expand the policy.

Projects may require manual approval instead. Any wording change outside the allowlist, any malformed
manifest, or any validator uncertainty preserves the unchanged parsed transcript or routes a separate
correction version to a human reviewer. Raw and parsed inputs remain immutable.

## Alternatives considered

- Formatting-only cleanup was safer but did not meet the approved product behavior.
- Unrestricted model-based semantic equivalence was rejected because it cannot provide a deterministic
  source-integrity guarantee.
- A general paraphrase similarity threshold was rejected because scores are model-dependent and can
  accept changed facts, negation, attribution, or degree.

## Consequences

Automatic canonical wording can differ from raw STT output, so the UI and provenance must identify the
policy version and retained edit manifest. Expansion of either lexicon or addition of another rule is
a reviewed policy-version change with regression fixtures. Quote fidelity remains exact against the
approved published canonical version, not against raw STT wording or audio.

## Security implications

The controlled-cleanup service receives no general approval authority. It can approve only validator-
accepted output under the project's configured policy. Protected tokens and punctuation fail closed.
Confidential text and edit bodies stay out of ordinary logs.

## Migration implications

No schema replacement is required: transcript versions already record policy version and cleanup
manifest, and approvals bind to the exact canonical hash. Existing version-1 publications remain
immutable and retain their original policy provenance.
