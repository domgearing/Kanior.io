#!/usr/bin/env python3
"""KaniorAI eval runner.

Each eval command must print one JSON object as its final non-empty stdout line:
    {"metric": "metric_name", "value": 0.97, "details": "optional"}

The threshold and comparison operator live in evals/manifest.toml so an eval
cannot silently choose its own passing threshold.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "evals" / "manifest.toml"


def load_manifest() -> dict[str, Any]:
    with MANIFEST.open("rb") as fh:
        return tomllib.load(fh)


def compare(value: float, op: str, threshold: float) -> bool:
    if op == "gte":
        return value >= threshold
    if op == "gt":
        return value > threshold
    if op == "lte":
        return value <= threshold
    if op == "lt":
        return value < threshold
    if op == "eq":
        return value == threshold
    raise ValueError(f"Unsupported comparison operator: {op}")


def parse_result(stdout: str) -> dict[str, Any]:
    lines = [line.strip() for line in stdout.splitlines() if line.strip()]
    if not lines:
        raise ValueError("eval produced no stdout")
    return json.loads(lines[-1])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--suite", default="pr")
    args = parser.parse_args()

    manifest = load_manifest()
    suites = manifest.get("suites", {})
    eval_defs = manifest.get("evals", {})

    if args.suite not in suites:
        print(f"Unknown eval suite: {args.suite}", file=sys.stderr)
        return 2

    names = suites[args.suite].get("evals", [])
    if not names:
        print(f"Eval suite '{args.suite}' is empty; refusing to pass.", file=sys.stderr)
        return 2

    failures = 0
    print(f"KaniorAI eval suite: {args.suite}")
    print("=" * 72)

    for name in names:
        if name not in eval_defs:
            print(f"{name:<32} ERROR  missing definition")
            failures += 1
            continue

        cfg = eval_defs[name]
        command = cfg.get("command")
        if not isinstance(command, list) or not command:
            print(f"{name:<32} ERROR  invalid command")
            failures += 1
            continue

        proc = subprocess.run(
            [str(part) for part in command],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        if proc.returncode != 0:
            print(f"{name:<32} FAIL   command exited {proc.returncode}")
            if proc.stdout.strip():
                print(proc.stdout.rstrip())
            if proc.stderr.strip():
                print(proc.stderr.rstrip(), file=sys.stderr)
            failures += 1
            continue

        try:
            result = parse_result(proc.stdout)
            metric = result["metric"]
            value = float(result["value"])
            expected_metric = cfg["metric"]
            threshold = float(cfg["threshold"])
            op = cfg["comparison"]

            if metric != expected_metric:
                raise ValueError(f"metric mismatch: expected {expected_metric!r}, got {metric!r}")

            passed = compare(value, op, threshold)
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            print(f"{name:<32} ERROR  {exc}")
            failures += 1
            continue

        status = "PASS" if passed else "FAIL"
        print(f"{name:<32} {status:<6} {metric}={value:g} required {op} {threshold:g}")
        if not passed and bool(cfg.get("blocking", True)):
            failures += 1

    print("=" * 72)
    if failures:
        print(f"RESULT: FAIL ({failures} blocking failure(s))")
        return 1

    print("RESULT: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
