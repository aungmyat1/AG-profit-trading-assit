"""btc_sweep_research.pipeline.run_research_cycle -- the NEW orchestration layer wiring a
CryptoCandleFeed around the EXISTING, untouched SweepRetestRuntime/evaluate_setup (that
engine's own sweep/MSS/retest/target-geometry logic is already covered by 638 lines in
tests/test_liquidity_sweep_retest_strategy.py and is NOT re-tested here). This file only
tests: candle-fetch wiring, occurrence-id + ledger recording on ENTRY_READY, dedup on
re-observation, and the guards being reachable.

Fixture note: the M5 sweep/MSS/retest candle shape below is the same-shape adaptation of
test_liquidity_sweep_retest_strategy.py's own `_btc_high_sweep_sequence` fixture (a HIGH
sweep of a previous-day high, MSS on the 3rd post-sweep candle, retest at 14:05),
translated by a fixed offset so it sits just below whatever PREVIOUS_DAY reference high
this file's own H1 fixture produces (pipeline.py fetches ONE H1 series for BOTH the H1
trend filter AND the PREVIOUS_DAY reference box -- spec section 2 -- so, unlike the
engine-level test's two independent candle lists, this file's H1 fixture must itself
contain the previous-day reference window). market_structure_config uses swing_length=1
(same as this repo's own engine-level test suite's CFG) so a compact 96-candle H1 fixture
and a 9-candle M5 fixture produce real, detectable swings -- the production default
(swing_length=5, via load_market_structure_config()) is designed for a live feed's much
larger real candle history, not a hand-built unit-test fixture.
"""
from __future__ import annotations

import datetime as dt
from typing import List

from execution.daily_loss_guard import DailyLossGuard
from execution.position_guard import OpenPositionGuard
from market_structure.models import MarketStructureConfig
from runtime_state.store import JsonKeyValueStore
from strategy_engine.session import Candle
from strategy_engine.sweep_retest.engine import SweepRetestRuntime
from strategy_engine.sweep_retest.models import STATE_ENTRY_READY, STATE_WAITING_REFERENCE
from strategy_engine.sweep_retest.profile import filter_previous_day_candles
from strategy_engine.sweep_retest.state_store import SweepRetestStateStore

from btc_sweep_research.ledger import BTCResearchLedger
from btc_sweep_research.pipeline import run_research_cycle

UTC = dt.timezone.utc
NOW = dt.datetime(2026, 1, 5, 14, 15, tzinfo=UTC)
# Compact-fixture market structure config -- same convention as this repo's own
# tests/test_liquidity_sweep_retest_strategy.py::CFG (swing_length=1); the production
# default (swing_length=5) needs a much larger real candle history than a hand-built
# unit-test fixture can practically provide.
TEST_MS_CONFIG = MarketStructureConfig(swing_length=1, close_break=True, default_analysis_count=200)


def _h1_zigzag(cycles=13, down_len=8, up_len=3, down_step=150.0, up_step=60.0, start=50000.0,
                start_time=dt.datetime(2026, 1, 1, tzinfo=UTC)) -> List[Candle]:
    """A bearish (declining) H1 zigzag with long enough legs (8 down-candles, 3 up-candles
    per cycle) for market_structure's swing detection to find real pivots, and enough
    total range per UTC day for the previous-day reference box to be comfortably wide
    (spec: strict UTC previous-day box, no separate synthetic reference is invented)."""
    price = start
    out, t = [], start_time
    for _ in range(cycles):
        for _ in range(down_len):
            price -= down_step
            out.append(Candle(time=t, open=price, high=price + 5, low=price - 5, close=price, volume=1.0))
            t += dt.timedelta(hours=1)
        for _ in range(up_len):
            price += up_step
            out.append(Candle(time=t, open=price, high=price + 5, low=price - 5, close=price, volume=1.0))
            t += dt.timedelta(hours=1)
    return [c for c in out if c.time < dt.datetime(2026, 1, 5, 0, 0, tzinfo=UTC)]


def _c(day, hour, minute, o, h, l, cl):
    return Candle(time=dt.datetime(2026, 1, day, hour, minute, tzinfo=UTC), open=o, high=h, low=l, close=cl, volume=1.0)


_M5_RAW_HIGH_SWEEP = [
    # Same shape as test_liquidity_sweep_retest_strategy.py::_btc_high_sweep_sequence,
    # anchored to a PDH of 42000.0 -- translated by `off` below to sit just under
    # whichever previous-day high this file's own H1 fixture actually produces.
    (5, 13, 30, 41700, 41710, 41690, 41700),
    (5, 13, 35, 41680, 41685, 41600, 41650),   # swing low candidate
    (5, 13, 40, 41660, 41720, 41655, 41710),   # rally
    (5, 13, 45, 41710, 42150, 41500, 41550),   # SWEEP: high>42000, close<42000
    (5, 13, 50, 41550, 41650, 41580, 41630),   # intrabar only
    (5, 13, 55, 41630, 41650, 41610, 41620),   # still above
    (5, 14, 0, 41620, 41625, 41400, 41450),    # closes below swing low -> MSS
    (5, 14, 5, 41450, 41650, 41400, 41500),    # retest
    (5, 14, 10, 41500, 41510, 41300, 41350),
]


def _m5_high_sweep_sequence(offset: float) -> List[Candle]:
    return [_c(day, hour, minute, o + offset, h + offset, l + offset, cl + offset)
            for day, hour, minute, o, h, l, cl in _M5_RAW_HIGH_SWEEP]


def _build_fixture():
    """Returns (h1_candles, m5_candles) where the M5 HIGH-sweep sequence is anchored
    exactly under the PREVIOUS_DAY reference high the H1 fixture itself produces (computed
    the same way pipeline.py computes it: filter_previous_day_candles(h1, NOW))."""
    h1 = _h1_zigzag()
    ref = filter_previous_day_candles(h1, NOW)
    box_high = max(c.high for c in ref)
    offset = box_high - 42000.0
    m5 = _m5_high_sweep_sequence(offset)
    return h1, m5


class _FixtureFeed:
    def __init__(self, h1_candles, m5_candles):
        self._h1 = h1_candles
        self._m5 = m5_candles

    def get_latest_candles(self, symbol, timeframe, count):
        if timeframe == "H1":
            return list(self._h1)
        if timeframe == "M5":
            return list(self._m5)
        raise ValueError(f"unexpected timeframe {timeframe!r}")


class _EmptyFeed:
    def get_latest_candles(self, symbol, timeframe, count):
        return []


def _fresh_runtime_and_guards(tmp_path):
    runtime = SweepRetestRuntime(SweepRetestStateStore(str(tmp_path / "setup_state.json")))
    ledger = BTCResearchLedger(str(tmp_path / "occurrences.json"))
    daily_loss_guard = DailyLossGuard(JsonKeyValueStore(str(tmp_path / "daily_loss.json")), "ST_LIQUIDITY_SWEEP_RETEST_V1")
    open_position_guard = OpenPositionGuard(JsonKeyValueStore(str(tmp_path / "open_positions.json")))
    return runtime, ledger, daily_loss_guard, open_position_guard


def test_qualified_setup_reaches_entry_ready_and_records_ledger(tmp_path):
    h1, m5 = _build_fixture()
    feed = _FixtureFeed(h1, m5)
    runtime, ledger, daily_loss_guard, open_position_guard = _fresh_runtime_and_guards(tmp_path)

    result = run_research_cycle(
        feed, runtime=runtime, ledger=ledger, daily_loss_guard=daily_loss_guard,
        open_position_guard=open_position_guard, now=NOW, market_structure_config=TEST_MS_CONFIG,
    )

    assert result.setup_state.state == STATE_ENTRY_READY
    assert result.setup_state.direction == "SHORT"
    assert result.proposal is not None
    assert result.ledger_new_row is True
    assert result.proposal.occurrence_id.startswith("BTC-OCC-")
    assert ledger.has(result.proposal.occurrence_id)
    assert result.proposal.execution_domain == "CRYPTO_RESEARCH"
    assert result.proposal.execution_authority == "DISABLED"
    assert result.proposal.authority == "RESEARCH_ONLY"
    assert result.proposal.exchange == "BINANCE_USDT_M_PERP"
    assert result.proposal.instrument == "BTCUSDT"
    assert result.proposal.estimated_fees > 0
    assert result.proposal.RR is not None and result.proposal.RR >= 1.5
    assert result.proposal.expiry is not None
    assert result.proposal.reference_day == dt.date(2026, 1, 4)


def test_reobserving_same_occurrence_does_not_duplicate_ledger_row(tmp_path):
    h1, m5 = _build_fixture()
    feed = _FixtureFeed(h1, m5)
    runtime, ledger, daily_loss_guard, open_position_guard = _fresh_runtime_and_guards(tmp_path)

    first = run_research_cycle(
        feed, runtime=runtime, ledger=ledger, daily_loss_guard=daily_loss_guard,
        open_position_guard=open_position_guard, now=NOW, market_structure_config=TEST_MS_CONFIG,
    )
    second = run_research_cycle(
        feed, runtime=runtime, ledger=ledger, daily_loss_guard=daily_loss_guard,
        open_position_guard=open_position_guard, now=NOW, market_structure_config=TEST_MS_CONFIG,
    )

    assert first.ledger_new_row is True
    assert second.ledger_new_row is False
    assert first.proposal.occurrence_id == second.proposal.occurrence_id
    assert ledger.count() == 1


def test_no_data_yields_waiting_reference_and_no_proposal(tmp_path):
    feed = _EmptyFeed()
    runtime, ledger, daily_loss_guard, open_position_guard = _fresh_runtime_and_guards(tmp_path)

    result = run_research_cycle(
        feed, runtime=runtime, ledger=ledger, daily_loss_guard=daily_loss_guard,
        open_position_guard=open_position_guard, now=NOW, market_structure_config=TEST_MS_CONFIG,
    )

    assert result.setup_state.state == STATE_WAITING_REFERENCE
    assert result.proposal is None
    assert result.ledger_new_row is False
    assert ledger.count() == 0


def test_open_position_guard_blocks_before_any_candle_work(tmp_path):
    h1, m5 = _build_fixture()
    feed = _FixtureFeed(h1, m5)
    runtime, ledger, daily_loss_guard, open_position_guard = _fresh_runtime_and_guards(tmp_path)
    open_position_guard.register_open("some-other-position", "SOME_OTHER_STRATEGY", "EURUSD")

    result = run_research_cycle(
        feed, runtime=runtime, ledger=ledger, daily_loss_guard=daily_loss_guard,
        open_position_guard=open_position_guard, now=NOW, market_structure_config=TEST_MS_CONFIG,
    )

    assert result.setup_state.state == "BLOCKED_OPEN_POSITION"
    assert result.proposal is None
    assert ledger.count() == 0
