## Pull Request Gate

An agent MUST NOT create, submit, or mark a pull request ready for review until:

```bash
./scripts/pr-ready.sh
```

completes successfully with exit code `0` from the repository root.

This requirement is mandatory. If the command fails, the agent must:

1. diagnose the failure;
2. fix the implementation, test, fixture, or contract as appropriate;
3. rerun the smallest relevant failing check while iterating;
4. rerun the complete `./scripts/pr-ready.sh` gate;
5. repeat until the complete gate passes.

An agent MUST NOT:

- skip or disable a failing required test;
- delete a test merely to obtain a green build;
- weaken an assertion merely to obtain a green build;
- mark a real failure as expected merely to obtain a green build;
- lower a blocking eval threshold merely to obtain a green build;
- change a gold/expected eval output solely because the implementation produced a different result;
- bypass architecture, authorization, tenant-isolation, quote-integrity, versioning, or security checks;
- create a PR while any required local gate is failing.

When an implementation causes an existing test or eval to fail, assume the implementation is wrong before assuming the test is wrong.

A test, fixture, gold output, or eval threshold may change only when at least one of the following is true:

1. the authoritative specification changed;
2. the existing expectation incorrectly represented the authoritative specification;
3. an approved ADR explicitly changes the expected behavior.

The PR description must explain any such expectation or threshold change and cite the controlling spec/ADR.

A successful local run does not replace CI. A PR is mergeable only after GitHub reports `PR Gate / required` as successful and all repository review requirements are satisfied.

### Required completion report

Before creating the PR, the agent must report:

- implementation summary;
- tests added/changed;
- `./scripts/pr-ready.sh`: PASS;
- material eval metrics;
- known limitations;
- architecture/spec deviations, or `none`;
- ADR references for approved architecture changes.
