#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/_lib.sh"
cd "$ROOT_DIR"

if [[ "${OS:-}" == "Windows_NT" ]] && [[ "${MSYSTEM:-}" != MINGW* ]]; then
  echo "On Windows, run this repository's scripts from Git Bash." >&2
  exit 1
fi

for command_name in python node npm corepack; do
  if ! command -v "$command_name" >/dev/null 2>&1; then
    echo "Missing required command: $command_name" >&2
    exit 1
  fi
done

if [[ ! -f .env ]]; then
  cp .env.example .env
  echo "Created .env from the synthetic local template."
fi

section "Install contract tooling"
python -m pip install --disable-pip-version-check -r tools/contracts/requirements.lock
npm ci --prefix tools/contracts --ignore-scripts

if ! python -m uv --version >/dev/null 2>&1; then
  section "Install uv"
  python -m pip install --disable-pip-version-check uv
fi

section "Install Python dependencies"
run "$PYTHON_SYNC_CMD"

section "Install Node dependencies"
run "$NODE_INSTALL_CMD"

echo
echo "Setup complete. Start PostgreSQL with: ./scripts/services.sh up"
