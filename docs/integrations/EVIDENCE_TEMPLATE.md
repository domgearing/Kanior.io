# Integration feasibility / smoke-test evidence

Copy to a dated provider-specific report after a real experiment. Do not mark this template complete or replace NOT RUN with PASS based on documentation alone. Commit only sanitized summaries; restricted raw evidence remains outside git.

| Field | Value |
|---|---|
| Provider / gate | R1, G1 or provider smoke test |
| Status | NOT RUN / PASS / FAIL / INCONCLUSIVE |
| Date, operator, reviewer | Pending |
| Commit / test procedure revision | Pending |
| API version, SDK/client lockfile version | Pending |
| OS/Electron/meeting client where relevant | Pending |
| Account region / environment | Synthetic test environment; actual identifiers in restricted evidence |
| Approved resource boundary / spend limit | Pending |
| Permission scopes and resource roles | Exact tested values, no tokens |
| Processor/retention/consent approval references | Pending; feasibility PASS is not confidential-data approval |

## Results

| Step / operation | Expected | Observed | Safe evidence reference | Pass/fail |
|---|---|---|---|---|
| Positive control | | | | |
| Outside-scope negative control | | | | |
| Duplicate / uncertain outcome | | | | |
| Revocation / expired credential | | | | |
| Cleanup / retained copies | | | | |

## Required gate-specific evidence

- R1: exact audio config, signed event shape, recording-to-media field path, original byte hash/count/duration, both voices, independent storage read-back, no extra transcription service, recovery/gaps and deletion coverage.
- G1: destination type/ownership, consent plus resource grant, each supported operation, forbidden sibling access, completeness of effective-reader verification, unauthorized reader detection, revocation, drift, artifact hashes and deletion/recycle behavior.

## Remaining decisions and conclusion

List blockers, owner and required-before phase. Identify provisional assumptions disproved by the test. Link any required ADR. Record exact cleanup resources and unresolved retained copies, without keys, signed URLs, customer content or real account identifiers. State which implementation work may now proceed and which live/confidential uses remain blocked.
