"""Deterministic evidence IDs (spec section 42): stable, reproducible identifiers for
objects already produced by market_structure/supply_demand/liquidity, so surveillance,
proposal, and visual-explanation layers can cross-reference the SAME detected object
without re-deriving it. Not a database key, not random -- a pure hash of the fields that
already uniquely identify the object within one snapshot: symbol, timeframe, kind, and
the object's own origin/level timestamp+price. Two calls with the same inputs always
produce the same ID (determinism, spec section 54); different inputs (almost) never
collide (blake2b, 10 hex chars is ample for one snapshot's object count).
"""
from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Optional

_PREFIXES = {
    "STRUCT": "STRUCT",
    "OB": "OB",
    "FVG": "FVG",
    "ZONE": "ZONE",
    "LIQ": "LIQ",
    "SESSION": "SESSION",
    "PD": "PD",
}


def evidence_id(kind: str, symbol: str, timeframe: str, origin_time: Optional[datetime], price: Optional[float]) -> str:
    """`kind` is a short tag such as "STRUCT", "OB", "FVG", "LIQ", "ZONE", "SESSION", "PD"
    -- the caller picks it, this function does not validate it against a fixed enum
    (new zone/liquidity families should not require touching this module)."""
    origin_str = origin_time.isoformat() if origin_time is not None else "NONE"
    price_str = f"{price:.10f}" if price is not None else "NONE"
    digest = hashlib.blake2b(
        f"{symbol}|{timeframe}|{kind}|{origin_str}|{price_str}".encode("utf-8"), digest_size=5,
    ).hexdigest()
    return f"{kind}-{timeframe}-{digest}"
