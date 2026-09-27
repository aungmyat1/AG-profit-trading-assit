"""One-shot, public-only BTCUSDT previous-day sweep observer.

The observer reuses ST_LIQUIDITY_SWEEP_RETEST_V1's closed-candle sweep primitive but
does not run its sizing/research-proposal pipeline. A detected wick rejection is an
early-stage OpportunityCandidate only; it is not a qualified trade or a proposal.
"""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import TYPE_CHECKING, Optional, Sequence

from execution_runtime.bybit_linear_perp_feed import (
    BybitFeedDataError,
    BybitFeedError,
    BybitFeedRequestError,
    BybitFeedStaleData,
    BybitLinearPerpFeed,
    CANONICAL_SYMBOL,
    EXCHANGE_ID,
)
from opportunity.adapter import FunnelProjection, StrategyFunnelAdapter, StrategyObservation
from opportunity.candidate_store import CandidateStore
from opportunity.contracts import (
    MARKET_DATA_MODE_REAL,
    MARKET_DATA_MODE_REPLAY,
    MARKET_DATA_MODE_SYNTHETIC,
    MarketEvent,
    OpportunityCandidate,
)
from opportunity.engine import evaluate_funnel
from opportunity.registry_binding import StrategyBinding
from opportunity.stages import OUTCOME_ACTIVE, STAGE_SETUP_DETECTED
from packages.contracts.v1 import MarketState, SCHEMA_VERSION
if TYPE_CHECKING:
    from strategy_engine.session import Candle

from .constants import (
    DEFAULT_STORE_PATH,
    LOOKBACK_CANDLES,
    STRATEGY_CLASSIFICATION,
    STRATEGY_ID,
    STRATEGY_VERSION,
    SYMBOL,
    TIMEFRAME,
    VENUE,
)


# REAL provenance is granted only to the exact immutable window constructed inside
# scan_live_once after the public feed returns successfully. A caller-supplied flag or
# source string cannot authorize a different window.
_LIVE_FEED_WINDOWS: dict[int, "CryptoMarketWindow"] = {}

_BAR = timedelta(minutes=5)
_DAY_BARS = 24 * 60 // 5
_MAX_CLOSED_BAR_AGE = 3 * _BAR
_VALID_MODES = {MARKET_DATA_MODE_REAL, MARKET_DATA_MODE_REPLAY, MARKET_DATA_MODE_SYNTHETIC}


@dataclass(frozen=True)
class CryptoMarketWindow:
    """Normalized candle window with explicit provenance; tests must label fixtures."""

    candles: tuple[Candle, ...]
    observed_at: datetime
    market_data_mode: str
    source: str
    venue: str = VENUE
    symbol: str = SYMBOL
    timeframe: str = TIMEFRAME
    freshness: str = "LIVE_FRESH"


@dataclass(frozen=True)
class ScannerResult:
    status: str
    marketstate: Optional[MarketState] = None
    candidate: Optional[OpportunityCandidate] = None
    deduplicated: bool = False
    reason_code: Optional[str] = None


@dataclass(frozen=True)
class _SweepHit:
    direction: str
    level_name: str
    level: float
    extreme: float


class ScannerInputError(ValueError):
    def __init__(self, status: str, reason_code: str):
        super().__init__(f"{status}: {reason_code}")
        self.status = status
        self.reason_code = reason_code


def _binding() -> StrategyBinding:
    return StrategyBinding(
        strategy_id=STRATEGY_ID,
        semantic_version=STRATEGY_VERSION,
        engine_id="crypto_opportunity_scanner.previous_day_sweep",
        engine_version="1",
        adapter_id="crypto_opportunity_scanner.funnel_adapter",
        adapter_version="1",
        dispatchable=False,
        supported_symbols=(SYMBOL,),
        supported_timeframes=(TIMEFRAME,),
        lifecycle="RESEARCH",
        opportunity_authority=True,
        proposal_authority=False,
        execution_authority="NONE",
        replay_supported=True,
        live_observation_supported=True,
    )


class _SweepObservationAdapter(StrategyFunnelAdapter):
    strategy_id = STRATEGY_ID
    strategy_version = STRATEGY_VERSION

    def __init__(self, raw_state: dict, context: dict, setup_evidence: dict):
        self._raw_state = raw_state
        self._context = context
        self._setup_evidence = setup_evidence

    def supports(self, event: MarketEvent, binding: StrategyBinding) -> bool:
        return (
            event.symbol == SYMBOL
            and event.market == "CRYPTO"
            and event.venue == VENUE
            and event.timeframe == TIMEFRAME
            and binding.strategy_id == STRATEGY_ID
        )

    def observe(self, event: MarketEvent, previous_state) -> StrategyObservation:
        return StrategyObservation(
            strategy_id=STRATEGY_ID,
            event_id=event.event_id,
            market_data_mode=event.market_data_mode,
            raw_strategy_state=self._raw_state,
        )

    def project(self, observation: StrategyObservation) -> FunnelProjection:
        return FunnelProjection(
            stage=STAGE_SETUP_DETECTED,
            outcome=OUTCOME_ACTIVE,
            reason_codes=("CLOSED_M5_SWEEP_REJECTION_DETECTED",),
            context_evidence=self._context,
            setup_evidence=self._setup_evidence,
        )

    def candidate_geometry(self, observation: StrategyObservation):
        # This detector reports no trade direction, entry, stop, or targets.
        return None


def _aware_utc(value: datetime, field: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ScannerInputError("CLOCK/TIMESTAMP_ERROR", f"{field}_MUST_BE_TIMEZONE_AWARE")
    return value.astimezone(timezone.utc)


def _validate_window(window: CryptoMarketWindow) -> tuple[Candle, ...]:
    if window.symbol != SYMBOL or window.venue != VENUE or window.timeframe != TIMEFRAME:
        raise ScannerInputError("INVALID_RESPONSE", "UNSUPPORTED_MARKET_WINDOW_IDENTITY")
    if not isinstance(window.source, str) or not window.source:
        raise ScannerInputError("INVALID_RESPONSE", "MARKET_DATA_SOURCE_REQUIRED")
    if window.market_data_mode not in _VALID_MODES:
        raise ScannerInputError("INVALID_RESPONSE", "UNKNOWN_MARKET_DATA_MODE")
    if window.market_data_mode == MARKET_DATA_MODE_REAL and window.source != VENUE:
        raise ScannerInputError("INVALID_RESPONSE", "REAL_MODE_REQUIRES_BYBIT_SOURCE")
    if (window.market_data_mode == MARKET_DATA_MODE_REAL
            and _LIVE_FEED_WINDOWS.get(id(window)) is not window):
        raise ScannerInputError("INVALID_RESPONSE", "REAL_MODE_REQUIRES_LIVE_FEED_ENTRYPOINT")
    if window.freshness != "LIVE_FRESH":
        status = window.freshness if window.freshness in {
            "STALE", "VENUE_UNAVAILABLE", "RATE_LIMITED", "INVALID_RESPONSE",
            "CLOCK/TIMESTAMP_ERROR",
        } else "INVALID_RESPONSE"
        raise ScannerInputError(status, "MARKET_WINDOW_NOT_FRESH")
    observed_at = _aware_utc(window.observed_at, "observed_at")
    candles = tuple(window.candles)
    if len(candles) < _DAY_BARS + 1:
        raise ScannerInputError("INVALID_RESPONSE", "INSUFFICIENT_CLOSED_M5_HISTORY")
    previous_time = None
    for candle in candles:
        candle_time = _aware_utc(candle.time, "candle_time")
        if candle_time.second or candle_time.microsecond or candle_time.minute % 5:
            raise ScannerInputError("CLOCK/TIMESTAMP_ERROR", "M5_TIMESTAMP_NOT_ALIGNED")
        if previous_time is not None and candle_time - previous_time != _BAR:
            raise ScannerInputError("INVALID_RESPONSE", "M5_SERIES_NOT_CONTIGUOUS")
        prices = (candle.open, candle.high, candle.low, candle.close)
        volume = () if candle.volume is None else (candle.volume,)
        if any(not isinstance(value, (int, float)) or not math.isfinite(value) for value in prices + volume):
            raise ScannerInputError("INVALID_RESPONSE", "NON_FINITE_CANDLE_VALUE")
        if (min(prices) <= 0 or candle.low > min(candle.open, candle.close)
                or candle.high < max(candle.open, candle.close) or candle.low > candle.high
                or (candle.volume is not None and candle.volume < 0)):
            raise ScannerInputError("INVALID_RESPONSE", "INVALID_CANDLE_OHLC_OR_VOLUME")
        previous_time = candle_time
    latest = _aware_utc(candles[-1].time, "latest_candle_time")
    latest_close = latest + _BAR
    if latest_close > observed_at:
        raise ScannerInputError("INVALID_RESPONSE", "FORMING_CANDLE_REJECTED")
    if observed_at - latest_close > _MAX_CLOSED_BAR_AGE:
        raise ScannerInputError("STALE", "LATEST_CLOSED_CANDLE_EXCEEDS_AGE_LIMIT")
    return candles


def _fingerprint(candles: Sequence[Candle], source: str) -> str:
    payload = {
        "source": source,
        "symbol": SYMBOL,
        "timeframe": TIMEFRAME,
        "candles": [
            [c.time.astimezone(timezone.utc).isoformat(), c.open, c.high, c.low, c.close, c.volume]
            for c in candles
        ],
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _utc_day_bounds(day: date) -> tuple[datetime, datetime]:
    start = datetime.combine(day, time.min, tzinfo=timezone.utc)
    return start, start + timedelta(days=1)


def scan_window(
    window: CryptoMarketWindow,
    *,
    store: Optional[CandidateStore] = None,
) -> ScannerResult:
    """Evaluate explicit fixture/replay evidence; REAL data uses scan_live_once only."""
    if window.market_data_mode == MARKET_DATA_MODE_REAL:
        raise ScannerInputError("INVALID_RESPONSE", "REAL_MODE_REQUIRES_LIVE_FEED_ENTRYPOINT")
    return _scan_window(window, store=store)


def _scan_window(
    window: CryptoMarketWindow,
    *,
    store: Optional[CandidateStore] = None,
) -> ScannerResult:
    """Evaluate a validated window; REAL windows require live-feed-issued identity."""
    candles = _validate_window(window)
    latest = candles[-1]
    latest_open = _aware_utc(latest.time, "latest_candle_time")
    current_day_start, _ = _utc_day_bounds(latest_open.date())
    previous_day_start = current_day_start - timedelta(days=1)
    reference = tuple(
        c for c in candles
        if previous_day_start <= _aware_utc(c.time, "candle_time") < current_day_start
    )
    if len(reference) != _DAY_BARS:
        raise ScannerInputError("INVALID_RESPONSE", "PREVIOUS_UTC_DAY_M5_REFERENCE_INCOMPLETE")
    reference_high = max(c.high for c in reference)
    reference_low = min(c.low for c in reference)
    high_sweep = latest.high > reference_high and latest.close < reference_high
    low_sweep = latest.low < reference_low and latest.close > reference_low
    # A bar that sweeps both sides has no unambiguous observation direction.
    if high_sweep == low_sweep:
        sweep = None
    elif high_sweep:
        sweep = _SweepHit("HIGH_SWEEP", "REF_HIGH", reference_high, latest.high)
    else:
        sweep = _SweepHit("LOW_SWEEP", "REF_LOW", reference_low, latest.low)
    fingerprint = _fingerprint(candles, window.source)
    marketstate = _marketstate(window, latest, sweep)
    if sweep is None:
        return ScannerResult(status="NO_OPPORTUNITY", marketstate=marketstate)

    close_at = latest_open + _BAR
    side = sweep.direction
    event_id = f"CRYPTO_SWEEP_OBSERVATION_{VENUE}_{SYMBOL}_{TIMEFRAME}_{close_at.strftime('%Y%m%dT%H%M%SZ')}_{side}"
    event = MarketEvent(
        event_id=event_id,
        event_type="BAR_CLOSE",
        symbol=SYMBOL,
        market="CRYPTO",
        venue=VENUE,
        timeframe=TIMEFRAME,
        bar_open_time=latest_open,
        bar_close_time=close_at,
        market_data_asof=_aware_utc(window.observed_at, "observed_at"),
        market_data_mode=window.market_data_mode,
        snapshot_fingerprint=fingerprint,
        source=window.source,
    )
    raw_state = {
        "classification": STRATEGY_CLASSIFICATION,
        "observation": "PREVIOUS_UTC_DAY_SWEEP_REJECTION",
        "event_id": event_id,
        "sweep_side": side,
        "source_timestamp": close_at.isoformat(),
        "timeframe": TIMEFRAME,
        "market_data_mode": window.market_data_mode,
        "source_fingerprint": fingerprint,
    }
    adapter = _SweepObservationAdapter(
        raw_state=raw_state,
        context={
            "asset_class": "CRYPTO",
            "classification": STRATEGY_CLASSIFICATION,
            "venue": VENUE,
            "source": window.source,
            "source_timestamp": close_at.isoformat(),
            "observation_timestamp": _aware_utc(window.observed_at, "observed_at").isoformat(),
            "marketstate_semantic_hash": marketstate.semantic_hash,
            "market_data_mode": window.market_data_mode,
            "economic_validation": "NOT_ESTABLISHED",
        },
        setup_evidence={
            "observation": "CLOSED_M5_WICK_CROSSED_PREVIOUS_UTC_DAY_LEVEL_AND_CLOSED_BACK_INSIDE",
            "sweep_side": side,
            "level_name": sweep.level_name,
            "reference_level": sweep.level,
            "sweep_extreme": sweep.extreme,
            "previous_utc_day_start": previous_day_start.isoformat(),
            "previous_utc_day_end": current_day_start.isoformat(),
            "trigger_candle_open_time": latest_open.isoformat(),
            "trigger_candle_close_time": close_at.isoformat(),
            "reference_high": reference_high,
            "reference_low": reference_low,
        },
    )
    binding = _binding()
    probe, _ = evaluate_funnel(event=event, binding=binding, adapter=adapter)
    candidate_store = store or CandidateStore(DEFAULT_STORE_PATH)
    previous = candidate_store.get(probe.candidate_id)
    if previous is not None and previous.market_data_mode != event.market_data_mode:
        raise ScannerInputError("INVALID_RESPONSE", "CANDIDATE_MARKET_DATA_MODE_CONFLICT")
    if previous is None:
        candidate, transition_obj = evaluate_funnel(event=event, binding=binding, adapter=adapter)
    else:
        candidate, transition_obj = evaluate_funnel(
            event=event, binding=binding, adapter=adapter, previous_candidate=previous,
        )
    deduplicated = transition_obj is None
    if transition_obj is not None:
        candidate_store.persist(candidate, transition_obj)
    return ScannerResult(
        status="OPPORTUNITY_UPDATED" if not deduplicated else "UNCHANGED",
        marketstate=marketstate,
        candidate=candidate,
        deduplicated=deduplicated,
    )


def _marketstate(window: CryptoMarketWindow, latest: Candle, sweep: Optional[_SweepHit]) -> MarketState:
    observed_at = _aware_utc(window.observed_at, "observed_at")
    close_at = _aware_utc(latest.time, "latest_candle_time") + _BAR
    age_seconds = max(0.0, (observed_at - close_at).total_seconds())
    event_id = f"CRYPTO_MARKETSTATE_{VENUE}_{SYMBOL}_{close_at.strftime('%Y%m%dT%H%M%SZ')}"
    facts = {
            "symbol": SYMBOL,
            "source": window.source,
            "source_timestamp": close_at.isoformat(),
            "observed_at": observed_at.isoformat(),
            "freshness": {
                "is_fresh": True,
                "age_seconds": age_seconds,
                "as_of": observed_at.isoformat(),
                "closed_bar": True,
            },
            "provenance": {
                "provider": "BYBIT" if window.market_data_mode == MARKET_DATA_MODE_REAL else window.source,
                "feed": "V5_PUBLIC_LINEAR_KLINE" if window.market_data_mode == MARKET_DATA_MODE_REAL else "EXPLICIT_FIXTURE",
                "instrument": SYMBOL,
            },
            "sweep": {
                "detected": sweep is not None,
                "liquidity_side": "BUY_SIDE" if sweep and sweep.direction == "HIGH_SWEEP" else "SELL_SIDE" if sweep else "UNKNOWN",
                "price": sweep.extreme if sweep else latest.close,
                "occurred_at": close_at.isoformat(),
            },
        }
    return MarketState(
        schema_version=SCHEMA_VERSION,
        event_id=event_id,
        created_at=observed_at,
        source=window.source,
        correlation_id=event_id,
        symbol=SYMBOL,
        facts=facts,
    )


def _status_for_feed_error(error: BybitFeedError) -> str:
    reason = error.reason_code.upper()
    message = str(error).upper()
    if isinstance(error, BybitFeedStaleData) or "STALE" in reason:
        return "STALE"
    if "TIMESTAMP" in reason or "CLOCK" in reason:
        return "CLOCK/TIMESTAMP_ERROR"
    if "429" in message or "TOO MANY REQUESTS" in message:
        return "RATE_LIMITED"
    if isinstance(error, BybitFeedDataError):
        return "INVALID_RESPONSE"
    if isinstance(error, BybitFeedRequestError):
        return "VENUE_UNAVAILABLE"
    return "INVALID_RESPONSE"


def scan_live_once(*, store: Optional[CandidateStore] = None) -> ScannerResult:
    """Fetch one bounded public Bybit window and run one scan; never polls or trades."""
    try:
        candles = tuple(BybitLinearPerpFeed().get_latest_candles(SYMBOL, TIMEFRAME, LOOKBACK_CANDLES))
    except BybitFeedError as exc:
        return ScannerResult(status=_status_for_feed_error(exc), reason_code=exc.reason_code)
    window = CryptoMarketWindow(
        candles=candles,
        observed_at=datetime.now(timezone.utc),
        market_data_mode=MARKET_DATA_MODE_REAL,
        source=VENUE,
    )
    _LIVE_FEED_WINDOWS[id(window)] = window
    try:
        return _scan_window(window, store=store)
    except ScannerInputError as exc:
        return ScannerResult(status=exc.status, reason_code=exc.reason_code)
    finally:
        _LIVE_FEED_WINDOWS.pop(id(window), None)
