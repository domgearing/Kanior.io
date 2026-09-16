# Pull Request Quality Gate

## Goal

No human or coding agent should be able to merge code to `main` simply because it "looks done."

KaniorAI uses two independent gates:

1. **Local readiness gate** — `./scripts/pr-ready.sh` must pass before a PR is created or marked ready.
2. **GitHub merge gate** — GitHub Actions reruns independent checks and the repository ruleset requires `PR Gate / required` to pass before merge.

The local gate speeds up feedback. GitHub CI is the enforcement boundary.

## Canonical commands

During development, run the narrowest relevant test repeatedly. Before PR submission, always run:

```bash
./scripts/pr-ready.sh
```

The full local gate runs:

```text
scripts/check.sh
  -> scaffold validation
  -> git whitespace check
  -> Python format/lint/typecheck/tests, when pyproject.toml exists
  -> Node format/lint/typecheck/tests/build, when package.json exists

scripts/test-integration.sh
  -> integration tests when they exist

scripts/check-migrations.sh
  -> clean-database Alembic migration validation when migrations exist

scripts/eval.sh pr
  -> all blocking PR evals in evals/manifest.toml
```

A non-zero exit code means **not PR-ready**.

## Automatic activation

The scaffold can be installed before application code exists.

- If `api/`, `workers/`, or `domain/` appears without `pyproject.toml`, the gate fails.
- Once `pyproject.toml` exists, Python format/lint/typecheck checks become mandatory.
- If `web/` appears without root `package.json`, the gate fails.
- Once `package.json` exists, frontend format/lint/typecheck/test/build checks become mandatory.
- Once integration tests exist, they become mandatory.
- Once `alembic.ini` exists, migration validation becomes mandatory.

This avoids fake Phase-0 failures without allowing a developed application to silently opt out of its toolchain.

## GitHub Actions

`.github/workflows/pr-gate.yml` runs on both `pull_request` and `merge_group`.

It has three independent jobs:

- `Checks`
- `Integration + Migrations`
- `PR Evals`

A fourth aggregation job named exactly:

```text
PR Gate / required
```

passes only when all three required jobs pass. Configure the GitHub ruleset to require this single status check.

## Required agent behavior

Copy `docs/snippets/AGENTS_PR_GATE.md` into the root `AGENTS.md` under your development/process rules. That turns local PR readiness into an explicit agent instruction.

Agents must fix failures rather than editing the judge to match their answer. Tests, gold outputs, and eval thresholds can change only when supported by the authoritative spec or an approved ADR.

## Pull request contents

Every PR should state:

- objective / active plan;
- implementation summary;
- contracts or architecture affected;
- tests added or changed;
- local `pr-ready` result;
- material eval results;
- security/data-isolation impact;
- known limitations.

The repository PR template enforces this structure.

## Merge policy

Recommended rules for `main`:

- require a pull request before merging;
- require at least one approval once more than one trusted reviewer exists;
- require conversations to be resolved;
- require `PR Gate / required`;
- require the branch to be up to date before merging (strict checks), or use merge queue later;
- block force pushes;
- block deletion of `main`;
- do not grant routine bypass permission to coding agents/bots.

If you later enable GitHub merge queue, keep the `merge_group` trigger in the workflow. Without it, required GitHub Actions checks do not run for merge groups.

## No routine bypass

There should be no `--skip-tests` or agent-accessible override for a normal PR.

If repository administration genuinely needs an emergency bypass, that is a human governance action at the GitHub ruleset level, not a code-path available to the agent. Document the incident and restore enforcement immediately afterward.
