# PR Gate Toolchain Contract

The PR gate deliberately calls stable repository-level commands rather than embedding tool-specific logic throughout GitHub Actions.

Edit `scripts/pr-gate.conf.sh` if your final toolchain differs.

## Python project

When `pyproject.toml` exists, the default gate expects these developer tools to be available through `uv`:

- `ruff`
- `mypy`
- `pytest`
- `alembic` once migrations are introduced

Recommended dev dependency group conceptually:

```toml
[dependency-groups]
dev = [
  "ruff",
  "mypy",
  "pytest",
  "pytest-asyncio",
  "alembic",
]
```

Commit both `pyproject.toml` and the generated `uv.lock`. CI uses `uv sync --frozen --all-groups`; a stale or missing lockfile should be treated as a failure rather than silently rewritten in CI.

The default Python commands are:

```text
uv run ruff format --check .
uv run ruff check .
uv run mypy .
uv run pytest -q tests/unit tests/architecture tests/contract
uv run pytest -q tests/integration
```

Configure Ruff/Mypy/Pytest in `pyproject.toml` so those root-level commands represent the authoritative project behavior.

## TypeScript / Vite project

When root `package.json` exists, the gate expects a committed `pnpm-lock.yaml` and these root scripts:

```json
{
  "scripts": {
    "format:check": "<your formatter check command>",
    "lint": "<your lint command>",
    "typecheck": "<your TypeScript typecheck command>",
    "test": "<your non-watch test command>",
    "build": "<your production build command>"
  }
}
```

For a typical Vite application those commonly map to Prettier, ESLint, `tsc --noEmit`, Vitest in run mode, and `vite build`, but keep the exact implementation in `package.json` rather than duplicating it in the gate.

Also set the package manager in `package.json`, for example:

```json
{
  "packageManager": "pnpm@<locked-version>"
}
```

CI calls `corepack enable` and `pnpm install --frozen-lockfile`.

## PostgreSQL / migrations

Once `alembic.ini` exists, migration validation becomes blocking.

Locally, `scripts/check-migrations.sh` starts a disposable `postgres:17-alpine` container unless `PR_GATE_DATABASE_URL` is supplied.

In GitHub Actions, the integration job supplies a clean PostgreSQL service and sets `PR_GATE_DATABASE_URL` automatically.

## Changing tools later

If you move from a tool (for example Mypy to Pyright), update:

1. the dependency/package configuration;
2. `scripts/pr-gate.conf.sh`;
3. this document if the developer contract changed.

Do not create a second CI-only command path. Local and CI gates should continue to call the same repository scripts.
