#!/usr/bin/env bash
# Central command configuration for KaniorAI's PR gate.
# Change commands here when the repository toolchain changes; do not duplicate
# command definitions in CI.

PYTHON_SYNC_CMD='uv sync --frozen --all-groups'
PYTHON_FORMAT_CMD='uv run ruff format --check .'
PYTHON_LINT_CMD='uv run ruff check .'
PYTHON_TYPECHECK_CMD='uv run mypy .'
PYTHON_TEST_CMD='uv run pytest -q tests/unit tests/architecture tests/contract'
PYTHON_INTEGRATION_CMD='uv run pytest -q tests/integration'

NODE_INSTALL_CMD='pnpm install --frozen-lockfile'
NODE_FORMAT_CMD='pnpm format:check'
NODE_LINT_CMD='pnpm lint'
NODE_TYPECHECK_CMD='pnpm typecheck'
NODE_TEST_CMD='pnpm test'
NODE_BUILD_CMD='pnpm build'

EVAL_PR_CMD='python evals/run.py --suite pr'
EVAL_FULL_CMD='python evals/run.py --suite full'
