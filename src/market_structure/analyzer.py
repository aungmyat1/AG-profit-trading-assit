"""Public entry point: analyze_structure(). Only this module (plus smc_adapter.py) may
import smartmoneyconcepts or mt5 -- callers (assistant, scripts) go through this.

MT5 -> Market Data Adapter (mt5.market_data) -> canonical Candle -> pandas frame ->
smartmoneyconcepts (smc_adapter.py) -> project-owned StructureResult.

Uses only CLOSED candles (mt5.market_data.get_latest_candles already excludes the
still-forming bar) -- a swing/BOS/CHOCH computed against a bar whose high/low/close can
still change would be a moving target.
"""
from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version as _pkg_version
from typing import Optional

from mt5.market_data import MarketDataError, get_latest_candles

from .config import load_market_structure_config
from .models import STATE_BEARISH, STATE_BULLISH, STATE_UNDEFINED, MarketStructureConfig, StructurePoint, StructureResult
from .smc_adapter import (
    StructureLibraryError,
    StructureOutputInvalid,
    all_breaks,
    candles_to_dataframe,
    latest_swings_and_breaks,
    previous_high_low,
)

_DERIVED_FEATURE_VERSION = "MARKET_STRUCTURE_ANALYZER_TD8B_V1"


def _structure_cache_key(symbol, timeframe, candles, count, fetch_count, config):
    """Use the actual fetched population, plus replay dataset and clock when present."""
    from historical_replay.data_source_patch import active_replay_identity
    from historical_replay.dataset_identity import compute_candle_series_fingerprint
    from shared_cache.derived_fact_cache import build_key

    replay = active_replay_identity(symbol, timeframe)
    source = f"REPLAY:{replay[0]}" if replay else "LIVE_MT5"
    visible = compute_candle_series_fingerprint(symbol, timeframe, candles)
    boundary = replay[1].isoformat() if replay else "LIVE_CURRENT"
    return build_key(
        source_dataset_identity=source, symbol=symbol, timeframe=timeframe,
        closed_bar_identity=f"{candles[-1].time.isoformat()}|{boundary}|{visible}",
        authority_definition_id="SMC_MARKET_STRUCTURE_V1",
        feature_version=_DERIVED_FEATURE_VERSION,
        parameters=(("count", count), ("fetch_count", fetch_count),
                    ("swing_length", config.swing_length), ("close_break", config.close_break),
                    ("default_analysis_count", config.default_analysis_count),
                    ("smc_version", _smc_version())),
    )

_PREVIOUS_HL_TIMEFRAME = {"M1": "15m", "M5": "15m", "M15": "1H", "M30": "4H", "H1": "1D", "H4": "1D", "D1": "1W"}


def _smc_version() -> Optional[str]:
    try:
        return _pkg_version("smartmoneyconcepts")
    except PackageNotFoundError:
        return None


def analyze_structure(
    symbol: str,
    timeframe: str,
    count: Optional[int] = None,
    config: Optional[MarketStructureConfig] = None,
) -> StructureResult:
    config = config or load_market_structure_config()
    count = count or config.default_analysis_count

    # Warm-up derived from the algorithm: swing_highs_lows needs swing_length candles of
    # forward context to confirm a point, and bos_choch needs >=4 confirmed swing points
    # before it can emit a first event. This is a documented heuristic, not a proof --
    # too little history degrades to fewer/no confirmed events, which the empty-result
    # paths below already report honestly (NO_CONFIRMED_SWINGS) rather than guessing.
    warmup_bars = max(config.swing_length * 20, 100)
    fetch_count = count + warmup_bars

    try:
        candles = get_latest_candles(symbol, timeframe, fetch_count)
    except MarketDataError as exc:
        return StructureResult(symbol=symbol, timeframe=timeframe, status="MARKET_DATA_INVALID",
                                reason_codes=(exc.reason_code,))

    if len(candles) < warmup_bars:
        return StructureResult(symbol=symbol, timeframe=timeframe, status="INSUFFICIENT_STRUCTURE_HISTORY",
                                reason_codes=("INSUFFICIENT_STRUCTURE_HISTORY",),
                                closed_candle_count=len(candles), config=config)

    # Cache failure is never market-fact authority: recompute on lookup failure.
    cache_key = None
    try:
        from shared_cache import derived_fact_cache
        cache_key = _structure_cache_key(symbol, timeframe, candles, count, fetch_count, config)
        cached = derived_fact_cache.get(cache_key)
        if cached is not None:
            return cached
    except Exception:
        cache_key = None

    df = candles_to_dataframe(candles)

    try:
        latest = latest_swings_and_breaks(df, config.swing_length, config.close_break)
    except StructureLibraryError as exc:
        return StructureResult(symbol=symbol, timeframe=timeframe, status="STRUCTURE_LIBRARY_ERROR",
                                reason_codes=(str(exc),), closed_candle_count=len(candles), config=config)
    except StructureOutputInvalid as exc:
        return StructureResult(symbol=symbol, timeframe=timeframe, status="STRUCTURE_OUTPUT_INVALID",
                                reason_codes=(str(exc),), closed_candle_count=len(candles), config=config)

    prev_high, prev_low = None, None
    try:
        prev_high, prev_low = previous_high_low(df, _PREVIOUS_HL_TIMEFRAME.get(timeframe, "1D"))
    except (StructureLibraryError, StructureOutputInvalid):
        pass  # previous-high/low is supplementary reference data; its failure doesn't invalidate the rest

    reason_codes = []
    if latest["latest_bos"] is None and latest["latest_choch"] is None:
        reason_codes.append("NO_CONFIRMED_STRUCTURE_BREAK")
    if latest["latest_swing_high"] is None and latest["latest_swing_low"] is None:
        reason_codes.append("NO_CONFIRMED_SWINGS")

    state = _structure_state(latest["latest_bos"], latest["latest_choch"])

    result = StructureResult(
        symbol=symbol, timeframe=timeframe, status="VALID", reason_codes=tuple(reason_codes),
        state=state,
        latest_swing_high=latest["latest_swing_high"], latest_swing_low=latest["latest_swing_low"],
        latest_bos=latest["latest_bos"], latest_choch=latest["latest_choch"],
        previous_high=prev_high, previous_low=prev_low,
        broker_resolved_symbol=symbol,
        data_start_utc=candles[0].time, data_end_utc=candles[-1].time,
        closed_candle_count=len(candles), config=config, smc_version=_smc_version(),
    )
    if cache_key is not None:
        try:
            derived_fact_cache.put(cache_key, result)
        except Exception:
            pass  # successful market fact still takes precedence over cache storage
    return result


def structural_breaks_for_candles(candles, config: Optional[MarketStructureConfig] = None) -> "list[StructurePoint]":
    """ALL confirmed BOS/CHOCH events for an ALREADY-FETCHED candle list (not a fresh
    MT5 fetch) -- lets a caller (e.g. supply_demand/ob_contract.py) compute breaks over
    the EXACT SAME candle set it's using for other purposes, so positions/times line up.
    Returns [] on any structure-library failure rather than raising -- callers treat an
    empty list the same as "no matching structure event found"."""
    config = config or load_market_structure_config()
    if not candles:
        return []
    df = candles_to_dataframe(candles)
    try:
        return all_breaks(df, config.swing_length, config.close_break)
    except (StructureLibraryError, StructureOutputInvalid):
        return []


def _structure_state(latest_bos, latest_choch) -> str:
    """Deterministic rule: whichever of the latest BOS/CHOCH happened most recently
    (by confirmation time) sets the state. Neither present -> UNDEFINED. This is
    deliberately the ONLY rule -- no RANGE state, because smc gives no objective range
    signal to derive one from; that would be invented bias, not a defined rule. This is
    unrelated to strategy_engine's session-specific TREND/RANGE regime call."""
    candidates = [p for p in (latest_bos, latest_choch) if p is not None]
    if not candidates:
        return STATE_UNDEFINED
    latest = max(candidates, key=lambda p: p.time_utc)
    is_bullish = "BULLISH" in latest.kind.value
    return STATE_BULLISH if is_bullish else STATE_BEARISH
