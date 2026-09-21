#!/usr/bin/env bash
set -euo pipefail
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/_lib.sh"
cd "$ROOT_DIR"

PIP_AUDIT_VERSION="2.10.1"
GITLEAKS_IMAGE="ghcr.io/gitleaks/gitleaks:v8.30.1"

scan_secrets() {
  section "Secret scan"
  if command -v gitleaks >/dev/null 2>&1; then
    gitleaks git "$ROOT_DIR" --no-banner --redact
    return
  fi

  if command -v docker >/dev/null 2>&1; then
    local docker_source="$ROOT_DIR"
    if command -v cygpath >/dev/null 2>&1; then
      docker_source="$(cygpath -w "$ROOT_DIR")"
    fi
    # Disable Git Bash path rewriting so Docker receives the container path verbatim.
    MSYS_NO_PATHCONV=1 docker run --rm \
      --volume "$docker_source:/repo:ro" \
      "$GITLEAKS_IMAGE" git /repo --no-banner --redact
    return
  fi

  echo "Secret scanning requires gitleaks or Docker (image: $GITLEAKS_IMAGE)." >&2
  return 1
}

audit_dependencies() {
  section "Python dependency audit"
  if has_python_project; then
    local requirements_file
    local cleanup_command
    requirements_file="$(mktemp)"
    printf -v cleanup_command 'rm -f %q' "$requirements_file"
    trap "$cleanup_command" EXIT
    python -m uv export \
      --quiet \
      --frozen \
      --all-groups \
      --no-emit-project \
      --output-file "$requirements_file"
    set +e
    python -m uv tool run \
      --from "pip-audit==$PIP_AUDIT_VERSION" \
      pip-audit \
      --requirement "$requirements_file" \
      --require-hashes \
      --disable-pip
    local audit_status=$?
    set -e
    rm -f "$requirements_file"
    trap - EXIT
    if [[ "$audit_status" -ne 0 ]]; then
      return "$audit_status"
    fi
  else
    echo "No pyproject.toml; Python dependency audit is not applicable."
  fi

  section "Node dependency audit"
  if has_node_project; then
    # Electron's installer currently depends on extract-zip 2.0.1, and upstream
    # publishes no fixed release for these two archive-symlink advisories. Keep
    # the exceptions explicit so every other high/critical advisory still blocks.
    corepack pnpm audit \
      --audit-level high \
      --ignore GHSA-jmr9-qjv8-65gv \
      --ignore GHSA-7pqw-9j4j-h8q3
  else
    echo "No package.json; Node dependency audit is not applicable."
  fi
}

case "${1:-all}" in
  secrets)
    scan_secrets
    ;;
  dependencies)
    audit_dependencies
    ;;
  all)
    scan_secrets
    audit_dependencies
    ;;
  *)
    echo "Usage: $0 [all|secrets|dependencies]" >&2
    exit 2
    ;;
esac
