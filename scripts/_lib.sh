#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=pr-gate.conf.sh
source "$ROOT_DIR/scripts/pr-gate.conf.sh"

section() {
  printf '\n== %s ==\n' "$1"
}

run() {
  printf '+ %s\n' "$*"
  bash -o pipefail -c "$*"
}

has_python_project() {
  [[ -f "$ROOT_DIR/pyproject.toml" ]]
}

has_python_source_without_project() {
  [[ ! -f "$ROOT_DIR/pyproject.toml" ]] && \
    { [[ -d "$ROOT_DIR/api" ]] || [[ -d "$ROOT_DIR/workers" ]] || [[ -d "$ROOT_DIR/domain" ]]; }
}

has_node_project() {
  [[ -f "$ROOT_DIR/package.json" ]]
}

has_web_source_without_project() {
  [[ ! -f "$ROOT_DIR/package.json" ]] && [[ -d "$ROOT_DIR/web" ]]
}

contains_test_files() {
  local dir="$1"
  [[ -d "$dir" ]] && find "$dir" -type f \( -name 'test_*.py' -o -name '*.test.ts' -o -name '*.test.tsx' -o -name '*.spec.ts' -o -name '*.spec.tsx' \) -print -quit | grep -q .
}
