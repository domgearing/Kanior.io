#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/_lib.sh"
cd "$ROOT_DIR"

if has_python_project; then
  section "Install Python tooling"
  python -m pip install --disable-pip-version-check --quiet uv
  run "$PYTHON_SYNC_CMD"
fi

if has_node_project; then
  section "Install Node dependencies"
  corepack enable
  run "$NODE_INSTALL_CMD"
fi
