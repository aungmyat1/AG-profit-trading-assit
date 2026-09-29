"""A5-compatible raw spread observation semantics (owner/architect-provided interface).

    spread_price = ask - bid
    spread_pips  = spread_price / pip_size

from contemporaneous MT5 live-tick bid/ask only -- never a bar `spread` field. Every
sampled observation becomes exactly one row, including invalid ones; nothing is dropped,
filled, or edited after acquisition. A zero spread is preserved and flagged, never
interpreted as zero economic friction.

Validity precedence (first match wins):
    WRONG_BROKER, WRONG_SERVER, WRONG_ENVIRONMENT, WRONG_SYMBOL   venue/symbol isolation
    MISSING_TICK                                                  no tick returned
    NONFINITE_QUOTE, NONPOSITIVE_BID, NONPOSITIVE_ASK, ASK_BELOW_BID
    STALE_TICK                                                    tick age > frozen tolerance
    VALID

Pure: no MT5 import. Serialization is canonical (sorted keys, fixed separators), so equal
rows hash equally. Rows and manifests carry no login, account number, password or .env data.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import math
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

# V2 (P6-R3): adds the optional, additive `quote_metadata` row field; every V1 field and
# its semantics are unchanged. V1 evidence (capture VT_SPREAD_20260928T190357Z_18ee81e6)
# remains attributed to V1 via its own rows/manifest.
# V3 (P6-R3 correction): the fixed-cadence scheduler skips rounds that are more than one
# cadence late (host/terminal stall) instead of bursting them back-to-back; skips are
# recorded in the manifest. V2 burst 83 overdue rounds at one instant in capture
# VT_SPREAD_POST_LONDON_20260929T120121Z_476ba253 (preserved, marked defective).
COLLECTOR_VERSION = "AG_VT_SPREAD_COLLECTOR_V3"
# A capture that had to skip more than this fraction of its scheduled rounds fails.
MAX_SKIPPED_ROUND_FRACTION = 0.10
SOURCE = "MT5_LIVE_TICK"
EXPECTED_BROKER = "VT_MARKETS"
EXPECTED_SERVER = "VTMarkets-Demo"
EXPECTED_ENVIRONMENT = "DEMO"
# Frozen before capture: a tick whose own timestamp is more than this many seconds older
# than the sampling instant is STALE_TICK. Recorded in every manifest.
STALE_TOLERANCE_SECONDS = 60.0

VALID = "VALID"
IDENTITY_FAILURES = ("WRONG_BROKER", "WRONG_SERVER", "WRONG_ENVIRONMENT")
MISSING_TICK = "MISSING_TICK"
INVALID_QUOTE_CODES = ("NONFINITE_QUOTE", "NONPOSITIVE_BID", "NONPOSITIVE_ASK", "ASK_BELOW_BID", "STALE_TICK",
                       "WRONG_SYMBOL") + IDENTITY_FAILURES

# Session labels are the actual UTC execution windows of the canonical pilot cycles
# (config/pilot/*: POST_ASIAN 07:00-11:00, POST_LONDON 12:00-15:00), weekdays only.
SESSION_WINDOWS: Tuple[Tuple[str, dt.time, dt.time], ...] = (
    ("POST_ASIAN", dt.time(7, 0), dt.time(11, 0)),
    ("POST_LONDON", dt.time(12, 0), dt.time(15, 0)),
)

_FORBIDDEN_KEYS = ("login", "password", "account", "passwd", "investor")


@dataclass(frozen=True)
class VenueIdentity:
    broker: str
    server: str
    environment: str


@dataclass(frozen=True)
class RawTick:
    bid: float
    ask: float
    time_utc: dt.datetime   # tick's own timestamp, converted to true UTC
    time_msc: int           # raw broker-clock milliseconds, as returned


def round_action(k: int, t0: float, now: float, cadence: float) -> Tuple[str, float]:
    """Fixed-cadence schedule: round k is due at t0 + k*cadence (monotonic seconds).
    ("SAMPLE", delay>=0) when it is early or at most one cadence late, else
    ("SKIP_LATE", lateness). Missed rounds are never sampled late, bursted or backfilled."""
    due = t0 + k * cadence
    if now > due + cadence:
        return "SKIP_LATE", now - due
    return "SAMPLE", max(0.0, due - now)


def classify_session(t: dt.datetime) -> str:
    if t.weekday() >= 5:
        return "OTHER"
    for name, start, end in SESSION_WINDOWS:
        if start <= t.timetz().replace(tzinfo=None) < end:
            return name
    return "OTHER"


def _finite(x: Any) -> bool:
    try:
        return math.isfinite(float(x))
    except (TypeError, ValueError):
        return False


def observe(
    *,
    capture_id: str,
    sequence: int,
    sampled_at_utc: dt.datetime,
    expected_symbol: str,
    observed_symbol: Optional[str],
    venue: VenueIdentity,
    tick: Optional[RawTick],
    pip_size: float,
    git_lineage: str,
    session_classification: str,
    quote_metadata: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """One raw evidence row. Never raises for bad market data -- it classifies it.
    `quote_metadata` (quote_metadata.py) is recorded verbatim and never affects validity."""
    validity = VALID
    if venue.broker != EXPECTED_BROKER:
        validity = "WRONG_BROKER"
    elif venue.server != EXPECTED_SERVER:
        validity = "WRONG_SERVER"
    elif venue.environment != EXPECTED_ENVIRONMENT:
        validity = "WRONG_ENVIRONMENT"
    elif observed_symbol != expected_symbol:
        validity = "WRONG_SYMBOL"
    elif tick is None:
        validity = MISSING_TICK
    elif not (_finite(tick.bid) and _finite(tick.ask)):
        validity = "NONFINITE_QUOTE"
    elif tick.bid <= 0:
        validity = "NONPOSITIVE_BID"
    elif tick.ask <= 0:
        validity = "NONPOSITIVE_ASK"
    elif tick.ask < tick.bid:
        validity = "ASK_BELOW_BID"
    elif (sampled_at_utc - tick.time_utc).total_seconds() > STALE_TOLERANCE_SECONDS:
        validity = "STALE_TICK"

    quote_usable = tick is not None and _finite(tick.bid) and _finite(tick.ask)
    spread_price = round(tick.ask - tick.bid, 10) if quote_usable else None
    spread_pips = round(spread_price / pip_size, 6) if spread_price is not None else None
    return {
        "capture_id": capture_id,
        "sequence": sequence,
        "timestamp_utc": sampled_at_utc.isoformat(),
        "tick_timestamp_utc": tick.time_utc.isoformat() if tick is not None else None,
        "tick_time_msc_broker_clock": tick.time_msc if tick is not None else None,
        "tick_age_seconds": round((sampled_at_utc - tick.time_utc).total_seconds(), 3) if tick is not None else None,
        "broker": venue.broker,
        "server": venue.server,
        "environment": venue.environment,
        "symbol": expected_symbol,
        "observed_symbol": observed_symbol,
        "bid": float(tick.bid) if quote_usable else (None if tick is None else str(tick.bid)),
        "ask": float(tick.ask) if quote_usable else (None if tick is None else str(tick.ask)),
        "spread_price": spread_price,
        "spread_pips": spread_pips,
        "pip_size": pip_size,
        "zero_spread": spread_price == 0.0 if spread_price is not None else None,
        "session_classification": session_classification,
        "source": SOURCE,
        "collector_version": COLLECTOR_VERSION,
        "git_lineage": git_lineage,
        "validity": validity,
        "quote_metadata": dict(quote_metadata) if quote_metadata is not None else None,
    }


def serialize_rows(rows: Iterable[Mapping[str, Any]]) -> bytes:
    """Canonical JSONL bytes (sorted keys, no whitespace variance, trailing newline)."""
    lines = [json.dumps(dict(r), sort_keys=True, separators=(",", ":"), allow_nan=False) for r in rows]
    for line in lines:
        assert_secret_free(json.loads(line))
    return ("\n".join(lines) + "\n").encode("utf-8") if lines else b""


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def assert_secret_free(obj: Any) -> None:
    """Fail closed if any key looks like an account secret/identifier."""
    if isinstance(obj, Mapping):
        for k, v in obj.items():
            if any(f in str(k).lower() for f in _FORBIDDEN_KEYS):
                raise ValueError(f"secret-like key {k!r} in evidence")
            assert_secret_free(v)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            assert_secret_free(v)


def symbol_counts(rows: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    """Acquisition sanity only (N, min/max, zero, invalid) -- no aggregation authority."""
    valid = [r for r in rows if r["validity"] == VALID]
    spreads = [r["spread_pips"] for r in valid]
    return {
        "attempted": len(rows),
        "valid": len(valid),
        "missing": sum(r["validity"] == MISSING_TICK for r in rows),
        "invalid": sum(r["validity"] not in (VALID, MISSING_TICK) for r in rows),
        "invalid_by_code": {c: n for c in sorted({r["validity"] for r in rows} - {VALID, MISSING_TICK})
                            for n in [sum(r["validity"] == c for r in rows)]},
        "zero_spread_samples": sum(bool(r["zero_spread"]) for r in valid),
        "spread_min_pips": min(spreads) if spreads else None,
        "spread_max_pips": max(spreads) if spreads else None,
    }


def capture_status(per_symbol_rows: Mapping[str, Sequence[Mapping[str, Any]]]) -> str:
    """Venue isolation: any wrong broker/server/environment row fails the whole capture."""
    rows: List[Mapping[str, Any]] = [r for rs in per_symbol_rows.values() for r in rs]
    if any(r["validity"] in IDENTITY_FAILURES for r in rows):
        return "VT_CAPTURE_VALIDATION_FAILED"
    if len({(r["broker"], r["server"], r["environment"]) for r in rows}) > 1:
        return "VT_CAPTURE_VALIDATION_FAILED"
    if not rows or not all(any(r["validity"] == VALID for r in rs) for rs in per_symbol_rows.values()):
        return "VT_CAPTURE_VALIDATION_FAILED"
    sessions = {r["session_classification"] for r in rows}
    return "VT_INITIAL_FRICTION_CAPTURE_COMPLETE" if sessions <= {"POST_ASIAN", "POST_LONDON"} \
        else "VT_CAPTURE_OUTSIDE_TARGET_SESSION"
