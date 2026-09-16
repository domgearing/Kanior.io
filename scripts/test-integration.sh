#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/_lib.sh"
cd "$ROOT_DIR"

if ! contains_test_files "$ROOT_DIR/tests/integration"; then
  echo "No integration tests exist yet; integration gate is not applicable."
  exit 0
fi

if ! has_python_project; then
  echo "Integration tests exist but pyproject.toml is missing." >&2
  exit 1
fi

section "Integration tests"
run "$PYTHON_INTEGRATION_CMD"
