# KaniorAI Model Routing Policy

## Purpose

Use the least expensive model that can reliably complete a task while escalating
difficult, ambiguous, or high-risk work to more capable models.

The objective is not minimum token cost.

The objective is:

    lowest expected cost to produce correct, maintainable code

including the cost of rework.

---

## Model hierarchy

### Luna

Use for mechanical work where the desired transformation is already known.

Examples:

- file renames
- formatting
- repetitive edits
- generating fixtures from an existing schema
- moving files
- simple documentation cleanup
- adding obvious boilerplate
- updating imports after a known rename

Do not use for:

- architecture
- new business logic
- security-sensitive behavior
- ambiguous debugging
- cross-module implementation


### Terra

Use for routine implementation with clear contracts.

Examples:

- straightforward CRUD
- database models from an approved DATA_MODEL.md
- API endpoints from an existing OpenAPI contract
- unit tests
- simple adapters
- documentation
- well-scoped refactors
- straightforward validation

Escalate when substantial ambiguity or cross-system reasoning appears.


### Sol

Sol is the default KaniorAI engineering model.

Use for:

- substantial feature implementation
- business logic
- integrations
- debugging
- non-trivial refactors
- code review
- test design
- database changes
- API/domain implementation
- multi-file changes
- unfamiliar code within a bounded module

Most KaniorAI development work should occur here.


### Astra

Use selectively for high-complexity reasoning.

Examples:

- architecture
- system-wide design
- security model changes
- authorization design
- retrieval architecture
- difficult concurrency problems
- unfamiliar system-wide bugs
- repeated failed implementations
- difficult migrations
- major refactors across boundaries
- reliability/integrity issues
- resolving conflicting specifications

Astra should generally diagnose, design, or unblock.

Where practical, implementation should then return to Sol or Terra.

---

## Default routing

When no explicit model is assigned:

1. Determine task complexity.
2. Select the cheapest model likely to succeed.
3. Default uncertain substantial engineering tasks to Sol.
4. Escalate only when justified.

Escalation:

    Luna → Terra → Sol → Astra

---

## Escalation triggers

Escalate one level when one or more of the following occurs:

- two reasonable implementation attempts fail;
- acceptance tests remain unexplained;
- architecture boundaries become unclear;
- undocumented behavior must be inferred;
- multiple subsystems must change together;
- implementation requires a new architectural decision;
- security or authorization behavior is affected;
- data-loss or corruption risk exists;
- concurrency or distributed-state reasoning is required.

Immediately consider Astra for:

- tenant-isolation architecture;
- quote-integrity architecture;
- authentication/authorization architecture;
- major persistence-model changes;
- retrieval architecture;
- major system-wide refactors.

---

## De-escalation

High-capability models should not remain attached to routine work unnecessarily.

Example:

    Astra identifies root cause
        ↓
    Astra writes bounded implementation plan
        ↓
    Sol implements
        ↓
    Sol/Terra tests
        ↓
    Astra reviews only if risk warrants it

---

## Routing and tests

Tests and evals are routing signals.

A task that appears simple but repeatedly fails deterministic acceptance tests
should escalate.

Do not respond to test failures by weakening tests or eval thresholds.

---

## Typical allocation target

Long-run engineering workload target:

Astra: 10-20%
Sol: 70–80%
Terra: 20–30%

These are planning targets, not hard quotas.