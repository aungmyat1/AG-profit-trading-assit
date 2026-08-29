"""Deterministic, clock-independent coverage of liquidity_result() end-to-end: session
availability (present vs. legitimately absent), structural levels, PDH/PDL, equal
highs/lows, cross-source deduplication with provenance, empty results, and missing/
invalid data. All dependencies of liquidity.analyzer are monkeypatched with fixed,
explicit timestamps -- no test here depends on wall-clock time, weekday, or a live
broker connection. See tests/test_liquidity.py for the live MT5 smoke test.
"""
from __future__ import annotations

import datetime as dt

import pytest

import liquidity.analyzer as analyzer_mod
from liquidity.config import LiquidityConfig
from liquidity.models import LiquiditySide
from market_structure.models import StructurePoint, StructurePointKind, StructureResult
from mt5.market_data import MarketDataError
from mt5.symbol_resolver import SymbolMeta
from strategy_engine.session import Candle
from supply_demand.models import ZoneDirection, ZoneFamily, ZoneResult, ZoneRole, ZoneStatus

UTC = dt.timezone.utc


def _candle(t, o, h, l, c):
    return Candle(time=t, open=o, high=h, low=l, close=c, volume=1.0)


def _symbol_meta(symbol="EURUSD", tick_size=0.0001, digits=5):
    return SymbolMeta(symbol=symbol, tick_size=tick_size, tick_value=1.0, contract_size=100000.0,
                       volume_min=0.01, volume_max=100.0, volume_step=0.01, digits=digits)


def _empty_structure(symbol="EURUSD", timeframe="M15"):
    return StructureResult(symbol=symbol, timeframe=timeframe, status="NO_STRUCTURE", reason_codes=("NO_STRUCTURE",))


def _empty_zone(symbol="EURUSD", timeframe="M15", family=ZoneFamily.SESSION, reason="SESSION_INCOMPLETE"):
    return ZoneResult(symbol=symbol, timeframe=timeframe, family=family, role=ZoneRole.REFERENCE,
                       direction=ZoneDirection.NONE, status=ZoneStatus.UNKNOWN,
                       source="test", reason_codes=(reason,))


@pytest.fixture
def base_candles():
    """Strictly monotonic highs/lows so equal_levels.py never finds two local extremes
    within tolerance of each other -- an "empty result" fixture must not accidentally
    smuggle in an EQUAL_HIGHS/EQUAL_LOWS cluster the way a flat/repeating fixture would."""
    start = dt.datetime(2026, 1, 5, 0, 0, tzinfo=UTC)
    return [
        _candle(start + dt.timedelta(minutes=15 * m), 1.10 + m * 0.001, 1.1005 + m * 0.001,
                1.0995 + m * 0.001, 1.10 + m * 0.001)
        for m in range(20)
    ]


@pytest.fixture(autouse=True)
def _patch_config(monkeypatch):
    monkeypatch.setattr(analyzer_mod, "load_liquidity_config",
                         lambda: LiquidityConfig(equal_level_tolerance_points=5, local_extremum_window=2, lookback_bars=100))


@pytest.fixture(autouse=True)
def _patch_defaults(monkeypatch, base_candles):
    """Every dependency defaults to 'nothing found' / 'not available' -- individual
    tests override only what they're testing, so an untouched dependency can never
    smuggle in an unrelated liquidity level."""
    monkeypatch.setattr(analyzer_mod, "get_latest_candles", lambda symbol, timeframe, count: base_candles)
    monkeypatch.setattr(analyzer_mod, "get_tick", _raise_market_data_error)
    monkeypatch.setattr(analyzer_mod, "get_symbol_meta", lambda symbol: _symbol_meta(symbol))
    monkeypatch.setattr(analyzer_mod, "analyze_structure", lambda symbol, timeframe: _empty_structure(symbol, timeframe))
    monkeypatch.setattr(analyzer_mod, "session_zone", lambda symbol, name, session_date=None: _empty_zone(symbol))
    monkeypatch.setattr(analyzer_mod, "previous_day_high_low",
                         lambda symbol: _empty_zone(symbol, family=ZoneFamily.PREVIOUS_DAY, reason="DATA_MISSING"))
    monkeypatch.setattr(analyzer_mod, "previous_week_high_low",
                         lambda symbol: _empty_zone(symbol, family=ZoneFamily.PREVIOUS_WEEK, reason="DATA_MISSING"))


def _raise_market_data_error(symbol):
    raise MarketDataError("TICK_UNAVAILABLE", "no live tick in this deterministic test")


# --------------------------------------------------------------------------- empty result

def test_no_candidates_from_any_source_is_no_liquidity_levels():
    result = analyzer_mod.liquidity_result("EURUSD", "M15")
    assert result.status == "NO_LIQUIDITY_LEVELS"
    assert result.levels == ()
    assert result.nearest_buy_side is None
    assert result.nearest_sell_side is None


# --------------------------------------------------------------------------- session availability

@pytest.mark.parametrize("canonical_name,display", [("asian", "ASIAN"), ("london_am", "LONDON"), ("new_york_am", "NEW_YORK")])
def test_each_canonical_session_produces_high_and_low(monkeypatch, canonical_name, display):
    """Session-agnostic regression check (Task 12/16 Fixture A): the same session_zone
    integration path is used for all three canonical sessions -- proving it for one
    (asian, in test_session_available_produces_high_and_low) doesn't prove it for the
    other two since a display-name typo or off-by-one in _SESSION_DISPLAY would only
    show up per-session."""
    def fake_session_zone(symbol, name, session_date=None):
        if name != canonical_name:
            return _empty_zone(symbol)
        return ZoneResult(symbol=symbol, timeframe="M15", family=ZoneFamily.SESSION, role=ZoneRole.REFERENCE,
                           direction=ZoneDirection.NONE, status=ZoneStatus.UNKNOWN, source="test",
                           low=1.0900, high=1.1100, origin_time=dt.datetime(2026, 1, 5, tzinfo=UTC))

    monkeypatch.setattr(analyzer_mod, "session_zone", fake_session_zone)
    result = analyzer_mod.liquidity_result("EURUSD", "M15")

    sources = {l.source for l in result.levels}
    assert f"{display}_HIGH" in sources and f"{display}_LOW" in sources
    high = next(l for l in result.levels if l.source == f"{display}_HIGH")
    low = next(l for l in result.levels if l.source == f"{display}_LOW")
    assert high.price == 1.1100 and low.price == 1.0900


def test_all_sessions_incomplete_is_fixture_b_no_fabricated_levels():
    """Task 16 Fixture B: before any of today's three sessions have closed, none of the
    six session-derived sources may appear -- absence, not a guess, is correct."""
    result = analyzer_mod.liquidity_result("EURUSD", "M15")
    sources = {l.source for l in result.levels}
    for display in ("ASIAN", "LONDON", "NEW_YORK"):
        assert f"{display}_HIGH" not in sources and f"{display}_LOW" not in sources


def test_session_available_produces_high_and_low(monkeypatch, base_candles):
    end = dt.datetime(2026, 1, 5, 6, 0, tzinfo=UTC)

    def fake_session_zone(symbol, name, session_date=None):
        if name != "asian":
            return _empty_zone(symbol)
        return ZoneResult(symbol=symbol, timeframe="M15", family=ZoneFamily.SESSION, role=ZoneRole.REFERENCE,
                           direction=ZoneDirection.NONE, status=ZoneStatus.UNKNOWN, source="test",
                           low=1.0950, high=1.1050, origin_time=dt.datetime(2026, 1, 5, tzinfo=UTC))

    monkeypatch.setattr(analyzer_mod, "session_zone", fake_session_zone)
    result = analyzer_mod.liquidity_result("EURUSD", "M15")

    sources = {l.source for l in result.levels}
    assert "ASIAN_HIGH" in sources and "ASIAN_LOW" in sources
    high = next(l for l in result.levels if l.source == "ASIAN_HIGH")
    low = next(l for l in result.levels if l.source == "ASIAN_LOW")
    assert high.price == 1.1050 and high.side == LiquiditySide.BUY_SIDE
    assert low.price == 1.0950 and low.side == LiquiditySide.SELL_SIDE


def test_session_incomplete_produces_no_candidate_not_a_fabricated_level():
    """The exact scenario that made the old live test flaky: an in-progress session
    must yield NO level for that session, not a guessed/zero/stale one."""
    result = analyzer_mod.liquidity_result("EURUSD", "M15")
    sources = {l.source for l in result.levels}
    assert "ASIAN_HIGH" not in sources and "ASIAN_LOW" not in sources
    assert result.status == "NO_LIQUIDITY_LEVELS"


# --------------------------------------------------------------------------- structural liquidity

def test_structural_swing_high_and_low_reuse_market_structure(monkeypatch):
    structure = StructureResult(
        symbol="EURUSD", timeframe="M15", status="VALID", reason_codes=(), state="STATE_BULLISH",
        latest_swing_high=StructurePoint(dt.datetime(2026, 1, 5, 3, 0, tzinfo=UTC), 1.1100, StructurePointKind.SWING_HIGH),
        latest_swing_low=StructurePoint(dt.datetime(2026, 1, 5, 1, 0, tzinfo=UTC), 1.0900, StructurePointKind.SWING_LOW),
    )
    monkeypatch.setattr(analyzer_mod, "analyze_structure", lambda symbol, timeframe: structure)
    result = analyzer_mod.liquidity_result("EURUSD", "M15")

    high = next(l for l in result.levels if l.source == "SWING_HIGH")
    low = next(l for l in result.levels if l.source == "SWING_LOW")
    assert high.price == 1.1100 and high.side == LiquiditySide.BUY_SIDE
    assert low.price == 1.0900 and low.side == LiquiditySide.SELL_SIDE


def test_structure_not_valid_produces_no_structural_candidate():
    result = analyzer_mod.liquidity_result("EURUSD", "M15")
    sources = {l.source for l in result.levels}
    assert "SWING_HIGH" not in sources and "SWING_LOW" not in sources


# --------------------------------------------------------------------------- PDH/PDL

def test_previous_day_high_low_available(monkeypatch):
    zone = ZoneResult(symbol="EURUSD", timeframe="D1", family=ZoneFamily.PREVIOUS_DAY, role=ZoneRole.REFERENCE,
                       direction=ZoneDirection.NONE, status=ZoneStatus.FRESH, source="test",
                       low=1.0800, high=1.1200, origin_time=dt.datetime(2026, 1, 4, tzinfo=UTC))
    monkeypatch.setattr(analyzer_mod, "previous_day_high_low", lambda symbol: zone)
    result = analyzer_mod.liquidity_result("EURUSD", "M15")

    pdh = next(l for l in result.levels if l.source == "PDH")
    pdl = next(l for l in result.levels if l.source == "PDL")
    assert pdh.price == 1.1200 and pdh.side == LiquiditySide.BUY_SIDE
    assert pdl.price == 1.0800 and pdl.side == LiquiditySide.SELL_SIDE


def test_previous_day_unavailable_produces_no_pdh_pdl():
    result = analyzer_mod.liquidity_result("EURUSD", "M15")
    sources = {l.source for l in result.levels}
    assert "PDH" not in sources and "PDL" not in sources


# --------------------------------------------------------------------------- PWH/PWL

def test_previous_week_high_low_available(monkeypatch):
    zone = ZoneResult(symbol="EURUSD", timeframe="D1", family=ZoneFamily.PREVIOUS_WEEK, role=ZoneRole.REFERENCE,
                       direction=ZoneDirection.NONE, status=ZoneStatus.FRESH, source="test",
                       low=1.0700, high=1.1300, origin_time=dt.datetime(2025, 12, 28, tzinfo=UTC))
    monkeypatch.setattr(analyzer_mod, "previous_week_high_low", lambda symbol: zone)
    result = analyzer_mod.liquidity_result("EURUSD", "M15")

    pwh = next(l for l in result.levels if l.source == "PWH")
    pwl = next(l for l in result.levels if l.source == "PWL")
    assert pwh.price == 1.1300 and pwh.side == LiquiditySide.BUY_SIDE
    assert pwl.price == 1.0700 and pwl.side == LiquiditySide.SELL_SIDE


def test_previous_week_unavailable_produces_no_pwh_pwl():
    result = analyzer_mod.liquidity_result("EURUSD", "M15")
    sources = {l.source for l in result.levels}
    assert "PWH" not in sources and "PWL" not in sources


# --------------------------------------------------------------------------- equal highs/lows

def _equal_level_candles():
    """8 candles built for local_extremum_window=2 (the real config/liquidity.yaml
    default): two high peaks (idx2, idx5) and two low troughs (idx2, idx5) separated by
    a dip/bump wide enough that each is the max/min of its OWN +/-2 neighborhood, then
    close enough to each other (<= tolerance_price) to cluster. A narrower window (as
    used by the equal_levels.py unit tests elsewhere in this suite) would need less
    padding; this fixture is deliberately sized for the analyzer's real default."""
    highs = [1.1000, 1.1005, 1.1050, 1.1010, 1.1010, 1.1051, 1.1005, 1.1000]
    lows = [1.0980, 1.0975, 1.0930, 1.0970, 1.0970, 1.0929, 1.0975, 1.0980]
    start = dt.datetime(2026, 1, 5, 0, 0, tzinfo=UTC)
    return [
        _candle(start + dt.timedelta(minutes=15 * m), 1.10, highs[m], lows[m], 1.10)
        for m in range(8)
    ]


def test_equal_highs_and_lows_detected_from_candles(monkeypatch):
    candles = _equal_level_candles()
    monkeypatch.setattr(analyzer_mod, "get_latest_candles", lambda symbol, timeframe, count: candles)
    result = analyzer_mod.liquidity_result("EURUSD", "M15")

    sources = {l.source for l in result.levels}
    assert "EQUAL_HIGHS" in sources and "EQUAL_LOWS" in sources


def test_missing_symbol_meta_skips_equal_levels_without_crashing(monkeypatch):
    from mt5.symbol_resolver import SymbolMetaError
    monkeypatch.setattr(analyzer_mod, "get_symbol_meta", _raise_symbol_meta_error)
    result = analyzer_mod.liquidity_result("EURUSD", "M15")
    sources = {l.source for l in result.levels}
    assert "EQUAL_HIGHS" not in sources and "EQUAL_LOWS" not in sources


def _raise_symbol_meta_error(symbol):
    from mt5.symbol_resolver import SymbolMetaError
    raise SymbolMetaError("SYMBOL_METADATA_MISSING")


# --------------------------------------------------------------------------- deduplication / provenance

def test_multiple_sources_at_same_price_are_merged_with_provenance(monkeypatch):
    structure = StructureResult(
        symbol="EURUSD", timeframe="M15", status="VALID", reason_codes=(), state="STATE_BULLISH",
        latest_swing_high=StructurePoint(dt.datetime(2026, 1, 5, 3, 0, tzinfo=UTC), 1.1050, StructurePointKind.SWING_HIGH),
    )
    monkeypatch.setattr(analyzer_mod, "analyze_structure", lambda symbol, timeframe: structure)

    def fake_session_zone(symbol, name, session_date=None):
        if name != "asian":
            return _empty_zone(symbol)
        return ZoneResult(symbol=symbol, timeframe="M15", family=ZoneFamily.SESSION, role=ZoneRole.REFERENCE,
                           direction=ZoneDirection.NONE, status=ZoneStatus.UNKNOWN, source="test",
                           low=1.0800, high=1.1050, origin_time=dt.datetime(2026, 1, 5, tzinfo=UTC))

    monkeypatch.setattr(analyzer_mod, "session_zone", fake_session_zone)
    result = analyzer_mod.liquidity_result("EURUSD", "M15")

    highs_at_1105 = [l for l in result.levels if l.side == LiquiditySide.BUY_SIDE and abs(l.price - 1.1050) < 1e-9]
    assert len(highs_at_1105) == 1  # merged into one level, not two
    merged = highs_at_1105[0]
    assert set(merged.sources) == {"SWING_HIGH", "ASIAN_HIGH"}


def test_distinct_prices_are_not_merged(monkeypatch):
    structure = StructureResult(
        symbol="EURUSD", timeframe="M15", status="VALID", reason_codes=(), state="STATE_BULLISH",
        latest_swing_high=StructurePoint(dt.datetime(2026, 1, 5, 3, 0, tzinfo=UTC), 1.1100, StructurePointKind.SWING_HIGH),
    )
    monkeypatch.setattr(analyzer_mod, "analyze_structure", lambda symbol, timeframe: structure)

    def fake_session_zone(symbol, name, session_date=None):
        if name != "asian":
            return _empty_zone(symbol)
        return ZoneResult(symbol=symbol, timeframe="M15", family=ZoneFamily.SESSION, role=ZoneRole.REFERENCE,
                           direction=ZoneDirection.NONE, status=ZoneStatus.UNKNOWN, source="test",
                           low=1.0800, high=1.1050, origin_time=dt.datetime(2026, 1, 5, tzinfo=UTC))

    monkeypatch.setattr(analyzer_mod, "session_zone", fake_session_zone)
    result = analyzer_mod.liquidity_result("EURUSD", "M15")

    buy_side_prices = sorted({round(l.price, 4) for l in result.levels if l.side == LiquiditySide.BUY_SIDE})
    assert buy_side_prices == [1.1050, 1.1100]
    for level in result.levels:
        assert level.sources == (level.source,)  # unmerged levels: provenance is just themselves


# --------------------------------------------------------------------------- symbol digits / tolerance

def test_different_symbol_tick_size_changes_equal_level_tolerance(monkeypatch):
    highs = [150.00, 150.05, 150.50, 150.10, 150.10, 150.51, 150.05, 150.00]
    lows = [149.80, 149.75, 149.30, 149.70, 149.70, 149.29, 149.75, 149.80]
    start = dt.datetime(2026, 1, 5, 0, 0, tzinfo=UTC)
    candles = [
        _candle(start + dt.timedelta(minutes=15 * m), 150.00, highs[m], lows[m], 150.00)
        for m in range(8)
    ]
    monkeypatch.setattr(analyzer_mod, "get_latest_candles", lambda symbol, timeframe, count: candles)
    monkeypatch.setattr(analyzer_mod, "get_symbol_meta", lambda symbol: _symbol_meta(symbol, tick_size=0.01, digits=3))
    result = analyzer_mod.liquidity_result("USDJPY", "M15")

    sources = {l.source for l in result.levels}
    assert "EQUAL_HIGHS" in sources and "EQUAL_LOWS" in sources


# --------------------------------------------------------------------------- invalid/missing candles

def test_market_data_error_fails_closed(monkeypatch):
    def fail(symbol, timeframe, count):
        raise MarketDataError("INSUFFICIENT_CANDLES", "not enough candles in this deterministic test")

    monkeypatch.setattr(analyzer_mod, "get_latest_candles", fail)
    result = analyzer_mod.liquidity_result("EURUSD", "M15")
    assert result.status == "INSUFFICIENT_CANDLES"
    assert result.levels == ()
