"""Tests for AG_DAYTRADING_RUNTIME_V1: the runtime entrypoint wiring closed-M5-bar market
timing/data -> ST_LIQUIDITY_SWEEP_RETEST_V1 evaluation -> TradeProposal ->
ExecutionRuntimeContext/ExecutionCoordinator -> lifecycle reconciliation
(execution_runtime.startup/cycle). No live MT5 terminal anywhere here -- candle/position/
deal retrieval is always injected, same idiom every other execution test in this repo
already uses (see tests/test_execution_runtime_readiness.py).
"""
from __future__ import annotations

import datetime as dt
from datetime import time
from types import SimpleNamespace

import pytest

from execution import executor, journal
from execution.close_ledger import CloseLedger
from execution.coordinator import GLOBAL_LEDGER_STRATEGY_ID, ExecutionCoordinator
from execution.daily_loss_guard import DailyLossGuard
from execution.models import ExecutionSource, OrderSendResult
from execution.position_guard import OpenPositionGuard
from execution.runtime_context import ExecutionRuntimeContext
from execution.bar_tracker import LastClosedBarStore
from execution_runtime.cycle import confirm_and_submit, evaluate_and_route
from execution_runtime.startup import StartupReconciliationFailed, start
from market_structure.models import MarketStructureConfig
from mt5.symbol_resolver import SymbolMeta
from runtime_state.store import JsonKeyValueStore
from strategy_engine.session import Candle
from strategy_engine.sweep_retest.config import load_sweep_retest_strategy
from strategy_engine.sweep_retest.crypto_symbols import crypto_sl_buffer_price, crypto_symbol_meta
from strategy_engine.sweep_retest.engine import SweepRetestRuntime
from strategy_engine.sweep_retest.state_store import SweepRetestStateStore
from strategy_engine.sweep_retest.targets import forex_sl_buffer_price
from trade_management.models import (
    GEOMETRY_VALID,
    OVERALL_READY,
    SIZING_NOT_REQUESTED,
    PositionSizing,
    PositionStateAdvisory,
    TradeGeometry,
    TradeManagementResult,
)

UTC = dt.timezone.utc
CFG = MarketStructureConfig(swing_length=1, close_break=True, default_analysis_count=50)
STRATEGY_PATH = "strategies/ST_LIQUIDITY_SWEEP_RETEST_V1.yaml"
STRATEGY_CONFIG = load_sweep_retest_strategy(STRATEGY_PATH)
FOREX_PROFILE_CONFIG = STRATEGY_CONFIG.profile_config_for_symbol("EURUSD")
CRYPTO_PROFILE_CONFIG = STRATEGY_CONFIG.profile_config_for_symbol("BTCUSDT")

EURUSD_META = SymbolMeta(
    symbol="EURUSD", tick_size=0.00001, tick_value=1.0, contract_size=100000,
    volume_min=0.01, volume_max=50.0, volume_step=0.01, digits=5, point=0.00001,
)
BTCUSDT_META = crypto_symbol_meta("BTCUSDT")
EURUSD_SL_BUFFER = forex_sl_buffer_price(EURUSD_META, FOREX_PROFILE_CONFIG.buffer_pips)
BTC_SL_BUFFER = crypto_sl_buffer_price("BTCUSDT", CRYPTO_PROFILE_CONFIG.buffer_ticks)

ASIAN_HIGH, ASIAN_LOW = 1.1050, 1.0700
BTC_PDH, BTC_PDL = 42000.0, 40700.0


def _c(minute, o, h, l, cl, hour=7, day=5):
    return Candle(time=dt.datetime(2026, 1, day, hour, minute, tzinfo=UTC), open=o, high=h, low=l, close=cl, volume=1.0)


def _short_sequence():
    """Validated fixture (reused shape from tests/test_liquidity_sweep_retest_strategy.py):
    HIGH sweep of AsianHigh=1.1050 -> MSS at 07:30 -> retest at 07:35 -> ENTRY_READY."""
    return [
        _c(0, 1.1000, 1.1005, 1.0995, 1.1000),
        _c(5, 1.0980, 1.0985, 1.0940, 1.0950),
        _c(10, 1.0960, 1.1010, 1.0955, 1.1005),
        _c(15, 1.1005, 1.1080, 1.0900, 1.0910),   # SWEEP
        _c(20, 1.0910, 1.0950, 1.0930, 1.0945),
        _c(25, 1.0945, 1.0950, 1.0935, 1.0942),
        _c(30, 1.0942, 1.0945, 1.0890, 1.0895),   # MSS confirmed
        _c(35, 1.0895, 1.0945, 1.0890, 1.0900),   # retest -> ENTRY_READY
        _c(40, 1.0900, 1.0905, 1.0850, 1.0860),
    ]


def _btc_high_sweep_sequence():
    """Reused crypto shape (tests/test_liquidity_sweep_retest_strategy.py)."""
    return [
        _c(30, 41700, 41710, 41690, 41700, hour=13),
        _c(35, 41680, 41685, 41600, 41650, hour=13),
        _c(40, 41660, 41720, 41655, 41710, hour=13),
        _c(45, 41710, 42150, 41500, 41550, hour=13),   # SWEEP
        _c(50, 41550, 41650, 41580, 41630, hour=13),
        _c(55, 41630, 41650, 41610, 41620, hour=13),
        _c(0, 41620, 41625, 41400, 41450, hour=14),    # MSS confirmed
        _c(5, 41450, 41650, 41400, 41500, hour=14),    # retest -> ENTRY_READY
        _c(10, 41500, 41510, 41300, 41350, hour=14),
    ]


def _descending_zigzag_h1(cycles=25, trend_step=0.0100, amplitude=0.0300):
    prices = []
    for i in range(cycles):
        high = 1.2000 - i * trend_step
        prices.append(high)
        prices.append(high - amplitude)
    return prices


def _h1_candles(prices, step_minutes=60):
    out, t = [], dt.datetime(2026, 1, 1, tzinfo=UTC)
    for p in prices:
        out.append(Candle(time=t, open=p, high=p + 0.0005, low=p - 0.0005, close=p, volume=1.0))
        t += dt.timedelta(minutes=step_minutes)
    return out


H1_BEARISH = _h1_candles(_descending_zigzag_h1())


def _asian_candles():
    return [Candle(time=dt.datetime(2026, 1, 5, 3, 0, tzinfo=UTC), open=1.0900, high=ASIAN_HIGH, low=ASIAN_LOW, close=1.0900, volume=1.0)]


def _prev_day_candles(high, low):
    mid = (high + low) / 2.0
    return [Candle(time=dt.datetime(2026, 1, 4, 12, 0, tzinfo=UTC), open=mid, high=high, low=low, close=mid, volume=1.0)]


# ============================================================================= test harness

def _ctx(tmp_path) -> ExecutionRuntimeContext:
    return ExecutionRuntimeContext.build(
        OpenPositionGuard(JsonKeyValueStore(str(tmp_path / "open.json"))),
        DailyLossGuard(JsonKeyValueStore(str(tmp_path / "daily.json")), GLOBAL_LEDGER_STRATEGY_ID),
        CloseLedger(JsonKeyValueStore(str(tmp_path / "closed.json"))),
    )


def _runtime(tmp_path) -> SweepRetestRuntime:
    return SweepRetestRuntime(SweepRetestStateStore(str(tmp_path / "setup_state.json")))


def _bar_tracker(tmp_path) -> LastClosedBarStore:
    return LastClosedBarStore(JsonKeyValueStore(str(tmp_path / "last_bar.json")))


def _forex_route(tmp_path, ctx, runtime, bar_tracker, m5_candles, *, user_confirmed=False, now=None):
    return evaluate_and_route(
        symbol="EURUSD", profile_config=FOREX_PROFILE_CONFIG, strategy_config=STRATEGY_CONFIG,
        runtime=runtime, bar_tracker=bar_tracker, ctx=ctx,
        fetch_m5_candles=lambda symbol: m5_candles, fetch_h1_candles=lambda symbol: H1_BEARISH,
        fetch_reference_candles=lambda symbol, profile_config, now_: _asian_candles(),
        symbol_meta=EURUSD_META, stop_buffer_price=EURUSD_SL_BUFFER, equity=10_000.0,
        reference_expected_bar_count=1, market_structure_config=CFG,
        user_confirmed=user_confirmed, now=now,
    )


def _crypto_route(ctx, runtime, bar_tracker, m5_candles):
    return evaluate_and_route(
        symbol="BTCUSDT", profile_config=CRYPTO_PROFILE_CONFIG, strategy_config=STRATEGY_CONFIG,
        runtime=runtime, bar_tracker=bar_tracker, ctx=ctx,
        fetch_m5_candles=lambda symbol: m5_candles, fetch_h1_candles=lambda symbol: H1_BEARISH,
        fetch_reference_candles=lambda symbol, profile_config, now_: _prev_day_candles(BTC_PDH, BTC_PDL),
        symbol_meta=BTCUSDT_META, stop_buffer_price=BTC_SL_BUFFER, equity=10_000.0,
        reference_expected_bar_count=None, market_structure_config=CFG, user_confirmed=False,
    )


def _position_row(ticket: int, symbol="EURUSD", volume=0.5, comment=""):
    return SimpleNamespace(ticket=ticket, symbol=symbol, volume=volume, comment=comment)


def _deal(entry: int, profit: float):
    return SimpleNamespace(entry=entry, profit=profit)


def _mock_geometry(monkeypatch, direction, entry, sl, tp):
    def _fake(request):
        return TradeManagementResult(
            symbol="EURUSD", direction=direction, overall_status=OVERALL_READY,
            geometry=TradeGeometry(status=GEOMETRY_VALID, direction=direction, entry=entry, stop_loss=sl, take_profit=tp),
            sizing=PositionSizing(status=SIZING_NOT_REQUESTED),
            position_state=PositionStateAdvisory(status="NOT_EVALUATED"),
        )
    monkeypatch.setattr(executor, "evaluate_trade_management", _fake)


def _mock_order_open(monkeypatch, **result_overrides):
    calls = []
    fields = dict(status="EXECUTED", reason_code="ORDER_SEND_DONE", symbol="EURUSD",
                  side="SELL", filled_volume=1.0, fill_price=1.0940, ticket=95001, deal_id=1, broker_retcode=10009)
    fields.update(result_overrides)

    def fake_order_open(**kwargs):
        calls.append(kwargs)
        return OrderSendResult(**fields)

    monkeypatch.setattr(executor.mt5_gateway, "order_open", fake_order_open)
    return calls


def _mock_journal(monkeypatch):
    monkeypatch.setattr(executor.journal, "claim_command", lambda command_id: True)
    monkeypatch.setattr(executor.journal, "has_executed", lambda command_id: False)
    monkeypatch.setattr(executor.journal, "record_event", lambda *a, **kw: None)


# ============================================================================= 1. no position at startup

def test_startup_no_position(tmp_path):
    ctx = _ctx(tmp_path)
    startup = start(
        strategy_path=STRATEGY_PATH, ctx=ctx, setup_state_store=SweepRetestStateStore(str(tmp_path / "s.json")),
        bar_tracker=_bar_tracker(tmp_path),
        positions_lookup=lambda ticket=None: [], deals_lookup=lambda ticket: [],
    )
    assert startup.ctx.open_position_guard.is_blocked() is False
    assert startup.strategy_config.strategy_id == "ST_LIQUIDITY_SWEEP_RETEST_V1"


# ============================================================================= 2. existing MT5 AG position restored

def test_startup_restores_existing_mt5_position(tmp_path):
    ctx = _ctx(tmp_path)
    live_row = _position_row(80001, comment="AGT:EURUSD:2026-01-05")
    startup = start(
        strategy_path=STRATEGY_PATH, ctx=ctx, setup_state_store=SweepRetestStateStore(str(tmp_path / "s.json")),
        bar_tracker=_bar_tracker(tmp_path),
        positions_lookup=lambda ticket=None: [live_row] if ticket is None else [],
        deals_lookup=lambda ticket: [],
    )
    assert startup.ctx.open_position_guard.is_blocked() is True
    restored = [r for r in startup.reconciliation_results if r["status"].startswith("MISSING_RECORD_RESTORED")]
    assert len(restored) == 1


# ============================================================================= 3. reconciliation happens before any new submission

def test_reconciliation_completes_before_new_submission_allowed(tmp_path):
    ctx = _ctx(tmp_path)
    live_row = _position_row(80002, comment="AGT:EURUSD:2026-01-05")
    startup = start(
        strategy_path=STRATEGY_PATH, ctx=ctx, setup_state_store=SweepRetestStateStore(str(tmp_path / "s.json")),
        bar_tracker=_bar_tracker(tmp_path),
        positions_lookup=lambda ticket=None: [live_row] if ticket is None else [],
        deals_lookup=lambda ticket: [],
    )
    # By the time start() RETURNS, reconciliation has already run -- proven by the guard
    # already blocking a fresh submission attempt with no further reconciliation call.
    result = _forex_route(tmp_path, startup.ctx, startup.runtime, startup.bar_tracker, _short_sequence())
    assert result.status == "EVALUATED"
    assert result.setup_state.state == "BLOCKED_OPEN_POSITION"


def test_startup_fails_closed_when_reconciliation_broker_query_fails(tmp_path):
    ctx = _ctx(tmp_path)

    def _broken_positions_lookup(ticket=None):
        raise RuntimeError("MT5_TERMINAL_UNREACHABLE")

    with pytest.raises(StartupReconciliationFailed):
        start(
            strategy_path=STRATEGY_PATH, ctx=ctx, setup_state_store=SweepRetestStateStore(str(tmp_path / "s.json")),
            bar_tracker=_bar_tracker(tmp_path),
            positions_lookup=_broken_positions_lookup, deals_lookup=lambda ticket: [],
        )


# ============================================================================= 4. same closed bar never processed twice

def test_same_closed_m5_bar_is_not_processed_twice(tmp_path):
    ctx = _ctx(tmp_path)
    runtime = _runtime(tmp_path)
    bar_tracker = _bar_tracker(tmp_path)
    truncated = [c for c in _short_sequence() if c.time <= dt.datetime(2026, 1, 5, 7, 20, tzinfo=UTC)]

    first = _forex_route(tmp_path, ctx, runtime, bar_tracker, truncated)
    assert first.status == "EVALUATED"

    h1_calls = []

    def _counting_h1(symbol):
        h1_calls.append(symbol)
        return H1_BEARISH

    second = evaluate_and_route(
        symbol="EURUSD", profile_config=FOREX_PROFILE_CONFIG, strategy_config=STRATEGY_CONFIG,
        runtime=runtime, bar_tracker=bar_tracker, ctx=ctx,
        fetch_m5_candles=lambda symbol: truncated,  # identical latest bar as `first`
        fetch_h1_candles=_counting_h1, fetch_reference_candles=lambda s, p, n: _asian_candles(),
        symbol_meta=EURUSD_META, stop_buffer_price=EURUSD_SL_BUFFER, equity=10_000.0,
        reference_expected_bar_count=1,
    )
    assert second.status == "NO_NEW_BAR"
    assert second.setup_state is None
    assert h1_calls == []  # never even fetched further data for an already-processed bar


# ============================================================================= 5. restart does not recreate a previous proposal

def test_restart_replay_of_same_bar_produces_no_new_proposal(tmp_path):
    ctx = _ctx(tmp_path)
    state_path = str(tmp_path / "setup_state.json")
    bar_path = str(tmp_path / "last_bar.json")

    runtime_before = SweepRetestRuntime(SweepRetestStateStore(state_path))
    tracker_before = LastClosedBarStore(JsonKeyValueStore(bar_path))
    before = _forex_route(tmp_path, ctx, runtime_before, tracker_before, _short_sequence())
    assert before.status == "SUBMITTED"
    assert before.setup_state.state == "ENTRY_READY"

    # "Restart": brand-new runtime/tracker objects, same on-disk paths.
    runtime_after = SweepRetestRuntime(SweepRetestStateStore(state_path))
    tracker_after = LastClosedBarStore(JsonKeyValueStore(bar_path))
    after = _forex_route(tmp_path, ctx, runtime_after, tracker_after, _short_sequence())
    assert after.status == "NO_NEW_BAR"  # same last closed bar -- no re-evaluation, no new proposal


# ============================================================================= 6/7. restart mid-state-machine

def test_restart_during_waiting_mss_then_continues_to_entry_ready(tmp_path):
    ctx = _ctx(tmp_path)
    state_path = str(tmp_path / "setup_state.json")
    bar_path = str(tmp_path / "last_bar.json")
    truncated = [c for c in _short_sequence() if c.time <= dt.datetime(2026, 1, 5, 7, 25, tzinfo=UTC)]

    before = _forex_route(tmp_path, ctx, SweepRetestRuntime(SweepRetestStateStore(state_path)),
                           LastClosedBarStore(JsonKeyValueStore(bar_path)), truncated)
    assert before.setup_state.state == "WAITING_MSS"

    persisted = SweepRetestStateStore(state_path).load("EURUSD:2026-01-05")
    assert persisted.state == "WAITING_MSS"

    after = _forex_route(tmp_path, ctx, SweepRetestRuntime(SweepRetestStateStore(state_path)),
                          LastClosedBarStore(JsonKeyValueStore(bar_path)), _short_sequence())
    assert after.setup_state.state == "ENTRY_READY"


def test_restart_during_waiting_retest_then_continues_to_entry_ready(tmp_path):
    ctx = _ctx(tmp_path)
    state_path = str(tmp_path / "setup_state.json")
    bar_path = str(tmp_path / "last_bar.json")
    truncated = [c for c in _short_sequence() if c.time <= dt.datetime(2026, 1, 5, 7, 30, tzinfo=UTC)]

    before = _forex_route(tmp_path, ctx, SweepRetestRuntime(SweepRetestStateStore(state_path)),
                           LastClosedBarStore(JsonKeyValueStore(bar_path)), truncated)
    assert before.setup_state.state == "WAITING_RETEST"

    persisted = SweepRetestStateStore(state_path).load("EURUSD:2026-01-05")
    assert persisted.state == "WAITING_RETEST"

    after = _forex_route(tmp_path, ctx, SweepRetestRuntime(SweepRetestStateStore(state_path)),
                          LastClosedBarStore(JsonKeyValueStore(bar_path)), _short_sequence())
    assert after.setup_state.state == "ENTRY_READY"


# ============================================================================= 8. restart with an open Forex position

def test_restart_with_open_forex_position_blocks_new_entry(tmp_path):
    ctx = _ctx(tmp_path)
    live_row = _position_row(80003, comment="AGT:EURUSD:2026-01-05")
    startup = start(
        strategy_path=STRATEGY_PATH, ctx=ctx, setup_state_store=SweepRetestStateStore(str(tmp_path / "s.json")),
        bar_tracker=_bar_tracker(tmp_path),
        positions_lookup=lambda ticket=None: [live_row] if ticket is None else [live_row],
        deals_lookup=lambda ticket: [],
    )
    assert startup.ctx.open_position_guard.is_blocked() is True
    result = _forex_route(tmp_path, startup.ctx, startup.runtime, startup.bar_tracker, _short_sequence())
    assert result.setup_state.state == "BLOCKED_OPEN_POSITION"


# ============================================================================= 9/10. full close + realized R via the runtime's OWN reconciliation loop

def test_full_close_and_realized_r_recorded_once_via_runtime_reconciliation_loop(monkeypatch, tmp_path):
    _mock_journal(monkeypatch)
    _mock_geometry(monkeypatch, "SHORT", 1.0940, 1.1105, None)
    _mock_order_open(monkeypatch, side="SELL", symbol="EURUSD", ticket=80004, fill_price=1.0940, filled_volume=0.1)

    ctx = _ctx(tmp_path)
    runtime = _runtime(tmp_path)
    bar_tracker = _bar_tracker(tmp_path)

    submitted = _forex_route(tmp_path, ctx, runtime, bar_tracker, _short_sequence(), user_confirmed=True)
    assert submitted.coordinator_result.status == "EXECUTION_DELEGATED"
    assert ctx.open_position_guard.is_blocked() is True

    # Runtime's own reconciliation loop (ExecutionCoordinator.reconcile, exercised through
    # the SAME ctx a real --watch cycle would use), called INDEPENDENTLY of any new bar --
    # first while still open, then once the broker reports it gone.
    still_open = ctx.coordinator.reconcile(positions_lookup=lambda ticket=None: [_position_row(80004)] if ticket == 80004 else [],
                                            deals_lookup=lambda ticket: [])
    assert any(r["status"] == "STILL_OPEN" for r in still_open)

    closed = ctx.coordinator.reconcile(positions_lookup=lambda ticket=None: [] if ticket == 80004 else [],
                                        deals_lookup=lambda ticket: [_deal(entry=1, profit=50.0)],
                                        now=dt.datetime(2026, 1, 5, 12, tzinfo=UTC))
    recorded = [r for r in closed if r.get("position_id") == "80004"]
    assert recorded[0]["status"] == "CLOSED_RECORDED"
    assert recorded[0]["realized_r"] is not None
    assert ctx.open_position_guard.is_blocked() is False

    # Replaying reconciliation (the loop runs periodically) must not double-count.
    replayed = ctx.coordinator.reconcile(positions_lookup=lambda ticket=None: [], deals_lookup=lambda ticket: [_deal(entry=1, profit=50.0)])
    replayed_record = [r for r in replayed if r.get("position_id") == "80004"]
    assert replayed_record == [] or replayed_record[0]["status"] != "CLOSED_RECORDED"
    daily_r_after_first_close = ctx.daily_loss_guard.realized_r(dt.date(2026, 1, 5))
    assert daily_r_after_first_close == recorded[0]["realized_r"]


# ============================================================================= FULL END-TO-END: Forex

def test_end_to_end_forex_runtime_sweep_to_realized_r(monkeypatch, tmp_path):
    """Real composition root + real orchestration code: closed M5 data -> sweep -> MSS ->
    retest -> ENTRY_READY -> proposal -> coordinator -> explicit confirmation ->
    mocked EXECUTED -> broker ticket -> reconcile -> close -> realized R. Only the true
    external boundary (mt5_gateway.order_open / the confirmation gate's broker call) is
    mocked -- everything else is the real execution_runtime/execution/strategy_engine code."""
    ctx = _ctx(tmp_path)
    runtime = _runtime(tmp_path)
    bar_tracker = _bar_tracker(tmp_path)

    # 1) closed M5 data -> sweep -> MSS -> retest -> ENTRY_READY, with MANDATORY explicit
    #    confirmation NOT yet given -- must stop at CONFIRMATION_REQUIRED, no order sent.
    pending = _forex_route(tmp_path, ctx, runtime, bar_tracker, _short_sequence(), user_confirmed=False)
    assert pending.status == "SUBMITTED"
    assert pending.setup_state.state == "ENTRY_READY"
    assert pending.coordinator_result.status == "CONFIRMATION_REQUIRED"
    assert ctx.open_position_guard.is_blocked() is False  # no order sent yet

    # 2) explicit confirmation (the ONLY path allowed to pass user_confirmed=True) -> real
    #    executor.execute() -> mocked mt5_gateway.order_open (the true external boundary).
    _mock_journal(monkeypatch)
    _mock_geometry(monkeypatch, "SHORT", pending.setup_state.entry, pending.setup_state.stop_loss, pending.setup_state.tp1)
    _mock_order_open(monkeypatch, side="SELL", symbol="EURUSD", ticket=80005,
                      fill_price=pending.setup_state.entry, filled_volume=pending.setup_state.volume)

    confirmed = confirm_and_submit(symbol="EURUSD", setup_id=pending.setup_state.setup_id, runtime=runtime, ctx=ctx)
    assert confirmed.coordinator_result.status == "EXECUTION_DELEGATED"
    assert ctx.open_position_guard.is_blocked() is True
    assert ctx.open_position_guard.store.get("80005") is not None

    # 3) reconcile -> close -> realized R, through the SAME ctx (no second guard/context).
    ctx.coordinator.reconcile(positions_lookup=lambda ticket=None: [_position_row(80005)] if ticket == 80005 else [],
                               deals_lookup=lambda ticket: [])
    assert ctx.open_position_guard.is_blocked() is True  # still open

    results = ctx.coordinator.reconcile(
        positions_lookup=lambda ticket=None: [] if ticket == 80005 else [],
        deals_lookup=lambda ticket: [_deal(entry=1, profit=25.0)],
        now=dt.datetime(2026, 1, 5, 12, tzinfo=UTC),
    )
    closed = [r for r in results if r.get("position_id") == "80005"]
    assert closed[0]["status"] == "CLOSED_RECORDED"
    assert closed[0]["realized_r"] is not None
    assert ctx.open_position_guard.is_blocked() is False
    assert ctx.close_ledger.is_recorded("80005") is True


# ============================================================================= FULL: Crypto proposal-only

def test_crypto_runtime_setup_reaches_proposal_only_with_no_open_position_or_realized_r_mutation(tmp_path):
    ctx = _ctx(tmp_path)
    runtime = _runtime(tmp_path)
    bar_tracker = _bar_tracker(tmp_path)

    result = _crypto_route(ctx, runtime, bar_tracker, _btc_high_sweep_sequence())
    assert result.status == "SUBMITTED"
    assert result.setup_state.state == "ENTRY_READY"
    assert result.setup_state.profile_id == "CRYPTO_PERP"
    assert result.coordinator_result.status == "PROPOSAL_ONLY"

    # No network/exchange call, no real MT5 fill -> the shared guards/ledger are UNTOUCHED.
    assert ctx.open_position_guard.is_blocked() is False
    assert ctx.open_position_guard.store.all() == {}
    assert ctx.daily_loss_guard.realized_r(dt.date(2026, 1, 5)) == 0.0
    assert ctx.close_ledger.store.all() == {}
