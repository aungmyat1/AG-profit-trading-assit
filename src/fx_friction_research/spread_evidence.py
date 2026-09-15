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
import time as _time
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable, Dict, List, Sequence

from mt5.account import account as _mt5_account
from mt5.connection import MT5ConnectionError, is_connected
from mt5.market_data import MarketDataError, get_tick

# Row-level source tag for a scheduled grid tick that could not be filled with a real
# observation (WP3A.1 P2/WP2) -- distinct from SpreadObservation.source
# ("MT5_LIVE_TICK") so a gap is never mistaken for a real quote downstream.
MISSING_SOURCE = "MISSING_GAP"


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


def collect_fixed_grid(
    symbol: str,
    pip_size: float,
    campaign_id: str,
    window_id: str,
    sample_count: int,
    interval_seconds: float,
    sleep_fn: Callable[[float], None] = _time.sleep,
    now_fn: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
) -> List[dict]:
    """Campaign-aware extension of capture_observation (WP3A.1 P2) -- samples on a FIXED
    absolute-time grid anchored to this call's own start time: tick i fires at
    (start + i*interval_seconds) regardless of how long capture i-1 took, so a slow MT5
    round-trip never silently compresses or skips the schedule (no adaptive sampling).

    A capture that raises (MT5ConnectionError: no connection; MarketDataError: symbol not
    found / no live quote / stale data) becomes a MISSING_SOURCE row carrying the failure
    reason at its scheduled grid time -- it is never dropped silently, never retried
    out-of-schedule, and price fields are never backfilled or interpolated. Returns plain
    dicts (not SpreadObservation) because a MISSING row has no bid/ask/spread to carry.
    """
    start = now_fn()
    rows: List[dict] = []
    for i in range(sample_count):
        target = start + timedelta(seconds=i * interval_seconds)
        wait = (target - now_fn()).total_seconds()
        if wait > 0:
            sleep_fn(wait)
        try:
            observation = capture_observation(symbol, pip_size)
            account_login = _mt5_account().login
            rows.append({
                "campaign_id": campaign_id,
                "window_id": window_id,
                "timestamp_utc": observation.timestamp_utc,
                "symbol": observation.symbol,
                "bid": observation.bid,
                "ask": observation.ask,
                "spread_price": observation.spread_price,
                "spread_pips": observation.spread_pips,
                "broker_server": observation.broker_server,
                "account_login": account_login,
                "source": observation.source,
                "missing_reason": None,
            })
        except (MT5ConnectionError, MarketDataError) as exc:
            rows.append({
                "campaign_id": campaign_id,
                "window_id": window_id,
                "timestamp_utc": target.isoformat(),
                "symbol": symbol,
                "bid": None,
                "ask": None,
                "spread_price": None,
                "spread_pips": None,
                "broker_server": None,
                "account_login": None,
                "source": MISSING_SOURCE,
                "missing_reason": f"{type(exc).__name__}: {exc}",
            })
    return rows


def summarize_campaign_rows(rows: Sequence[dict]) -> Dict[str, float]:
    """sample_count/missing_sample_count/min/median/mean/p75/p90/p95/p99/max over the
    present (non-MISSING) rows' spread_pips, computed from unrounded raw values. Raises
    on an empty row sequence; a window with zero present rows still returns a summary
    (missing_sample_count == total_scheduled, no spread statistics)."""
    if not rows:
        raise ValueError("cannot summarize an empty row set")
    present = [r for r in rows if r.get("source") != MISSING_SOURCE]
    missing = [r for r in rows if r.get("source") == MISSING_SOURCE]
    summary: Dict[str, float] = {
        "total_scheduled": len(rows),
        "sample_count": len(present),
        "missing_sample_count": len(missing),
    }
    if present:
        values = sorted(r["spread_pips"] for r in present)
        summary.update({
            "minimum_pips": values[0],
            "median_pips": statistics.median(values),
            "mean_pips": statistics.fmean(values),
            "p75_pips": _percentile(values, 75),
            "p90_pips": _percentile(values, 90),
            "p95_pips": _percentile(values, 95),
            "p99_pips": _percentile(values, 99),
            "maximum_pips": values[-1],
        })
    return summary


def combine_hashes(hashes: Sequence[str]) -> str:
    """Deterministic combination of N per-window/session raw_rows_hash values into one
    campaign-level hash -- sha256 over the sorted hash list joined with a separator, so
    the combined hash is independent of the order the sessions were aggregated in."""
    if not hashes:
        raise ValueError("cannot combine an empty hash set")
    blob = "|".join(sorted(hashes)).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def raw_rows_hash(rows: Sequence[dict]) -> str:
    """SHA-256 over canonical sorted JSON of campaign row dicts (order-independent, sorted
    by (window_id, timestamp_utc)) -- same technique as raw_observations_hash, extended to
    the plain-dict shape collect_fixed_grid produces (including MISSING rows, which are
    part of the evidence, not excluded from it)."""
    canonical = sorted(rows, key=lambda r: (r["window_id"], r["timestamp_utc"]))
    blob = json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()
