#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/_lib.sh"
cd "$ROOT_DIR"

started_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
printf '\n========================================\n'
printf 'KaniorAI PR Readiness Gate\n'
printf 'Started: %s\n' "$started_at"
printf '========================================\n'

bash ./scripts/check.sh
bash ./scripts/test-integration.sh
bash ./scripts/check-migrations.sh
bash ./scripts/eval.sh pr

printf '\n========================================\n'
printf 'PR READY: PASS\n'
printf '========================================\n'
