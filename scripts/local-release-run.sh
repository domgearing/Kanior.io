#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/_lib.sh"
cd "$ROOT_DIR"

if [[ ! -f .env ]]; then
  echo "Missing ignored .env configuration." >&2
  exit 1
fi
set -a
# shellcheck disable=SC1091
source .env
set +a

if [[ "${VERELO_ENVIRONMENT:-}" != local ]]; then
  echo "The single-user release runner supports local mode only." >&2
  exit 1
fi
if [[ ! -f web/dist/index.html || ! -d web/dist/assets ]]; then
  echo "Build the release first with ./scripts/local-release-update.sh." >&2
  exit 1
fi

export VERELO_DESKTOP_API_BASE_URL="${VERELO_DESKTOP_API_BASE_URL:-http://127.0.0.1:${VERELO_API_PORT:-8000}}"
export VERELO_DESKTOP_CAPTURE_PROVIDER="${VERELO_DESKTOP_CAPTURE_PROVIDER:-recall_desktop}"

./scripts/services.sh up
uv run --frozen python scripts/prepare-live-test.py >/dev/null

if curl --max-time 2 --fail --silent "http://127.0.0.1:${VERELO_API_PORT:-8000}/ready" >/dev/null; then
  echo "An API is already listening on the local port. Stop the development launcher first." >&2
  exit 1
fi

exec uv run --frozen python scripts/local_release_supervisor.py
