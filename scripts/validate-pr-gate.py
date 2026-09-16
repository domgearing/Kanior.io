#!/usr/bin/env python3
"""Validate the PR-gate scaffold using only the Python standard library."""

from __future__ import annotations

import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQUIRED_FILES = [
    ".github/workflows/pr-gate.yml",
    ".github/pull_request_template.md",
    "docs/PR_PROCESS.md",
    "docs/EVALS.md",
    "evals/manifest.toml",
    "evals/run.py",
    "scripts/check.sh",
    "scripts/eval.sh",
    "scripts/pr-ready.sh",
    "scripts/test-integration.sh",
    "scripts/check-migrations.sh",
]


def fail(message: str) -> None:
    print(f"ERROR: {message}", file=sys.stderr)


def main() -> int:
    errors = 0
    for relative in REQUIRED_FILES:
        if not (ROOT / relative).is_file():
            fail(f"missing required file: {relative}")
            errors += 1

    manifest_path = ROOT / "evals/manifest.toml"
    if manifest_path.is_file():
        with manifest_path.open("rb") as fh:
            manifest = tomllib.load(fh)
        pr_evals = manifest.get("suites", {}).get("pr", {}).get("evals", [])
        eval_defs = manifest.get("evals", {})
        if not pr_evals:
            fail("PR eval suite must contain at least one eval")
            errors += 1
        full_evals = manifest.get("suites", {}).get("full", {}).get("evals", [])
        if not set(pr_evals).issubset(set(full_evals)):
            fail("full eval suite must contain every PR eval")
            errors += 1
        for name in pr_evals:
            cfg = eval_defs.get(name)
            if cfg is None:
                fail(f"PR suite references missing eval: {name}")
                errors += 1
                continue
            for field in ("command", "metric", "comparison", "threshold", "blocking"):
                if field not in cfg:
                    fail(f"eval {name!r} is missing required field {field!r}")
                    errors += 1
            if cfg.get("blocking") is not True:
                fail(f"PR eval {name!r} must be blocking")
                errors += 1

    workflow_path = ROOT / ".github/workflows/pr-gate.yml"
    if workflow_path.is_file():
        workflow = workflow_path.read_text(encoding="utf-8")
        for token in ("pull_request:", "merge_group:", "name: PR Gate / required"):
            if token not in workflow:
                fail(f"workflow missing required token: {token}")
                errors += 1

    if errors:
        return 1
    print("PR-gate scaffold validation: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
