"""btc_sweep_research.pipeline.run_research_cycle -- the orchestration layer wiring a
CryptoCandleFeed around the EXISTING, untouched SweepRetestRuntime/evaluate_setup (that
engine's own sweep/MSS/retest/target-geometry logic is already covered by
tests/test_liquidity_sweep_retest_strategy.py and is NOT re-tested here). This file tests:
candle-fetch wiring, occurrence-id + ledger recording on qualification, dedup on
re-observation, multi-occurrence collection (remediation Gap 1), and the
strategy-qualification/tradability separation (remediation Gap 2).

Fixture note: the M5 sweep/MSS/retest candle shape below is the same-shape adaptation of
test_liquidity_sweep_retest_strategy.py's own `_btc_high_sweep_sequence` fixture (a HIGH
sweep of a previous-day high, MSS on the 3rd post-sweep candle, retest at +35min),
translated by a fixed price offset so it sits just below whatever PREVIOUS_DAY reference
high this file's own H1 fixture produces (pipeline.py fetches ONE H1 series for BOTH the
H1 trend filter AND the PREVIOUS_DAY reference box -- spec section 2), and by a time
shift so multiple, independent occurrences can be placed within one 13:30-16:00 UTC
activity window without overlapping. market_structure_config uses swing_length=1 (same as
this repo's own engine-level test suite's CFG) so a compact H1/M5 fixture produces real,
detectable swings -- the production default (swing_length=5) needs a much larger real
candle history than a hand-built unit-test fixture can practically provide.
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
from strategy_engine.sweep_retest.models import (
    STATE_ENTRY_READY,
    STATE_SETUP_EXPIRED,
    STATE_WAITING_REFERENCE,
)
from strategy_engine.sweep_retest.profile import filter_previous_day_candles
from strategy_engine.sweep_retest.state_store import SweepRetestStateStore

from btc_sweep_research.ledger import BTCResearchLedger
from btc_sweep_research.pipeline import run_research_cycle

UTC = dt.timezone.utc
NOW = dt.datetime(2026, 1, 5, 16, 5, tzinfo=UTC)  # after the 13:30-16:00 activity window closes
# Compact-fixture market structure config -- same convention as this repo's own
# tests/test_liquidity_sweep_retest_strategy.py::CFG (swing_length=1); the production
# default (swing_length=5) needs a much larger real candle history than a hand-built
# unit-test fixture can practically provide.
TEST_MS_CONFIG = MarketStructureConfig(swing_length=1, close_break=True, default_analysis_count=200)


def _h1_zigzag(cycles=13, down_len=8, up_len=3, down_step=150.0, up_step=60.0, start=50000.0,
                start_time=dt.datetime(2026, 1, 1, tzinfo=UTC)) -> List[Candle]:
    """A bearish (declining) H1 zigzag with long enough legs for market_structure's swing
    detection to find real pivots, and enough total range per UTC day for the
    previous-day reference box to be comfortably wide."""
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


def _c(hour, minute, o, h, l, cl):
    return Candle(time=dt.datetime(2026, 1, 5, hour, minute, tzinfo=UTC), open=o, high=h, low=l, close=cl, volume=1.0)


# (hour_offset_minutes, minute_within_shape) pairs relative to a shape's own start -- a
# HIGH sweep of the previous-day high, MSS on the 3rd post-sweep candle (one intrabar-only
# penetration first), retest on the 4th.
_SHAPE_MINUTES = [0, 5, 10, 15, 20, 25, 30, 35, 40]
_SHAPE_OHLC = [
    (41700, 41710, 41690, 41700),
    (41680, 41685, 41600, 41650),   # swing low candidate
    (41660, 41720, 41655, 41710),   # rally
    (41710, 42150, 41500, 41550),   # SWEEP: high>PDH, close<PDH
    (41550, 41650, 41580, 41630),   # intrabar only
    (41630, 41650, 41610, 41620),   # still above
    (41620, 41625, 41400, 41450),   # closes below swing low -> MSS
    (41450, 41650, 41400, 41500),   # retest
    (41500, 41510, 41300, 41350),
]
# A truncated shape that reaches MSS_CONFIRMED but never retests within entry_ttl_m5_bars
# (3 bars) -> SETUP_EXPIRED. Same sweep/MSS, just no retest candle and enough trailing
# no-retest bars to exhaust the TTL.
_EXPIRING_SHAPE_MINUTES = [0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50]
_EXPIRING_SHAPE_OHLC = _SHAPE_OHLC[:7] + [(41450, 41455, 41440, 41445), (41445, 41448, 41430, 41440),
                                          (41440, 41442, 41425, 41435), (41435, 41438, 41420, 41430)]


def _shape_candles(start_hour: int, start_minute: int, offset: float, minutes=None, ohlc=None) -> List[Candle]:
    minutes = minutes if minutes is not None else _SHAPE_MINUTES
    ohlc = ohlc if ohlc is not None else _SHAPE_OHLC
    base = dt.datetime(2026, 1, 5, start_hour, start_minute, tzinfo=UTC)
    out = []
    for m, (o, h, l, cl) in zip(minutes, ohlc):
        t = base + dt.timedelta(minutes=m)
        out.append(Candle(time=t, open=o + offset, high=h + offset, low=l + offset, close=cl + offset, volume=1.0))
    return out


def _build_fixture(occurrence_starts):
    """(h1_candles, m5_candles) where each (start_hour, start_minute[, minutes, ohlc]) in
    occurrence_starts places one independent HIGH-sweep shape, anchored under the
    PREVIOUS_DAY reference high the H1 fixture itself produces (computed the same way
    pipeline.py computes it: filter_previous_day_candles(h1, NOW))."""
    h1 = _h1_zigzag()
    ref = filter_previous_day_candles(h1, NOW)
    box_high = max(c.high for c in ref)
    offset = box_high - 42000.0
    m5: List[Candle] = []
    for spec in occurrence_starts:
        hour, minute = spec[0], spec[1]
        minutes = spec[2] if len(spec) > 2 else None
        ohlc = spec[3] if len(spec) > 3 else None
        m5 += _shape_candles(hour, minute, offset, minutes, ohlc)
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


def _fresh_runtime_and_guards(tmp_path, suffix=""):
    runtime = SweepRetestRuntime(SweepRetestStateStore(str(tmp_path / f"setup_state{suffix}.json")))
    ledger = BTCResearchLedger(str(tmp_path / f"occurrences{suffix}.json"))
    daily_loss_guard = DailyLossGuard(JsonKeyValueStore(str(tmp_path / f"daily_loss{suffix}.json")), "ST_LIQUIDITY_SWEEP_RETEST_V1")
    open_position_guard = OpenPositionGuard(JsonKeyValueStore(str(tmp_path / f"open_positions{suffix}.json")))
    return runtime, ledger, daily_loss_guard, open_position_guard


def _run(feed, runtime, ledger, daily_loss_guard, open_position_guard, now=NOW):
    return run_research_cycle(
        feed, runtime=runtime, ledger=ledger, daily_loss_guard=daily_loss_guard,
        open_position_guard=open_position_guard, now=now, market_structure_config=TEST_MS_CONFIG,
    )


# --------------------------------------------------------------------------- single occurrence

def test_qualified_setup_reaches_entry_ready_and_records_ledger(tmp_path):
    h1, m5 = _build_fixture([(13, 30)])
    feed = _FixtureFeed(h1, m5)
    runtime, ledger, daily_loss_guard, open_position_guard = _fresh_runtime_and_guards(tmp_path)

    report = _run(feed, runtime, ledger, daily_loss_guard, open_position_guard)

    assert report.container_state is None
    assert len(report.occurrences) == 1
    result = report.occurrences[0]
    assert result.setup_state.state == STATE_ENTRY_READY
    assert result.setup_state.strategy_qualified is True
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
    assert result.proposal.tradability_allowed is True


def test_backfill_ignores_m5_candles_after_observation_date(tmp_path):
    h1, m5 = _build_fixture([(13, 30)])
    future = [Candle(time=c.time + dt.timedelta(days=1), open=c.open, high=c.high,
                     low=c.low, close=c.close, volume=c.volume) for c in m5]
    feed = _FixtureFeed(h1, m5 + future)
    runtime, ledger, daily_loss_guard, open_position_guard = _fresh_runtime_and_guards(tmp_path)

    report = _run(feed, runtime, ledger, daily_loss_guard, open_position_guard)

    assert len(report.occurrences) == 1
    assert report.occurrences[0].trading_day == NOW.date()
    assert report.occurrences[0].setup_state.sweep_time.date() == NOW.date()


def test_reobserving_same_occurrence_does_not_duplicate_ledger_row(tmp_path):
    h1, m5 = _build_fixture([(13, 30)])
    feed = _FixtureFeed(h1, m5)
    runtime, ledger, daily_loss_guard, open_position_guard = _fresh_runtime_and_guards(tmp_path)

    first = _run(feed, runtime, ledger, daily_loss_guard, open_position_guard)
    second = _run(feed, runtime, ledger, daily_loss_guard, open_position_guard)

    assert first.occurrences[0].ledger_new_row is True
    assert second.occurrences[0].ledger_new_row is False
    assert first.occurrences[0].proposal.occurrence_id == second.occurrences[0].proposal.occurrence_id
    assert ledger.count() == 1


def test_no_data_yields_waiting_reference_container_and_no_occurrences(tmp_path):
    feed = _EmptyFeed()
    runtime, ledger, daily_loss_guard, open_position_guard = _fresh_runtime_and_guards(tmp_path)

    report = _run(feed, runtime, ledger, daily_loss_guard, open_position_guard)

    assert report.container_state is not None
    assert report.container_state.state == STATE_WAITING_REFERENCE
    assert report.occurrences == ()
    assert ledger.count() == 0


# --------------------------------------------------------------------- Gap 1: multi-occurrence

def test_two_independent_occurrences_same_day_both_recorded(tmp_path):
    h1, m5 = _build_fixture([(13, 30), (14, 30)])
    feed = _FixtureFeed(h1, m5)
    runtime, ledger, daily_loss_guard, open_position_guard = _fresh_runtime_and_guards(tmp_path)

    report = _run(feed, runtime, ledger, daily_loss_guard, open_position_guard)

    assert len(report.occurrences) == 2
    assert all(o.setup_state.state == STATE_ENTRY_READY for o in report.occurrences)
    ids = {o.proposal.occurrence_id for o in report.occurrences}
    assert len(ids) == 2  # distinct occurrence identities
    assert ledger.count() == 2


def test_three_independent_occurrences_no_hidden_cap(tmp_path):
    h1, m5 = _build_fixture([(13, 30), (14, 20), (15, 10)])
    feed = _FixtureFeed(h1, m5)
    runtime, ledger, daily_loss_guard, open_position_guard = _fresh_runtime_and_guards(tmp_path)

    report = _run(feed, runtime, ledger, daily_loss_guard, open_position_guard)

    assert len(report.occurrences) == 3
    assert all(o.setup_state.state == STATE_ENTRY_READY for o in report.occurrences)
    assert ledger.count() == 3


def test_first_occurrence_expired_does_not_block_second(tmp_path):
    h1, m5 = _build_fixture([
        (13, 30, _EXPIRING_SHAPE_MINUTES, _EXPIRING_SHAPE_OHLC),  # never retests -> SETUP_EXPIRED
        (14, 40),  # independent, fully qualifies
    ])
    feed = _FixtureFeed(h1, m5)
    runtime, ledger, daily_loss_guard, open_position_guard = _fresh_runtime_and_guards(tmp_path)

    report = _run(feed, runtime, ledger, daily_loss_guard, open_position_guard)

    assert len(report.occurrences) == 2
    first, second = report.occurrences
    assert first.setup_state.state == STATE_SETUP_EXPIRED
    assert first.setup_state.strategy_qualified is False
    assert first.proposal is None
    assert second.setup_state.state == STATE_ENTRY_READY
    assert second.proposal is not None
    assert ledger.count() == 1  # only the qualified one


def test_duplicate_suppressed_but_new_later_occurrence_discovered_after_restart(tmp_path):
    h1, m5_first_only = _build_fixture([(13, 30)])
    feed_first = _FixtureFeed(h1, m5_first_only)
    runtime, ledger, daily_loss_guard, open_position_guard = _fresh_runtime_and_guards(tmp_path)

    before_restart = _run(feed_first, runtime, ledger, daily_loss_guard, open_position_guard)
    assert len(before_restart.occurrences) == 1
    assert ledger.count() == 1
    first_occurrence_id = before_restart.occurrences[0].proposal.occurrence_id

    # "Restart": fresh runtime/ledger instances backed by the SAME persisted files.
    runtime_after = SweepRetestRuntime(SweepRetestStateStore(str(tmp_path / "setup_state.json")))
    ledger_after = BTCResearchLedger(str(tmp_path / "occurrences.json"))

    _, m5_both = _build_fixture([(13, 30), (14, 40)])
    feed_both = _FixtureFeed(h1, m5_both)
    after_restart = _run(feed_both, runtime_after, ledger_after, daily_loss_guard, open_position_guard)

    assert len(after_restart.occurrences) == 2
    ids_after = {o.proposal.occurrence_id for o in after_restart.occurrences}
    assert first_occurrence_id in ids_after  # the earlier occurrence, re-discovered, same identity
    assert ledger_after.count() == 2  # the original row plus exactly one new row
    new_rows = [o for o in after_restart.occurrences if o.ledger_new_row]
    assert len(new_rows) == 1
    assert new_rows[0].proposal.occurrence_id != first_occurrence_id


# ------------------------------------------------------------------ Gap 2: guard separation

def test_open_position_guard_blocks_tradability_but_occurrence_still_recorded(tmp_path):
    h1, m5 = _build_fixture([(13, 30)])
    feed = _FixtureFeed(h1, m5)
    runtime, ledger, daily_loss_guard, open_position_guard = _fresh_runtime_and_guards(tmp_path)
    open_position_guard.register_open("some-other-position", "SOME_OTHER_STRATEGY", "EURUSD")

    report = _run(feed, runtime, ledger, daily_loss_guard, open_position_guard)

    assert len(report.occurrences) == 1
    result = report.occurrences[0]
    assert result.setup_state.state == "BLOCKED_OPEN_POSITION"
    assert result.setup_state.strategy_qualified is True  # the opportunity DID exist
    assert result.setup_state.tradability_blocked is True
    assert result.proposal is not None  # research evidence is preserved, not erased
    assert result.proposal.tradability_allowed is False
    assert result.proposal.tradability_block_reason == "BLOCKED_OPEN_POSITION"
    assert result.ledger_new_row is True
    assert ledger.count() == 1


def test_daily_loss_guard_blocks_tradability_but_occurrence_still_recorded(tmp_path):
    h1, m5 = _build_fixture([(13, 30)])
    feed = _FixtureFeed(h1, m5)
    runtime, ledger, daily_loss_guard, open_position_guard = _fresh_runtime_and_guards(tmp_path)
    daily_loss_guard.record_trade_result(dt.date(2026, 1, 5), -1.0)
    daily_loss_guard.record_trade_result(dt.date(2026, 1, 5), -1.0)
    assert daily_loss_guard.is_blocked(dt.date(2026, 1, 5)) is True

    report = _run(feed, runtime, ledger, daily_loss_guard, open_position_guard)

    result = report.occurrences[0]
    assert result.setup_state.state == "BLOCKED_DAILY_LOSS"
    assert result.setup_state.strategy_qualified is True
    assert result.proposal is not None
    assert result.proposal.tradability_allowed is False
    assert ledger.count() == 1


def test_research_occurrence_count_identical_regardless_of_guard_state(tmp_path):
    h1, m5 = _build_fixture([(13, 30), (14, 30)])

    feed_a = _FixtureFeed(h1, m5)
    runtime_a, ledger_a, daily_loss_a, open_position_a = _fresh_runtime_and_guards(tmp_path, "_a")
    report_unblocked = _run(feed_a, runtime_a, ledger_a, daily_loss_a, open_position_a)

    feed_b = _FixtureFeed(h1, m5)
    runtime_b, ledger_b, daily_loss_b, open_position_b = _fresh_runtime_and_guards(tmp_path, "_b")
    open_position_b.register_open("blocker", "SOME_OTHER_STRATEGY", "EURUSD")
    report_blocked = _run(feed_b, runtime_b, ledger_b, daily_loss_b, open_position_b)

    assert len(report_unblocked.occurrences) == len(report_blocked.occurrences) == 2
    assert ledger_a.count() == ledger_b.count() == 2  # research evidence identical either way
    assert all(not o.setup_state.tradability_blocked for o in report_unblocked.occurrences)
    assert all(o.setup_state.tradability_blocked for o in report_blocked.occurrences)
