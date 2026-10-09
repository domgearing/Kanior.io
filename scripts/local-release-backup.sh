#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/_lib.sh"
cd "$ROOT_DIR"

if [[ ! -f .env ]]; then
  echo "Missing ignored .env configuration." >&2
  exit 1
fi

exec uv run --frozen python scripts/local_release_backup.py
