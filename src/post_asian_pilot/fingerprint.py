"""Deterministic SHA-256 fingerprints for release/strategy/session/risk config content.

Same canonical-JSON technique already proven in
historical_replay.stage1.fingerprint_qualified_e_events: sort_keys, no whitespace, hash
only deterministic semantic content -- never wall-clock/runtime-generated fields.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any


def fingerprint(content: Any) -> str:
    canonical = json.dumps(content, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
