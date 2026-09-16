# KaniorAI PR Gate Package

This package is intended to be copied into the **root of the KaniorAI repository**. It installs the local/CI process that makes tests and evals a hard pull-request gate.

## Copy into the repo

From a temporary directory containing this package:

```bash
cp -R .github docs evals scripts tests /path/to/kanior-ai/
cat .gitignore.additions >> /path/to/kanior-ai/.gitignore
```

If any destination file already exists, merge it deliberately rather than overwriting project-specific content.

Then:

```bash
cd /path/to/kanior-ai
chmod +x scripts/*.sh scripts/*.py evals/run.py evals/checks/*.py
python scripts/validate-pr-gate.py
./scripts/eval.sh pr
```

Copy the contents of `docs/snippets/AGENTS_PR_GATE.md` into the root `AGENTS.md`.

Read `docs/PR_PROCESS.md`, `docs/TOOLCHAIN_REQUIREMENTS.md`, and `SETUP_GITHUB.md` before turning on branch rules.

## Toolchain assumptions

The provided defaults match the intended KaniorAI direction:

- Python 3.13 / `uv`
- FastAPI-oriented Python backend/workers/domain
- TypeScript frontend managed with `pnpm`
- PostgreSQL migrations via Alembic
- GitHub Actions on Ubuntu

All project commands live in `scripts/pr-gate.conf.sh`. If your final package scripts differ, change that one file and keep local/CI behavior aligned.
