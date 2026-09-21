#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/_lib.sh"
cd "$ROOT_DIR"

if ! command -v docker >/dev/null 2>&1; then
  echo "Docker Desktop with Docker Compose v2 is required." >&2
  exit 1
fi

compose=(docker compose --env-file "$ROOT_DIR/.env.example" -f "$ROOT_DIR/infra/local/compose.yaml")
if [[ -f "$ROOT_DIR/.env" ]]; then
  compose=(docker compose --env-file "$ROOT_DIR/.env" -f "$ROOT_DIR/infra/local/compose.yaml")
fi

case "${1:-}" in
  up)
    "${compose[@]}" up -d --wait
    ;;
  down)
    "${compose[@]}" down
    ;;
  status)
    "${compose[@]}" ps
    ;;
  logs)
    "${compose[@]}" logs -f postgres
    ;;
  *)
    echo "Usage: $0 {up|down|status|logs}" >&2
    exit 2
    ;;
esac
