"""Read-only EURUSD spread evidence collector (AG_LARGE_SMC_EURUSD_FRICTION_EVIDENCE_V1,
WP3A P2). Captures live bid/ask observations via the existing MT5 read path only --
mt5.market_data.get_tick(), which itself requires mt5.connection.connect() to already
have succeeded -- and never calls order_send/order_check or anything in execution.* /
mt5.management_gateway. This module does not call connect() itself, so a caller that
never connected (or whose connection dropped) gets a fail-closed error, never a silently
re-established connection or a synthetic observation.

Deliberately dependency-free percentile/hash logic mirrors
fx_friction_research.provenance.resolved_record_hash's convention (deterministic
sha256 over canonical sorted JSON) rather than inventing a second technique.
"""
from __future__ import annotations

import hashlib
import json
import statistics
from dataclasses import asdict, dataclass
from typing import Dict, List, Sequence

from mt5.account import account as _mt5_account
from mt5.connection import MT5ConnectionError, is_connected
from mt5.market_data import get_tick


@dataclass(frozen=True)
class SpreadObservation:
    timestamp_utc: str
    symbol: str
    bid: float
    ask: float
    spread_price: float
    spread_pips: float
    broker_server: str
    source: str = "MT5_LIVE_TICK"


def capture_observation(symbol: str, pip_size: float) -> SpreadObservation:
    """One read-only bid/ask sample. Fails closed (MT5ConnectionError) if the caller has
    not already established a live MT5 connection -- this function refuses to fabricate
    an observation rather than connecting on the caller's behalf."""
    if not is_connected():
        raise MT5ConnectionError(
            "MT5_NOT_CONNECTED: refusing to fabricate a spread observation"
        )
    tick = get_tick(symbol)  # raises MarketDataError (propagated, not caught) if no live quote
    spread_price = tick.ask - tick.bid
    broker_info = _mt5_account()
    return SpreadObservation(
        timestamp_utc=tick.time_utc.isoformat(),
        symbol=symbol,
        bid=tick.bid,
        ask=tick.ask,
        spread_price=spread_price,
        spread_pips=spread_price / pip_size,
        broker_server=broker_info.server,
    )


def summarize(observations: Sequence[SpreadObservation]) -> Dict[str, float]:
    """sample_count/min/median/mean/p75/p90/p95/max over spread_pips. Raises on an empty
    sequence rather than returning a misleading zeroed summary."""
    if not observations:
        raise ValueError("cannot summarize an empty observation set")
    values = sorted(o.spread_pips for o in observations)
    return {
        "sample_count": len(values),
        "minimum_pips": values[0],
        "median_pips": statistics.median(values),
        "mean_pips": statistics.fmean(values),
        "p75_pips": _percentile(values, 75),
        "p90_pips": _percentile(values, 90),
        "p95_pips": _percentile(values, 95),
        "maximum_pips": values[-1],
    }


def _percentile(sorted_values: Sequence[float], pct: float) -> float:
    """Nearest-rank-with-interpolation percentile over already-sorted values --
    deterministic, no external statistics-library dependency, reproducible from the same
    raw observations every time."""
    if len(sorted_values) == 1:
        return sorted_values[0]
    k = (pct / 100) * (len(sorted_values) - 1)
    lower = int(k)
    upper = min(lower + 1, len(sorted_values) - 1)
    if lower == upper:
        return sorted_values[lower]
    return sorted_values[lower] + (sorted_values[upper] - sorted_values[lower]) * (k - lower)


def raw_observations_hash(observations: Sequence[SpreadObservation]) -> str:
    """SHA-256 over canonical sorted JSON, order-independent (sorted by timestamp_utc) --
    re-hashing an unchanged observation set always reproduces the same digest regardless
    of collection/iteration order, same technique as
    fx_friction_research.provenance.resolved_record_hash."""
    rows: List[dict] = sorted((asdict(o) for o in observations), key=lambda r: r["timestamp_utc"])
    blob = json.dumps(rows, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()
