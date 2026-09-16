#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/_lib.sh"
cd "$ROOT_DIR"

SUITE="${1:-pr}"
case "$SUITE" in
  pr) run "$EVAL_PR_CMD" ;;
  full) run "$EVAL_FULL_CMD" ;;
  *) echo "Usage: $0 [pr|full]" >&2; exit 2 ;;
esac
