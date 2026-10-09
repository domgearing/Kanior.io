#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/_lib.sh"
cd "$ROOT_DIR"

if [[ ! -f .env || ! -f desktop/dist/main.js ]]; then
  echo "Build the local release before launching Electron." >&2
  exit 1
fi
set -a
# shellcheck disable=SC1091
source .env
set +a

ready=false
for _ in {1..90}; do
  if curl --max-time 2 --fail --silent "http://127.0.0.1:${VERELO_API_PORT:-8000}/ready" >/dev/null; then
    ready=true
    break
  fi
  sleep 3
done
if [[ "$ready" != true ]]; then
  echo "The API did not become ready before desktop startup timed out." >&2
  exit 1
fi

if [[ -z "${VERELO_PUBLIC_ORIGIN:-}" ]]; then
  echo "VERELO_PUBLIC_ORIGIN is required for desktop sign-in." >&2
  exit 1
fi
web_ready=false
for _ in {1..90}; do
  if curl --max-time 4 --fail --silent --user-agent 'Mozilla/5.0 (Verelo local startup)' \
    "${VERELO_PUBLIC_ORIGIN%/}/" >/dev/null; then
    web_ready=true
    break
  fi
  sleep 3
done
if [[ "$web_ready" != true ]]; then
  echo "The public web route did not become ready before desktop startup timed out." >&2
  exit 1
fi

export VERELO_DESKTOP_API_BASE_URL="${VERELO_DESKTOP_API_BASE_URL:-http://127.0.0.1:${VERELO_API_PORT:-8000}}"
export VERELO_DESKTOP_CAPTURE_PROVIDER="${VERELO_DESKTOP_CAPTURE_PROVIDER:-recall_desktop}"
for variable in ${!VERELO_@} ${!VITE_@} ${!OPENAI_@} ${!GRAPH_@} ${!ENTRA_@} ${!AWS_@} ${!B2_@}; do
  case "$variable" in
    VERELO_DESKTOP_API_BASE_URL|VERELO_DESKTOP_CAPTURE_PROVIDER|VERELO_RECALL_API_BASE_URL|VERELO_PUBLIC_ORIGIN) ;;
    *) unset "$variable" ;;
  esac
done

cd desktop
exec node scripts/launch-electron.mjs
