#!/usr/bin/env bash
# Central command configuration for KaniorAI's PR gate.
# Change commands here when the repository toolchain changes; do not duplicate
# command definitions in CI.

PYTHON_SYNC_CMD='python -m uv sync --frozen --all-groups'
PYTHON_FORMAT_CMD='python -m uv run ruff format --check .'
PYTHON_LINT_CMD='python -m uv run ruff check .'
PYTHON_TYPECHECK_CMD='python -m uv run mypy'
PYTHON_TEST_CMD='python -m uv run pytest -q tests/unit tests/architecture tests/contract'
PYTHON_INTEGRATION_CMD='python -m uv run pytest -q tests/integration'

NODE_INSTALL_CMD='corepack pnpm install --frozen-lockfile'
NODE_FORMAT_CMD='corepack pnpm format:check'
NODE_LINT_CMD='corepack pnpm lint'
NODE_TYPECHECK_CMD='corepack pnpm typecheck'
NODE_TEST_CMD='corepack pnpm test'
NODE_BUILD_CMD='corepack pnpm build'

EVAL_PR_CMD='python evals/run.py --suite pr'
EVAL_FULL_CMD='python evals/run.py --suite full'
