#!/usr/bin/env python3
"""Run contract boundary tests without requiring an application or pytest."""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

if __name__ == "__main__":
    suite = unittest.defaultTestLoader.discover(str(ROOT / "tests/contract"))
    if suite.countTestCases() == 0:
        raise SystemExit("No contract tests discovered")
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    raise SystemExit(0 if result.wasSuccessful() else 1)
