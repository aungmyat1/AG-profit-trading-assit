"""historical_data_context() -- swaps the live MT5 data-retrieval calls the frozen
analyzers use for a HistoricalCandleStore lookup at a fixed replay clock time, WITHOUT
touching analyzer semantics (spec section 9: reuse the live engine; differences limited
to data source / clock / execution simulator).

Every consumer module below did `from mt5.market_data import get_latest_candles` (and
some also `get_tick`) at import time, binding the name into ITS OWN module namespace --
patching `mt5.market_data.get_latest_candles` itself would not reach them. So each
bound name is patched individually. `liquidity.affinity` imports locally inside its
function body on every call, so patching the source module (`mt5.market_data`) is
sufficient for it alone; it is patched too, for completeness and to catch any future
top-level import there.

RESEARCH_ASSUMPTION / NOT_STRATEGY_CONTRACT: the synthesized historical Tick uses the
latest closed M1 candle's close price for both bid and ask (spread = 0). This is a
semantic-replay-only stand-in, not a broker-realistic quote -- Stage D (spec sections
29, 63) is where spread/commission/slippage get modeled explicitly.
"""
from __future__ import annotations

import contextlib
from datetime import datetime
from typing import List
from unittest.mock import patch

import MetaTrader5 as _mt5_sdk

from mt5.market_data import MarketDataError, Tick

from .candle_store import HistoricalCandleStore, HistoricalDataError

# Defense-in-depth for the "replay silently falls back to live MT5" bug class found
# this phase (a consumer module's own get_latest_candles/get_tick import was missed
# from _PATCHED_*_TARGETS below). These guard the raw MetaTrader5 SDK functions
# themselves -- patched globally, not per-consumer-module -- so ANY unpatched path
# (present or future) that reaches real MT5 during replay fails loudly instead of
# silently querying (or worse, silently getting no data from) a live terminal.
#
# Deliberately excludes terminal_info/symbol_info/symbol_info_tick/symbol_select:
# EVERY mt5.market_data wrapper (patched or not, e.g. get_candles/get_symbol_meta on
# paths this module doesn't cover, like session-based liquidity levels) calls
# terminal_info() first as its own connectivity check, and -- since replay scripts never
# call mt5.connection.connect() -- it naturally returns None, which each wrapper already
# turns into its own properly-typed exception (MarketDataError/SymbolMetaError) that its
# caller already catches and degrades gracefully on, live or historical. Guarding
# terminal_info() itself would raise a DIFFERENT exception type than what those callers
# expect, turning a harmless "not connected, historical data unavailable for this
# secondary feature" degradation into an unhandled crash -- confirmed by two real
# regressions this session (get_symbol_meta via liquidity_result; get_candles via
# assistant.market_data.session_snapshot via supply_demand.native_zones.session_zone).
# copy_rates_from_pos/copy_rates_range are ONLY reached after terminal_info() has
# already returned non-None (i.e. a REAL live connection exists) -- exactly the
# dangerous case worth guarding, and one with no legitimate caller during replay.
_FORBIDDEN_MT5_SDK_CALLS = ("copy_rates_from_pos", "copy_rates_range")


def _forbidden_mt5_call(name: str):
    def _raise(*_args, **_kwargs):
        raise HistoricalDataError(
            "HISTORICAL_REPLAY_MT5_ACCESS_FORBIDDEN",
            f"MetaTrader5.{name}() was called during historical_data_context -- historical replay "
            "must never touch live MT5. This means a data-access path is missing from "
            "_PATCHED_CANDLE_TARGETS/_PATCHED_TICK_TARGETS.",
        )
    return _raise

_PATCHED_CANDLE_TARGETS = (
    "market_structure.tiers.get_latest_candles",
    "market_structure.analyzer.get_latest_candles",
    "supply_demand.analyzer.get_latest_candles",
    "supply_demand.native_zones.get_latest_candles",
    "liquidity.analyzer.get_latest_candles",
    "daytrading_runtime.conditional_entry_snapshot.get_latest_candles",
    "historical_replay.stage2.get_latest_candles",
    "mt5.market_data.get_latest_candles",  # covers liquidity.affinity's per-call local import
)

_PATCHED_TICK_TARGETS = (
    "supply_demand.native_zones.get_tick",
    "liquidity.analyzer.get_tick",
    "smc_map.builder.get_tick",
    "daytrading_runtime.conditional_entry_snapshot.get_tick",
    "historical_replay.stage2.get_tick",
    "mt5.market_data.get_tick",  # covers liquidity.affinity's per-call local import
)

_PATCHED_RANGE_CANDLE_TARGETS = (
    # Session snapshots need an arbitrary UTC range, while HistoricalCandleStore's
    # replay interface is count/as-of based. Until that completeness seam exists,
    # fail closed here rather than allowing a connected terminal to answer historically.
    "assistant.market_data.get_candles",
)


def _raise_as_market_data_error(exc: HistoricalDataError):
    raise MarketDataError(exc.reason_code, str(exc)) from exc


def _make_get_latest_candles(store: HistoricalCandleStore, as_of: datetime):
    def _get_latest_candles(symbol: str, timeframe: str, count: int) -> List:
        try:
            return store.closed_candles(symbol, timeframe, as_of, count)
        except HistoricalDataError as exc:
            _raise_as_market_data_error(exc)
    return _get_latest_candles


def _make_get_tick(store: HistoricalCandleStore, as_of: datetime):
    def _get_tick(symbol: str) -> Tick:
        try:
            # Finest available granularity for the synthetic quote; falls back to M5
            # if M1 history was not loaded for this symbol.
            try:
                price = store.last_closed_price(symbol, "M1", as_of)
            except HistoricalDataError:
                price = store.last_closed_price(symbol, "M5", as_of)
        except HistoricalDataError as exc:
            _raise_as_market_data_error(exc)
        return Tick(symbol=symbol, time_utc=as_of, bid=price, ask=price, spread_points=0)
    return _get_tick


def _historical_range_unavailable(symbol: str, timeframe: str, start_utc: datetime, end_utc: datetime):
    raise MarketDataError(
        "HISTORICAL_SESSION_DATA_UNAVAILABLE",
        "range-based session candles are not supplied by historical_data_context",
    )


@contextlib.contextmanager
def historical_data_context(store: HistoricalCandleStore, as_of: datetime):
    """Within this context, every frozen analyzer's candle/tick retrieval is redirected
    to `store` as of `as_of` (the replay clock's current knowledge_time). No-lookahead
    is enforced entirely by `HistoricalCandleStore.closed_candles`'s closure check
    (spec sections 7, 51) -- this context manager only performs the substitution."""
    get_candles_fn = _make_get_latest_candles(store, as_of)
    get_tick_fn = _make_get_tick(store, as_of)

    with contextlib.ExitStack() as stack:
        for target in _PATCHED_CANDLE_TARGETS:
            stack.enter_context(patch(target, get_candles_fn))
        for target in _PATCHED_TICK_TARGETS:
            stack.enter_context(patch(target, get_tick_fn))
        for target in _PATCHED_RANGE_CANDLE_TARGETS:
            stack.enter_context(patch(target, _historical_range_unavailable))
        # Applied AFTER the real substitutions above (patch() stacks correctly since
        # get_latest_candles/get_tick above never call the real MetaTrader5 SDK) --
        # HISTORICAL_REPLAY_MT5_ACCESS = FORBIDDEN, enforced globally, not just at the
        # known call sites.
        for name in _FORBIDDEN_MT5_SDK_CALLS:
            stack.enter_context(patch.object(_mt5_sdk, name, side_effect=_forbidden_mt5_call(name)))
        yield
