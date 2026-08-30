"""No-lookahead invariant tests (historical-validation spec sections 7, 51, 54-56).

Covers:
- HistoricalCandleStore.closed_candles enforces bar closure per timeframe (H1, D1).
- historical_data_context correctly redirects a real frozen analyzer
  (supply_demand.native_zones.previous_day_high_low) to historical data, proving the
  SAME live analyzer code path is reused for replay (spec section 9), not a
  reimplementation.
"""
from __future__ import annotations

import datetime as dt

import pytest

from historical_replay import HistoricalCandleStore, HistoricalDataError, historical_data_context
from mt5.market_data import MarketDataError
from strategy_engine.session import Candle

UTC = dt.timezone.utc


def _h1_series(start, n):
    return [Candle(time=start + dt.timedelta(hours=i), open=1.0, high=1.0, low=1.0, close=1.0 + i * 0.0001)
            for i in range(n)]


def _d1_series(start, n):
    return [Candle(time=start + dt.timedelta(days=i), open=1.0, high=1.0 + i * 0.01, low=1.0 - i * 0.01,
                    close=1.0, volume=None) for i in range(n)]


# --------------------------------------------------------------------------- H1 closure

def test_h1_bar_not_visible_before_its_close():
    store = HistoricalCandleStore()
    bar_open = dt.datetime(2026, 1, 5, 10, 0, tzinfo=UTC)  # 10:00-11:00 H1 bar
    store.load_series("EURUSD", "H1", _h1_series(dt.datetime(2026, 1, 5, 0, 0, tzinfo=UTC), 24))

    just_before_close = bar_open + dt.timedelta(minutes=59, seconds=59)
    latest = store.closed_candles("EURUSD", "H1", just_before_close, 1)
    assert latest[0].time < bar_open  # the 10:00 bar itself is NOT yet visible


def test_h1_bar_visible_exactly_at_its_close():
    store = HistoricalCandleStore()
    bar_open = dt.datetime(2026, 1, 5, 10, 0, tzinfo=UTC)
    store.load_series("EURUSD", "H1", _h1_series(dt.datetime(2026, 1, 5, 0, 0, tzinfo=UTC), 24))

    at_close = bar_open + dt.timedelta(hours=1)  # 11:00 -- the bar has now closed
    latest = store.closed_candles("EURUSD", "H1", at_close, 1)
    assert latest[0].time == bar_open


def test_m5_1035_cannot_consume_the_1000_1100_h1_bar():
    """Spec section 51's exact example."""
    store = HistoricalCandleStore()
    store.load_series("EURUSD", "H1", _h1_series(dt.datetime(2026, 1, 5, 0, 0, tzinfo=UTC), 24))
    eval_time = dt.datetime(2026, 1, 5, 10, 35, tzinfo=UTC)
    latest = store.closed_candles("EURUSD", "H1", eval_time, 1)
    assert latest[0].time == dt.datetime(2026, 1, 5, 9, 0, tzinfo=UTC)  # 09:00-10:00, NOT 10:00-11:00


# --------------------------------------------------------------------------- D1 closure

def test_d1_bar_not_visible_before_its_close():
    store = HistoricalCandleStore()
    day_open = dt.datetime(2026, 1, 5, 0, 0, tzinfo=UTC)
    store.load_series("EURUSD", "D1", _d1_series(dt.datetime(2026, 1, 1, 0, 0, tzinfo=UTC), 10))

    mid_day = day_open + dt.timedelta(hours=12)
    latest = store.closed_candles("EURUSD", "D1", mid_day, 1)
    assert latest[0].time < day_open


def test_d1_bar_visible_after_its_close():
    store = HistoricalCandleStore()
    day_open = dt.datetime(2026, 1, 5, 0, 0, tzinfo=UTC)
    store.load_series("EURUSD", "D1", _d1_series(dt.datetime(2026, 1, 1, 0, 0, tzinfo=UTC), 10))

    next_day = day_open + dt.timedelta(days=1)
    latest = store.closed_candles("EURUSD", "D1", next_day, 1)
    assert latest[0].time == day_open


def test_insufficient_candles_before_history_start_raises():
    store = HistoricalCandleStore()
    store.load_series("EURUSD", "D1", _d1_series(dt.datetime(2026, 1, 1, 0, 0, tzinfo=UTC), 3))
    with pytest.raises(HistoricalDataError):
        store.closed_candles("EURUSD", "D1", dt.datetime(2026, 1, 10, tzinfo=UTC), 10)


def test_missing_series_raises_data_missing():
    store = HistoricalCandleStore()
    with pytest.raises(HistoricalDataError):
        store.closed_candles("GBPUSD", "D1", dt.datetime(2026, 1, 10, tzinfo=UTC), 1)


def test_load_series_rejects_duplicate_or_unordered_timestamps():
    store = HistoricalCandleStore()
    bad = [
        Candle(time=dt.datetime(2026, 1, 1, tzinfo=UTC), open=1, high=1, low=1, close=1),
        Candle(time=dt.datetime(2026, 1, 1, tzinfo=UTC), open=1, high=1, low=1, close=1),
    ]
    with pytest.raises(HistoricalDataError):
        store.load_series("EURUSD", "D1", bad)


# --------------------------------------------------------------------------- live-engine reuse (integration)

def test_historical_context_reuses_real_analyzer_previous_day_high_low():
    """Proves the patch reaches the actual frozen analyzer (supply_demand.native_zones),
    not a reimplementation, and respects D1 closure while doing it."""
    from supply_demand.native_zones import previous_day_high_low

    store = HistoricalCandleStore()
    d1 = [
        Candle(time=dt.datetime(2026, 1, 3, 0, 0, tzinfo=UTC), open=1.10, high=1.12, low=1.09, close=1.11),
        Candle(time=dt.datetime(2026, 1, 4, 0, 0, tzinfo=UTC), open=1.11, high=1.15, low=1.10, close=1.14),
        Candle(time=dt.datetime(2026, 1, 5, 0, 0, tzinfo=UTC), open=1.14, high=1.20, low=1.13, close=1.18),
    ]
    store.load_series("EURUSD", "D1", d1)
    store.load_series("EURUSD", "M1", [
        Candle(time=dt.datetime(2026, 1, 5, 11, 59, tzinfo=UTC), open=1.18, high=1.18, low=1.18, close=1.18),
    ])

    # As of Jan 5 12:00 -- Jan 5's D1 bar (opened Jan 5 00:00) has NOT closed yet
    # (closes Jan 6 00:00), so "previous day" must resolve to Jan 4's bar, not Jan 5's.
    with historical_data_context(store, dt.datetime(2026, 1, 5, 12, 0, tzinfo=UTC)):
        result = previous_day_high_low("EURUSD")

    assert result.origin_time == dt.datetime(2026, 1, 4, 0, 0, tzinfo=UTC)
    assert result.high == pytest.approx(1.15)
    assert result.low == pytest.approx(1.10)


def test_historical_context_advances_as_replay_clock_advances():
    from supply_demand.native_zones import previous_day_high_low

    store = HistoricalCandleStore()
    d1 = [
        Candle(time=dt.datetime(2026, 1, 3, 0, 0, tzinfo=UTC), open=1.10, high=1.12, low=1.09, close=1.11),
        Candle(time=dt.datetime(2026, 1, 4, 0, 0, tzinfo=UTC), open=1.11, high=1.15, low=1.10, close=1.14),
        Candle(time=dt.datetime(2026, 1, 5, 0, 0, tzinfo=UTC), open=1.14, high=1.20, low=1.13, close=1.18),
    ]
    store.load_series("EURUSD", "D1", d1)
    store.load_series("EURUSD", "M1", [
        Candle(time=dt.datetime(2026, 1, 6, 11, 59, tzinfo=UTC), open=1.18, high=1.18, low=1.18, close=1.18),
    ])

    # Now Jan 6 12:00 -- Jan 5's D1 bar HAS closed (at Jan 6 00:00), so "previous day"
    # advances to Jan 5.
    with historical_data_context(store, dt.datetime(2026, 1, 6, 12, 0, tzinfo=UTC)):
        result = previous_day_high_low("EURUSD")

    assert result.origin_time == dt.datetime(2026, 1, 5, 0, 0, tzinfo=UTC)


def test_missing_history_surfaces_as_market_data_error_not_historical_error():
    """Analyzers catch mt5.market_data.MarketDataError specifically -- the patch must
    translate HistoricalDataError into that same type so existing fail-closed handling
    in the frozen analyzers works unmodified."""
    from supply_demand.native_zones import previous_day_high_low

    store = HistoricalCandleStore()  # nothing loaded
    with historical_data_context(store, dt.datetime(2026, 1, 6, 12, 0, tzinfo=UTC)):
        result = previous_day_high_low("EURUSD")  # native_zones catches MarketDataError itself

    assert result.reason_codes and result.reason_codes[0] == "DATA_MISSING"


def test_full_conditional_entry_entrypoint_reuses_historical_data_not_live_mt5():
    """Regression test for a real bug found this phase: daytrading_runtime.
    conditional_entry_snapshot -- the actual live entrypoint build_symbol_
    conditional_entry_analysis calls -- imports get_latest_candles/get_tick into ITS
    OWN module namespace too (for D1/H1/M5 candles and current price), not just the
    analyzer modules underneath it. The first patch-target list omitted it, and every
    replay step silently fell back to live MT5 (MT5_NOT_CONNECTED), never touching
    historical data at all. This proves the full entrypoint -- not just one analyzer --
    is reached (spec sections 9, 29, 61: live/replay parity at the actual call site
    replay uses)."""
    from daytrading_runtime.conditional_entry_snapshot import build_symbol_conditional_entry_analysis

    store = HistoricalCandleStore()
    base = dt.datetime(2026, 1, 1, 0, 0, tzinfo=UTC)
    store.load_series("EURUSD", "D1", [
        Candle(time=base + dt.timedelta(days=i), open=1.10, high=1.11, low=1.09, close=1.105) for i in range(70)
    ])
    store.load_series("EURUSD", "H1", [
        Candle(time=base + dt.timedelta(hours=i), open=1.10, high=1.101, low=1.099, close=1.1005) for i in range(60)
    ])
    store.load_series("EURUSD", "M5", [
        Candle(time=base + dt.timedelta(minutes=5 * i), open=1.10, high=1.1005, low=1.0995, close=1.1002)
        for i in range(210)
    ])

    as_of = base + dt.timedelta(hours=2)
    with historical_data_context(store, as_of):
        analysis = build_symbol_conditional_entry_analysis("EURUSD")

    # The regression this guards against: every warning used to be MT5_NOT_CONNECTED
    # (falling through to live MT5) regardless of what historical data was loaded.
    # Any remaining warnings here must be honest data-sufficiency limits of this small
    # synthetic fixture (e.g. INSUFFICIENT_CANDLES for a lookback deeper than 210 bars),
    # never a connection failure.
    assert not any("MT5_NOT_CONNECTED" in w for w in analysis.warnings)


def test_symbol_meta_lookup_degrades_gracefully_not_via_forced_guard():
    """get_symbol_meta() is deliberately NOT in the forbidden-SDK-call list: it's static
    broker contract metadata (tick size etc.), not point-in-time price data, and its
    callers already catch SymbolMetaError and degrade gracefully when disconnected --
    same as live. Regression: an earlier version of the fail-fast guard intercepted
    symbol_info() globally and raised HistoricalDataError instead, which callers don't
    catch, turning a harmless degradation into a crash."""
    from liquidity.analyzer import liquidity_result

    store = HistoricalCandleStore()
    base = dt.datetime(2026, 1, 1, tzinfo=UTC)
    store.load_series("EURUSD", "H1", [
        Candle(time=base + dt.timedelta(hours=i), open=1.10, high=1.101, low=1.099, close=1.1005)
        for i in range(60)
    ])
    with historical_data_context(store, base + dt.timedelta(hours=55)):
        result = liquidity_result("EURUSD", "H1")  # must not raise

    assert result is not None


def test_unpatched_bulk_rate_fetch_fails_fast_not_silently():
    """Defense-in-depth for the same bug class: copy_rates_from_pos/copy_rates_range
    are ONLY reachable after a wrapper's own terminal_info() connectivity check has
    already passed -- i.e. a REAL live connection exists -- so guarding them can never
    collide with the "not connected, degrade gracefully" path every wrapper already
    handles on its own (see terminal_info's exclusion, documented in
    data_source_patch.py). This is the actually-dangerous case: a live terminal
    answering during what should be a fully historical replay."""
    import MetaTrader5 as mt5_sdk

    store = HistoricalCandleStore()
    with historical_data_context(store, dt.datetime(2026, 1, 1, tzinfo=UTC)):
        with pytest.raises(HistoricalDataError, match="HISTORICAL_REPLAY_MT5_ACCESS_FORBIDDEN"):
            mt5_sdk.copy_rates_from_pos("EURUSD", 0, 0, 10)


def test_session_range_path_degrades_without_touching_live_mt5(monkeypatch):
    """A connected terminal must not turn the known historical-session completeness
    gap into a live-data access during replay."""
    import mt5.market_data as market_data_module
    from supply_demand.native_zones import session_zone

    monkeypatch.setattr(market_data_module, "_require_connected", lambda: None)
    monkeypatch.setattr(market_data_module, "_require_symbol", lambda symbol: None)
    monkeypatch.setattr(market_data_module, "_broker_offset_hours", lambda symbol: 0)

    store = HistoricalCandleStore()
    as_of = dt.datetime(2026, 1, 6, 12, 0, tzinfo=UTC)
    with historical_data_context(store, as_of):
        zone = session_zone("EURUSD", "asian", dt.date(2026, 1, 5))

    assert zone.low is None and zone.high is None
    assert zone.reason_codes == ("HISTORICAL_SESSION_DATA_UNAVAILABLE",)
