#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/_lib.sh"
cd "$ROOT_DIR"

if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

case "${1:-}" in
  api)
    exec python -m uv run uvicorn api.main:app --reload --host 127.0.0.1 --port "${KANIOR_API_PORT:-8000}"
    ;;
  worker)
    exec python -m uv run python -m workers
    ;;
  web)
    exec corepack pnpm dev:web
    ;;
  desktop)
    exec corepack pnpm dev:desktop
    ;;
  *)
    echo "Usage: $0 {api|worker|web|desktop}" >&2
    exit 2
    ;;
esac
