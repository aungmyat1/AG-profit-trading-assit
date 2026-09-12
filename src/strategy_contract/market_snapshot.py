"""MarketSnapshot -- the canonical, versioned market-truth contract for the R2-R4
canonical proposal pipeline (WP1, AG_CANONICAL_R2_R4_PROPOSAL_PIPELINE_V1).

NON-GOALS (read first): this module is an ADDITIVE, READ-ONLY, ONE-WAY VIEW layer,
matching the pattern already established by strategy_contract/decision.py. It does not
replace, wrap, or mutate mt5/market_data.py, historical_replay/, or any existing feed --
those remain the sole authoritative retrieval/normalization code. A MarketSnapshot is
built FROM an already-retrieved candle; it never fetches or invents data itself beyond
what its constructors receive.

Purpose: every downstream contract in the canonical pipeline (StrategyDecision, a
canonical Proposal, evidence records, API/UI display metadata) must carry an unambiguous,
propagated answer to "is this REAL broker data, REPLAY fixture data, or SYNTHETIC test
data?" so that synthetic/replay output can never be silently presented as real broker
truth. Before this module, no such discriminator existed anywhere in src/ (see
docs/status/AG_CANONICAL_R2_R4_WP0_BASELINE_RECONCILIATION_STATUS.md, WP0 section 1).

Fail-closed contract: this module never substitutes synthetic data for unavailable real
data. `from_mt5_latest_closed()` propagates mt5.market_data.MarketDataError verbatim
(DATA_MISSING, MT5_NOT_CONNECTED, STALE_DATA, etc.) on any retrieval failure; callers must
treat that as DATA_UNAVAILABLE and must not proceed to a READY strategy decision or
proposal on that call.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from mt5.market_data import get_latest_candles
from strategy_engine.session import Candle

MARKET_DATA_MODE_REAL = "REAL"
MARKET_DATA_MODE_REPLAY = "REPLAY"
MARKET_DATA_MODE_SYNTHETIC = "SYNTHETIC"
VALID_MARKET_DATA_MODES = frozenset(
    {MARKET_DATA_MODE_REAL, MARKET_DATA_MODE_REPLAY, MARKET_DATA_MODE_SYNTHETIC}
)

# Mirrors mt5/market_data.py::_TIMEFRAMES keys -- kept independent (no import of a
# private symbol) since this module must also describe REPLAY/SYNTHETIC snapshots that
# never touch mt5/market_data.py at all.
_TIMEFRAME_MINUTES = {"M1": 1, "M5": 5, "M15": 15, "M30": 30, "H1": 60, "H4": 240, "D1": 1440}


class UnsupportedTimeframeError(ValueError):
    pass


@dataclass(frozen=True)
class MarketSnapshot:
    """Canonical market-truth contract. Every field is either copied verbatim from the
    candle/retrieval call that produced it or explicitly computed here from those verbatim
    values (bar_close_time, fingerprint) -- nothing is estimated or fabricated.

    market_data_mode is immutable once constructed and MUST be propagated unchanged into
    every downstream contract (StrategyDecision.setup_properties, a canonical Proposal,
    evidence records, API/UI responses) per the plan's mixed-mode-fails-closed invariant.
    """

    symbol: str
    timeframe: str
    source: str
    market_data_mode: str
    bar_open_time: datetime
    bar_close_time: datetime
    market_data_asof: datetime
    retrieved_at: datetime
    is_closed: bool
    fingerprint: str

    def __post_init__(self) -> None:
        if self.market_data_mode not in VALID_MARKET_DATA_MODES:
            raise ValueError(
                f"market_data_mode must be one of {sorted(VALID_MARKET_DATA_MODES)}, "
                f"got {self.market_data_mode!r}"
            )


def _bar_close_time(timeframe: str, bar_open_time: datetime) -> datetime:
    if timeframe not in _TIMEFRAME_MINUTES:
        raise UnsupportedTimeframeError(f"{timeframe!r} not in {sorted(_TIMEFRAME_MINUTES)}")
    return bar_open_time + timedelta(minutes=_TIMEFRAME_MINUTES[timeframe])


def _fingerprint(symbol: str, timeframe: str, mode: str, candle: Candle) -> str:
    """Deterministic identity over the candle's own values -- lets a caller detect whether
    two snapshots claiming the same bar actually carry the same OHLCV, e.g. across rerun,
    replay-vs-real mismatch, or a broker data revision."""
    payload = "|".join([
        symbol, timeframe, mode,
        candle.time.astimezone(timezone.utc).isoformat(),
        repr(candle.open), repr(candle.high), repr(candle.low), repr(candle.close),
        repr(candle.volume),
    ])
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def from_mt5_latest_closed(symbol: str, timeframe: str, source: str = "VANTAGE_DEMO_MT5") -> MarketSnapshot:
    """REAL mode. Fetches exactly the single most recent fully-closed candle via
    mt5.market_data.get_latest_candles (position 1, never the still-forming bar -- see
    that function's docstring) and wraps it as a canonical snapshot.

    Raises MarketDataError verbatim on any retrieval failure (MT5_NOT_CONNECTED,
    SYMBOL_NOT_FOUND, DATA_MISSING, DUPLICATE_TIMESTAMPS, NON_MONOTONIC_TIMESTAMPS,
    NONFINITE_PRICE, INVALID_OHLC, ...). Callers MUST treat any raised MarketDataError as
    DATA_UNAVAILABLE and must not substitute replay/synthetic data to continue toward a
    READY decision -- see module docstring."""
    candles = get_latest_candles(symbol, timeframe, 1)
    candle = candles[0]
    now_utc = datetime.now(timezone.utc)
    bar_close = _bar_close_time(timeframe, candle.time)
    return MarketSnapshot(
        symbol=symbol,
        timeframe=timeframe,
        source=source,
        market_data_mode=MARKET_DATA_MODE_REAL,
        bar_open_time=candle.time,
        bar_close_time=bar_close,
        market_data_asof=bar_close,
        retrieved_at=now_utc,
        is_closed=True,
        fingerprint=_fingerprint(symbol, timeframe, MARKET_DATA_MODE_REAL, candle),
    )


def from_real_candle(
    symbol: str, timeframe: str, candle: Candle, source: str = "VANTAGE_DEMO_MT5",
    retrieved_at: Optional[datetime] = None,
) -> MarketSnapshot:
    """REAL mode, for a caller that already fetched its own closed candle via a range
    query (e.g. mt5.market_data.get_candles(symbol, timeframe, start, end)) rather than
    get_latest_candles -- this function performs no I/O itself, unlike
    from_mt5_latest_closed above. Exists so a live evaluation loop that already holds the
    exact candle that triggered its decision can wrap THAT candle as REAL provenance
    without a second, potentially-racing live fetch (WP11A: AG_CANONICAL_R2_R4_
    PROPOSAL_PIPELINE_V1, post_asian_pilot/pipeline.py wiring -- "do not reconstruct
    market truth later," i.e. use the original fetched candle, not a fresh query)."""
    now_utc = retrieved_at or datetime.now(timezone.utc)
    bar_close = _bar_close_time(timeframe, candle.time)
    return MarketSnapshot(
        symbol=symbol,
        timeframe=timeframe,
        source=source,
        market_data_mode=MARKET_DATA_MODE_REAL,
        bar_open_time=candle.time,
        bar_close_time=bar_close,
        market_data_asof=bar_close,
        retrieved_at=now_utc,
        is_closed=True,
        fingerprint=_fingerprint(symbol, timeframe, MARKET_DATA_MODE_REAL, candle),
    )


def from_replay_candle(
    symbol: str, timeframe: str, candle: Candle, source: str, retrieved_at: Optional[datetime] = None,
) -> MarketSnapshot:
    """REPLAY mode. `source` must identify the specific replay fixture (e.g. a file path
    or fixture ID) -- never reuses a REAL source label. Caller supplies the candle already
    retrieved from historical_replay/; this function performs no I/O."""
    now_utc = retrieved_at or datetime.now(timezone.utc)
    bar_close = _bar_close_time(timeframe, candle.time)
    return MarketSnapshot(
        symbol=symbol,
        timeframe=timeframe,
        source=source,
        market_data_mode=MARKET_DATA_MODE_REPLAY,
        bar_open_time=candle.time,
        bar_close_time=bar_close,
        market_data_asof=bar_close,
        retrieved_at=now_utc,
        is_closed=True,
        fingerprint=_fingerprint(symbol, timeframe, MARKET_DATA_MODE_REPLAY, candle),
    )


def from_synthetic_candle(
    symbol: str, timeframe: str, candle: Candle, source: str = "SYNTHETIC_GENERATOR",
    retrieved_at: Optional[datetime] = None,
) -> MarketSnapshot:
    """SYNTHETIC mode. For UI development / research fixtures only (e.g.
    web/src/data/marketData.ts's generateRealisticCandles, mirrored here so a Python
    caller that ever needs to tag synthetic data uses the same contract). A snapshot built
    this way must never be treated as REAL by any downstream contract -- WP6's proposal
    formation gate rejects anything but market_data_mode=REAL."""
    now_utc = retrieved_at or datetime.now(timezone.utc)
    bar_close = _bar_close_time(timeframe, candle.time)
    return MarketSnapshot(
        symbol=symbol,
        timeframe=timeframe,
        source=source,
        market_data_mode=MARKET_DATA_MODE_SYNTHETIC,
        bar_open_time=candle.time,
        bar_close_time=bar_close,
        market_data_asof=bar_close,
        retrieved_at=now_utc,
        is_closed=True,
        fingerprint=_fingerprint(symbol, timeframe, MARKET_DATA_MODE_SYNTHETIC, candle),
    )
