#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/_lib.sh"
cd "$ROOT_DIR"

section "PR-gate scaffold"
run "python scripts/validate-pr-gate.py"
run "git diff --check"

section "Contract schemas and semantic boundaries"
run "python scripts/validate-contracts.py"
run "python scripts/generate-contracts.py --check"

if has_python_source_without_project; then
  echo "Python source directories exist but pyproject.toml is missing." >&2
  exit 1
fi

if has_web_source_without_project; then
  echo "web/ exists but root package.json is missing." >&2
  exit 1
fi

if has_python_project; then
  section "Python format"
  run "$PYTHON_FORMAT_CMD"

  section "Python lint"
  run "$PYTHON_LINT_CMD"

  section "Python typecheck"
  run "$PYTHON_TYPECHECK_CMD"

  if contains_test_files "$ROOT_DIR/tests/unit" || \
     contains_test_files "$ROOT_DIR/tests/architecture" || \
     contains_test_files "$ROOT_DIR/tests/contract"; then
    section "Python unit / architecture / contract tests"
    run "$PYTHON_TEST_CMD"
  else
    echo "No unit/architecture/contract tests exist yet; project checks continue."
  fi
else
  echo "No pyproject.toml yet; Python project checks are not applicable."
fi

if has_node_project; then
  section "Frontend format"
  run "$NODE_FORMAT_CMD"

  section "Frontend lint"
  run "$NODE_LINT_CMD"

  section "Frontend typecheck"
  run "$NODE_TYPECHECK_CMD"

  section "Frontend tests"
  run "$NODE_TEST_CMD"

  section "Frontend build"
  run "$NODE_BUILD_CMD"
else
  echo "No package.json yet; Node project checks are not applicable."
fi
