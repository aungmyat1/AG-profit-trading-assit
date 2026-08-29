"""Deterministic proposal identity (spec sections 12, 46; historical-validation spec
sections 17-19, 59). `setup_id` is a pure function of (symbol, combination, direction,
reference_key) -- no transient fields (current tick, unrealized distance, snapshot
timestamp) ever enter it, so the same underlying SMC setup keeps the same identity
across every poll regardless of what price does.

`reference_key` pins the *structural* E-condition reference (reference_type +
reference_low/high/level from the EConditionResult that qualified the combination --
the HTF gap/POI/liquidity level itself, not current price) so that two independent
setups on the same symbol/combination/direction (e.g. Monday's EURUSD E2M1 SHORT from
H1 POI A vs Wednesday's from H1 POI B) do NOT collide into one setup_id (spec section
17). It is optional and defaults to None for callers that don't have/need finer
identity (existing unit tests exercising the 3-field base contract keep working
unchanged); real proposal generation (gate.py/lifecycle.py) always supplies it.

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


def setup_id(symbol: str, combination: str, direction: Optional[str],
              reference_key: Optional[str] = None) -> str:
    digest = hashlib.blake2b(
        f"{symbol}|{combination}|{direction or 'NONE'}|{reference_key or 'NONE'}".encode("utf-8"),
        digest_size=8,
    ).hexdigest()
    return f"SETUP-{symbol}-{combination}-{digest}"


def reference_key_for(reference_type: Optional[str], reference_low: Optional[float],
                       reference_high: Optional[float], reference_level: Optional[float]) -> Optional[str]:
    """Builds the stable structural identity string consumed by `setup_id`'s
    `reference_key`. Returns None when no reference fields are available at all
    (nothing to disambiguate on -- falls back to the base 3-field identity)."""
    if reference_type is None and reference_low is None and reference_high is None and reference_level is None:
        return None
    return f"{reference_type or 'NONE'}|{reference_low}|{reference_high}|{reference_level}"


def proposal_id_for(setup: str) -> str:
    digest = hashlib.blake2b(setup.encode("utf-8"), digest_size=6).hexdigest()
    return f"PROPOSAL-{digest}"


def snapshot_id(symbol: str, snapshot_time: Optional[datetime]) -> str:
    stamp = snapshot_time.isoformat() if snapshot_time is not None else "NONE"
    digest = hashlib.blake2b(f"{symbol}|{stamp}".encode("utf-8"), digest_size=6).hexdigest()
    return f"SNAPSHOT-{symbol}-{digest}"
