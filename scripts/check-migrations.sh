#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/_lib.sh"
cd "$ROOT_DIR"

if [[ ! -f alembic.ini ]]; then
  echo "No alembic.ini yet; migration gate is not applicable."
  exit 0
fi

if ! has_python_project; then
  echo "alembic.ini exists but pyproject.toml is missing." >&2
  exit 1
fi

if [[ -n "${PR_GATE_DATABASE_URL:-}" ]]; then
  section "Migration validation"
  export DATABASE_URL="$PR_GATE_DATABASE_URL"
  run "python -m uv run alembic upgrade head"
  exit 0
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "Migration validation requires Docker locally or PR_GATE_DATABASE_URL." >&2
  exit 1
fi

name="kanior-pr-gate-pg-$$"
cleanup() { docker rm -f "$name" >/dev/null 2>&1 || true; }
trap cleanup EXIT

section "Start disposable PostgreSQL for migration validation"
docker run -d --rm \
  --name "$name" \
  -e POSTGRES_PASSWORD=postgres \
  -e POSTGRES_DB=kanior_pr_gate \
  -p 127.0.0.1::5432 \
  pgvector/pgvector:0.8.1-pg17 >/dev/null

for _ in $(seq 1 30); do
  if docker exec "$name" pg_isready -U postgres -d kanior_pr_gate >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

docker exec "$name" pg_isready -U postgres -d kanior_pr_gate >/dev/null
port="$(docker port "$name" 5432/tcp | awk -F: '{print $NF}')"
export DATABASE_URL="postgresql://postgres:postgres@127.0.0.1:${port}/kanior_pr_gate"
run "python -m uv run alembic upgrade head"
