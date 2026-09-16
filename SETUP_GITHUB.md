# Set up KaniorAI's PR gate in GitHub

## 1. Commit the gate files

Copy this package into the repository root, merge the AGENTS snippet, and commit it on a setup branch.

Before opening the setup PR, run:

```bash
python scripts/validate-pr-gate.py
./scripts/eval.sh pr
```

If the application toolchains already exist, run the full gate:

```bash
./scripts/pr-ready.sh
```

## 2. Push the branch and open the first PR

Push the branch to GitHub and open a PR to `main`. The workflow `.github/workflows/pr-gate.yml` should create these checks:

```text
Checks
Integration + Migrations
PR Evals
PR Gate / required
```

Confirm `PR Gate / required` passes.

GitHub often needs a check to have run at least once before it is convenient to select it as a required status check, so do this initial workflow run before configuring the ruleset.

## 3. Create a branch ruleset for `main`

In the repository:

```text
Settings
  -> Rules
  -> Rulesets
  -> New ruleset
  -> New branch ruleset
```

Suggested name:

```text
main-protection
```

Set enforcement to **Active** and target the default branch / `main`.

Enable:

1. **Require a pull request before merging**
2. **Require status checks to pass before merging**
3. Add the required status check **`PR Gate / required`**
4. **Require branches to be up to date before merging** (strict), unless you intentionally adopt merge queue
5. **Require conversation resolution before merging**
6. **Block force pushes**
7. Restrict branch deletion / do not allow normal users or agents to delete `main`

Once you have a stable human reviewer/team, also require at least one approval. Do not give routine bypass permission to the coding-agent identity.

## 4. Verify the enforcement

Open a tiny test PR that intentionally causes one check to fail (for example, introduce trailing whitespace caught by `git diff --check`). Confirm GitHub prevents merge.

Fix the failure. Confirm the workflow reruns, `PR Gate / required` becomes green, and the PR becomes eligible for review/merge.

Then revert/close any deliberately bad test change rather than merging it.

## 5. Agent workflow

The agent's lifecycle should now be:

```text
read AGENTS.md + architecture + active plan
        -> implement
        -> targeted tests during development
        -> ./scripts/pr-ready.sh
        -> fix until PASS
        -> create PR
        -> GitHub independently reruns gate
        -> PR Gate / required PASS
        -> review / conversations resolved
        -> merge
```

The agent may never treat a local PASS as permission to merge around a failing GitHub check.

## 6. Activate product evals as features arrive

Initially, `evals/manifest.toml` contains a harness self-test because the product modules do not yet exist.

When a feature first introduces a critical invariant, add the corresponding eval and place its name in `[suites.pr].evals` in the **same PR**. Examples:

- first verified-quote implementation -> quote fidelity + fabricated quote evals;
- first project-scoped retrieval -> authorization/cross-project isolation eval;
- first transcript versioning -> canonical-version eval;
- first durable workers -> job-idempotency eval;
- first production retrieval -> retrieval gold-set metric.

Do not wait until a later cleanup PR to add a critical invariant gate.

## 7. Optional next hardening

After the core gate is stable, add:

- CODEOWNERS for `evals/`, architecture, security, and ADR files;
- CodeQL/code scanning;
- GitHub secret scanning / push protection where your plan supports it;
- dependency vulnerability scanning;
- scheduled `./scripts/eval.sh full` runs;
- merge queue once concurrent PR volume makes strict rebasing expensive.
