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
  echo "The single-user release updater supports local mode only." >&2
  exit 1
fi
if [[ -z "${VITE_API_BASE_URL:-}" ]]; then
  echo "VITE_API_BASE_URL is required for the built web app." >&2
  exit 1
fi
export VERELO_DESKTOP_CAPTURE_PROVIDER="${VERELO_DESKTOP_CAPTURE_PROVIDER:-recall_desktop}"

echo "== Installing locked Python dependencies =="
uv sync --frozen --all-groups

echo "== Starting PostgreSQL and applying reviewed migrations =="
./scripts/services.sh up
uv run alembic upgrade head
uv run python scripts/prepare-live-test.py >/dev/null

echo "== Installing Node dependencies and building web/desktop =="
(
  # Node installation and builds receive only the public API URL, never server/provider secrets.
  for variable in ${!VERELO_@} ${!VITE_@} ${!OPENAI_@} ${!GRAPH_@} ${!ENTRA_@} ${!AWS_@} ${!B2_@}; do
    case "$variable" in
      VITE_API_BASE_URL) ;;
      *) unset "$variable" ;;
    esac
  done
  corepack pnpm install --frozen-lockfile
  corepack pnpm --filter @verelo/web build
  corepack pnpm --filter @verelo/desktop build
)

echo "== Registering the desktop open link for this Windows user =="
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/install-desktop-link.ps1

echo "Local release assets are ready. Restart the Verelo Local Release task to activate them."
