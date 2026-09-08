"""Tests for AG_EXECUTION_RUNTIME_READINESS_V1 -- the three hardening gaps:

  GAP 1: strategies/ST_ASIAN_SWEEP_5R_V1.yaml's entry_order_type ambiguity, resolved to a
         single deterministic MARKET contract; proven through the REAL loader/engine/
         intent_builder/adapter/coordinator path, not a fixture substitute.
  GAP 2: restart-safe original risk metadata, persisted via execution.journal (extending
         the existing per-command_id journal, not a second store) and recovered on
         restart reconciliation.
  GAP 3: ExecutionRuntimeContext, the one composition root sharing the SAME GLOBAL guard
         instances between an evaluation-side consumer and the authoritative coordinator.

No live MT5 terminal anywhere here: mt5_gateway.order_open / evaluate_trade_management are
monkeypatched at the point executor.py imports them, same idiom every other execution test
in this repo already uses.
"""
from __future__ import annotations

import datetime as dt
import uuid
from datetime import time
from types import SimpleNamespace

import pytest

from execution import build_intent, executor, journal, lifecycle
from execution.adapter import TradeProposal
from execution.close_ledger import CloseLedger
from execution.coordinator import (
    GLOBAL_LEDGER_STRATEGY_ID,
    STATUS_BLOCKED_OPEN_POSITION,
    STATUS_EXECUTION_DELEGATED,
    ExecutionCoordinator,
)
from execution.daily_loss_guard import DailyLossGuard
from execution.models import ExecutionReport, ExecutionSource, OrderSendResult
from execution.position_guard import OpenPositionGuard
from execution.runtime_context import ExecutionRuntimeContext
from mt5.symbol_resolver import SymbolMeta
from runtime_state.store import JsonKeyValueStore
from market_structure.models import MarketStructureConfig
from strategy_engine import evaluate, load_strategy
from strategy_engine.session import Candle
from strategy_engine.sweep_retest.engine import evaluate_setup
from strategy_engine.sweep_retest.models import STATE_BLOCKED_OPEN_POSITION
from strategy_engine.sweep_retest.profile import BUFFER_PIP, PROFILE_FOREX, REFERENCE_ASIAN_SESSION, MarketProfile
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
STRATEGY_PATH = "strategies/ST_ASIAN_SWEEP_5R_V1.yaml"

# Minimal ENTRY_READY-reaching sweep_retest fixture (Gap 2 remediation: evaluate_setup's
# guard checks moved to AFTER full qualification -- see engine.py's "Guard ordering"
# docstring -- so test_one_context_gives_consistent_blocking_between_evaluation_and_
# coordinator below needs candles that actually reach qualification to observe the guard,
# rather than the empty-candles shortcut it previously relied on). Same shape as
# tests/test_liquidity_sweep_retest_strategy.py's own validated Forex fixture (HIGH sweep
# of AsianHigh=1.1050, MSS on the 3rd post-sweep candle, retest at 07:35) -- duplicated
# here rather than cross-imported since no test file in this repo imports from another.
_SWEEP_RETEST_TEST_CFG = MarketStructureConfig(swing_length=1, close_break=True, default_analysis_count=50)
_ASIAN_HIGH, _ASIAN_LOW = 1.1050, 1.0700


def _sweep_retest_asian_candles():
    return [Candle(time=dt.datetime(2026, 1, 5, 3, 0, tzinfo=UTC), open=1.0900, high=_ASIAN_HIGH,
                   low=_ASIAN_LOW, close=1.0900, volume=1.0)]


def _sweep_retest_m5_sequence():
    def _c(minute, o, h, l, cl, hour=7):
        return Candle(time=dt.datetime(2026, 1, 5, hour, minute, tzinfo=UTC), open=o, high=h, low=l, close=cl, volume=1.0)
    return [
        _c(0, 1.1000, 1.1005, 1.0995, 1.1000),
        _c(5, 1.0980, 1.0985, 1.0940, 1.0950),   # swing low candidate ~1.0940
        _c(10, 1.0960, 1.1010, 1.0955, 1.1005),  # rally
        _c(15, 1.1005, 1.1080, 1.0900, 1.0910),  # SWEEP: high>1.1050, close<1.1050
        _c(20, 1.0910, 1.0950, 1.0930, 1.0945),  # intrabar only
        _c(25, 1.0945, 1.0950, 1.0935, 1.0942),  # still above
        _c(30, 1.0942, 1.0945, 1.0890, 1.0895),  # closes below 1.0940 -> MSS confirmed
        _c(35, 1.0895, 1.0945, 1.0890, 1.0900),  # retest: high 1.0945 >= 1.0940
        _c(40, 1.0900, 1.0905, 1.0850, 1.0860),
    ]


def _sweep_retest_h1_bearish():
    out, t, price = [], dt.datetime(2026, 1, 1, tzinfo=UTC), 1.2000
    for i in range(25):
        for p in (price - i * 0.0100, price - i * 0.0100 - 0.0300):
            out.append(Candle(time=t, open=p, high=p + 0.0005, low=p - 0.0005, close=p, volume=1.0))
            t += dt.timedelta(hours=1)
    return out


def _eurusd_meta(**overrides) -> SymbolMeta:
    fields = dict(symbol="EURUSD", tick_size=0.00001, tick_value=1.0, contract_size=100000.0,
                  volume_min=0.01, volume_max=50.0, volume_step=0.01, digits=5)
    fields.update(overrides)
    return SymbolMeta(**fields)


# ============================================================================= GAP 1: real strategy contract

def test_real_yaml_no_longer_declares_market_or_limit():
    """Test 3: the ambiguous string is gone from the executable contract entirely, not
    merely worked around -- checked at the raw-file level, not just the parsed model."""
    with open(STRATEGY_PATH, "r", encoding="utf-8") as f:
        raw = f.read()
    assert "MARKET_OR_LIMIT" not in raw


def test_real_yaml_entry_order_type_is_deterministic_market():
    """Test 1/2: the real, unmodified strategies/ST_ASIAN_SWEEP_5R_V1.yaml -- loaded via the
    real loader, no fixture-only override -- now declares a single executable order type
    for both setups (loader.py itself refuses to load if long/short ever diverge)."""
    strategy = load_strategy(STRATEGY_PATH)
    assert strategy.entry_order_type == "MARKET"


def test_real_signal_path_reaches_ready_for_order_check():
    """Real loader -> real strategy_engine.evaluate() (session/candle logic UNCHANGED) ->
    real build_intent() -> no longer ENTRY_EXECUTION_UNDEFINED. Reuses the exact validated
    sweep fixture from tests/test_strategy_engine.py::test_evaluate_range_with_sweep_yields_signal."""
    strategy = load_strategy(STRATEGY_PATH)
    day = dt.date(2026, 1, 5)
    session_candles = [
        Candle(dt.datetime(2026, 1, 5, 0, 0, tzinfo=UTC), 1.1000, 1.1050, 1.0950, 1.1010),
        Candle(dt.datetime(2026, 1, 5, 0, 15, tzinfo=UTC), 1.1010, 1.1040, 1.0960, 1.1005),
    ]
    sweep_candle = Candle(dt.datetime(2026, 1, 5, 7, 0, tzinfo=UTC), 1.1005, 1.1060, 1.1000, 1.1048)

    signal = evaluate(strategy, "ASIAN_LONDON", "EURUSD", day, session_candles, 2, [sweep_candle])
    assert signal.status == "SIGNAL"
    assert signal.direction == "SHORT"

    result = build_intent(signal, strategy, equity=10_000.0, symbol_meta=_eurusd_meta(), risk_per_trade_pct=1.0)

    assert result.status != "ENTRY_EXECUTION_UNDEFINED"
    assert result.status == "READY_FOR_ORDER_CHECK"
    assert result.intent.direction == "SHORT"
    assert result.intent.entry == pytest.approx(1.1048)
    assert result.intent.stop_loss == pytest.approx(1.1060)


def _mock_geometry(monkeypatch, direction, entry, sl, tp):
    def _fake(request):
        return TradeManagementResult(
            symbol="EURUSD", direction=direction, overall_status=OVERALL_READY,
            geometry=TradeGeometry(status=GEOMETRY_VALID, direction=direction, entry=entry,
                                    stop_loss=sl, take_profit=tp),
            sizing=PositionSizing(status=SIZING_NOT_REQUESTED),
            position_state=PositionStateAdvisory(status="NOT_EVALUATED"),
        )
    monkeypatch.setattr(executor, "evaluate_trade_management", _fake)


def _mock_order_open(monkeypatch, **result_overrides):
    calls = []
    fields = dict(status="EXECUTED", reason_code="ORDER_SEND_DONE", symbol="EURUSD",
                  side="SELL", filled_volume=1.0, fill_price=1.1048, ticket=901, deal_id=1901,
                  broker_retcode=10009)
    fields.update(result_overrides)

    def fake_order_open(**kwargs):
        calls.append(kwargs)
        return OrderSendResult(**fields)

    monkeypatch.setattr(executor.mt5_gateway, "order_open", fake_order_open)
    return calls


def _coordinator(tmp_path) -> ExecutionCoordinator:
    return ExecutionCoordinator(
        open_position_guard=OpenPositionGuard(JsonKeyValueStore(str(tmp_path / "open.json"))),
        daily_loss_guard=DailyLossGuard(JsonKeyValueStore(str(tmp_path / "daily.json")), GLOBAL_LEDGER_STRATEGY_ID),
        close_ledger=CloseLedger(JsonKeyValueStore(str(tmp_path / "closed.json"))),
    )


def test_real_signal_reaches_coordinator_without_entry_execution_undefined(monkeypatch, tmp_path):
    """Full real path: real YAML -> real evaluate() -> real build_intent() ->
    TradeProposal.from_trade_intent() -> ExecutionCoordinator.submit(). Proves the
    resolved contract reaches actual delegated execution, not merely READY_FOR_ORDER_CHECK
    in isolation."""
    monkeypatch.setattr(executor.journal, "claim_command", lambda command_id: True)
    monkeypatch.setattr(executor.journal, "has_executed", lambda command_id: False)
    monkeypatch.setattr(executor.journal, "record_event", lambda *a, **kw: None)
    # execution.executor._reconcile_via_broker (AG2 fail-closed fix): without a live MT5
    # terminal, real get_positions()/deals_for_symbol() calls raise -- mock them empty so
    # this test exercises CONFIRMED_ABSENT (no prior attempt), not a lookup failure.
    monkeypatch.setattr(executor, "get_positions", lambda **kw: [])
    monkeypatch.setattr(executor, "deals_for_symbol", lambda symbol, **kw: [])

    strategy = load_strategy(STRATEGY_PATH)
    day = dt.date(2026, 1, 5)
    session_candles = [
        Candle(dt.datetime(2026, 1, 5, 0, 0, tzinfo=UTC), 1.1000, 1.1050, 1.0950, 1.1010),
        Candle(dt.datetime(2026, 1, 5, 0, 15, tzinfo=UTC), 1.1010, 1.1040, 1.0960, 1.1005),
    ]
    sweep_candle = Candle(dt.datetime(2026, 1, 5, 7, 0, tzinfo=UTC), 1.1005, 1.1060, 1.1000, 1.1048)
    signal = evaluate(strategy, "ASIAN_LONDON", "EURUSD", day, session_candles, 2, [sweep_candle])
    intent_result = build_intent(signal, strategy, equity=10_000.0, symbol_meta=_eurusd_meta(), risk_per_trade_pct=1.0)
    assert intent_result.status == "READY_FOR_ORDER_CHECK"

    proposal = TradeProposal.from_trade_intent(intent_result.intent)
    assert proposal.strategy_id == "ST_ASIAN_SWEEP_5R_V1"

    _mock_geometry(monkeypatch, "SHORT", proposal.entry, proposal.stop_loss, proposal.tp1)
    calls = _mock_order_open(monkeypatch, side="SELL", symbol="EURUSD")

    coordinator = _coordinator(tmp_path)
    result = coordinator.submit(proposal, user_confirmed=True)

    assert result.status == STATUS_EXECUTION_DELEGATED
    assert len(calls) == 1
    assert coordinator.open_position_guard.is_blocked() is True


# ============================================================================= GAP 2: restart-safe risk metadata

def _forex_proposal(**overrides) -> TradeProposal:
    fields = dict(
        setup_id=f"EURUSD:{uuid.uuid4()}", strategy_id="ST_ASIAN_SWEEP_5R_V1", symbol="EURUSD",
        profile_id=PROFILE_FOREX, direction="LONG", entry=1.1000, stop_loss=1.0950,
        tp1=1.1050, tp2=None, volume=0.5, risk_amount=100.0, risk_percent=1.0,
    )
    fields.update(overrides)
    return TradeProposal(**fields)


def _executed_report(ticket: int, fill_price=1.1000, filled_volume=0.5) -> ExecutionReport:
    return ExecutionReport(
        command_id="cmd", source=ExecutionSource.USER_EXPLICIT_ORDER, status="EXECUTED",
        gate_reason_code="ORDER_SEND_DONE",
        result=OrderSendResult(status="EXECUTED", reason_code="ORDER_SEND_DONE", symbol="EURUSD",
                                side="BUY", filled_volume=filled_volume, fill_price=fill_price, ticket=ticket),
    )


def _position_row(ticket: int, symbol="EURUSD", volume=0.5, comment=""):
    return SimpleNamespace(ticket=ticket, symbol=symbol, volume=volume, comment=comment)


def _deal(entry: int, profit: float):
    return SimpleNamespace(entry=entry, profit=profit)


def test_confirmed_fill_persists_original_risk_metadata(tmp_path):
    """Test 4: register_confirmed_fill persists IMMUTABLE lifecycle metadata (ticket,
    strategy_id, setup_id, symbol, direction, entry, stop_loss, volume, risk_amount,
    risk_percent) into execution.journal, keyed by the SAME command_id (setup_id) the
    Forex TradeCommand already uses -- not a second persistence mechanism."""
    guard = OpenPositionGuard(JsonKeyValueStore(str(tmp_path / "open.json")))
    proposal = _forex_proposal(risk_amount=250.0, risk_percent=2.0, stop_loss=1.0940)

    position_id = lifecycle.register_confirmed_fill(guard, proposal, _executed_report(ticket=90001))

    assert position_id == "90001"
    metadata = journal.read_lifecycle_metadata(proposal.setup_id)
    assert metadata is not None
    assert metadata["ticket"] == "90001"
    assert metadata["strategy_id"] == proposal.strategy_id
    assert metadata["setup_id"] == proposal.setup_id
    assert metadata["symbol"] == "EURUSD"
    assert metadata["risk_amount"] == pytest.approx(250.0)
    assert metadata["risk_percent"] == pytest.approx(2.0)
    assert metadata["stop_loss"] == pytest.approx(1.0940)
    assert "ts" in metadata  # doubles as the opened timestamp


def test_confirmed_fill_lifecycle_metadata_is_immutable(tmp_path):
    """A second register_confirmed_fill for the SAME setup_id (e.g. a replayed call) must
    never silently overwrite the ORIGINAL risk metadata with a different value."""
    guard = OpenPositionGuard(JsonKeyValueStore(str(tmp_path / "open.json")))
    proposal = _forex_proposal(risk_amount=100.0)

    lifecycle.register_confirmed_fill(guard, proposal, _executed_report(ticket=90002))
    first = journal.read_lifecycle_metadata(proposal.setup_id)

    replayed_proposal = _forex_proposal(setup_id=proposal.setup_id, risk_amount=999.0)
    lifecycle.register_confirmed_fill(guard, replayed_proposal, _executed_report(ticket=90002))
    second = journal.read_lifecycle_metadata(proposal.setup_id)

    assert first["risk_amount"] == pytest.approx(100.0)
    assert second["risk_amount"] == pytest.approx(100.0)  # unchanged, not overwritten to 999.0


def test_restart_restores_original_risk_amount_from_persisted_metadata(tmp_path):
    """Test 5: a broker position surviving a crash (no OpenPositionGuard record left) but
    WITH persisted lifecycle metadata for its command_id restores the ORIGINAL
    risk_amount, not None."""
    open_guard = OpenPositionGuard(JsonKeyValueStore(str(tmp_path / "open.json")))
    daily_guard = DailyLossGuard(JsonKeyValueStore(str(tmp_path / "daily.json")), "T5")
    close_ledger = CloseLedger(JsonKeyValueStore(str(tmp_path / "closed.json")))
    proposal = _forex_proposal(risk_amount=175.0, strategy_id="ST_ASIAN_SWEEP_5R_V1")

    lifecycle.register_confirmed_fill(open_guard, proposal, _executed_report(ticket=90003))
    open_guard.store.remove("90003")  # simulate crash: guard record lost, journal metadata survives

    live_row = _position_row(90003, comment=f"AGT:{proposal.setup_id}")
    results = lifecycle.reconcile_open_positions(
        open_guard, daily_guard, close_ledger,
        positions_lookup=lambda ticket=None: [live_row] if ticket is None else [],
        deals_lookup=lambda ticket: [],
    )

    restored = [r for r in results if r["status"] == "MISSING_RECORD_RESTORED_FROM_METADATA"]
    assert len(restored) == 1
    record = open_guard.store.get("90003")
    assert record["risk_amount"] == pytest.approx(175.0)
    assert record["strategy_id"] == "ST_ASIAN_SWEEP_5R_V1"
    assert open_guard.is_blocked() is True


def test_restart_with_missing_metadata_fails_closed_not_guessed(tmp_path):
    """Test 6: a broker position with NO persisted lifecycle metadata (predates this
    phase, or the write itself failed) must never have a risk_amount invented -- fails
    closed with the explicit, documented status, exactly as before this phase."""
    open_guard = OpenPositionGuard(JsonKeyValueStore(str(tmp_path / "open.json")))
    daily_guard = DailyLossGuard(JsonKeyValueStore(str(tmp_path / "daily.json")), "T6")
    close_ledger = CloseLedger(JsonKeyValueStore(str(tmp_path / "closed.json")))
    unknown_command_id = f"NEVER-PERSISTED:{uuid.uuid4()}"

    live_row = _position_row(90004, comment=f"AGT:{unknown_command_id}")
    results = lifecycle.reconcile_open_positions(
        open_guard, daily_guard, close_ledger,
        positions_lookup=lambda ticket=None: [live_row] if ticket is None else [],
        deals_lookup=lambda ticket: [],
    )

    restored = [r for r in results if r["status"] == "MISSING_RECORD_RESTORED"]
    assert len(restored) == 1
    assert restored[0]["risk_metadata_status"] == "OPEN_RISK_METADATA_MISSING"
    record = open_guard.store.get("90004")
    assert record.get("risk_amount") is None  # never guessed


def test_missing_risk_metadata_position_still_blocks_new_submission(monkeypatch, tmp_path):
    """Test 7: a position restored WITHOUT recoverable risk metadata still counts toward
    and blocks the one-open-position rule -- only realized-R recording is refused, never
    the guard's blocking behavior."""
    ctx = ExecutionRuntimeContext.build(
        OpenPositionGuard(JsonKeyValueStore(str(tmp_path / "open.json"))),
        DailyLossGuard(JsonKeyValueStore(str(tmp_path / "daily.json")), GLOBAL_LEDGER_STRATEGY_ID),
        CloseLedger(JsonKeyValueStore(str(tmp_path / "closed.json"))),
    )
    unknown_command_id = f"NEVER-PERSISTED:{uuid.uuid4()}"
    live_row = _position_row(90005, comment=f"AGT:{unknown_command_id}")
    lifecycle.reconcile_open_positions(
        ctx.open_position_guard, ctx.daily_loss_guard, ctx.close_ledger,
        positions_lookup=lambda ticket=None: [live_row] if ticket is None else [],
        deals_lookup=lambda ticket: [],
    )
    assert ctx.open_position_guard.store.get("90005").get("risk_amount") is None

    result = ctx.coordinator.submit(_forex_proposal(), user_confirmed=True)

    assert result.status == STATUS_BLOCKED_OPEN_POSITION


def test_close_of_restart_restored_position_with_metadata_records_realized_r_once(tmp_path):
    """Test 8: once a restart-restored (WITH recovered metadata) position later closes,
    realized R is computed from the RECOVERED original risk_amount and recorded exactly
    once -- the same lifecycle a position that never lost its guard record would get."""
    open_guard = OpenPositionGuard(JsonKeyValueStore(str(tmp_path / "open.json")))
    daily_guard = DailyLossGuard(JsonKeyValueStore(str(tmp_path / "daily.json")), "T8")
    close_ledger = CloseLedger(JsonKeyValueStore(str(tmp_path / "closed.json")))
    proposal = _forex_proposal(risk_amount=50.0)

    lifecycle.register_confirmed_fill(open_guard, proposal, _executed_report(ticket=90006))
    open_guard.store.remove("90006")
    live_row = _position_row(90006, comment=f"AGT:{proposal.setup_id}")
    lifecycle.reconcile_open_positions(
        open_guard, daily_guard, close_ledger,
        positions_lookup=lambda ticket=None: [live_row] if ticket is None else [],
        deals_lookup=lambda ticket: [],
    )
    assert open_guard.store.get("90006")["risk_amount"] == pytest.approx(50.0)

    day = dt.date(2026, 1, 5)
    results = lifecycle.reconcile_open_positions(
        open_guard, daily_guard, close_ledger,
        positions_lookup=lambda ticket=None: [] if ticket == 90006 else [],
        deals_lookup=lambda ticket: [_deal(entry=1, profit=75.0)],  # +$75 on $50 risk = +1.5R
        now=dt.datetime(2026, 1, 5, 12, tzinfo=UTC),
    )

    closed = [r for r in results if r.get("position_id") == "90006"]
    assert closed[0]["status"] == "CLOSED_RECORDED"
    assert closed[0]["realized_r"] == pytest.approx(1.5)
    assert daily_guard.realized_r(day) == pytest.approx(1.5)
    assert open_guard.store.all() == {}


def test_duplicate_reconciliation_of_restored_position_does_not_double_count_r(tmp_path):
    """Test 9: replaying the SAME close observation for a restart-restored (metadata-
    recovered) position -- e.g. a re-run reconciliation pass -- must have zero additional
    effect on realized R, exactly like a position that never lost its guard record."""
    open_guard = OpenPositionGuard(JsonKeyValueStore(str(tmp_path / "open.json")))
    daily_guard = DailyLossGuard(JsonKeyValueStore(str(tmp_path / "daily.json")), "T9")
    close_ledger = CloseLedger(JsonKeyValueStore(str(tmp_path / "closed.json")))
    proposal = _forex_proposal(risk_amount=10.0)
    day = dt.date(2026, 1, 5)

    lifecycle.register_confirmed_fill(open_guard, proposal, _executed_report(ticket=90007))
    open_guard.store.remove("90007")
    live_row = _position_row(90007, comment=f"AGT:{proposal.setup_id}")
    lifecycle.reconcile_open_positions(
        open_guard, daily_guard, close_ledger,
        positions_lookup=lambda ticket=None: [live_row] if ticket is None else [],
        deals_lookup=lambda ticket: [],
    )
    record = open_guard.store.get("90007")
    assert record["risk_amount"] == pytest.approx(10.0)  # recovered from journal metadata

    first = lifecycle.reconcile_closed_position(
        open_guard, daily_guard, close_ledger, "90007", record,
        deals_lookup=lambda ticket: [_deal(entry=1, profit=10.0)],
        now=dt.datetime(2026, 1, 5, 12, tzinfo=UTC),
    )
    assert first["status"] == "CLOSED_RECORDED"
    assert daily_guard.realized_r(day) == pytest.approx(1.0)

    second = lifecycle.reconcile_closed_position(
        open_guard, daily_guard, close_ledger, "90007", record,
        deals_lookup=lambda ticket: [_deal(entry=1, profit=10.0)],
        now=dt.datetime(2026, 1, 5, 12, tzinfo=UTC),
    )
    assert second["status"] == "ALREADY_RECORDED"
    assert daily_guard.realized_r(day) == pytest.approx(1.0)  # unchanged, not doubled


# ============================================================================= GAP 3: one authoritative context

def test_one_context_gives_consistent_blocking_between_evaluation_and_coordinator(monkeypatch, tmp_path):
    """Test 10: ONE ExecutionRuntimeContext, used both by an evaluation-side consumer
    (strategy_engine.sweep_retest.engine.evaluate_setup's own advisory guard parameters)
    and by ExecutionCoordinator.submit() -- no drift between what the strategy 'sees' and
    what the coordinator enforces, because both read the SAME underlying guard stores."""
    monkeypatch.setattr(executor.journal, "claim_command", lambda command_id: True)
    monkeypatch.setattr(executor.journal, "has_executed", lambda command_id: False)
    monkeypatch.setattr(executor.journal, "record_event", lambda *a, **kw: None)
    # execution.executor._reconcile_via_broker (AG2 fail-closed fix): without a live MT5
    # terminal, real get_positions()/deals_for_symbol() calls raise -- mock them empty so
    # this test exercises CONFIRMED_ABSENT (no prior attempt), not a lookup failure.
    monkeypatch.setattr(executor, "get_positions", lambda **kw: [])
    monkeypatch.setattr(executor, "deals_for_symbol", lambda symbol, **kw: [])
    _mock_geometry(monkeypatch, "LONG", 1.1000, 1.0950, 1.1050)
    _mock_order_open(monkeypatch, side="BUY", symbol="EURUSD", ticket=90100)

    ctx = ExecutionRuntimeContext.build(
        OpenPositionGuard(JsonKeyValueStore(str(tmp_path / "open.json"))),
        DailyLossGuard(JsonKeyValueStore(str(tmp_path / "daily.json")), GLOBAL_LEDGER_STRATEGY_ID),
        CloseLedger(JsonKeyValueStore(str(tmp_path / "closed.json"))),
    )
    profile = MarketProfile(PROFILE_FOREX, ("EURUSD",), REFERENCE_ASIAN_SESSION, "Asian", BUFFER_PIP,
                            ((time(7, 0), time(10, 0)),))
    eval_kwargs = dict(
        setup_id="eval-1", strategy_id="ST_LIQUIDITY_SWEEP_RETEST_V1", symbol="EURUSD",
        trading_day=dt.date(2026, 1, 5), profile=profile,
        reference_candles=_sweep_retest_asian_candles(), h1_candles=_sweep_retest_h1_bearish(),
        m5_candles=_sweep_retest_m5_sequence(), execution_windows=[(time(7, 0), time(10, 0))], equity=10_000.0,
        symbol_meta=_eurusd_meta(), risk_percent=1.0, stop_buffer_price=0.0001,
        market_structure_config=_SWEEP_RETEST_TEST_CFG,
        daily_loss_guard=ctx.daily_loss_guard, open_position_guard=ctx.open_position_guard,
    )

    before = evaluate_setup(**eval_kwargs)
    assert before.state != STATE_BLOCKED_OPEN_POSITION  # nothing open yet, per the SAME guard
    assert before.strategy_qualified is True  # this fixture reaches full qualification (ENTRY_READY)

    result = ctx.coordinator.submit(_forex_proposal(setup_id="fill-1"), user_confirmed=True)
    assert result.status == STATUS_EXECUTION_DELEGATED
    assert ctx.open_position_guard.is_blocked() is True  # the coordinator's own fill just opened it

    after = evaluate_setup(**eval_kwargs)
    assert after.state == STATE_BLOCKED_OPEN_POSITION  # evaluation side sees the SAME block

    second_submit = ctx.coordinator.submit(_forex_proposal(setup_id="fill-2"), user_confirmed=True)
    assert second_submit.status == STATUS_BLOCKED_OPEN_POSITION  # coordinator agrees -- no drift


def test_runtime_context_shares_one_coordinator_instance_across_its_own_guards(tmp_path):
    """The composition root itself: ExecutionRuntimeContext.build()'s .coordinator is
    wired from the EXACT SAME guard instances exposed on the context, not copies."""
    open_guard = OpenPositionGuard(JsonKeyValueStore(str(tmp_path / "open.json")))
    daily_guard = DailyLossGuard(JsonKeyValueStore(str(tmp_path / "daily.json")), GLOBAL_LEDGER_STRATEGY_ID)
    close_ledger = CloseLedger(JsonKeyValueStore(str(tmp_path / "closed.json")))

    ctx = ExecutionRuntimeContext.build(open_guard, daily_guard, close_ledger)

    assert ctx.coordinator.open_position_guard is open_guard
    assert ctx.coordinator.daily_loss_guard is daily_guard
    assert ctx.coordinator.close_ledger is close_ledger

    open_guard.register_open("999", "SOME_STRATEGY", "EURUSD")
    assert ctx.coordinator.open_position_guard.is_blocked() is True  # same store, not a copy
