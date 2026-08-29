"""Deterministic proposal identity (spec sections 12, 46). `setup_id` is a pure
function of (symbol, combination, direction) ONLY -- no transient fields (current tick,
unrealized distance, snapshot timestamp) ever enter it, so the same underlying SMC
setup keeps the same identity across every poll regardless of what price does.
`proposal_id` is derived purely from `setup_id` (this package tracks exactly one
proposal per active setup; entry-metadata changes are LIFECYCLE transitions --
CREATED/STILL_VALID/UPDATED -- on that same proposal_id, never a new one -- see
lifecycle.py). `snapshot_id` is the one identity that DOES vary every poll (it names
"this specific analysis observation", spec section 12).
"""
from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Optional


def setup_id(symbol: str, combination: str, direction: Optional[str]) -> str:
    digest = hashlib.blake2b(f"{symbol}|{combination}|{direction or 'NONE'}".encode("utf-8"), digest_size=8).hexdigest()
    return f"SETUP-{symbol}-{combination}-{digest}"


def proposal_id_for(setup: str) -> str:
    digest = hashlib.blake2b(setup.encode("utf-8"), digest_size=6).hexdigest()
    return f"PROPOSAL-{digest}"


def snapshot_id(symbol: str, snapshot_time: Optional[datetime]) -> str:
    stamp = snapshot_time.isoformat() if snapshot_time is not None else "NONE"
    digest = hashlib.blake2b(f"{symbol}|{stamp}".encode("utf-8"), digest_size=6).hexdigest()
    return f"SNAPSHOT-{symbol}-{digest}"
