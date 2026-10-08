#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/_lib.sh"
cd "$ROOT_DIR"

# Local development only. Each new project gets its own scoped worker process;
# existing transcription jobs can finish without being interrupted.
declare -A started_projects=()
worker_pids=()

stop_workers() {
  trap - EXIT INT TERM
  for pid in "${worker_pids[@]:-}"; do
    if [[ -z "$pid" ]]; then continue; fi
    if command -v taskkill.exe >/dev/null 2>&1; then
      MSYS_NO_PATHCONV=1 taskkill.exe //PID "$pid" //T //F >/dev/null 2>&1 || true
    else
      kill "$pid" >/dev/null 2>&1 || true
    fi
  done
  wait 2>/dev/null || true
}
trap stop_workers EXIT
trap 'exit 0' INT TERM

start_new_scopes() {
  local exports project_id batch
  local -a project_ids=() new_ids=()
  exports="$(uv run python scripts/prepare-live-test.py)"
  eval "$exports"
  IFS=, read -r -a project_ids <<< "$VERELO_WORKER_PROJECT_IDS"
  for project_id in "${project_ids[@]:-}"; do
    if [[ -n "$project_id" && -z "${started_projects[$project_id]+x}" ]]; then
      new_ids+=("$project_id")
    fi
  done
  if [[ ${#new_ids[@]} -eq 0 ]]; then return; fi

  batch="$(IFS=,; printf '%s' "${new_ids[*]}")"
  (
    unset VERELO_LOCAL_ADMIN_DATABASE_URL VERELO_MIGRATOR_DATABASE_URL
    unset VERELO_POSTGRES_PASSWORD VERELO_MIGRATOR_DB_PASSWORD VERELO_API_DB_PASSWORD
    VERELO_WORKER_PROJECT_IDS="$batch" uv run python -m workers
  ) &
  worker_pids+=("$!")
  for project_id in "${new_ids[@]}"; do started_projects["$project_id"]=1; done
  echo "Worker started for ${#new_ids[@]} newly provisioned project(s)."
}

start_new_scopes
while true; do
  sleep 5
  for pid in "${worker_pids[@]:-}"; do
    if [[ -n "$pid" ]] && ! kill -0 "$pid" 2>/dev/null; then
      echo "A Verelo worker exited unexpectedly." >&2
      exit 1
    fi
  done
  start_new_scopes
done
