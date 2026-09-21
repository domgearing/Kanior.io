#!/usr/bin/env python3
"""Minimal deterministic eval used to prove the eval runner itself works."""

import json

print(json.dumps({"metric": "pass_rate", "value": 1.0, "details": "Eval harness is operational."}))
