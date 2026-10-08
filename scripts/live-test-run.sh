#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/_lib.sh"
cd "$ROOT_DIR"

if [[ ! -f .env ]]; then
  echo "Missing $ROOT_DIR/.env. Copy .env.example and add the live test values." >&2
  exit 1
fi

set -a
# .env is ignored and is the operator-approved source for this local test process.
# shellcheck disable=SC1091
source .env
set +a

# Legacy copied browser-session settings are no longer used by any process.
unset VERELO_DESKTOP_SESSION_COOKIE VERELO_DESKTOP_CSRF_TOKEN VERELO_DESKTOP_DOCUMENT_ID

# Avoid slow Windows localhost/IPv6 fallback for all local database identities.
VERELO_DATABASE_URL="${VERELO_DATABASE_URL:-postgresql+psycopg://verelo_api:verelo_api@127.0.0.1:5432/verelo}"
VERELO_MIGRATOR_DATABASE_URL="${VERELO_MIGRATOR_DATABASE_URL:-postgresql+psycopg://verelo_migrator:verelo_migrator@127.0.0.1:5432/verelo}"
VERELO_WORKER_DATABASE_URL="${VERELO_WORKER_DATABASE_URL:-postgresql+psycopg://verelo_worker:verelo_worker@127.0.0.1:5432/verelo}"
VERELO_LOCAL_ADMIN_DATABASE_URL="${VERELO_LOCAL_ADMIN_DATABASE_URL:-postgresql+psycopg://verelo_admin:verelo_admin@127.0.0.1:5432/verelo}"
export VERELO_DATABASE_URL="${VERELO_DATABASE_URL/localhost/127.0.0.1}"
export VERELO_MIGRATOR_DATABASE_URL="${VERELO_MIGRATOR_DATABASE_URL/localhost/127.0.0.1}"
export VERELO_WORKER_DATABASE_URL="${VERELO_WORKER_DATABASE_URL/localhost/127.0.0.1}"
export VERELO_LOCAL_ADMIN_DATABASE_URL="${VERELO_LOCAL_ADMIN_DATABASE_URL/localhost/127.0.0.1}"
export VERELO_DESKTOP_API_BASE_URL="${VERELO_DESKTOP_API_BASE_URL:-http://127.0.0.1:${VERELO_API_PORT:-8000}}"
export VERELO_DESKTOP_CAPTURE_PROVIDER="${VERELO_DESKTOP_CAPTURE_PROVIDER:-recall_desktop}"

echo "== Starting PostgreSQL =="
./scripts/services.sh up

echo "== Applying migrations =="
uv run alembic upgrade head

echo "== Validating live test and provisioning local worker scope =="
uv run python scripts/prepare-live-test.py >/dev/null

pids=()
cleanup() {
  local status=$?
  trap - EXIT INT TERM
  echo
  echo "== Stopping Verelo test processes =="
  for pid in "${pids[@]:-}"; do
    if [[ -n "$pid" ]]; then
      if command -v taskkill.exe >/dev/null 2>&1; then
        MSYS_NO_PATHCONV=1 taskkill.exe //PID "$pid" //T //F >/dev/null 2>&1 || true
      else
        kill "$pid" >/dev/null 2>&1 || true
      fi
    fi
  done
  wait 2>/dev/null || true
  exit "$status"
}
trap cleanup EXIT INT TERM

echo "== Launching API =="
uv run uvicorn api.main:app --reload --host 127.0.0.1 --port "${VERELO_API_PORT:-8000}" &
pids+=("$!")

for _ in {1..30}; do
  if curl --fail --silent "http://127.0.0.1:${VERELO_API_PORT:-8000}/ready" >/dev/null; then
    break
  fi
  sleep 1
done
if ! curl --fail --silent "http://127.0.0.1:${VERELO_API_PORT:-8000}/ready" >/dev/null; then
  echo "API did not become ready within 30 seconds." >&2
  exit 1
fi

echo "== Launching worker supervisor, web app, and Recall desktop recorder =="
bash ./scripts/local-worker-supervisor.sh &
pids+=("$!")
(
  for variable in ${!VERELO_@} ${!OPENAI_@} ${!GRAPH_@} ${!ENTRA_@} ${!AWS_@} ${!B2_@}; do
    case "$variable" in
      VITE_*|VERELO_DESKTOP_API_BASE_URL|VERELO_DESKTOP_CAPTURE_PROVIDER|VERELO_RECALL_API_BASE_URL|VERELO_PUBLIC_ORIGIN) ;;
      *) unset "$variable" ;;
    esac
  done
  corepack pnpm dev:web
) &
pids+=("$!")
(
  for variable in ${!VERELO_@} ${!OPENAI_@} ${!GRAPH_@} ${!ENTRA_@} ${!AWS_@} ${!B2_@}; do
    case "$variable" in
      VERELO_DESKTOP_API_BASE_URL|VERELO_DESKTOP_CAPTURE_PROVIDER|VERELO_RECALL_API_BASE_URL|VERELO_PUBLIC_ORIGIN) ;;
      *) unset "$variable" ;;
    esac
  done
  corepack pnpm dev:desktop
) &
pids+=("$!")

cat <<EOF

Verelo live test is running.
  Web:     ${VERELO_PUBLIC_ORIGIN:-http://127.0.0.1:5173}
  API:     http://127.0.0.1:${VERELO_API_PORT:-8000}
  Webhook: ${VERELO_RECALL_WEBHOOK_URL}

The public tunnel named by VERELO_RECALL_WEBHOOK_URL must already forward to the API.
Sign in and select or create a meeting in Electron, then record.
New projects created in Electron receive worker scope automatically.
Press Ctrl+C here to stop API, worker, web, and Electron. PostgreSQL remains running.
EOF

wait -n "${pids[@]}"
echo "A Verelo process exited; shutting down the test run." >&2
exit 1
