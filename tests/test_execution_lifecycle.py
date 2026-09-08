"""Tests for AG_GLOBAL_EXECUTION_LIFECYCLE_V1: execution.lifecycle + the coordinator wiring
that calls it (BROKER_FILL_CONFIRMED -> register_open, restart/periodic reconciliation ->
idempotent full-close -> realized-R recorded exactly once into the SHARED DailyLossGuard
ledger).

No live MT5 terminal anywhere here: positions_lookup/deals_lookup are always injected
fakes, same idiom tests/test_execution_coordinator.py and tests/test_execution_executor.py
already use for mt5_gateway/journal.
"""
from __future__ import annotations

import datetime as dt
from types import SimpleNamespace

import pytest

from execution import executor
from execution.adapter import TradeProposal
from execution.close_ledger import CloseLedger
from execution.coordinator import (
    GLOBAL_LEDGER_STRATEGY_ID,
    STATUS_BLOCKED_DAILY_LOSS,
    STATUS_EXECUTION_DELEGATED,
    STATUS_PROPOSAL_ONLY,
    ExecutionCoordinator,
)
from execution.daily_loss_guard import DailyLossGuard
from execution.lifecycle import (
    UNKNOWN_STRATEGY_ID,
    reconcile_closed_position,
    reconcile_open_positions,
    register_confirmed_fill,
)
from execution.models import ExecutionReport, ExecutionSource, OrderSendResult
from execution.position_guard import OpenPositionGuard
from runtime_state.store import JsonKeyValueStore
from strategy_engine.sweep_retest.profile import PROFILE_CRYPTO_PERP, PROFILE_FOREX
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
STRATEGY_A = "ST_ASIAN_SWEEP_5R_V1"
STRATEGY_B = "ST_LIQUIDITY_SWEEP_RETEST_V1"


def _deal(entry: int, profit: float):
    return SimpleNamespace(entry=entry, profit=profit)


def _position_row(ticket: int, symbol="EURUSD", volume=0.5, comment=""):
    return SimpleNamespace(ticket=ticket, symbol=symbol, volume=volume, comment=comment)


def _coordinator(tmp_path) -> ExecutionCoordinator:
    return ExecutionCoordinator(
        open_position_guard=OpenPositionGuard(JsonKeyValueStore(str(tmp_path / "open_positions.json"))),
        daily_loss_guard=DailyLossGuard(JsonKeyValueStore(str(tmp_path / "daily_r.json")), GLOBAL_LEDGER_STRATEGY_ID),
        close_ledger=CloseLedger(JsonKeyValueStore(str(tmp_path / "closed_r.json"))),
    )


def _forex_proposal(**overrides) -> TradeProposal:
    fields = dict(
        setup_id="EURUSD:2026-01-05:001", strategy_id=STRATEGY_B, symbol="EURUSD",
        profile_id=PROFILE_FOREX, direction="LONG", entry=1.1000, stop_loss=1.0950,
        tp1=1.1050, tp2=1.1100, volume=0.5, risk_amount=100.0,
    )
    fields.update(overrides)
    return TradeProposal(**fields)


def _crypto_proposal(**overrides) -> TradeProposal:
    fields = dict(
        setup_id="BTCUSDT:2026-01-05:001", strategy_id=STRATEGY_B, symbol="BTCUSDT",
        profile_id=PROFILE_CRYPTO_PERP, direction="SHORT", entry=42000.0, stop_loss=42200.0,
        tp1=41500.0, tp2=41000.0, volume=0.01, risk_amount=50.0,
    )
    fields.update(overrides)
    return TradeProposal(**fields)


def _fake_tm_result(direction, entry, sl, tp) -> TradeManagementResult:
    return TradeManagementResult(
        symbol="EURUSD", direction=direction, overall_status=OVERALL_READY,
        geometry=TradeGeometry(status=GEOMETRY_VALID, direction=direction, entry=entry,
                                stop_loss=sl, take_profit=tp),
        sizing=PositionSizing(status=SIZING_NOT_REQUESTED),
        position_state=PositionStateAdvisory(status="NOT_EVALUATED"),
    )


def _mock_geometry(monkeypatch, direction, entry, sl, tp):
    monkeypatch.setattr(executor, "evaluate_trade_management",
                         lambda request: _fake_tm_result(direction, entry, sl, tp))


def _mock_order_open(monkeypatch, **result_overrides):
    fields = dict(status="EXECUTED", reason_code="ORDER_SEND_DONE", symbol="EURUSD",
                  side="BUY", filled_volume=0.5, fill_price=1.1000, ticket=777, deal_id=999,
                  broker_retcode=10009)
    fields.update(result_overrides)
    monkeypatch.setattr(executor.mt5_gateway, "order_open", lambda **kwargs: OrderSendResult(**fields))


@pytest.fixture(autouse=True)
def _isolated_journal(monkeypatch):
    monkeypatch.setattr(executor.journal, "claim_command", lambda command_id: True)
    monkeypatch.setattr(executor.journal, "has_executed", lambda command_id: False)
    monkeypatch.setattr(executor.journal, "record_event", lambda *a, **kw: None)
    # execution.executor._reconcile_via_broker (AG2 fail-closed fix) now distinguishes a
    # genuine "broker confirmed no match" from a lookup FAILURE -- without a live MT5
    # terminal, the real get_positions()/deals_for_symbol() calls raise, which the fixed
    # executor correctly treats as STATE_AMBIGUOUS and rejects rather than silently
    # falling through. Mock them empty so these tests keep exercising CONFIRMED_ABSENT.
    monkeypatch.setattr(executor, "get_positions", lambda **kw: [])
    monkeypatch.setattr(executor, "deals_for_symbol", lambda symbol, **kw: [])


def _executed_report(ticket=777) -> ExecutionReport:
    return ExecutionReport(
        command_id="cmd-1", source=ExecutionSource.USER_EXPLICIT_ORDER, status="EXECUTED",
        gate_reason_code="ORDER_SEND_DONE",
        result=OrderSendResult(status="EXECUTED", reason_code="ORDER_SEND_DONE", symbol="EURUSD",
                                side="BUY", filled_volume=0.5, fill_price=1.1000, ticket=ticket),
    )


# ============================================================================= fill registration (Tests 5, 6)

def test_confirmed_fill_registers_open_position(tmp_path):
    coordinator = _coordinator(tmp_path)
    proposal = _forex_proposal()
    position_id = register_confirmed_fill(coordinator.open_position_guard, proposal, _executed_report(ticket=777))

    assert position_id == "777"
    record = coordinator.open_position_guard.store.get("777")
    assert record["strategy_id"] == STRATEGY_B
    assert record["setup_id"] == proposal.setup_id
    assert record["risk_amount"] == pytest.approx(100.0)
    assert coordinator.open_position_guard.is_blocked() is True


def test_submission_without_confirmed_fill_creates_no_open_lock(monkeypatch, tmp_path):
    coordinator = _coordinator(tmp_path)
    proposal = _forex_proposal()
    _mock_geometry(monkeypatch, "LONG", proposal.entry, proposal.stop_loss, proposal.tp1)

    result = coordinator.submit(proposal, user_confirmed=False)  # no order_open mocked -> would blow up if reached

    assert result.status == "CONFIRMATION_REQUIRED"
    assert coordinator.open_position_guard.store.all() == {}


def test_end_to_end_submit_registers_open_position_on_real_fill(monkeypatch, tmp_path):
    coordinator = _coordinator(tmp_path)
    proposal = _forex_proposal()
    _mock_geometry(monkeypatch, "LONG", proposal.entry, proposal.stop_loss, proposal.tp1)
    _mock_order_open(monkeypatch, ticket=888)

    result = coordinator.submit(proposal, user_confirmed=True)

    assert result.status == STATUS_EXECUTION_DELEGATED
    assert coordinator.open_position_guard.store.get("888") is not None
    assert coordinator.open_position_guard.is_blocked() is True


# ============================================================================= partial vs full close (Tests 7, 8)

def test_partial_close_keeps_guard_active(tmp_path):
    coordinator = _coordinator(tmp_path)
    coordinator.open_position_guard.register_open("777", STRATEGY_B, "EURUSD",
                                                    setup_id="s1", risk_amount=100.0, volume=1.0)

    # Broker still reports the ticket, just at reduced (post-TP1) volume.
    results = reconcile_open_positions(
        coordinator.open_position_guard, coordinator.daily_loss_guard, coordinator.close_ledger,
        positions_lookup=lambda ticket=None: [_position_row(777, volume=0.25)] if ticket == 777 else [],
        deals_lookup=lambda ticket: [],
    )

    assert results[0]["status"] == "STILL_OPEN"
    assert coordinator.open_position_guard.is_blocked() is True
    assert coordinator.daily_loss_guard.realized_r(dt.date.today()) == 0.0


def test_full_close_clears_guard_and_records_realized_r_once(tmp_path):
    coordinator = _coordinator(tmp_path)
    coordinator.open_position_guard.register_open("777", STRATEGY_B, "EURUSD",
                                                    setup_id="s1", risk_amount=10.0, volume=1.0)

    # TP1 partial +$5, runner close +$10 -> total +$15 realized PnL on $10 original risk -> +1.5R.
    deals = [_deal(entry=0, profit=0.0), _deal(entry=1, profit=5.0), _deal(entry=1, profit=10.0)]
    day = dt.date(2026, 1, 5)
    results = reconcile_open_positions(
        coordinator.open_position_guard, coordinator.daily_loss_guard, coordinator.close_ledger,
        positions_lookup=lambda ticket=None: [] if ticket == 777 else [],
        deals_lookup=lambda ticket: deals, now=dt.datetime(2026, 1, 5, 12, tzinfo=UTC),
    )

    assert results[0]["status"] == "CLOSED_RECORDED"
    assert results[0]["realized_r"] == pytest.approx(1.5)
    assert coordinator.open_position_guard.store.all() == {}
    assert coordinator.open_position_guard.is_blocked() is False
    assert coordinator.daily_loss_guard.realized_r(day) == pytest.approx(1.5)
    assert coordinator.close_ledger.is_recorded("777") is True


def test_duplicate_close_does_not_double_count_r(tmp_path):
    coordinator = _coordinator(tmp_path)
    coordinator.open_position_guard.register_open("777", STRATEGY_B, "EURUSD", risk_amount=10.0)
    day = dt.date(2026, 1, 5)
    deals = [_deal(entry=1, profit=10.0)]

    first = reconcile_closed_position(
        coordinator.open_position_guard, coordinator.daily_loss_guard, coordinator.close_ledger,
        "777", {"risk_amount": 10.0, "strategy_id": STRATEGY_B, "symbol": "EURUSD"},
        deals_lookup=lambda ticket: deals, now=dt.datetime(2026, 1, 5, tzinfo=UTC),
    )
    assert first["status"] == "CLOSED_RECORDED"
    assert coordinator.daily_loss_guard.realized_r(day) == pytest.approx(1.0)

    # Replayed close observation for the SAME position_id (e.g. a re-run reconciliation
    # pass, or a duplicate broker notification) must have ZERO additional effect.
    second = reconcile_closed_position(
        coordinator.open_position_guard, coordinator.daily_loss_guard, coordinator.close_ledger,
        "777", {"risk_amount": 10.0, "strategy_id": STRATEGY_B, "symbol": "EURUSD"},
        deals_lookup=lambda ticket: deals, now=dt.datetime(2026, 1, 5, tzinfo=UTC),
    )
    assert second["status"] == "ALREADY_RECORDED"
    assert coordinator.daily_loss_guard.realized_r(day) == pytest.approx(1.0)  # unchanged, not doubled


def test_full_close_with_unavailable_risk_amount_is_documented_not_guessed(tmp_path):
    """A position restored by reconciliation alone (no surviving risk_amount) must never
    have its realized R approximated from anything -- spec: fail closed / document."""
    coordinator = _coordinator(tmp_path)
    coordinator.open_position_guard.register_open("777", UNKNOWN_STRATEGY_ID, "EURUSD", risk_amount=None)

    result = reconcile_closed_position(
        coordinator.open_position_guard, coordinator.daily_loss_guard, coordinator.close_ledger,
        "777", {"risk_amount": None, "strategy_id": UNKNOWN_STRATEGY_ID, "symbol": "EURUSD"},
        deals_lookup=lambda ticket: [_deal(entry=1, profit=10.0)],
    )

    assert result["status"] == "CLOSED_RISK_AMOUNT_MISSING"
    assert result["realized_r"] is None
    assert coordinator.open_position_guard.store.all() == {}  # still safely de-registered
    assert coordinator.daily_loss_guard.realized_r(dt.date.today()) == 0.0  # never guessed


# ============================================================================= restart reconciliation (Tests 11, 12)

def test_restart_with_live_broker_position_restores_missing_guard_state(tmp_path):
    coordinator = _coordinator(tmp_path)
    # No OpenPositionGuard record survived (e.g. crash between broker fill and
    # register_confirmed_fill) -- but the broker still reports a real, AG-tagged position.
    live_row = _position_row(777, symbol="EURUSD", volume=0.5, comment="AGT:EURUSD:2026-01-05:001")

    results = reconcile_open_positions(
        coordinator.open_position_guard, coordinator.daily_loss_guard, coordinator.close_ledger,
        positions_lookup=lambda ticket=None: [live_row] if ticket is None else [],
        deals_lookup=lambda ticket: [],
    )

    restored = [r for r in results if r["status"] == "MISSING_RECORD_RESTORED"]
    assert len(restored) == 1
    assert coordinator.open_position_guard.is_blocked() is True
    record = coordinator.open_position_guard.store.get("777")
    assert record["setup_id"] == "EURUSD:2026-01-05:001"
    assert record.get("risk_amount") is None  # genuinely unrecoverable -- documented gap, not guessed


def test_restart_with_non_ag_position_is_never_adopted(tmp_path):
    coordinator = _coordinator(tmp_path)
    foreign_row = _position_row(999, symbol="EURUSD", volume=0.1, comment="")  # no AGT: tag

    results = reconcile_open_positions(
        coordinator.open_position_guard, coordinator.daily_loss_guard, coordinator.close_ledger,
        positions_lookup=lambda ticket=None: [foreign_row] if ticket is None else [],
        deals_lookup=lambda ticket: [],
    )

    assert all(r["status"] != "MISSING_RECORD_RESTORED" for r in results)
    assert coordinator.open_position_guard.store.all() == {}


def test_restart_with_stale_persisted_open_removes_stale_state(tmp_path):
    coordinator = _coordinator(tmp_path)
    # A legacy-shaped record with no risk_amount (register_open's 3-arg form) whose ticket
    # the broker no longer reports at all.
    coordinator.open_position_guard.register_open("999999", STRATEGY_A, "GBPUSD")

    results = reconcile_open_positions(
        coordinator.open_position_guard, coordinator.daily_loss_guard, coordinator.close_ledger,
        positions_lookup=lambda ticket=None: [],
        deals_lookup=lambda ticket: [],  # no deal history either -- genuinely stale/fabricated
    )

    assert results[0]["status"] == "CLOSED_RISK_AMOUNT_MISSING"
    assert coordinator.open_position_guard.store.all() == {}
    assert coordinator.open_position_guard.is_blocked() is False
    assert coordinator.daily_loss_guard.realized_r(dt.date.today()) == 0.0  # no fabricated R


def test_broker_query_failure_fails_closed_and_never_removes_open_state(tmp_path):
    """AG_CURRENT_ROADMAP_IMPLEMENTATION_ACTION_PLAN_V1 Phase 1 items 4-5: UNKNOWN !=
    NOT_FOUND. A positions_lookup that raises (timeout/connection failure) must be
    reported as a distinct POSITION_QUERY_FAILED status and must leave the existing
    open-position guard record untouched -- unlike the genuinely-empty-list NOT_FOUND
    case (test_restart_with_stale_persisted_open_removes_stale_state above), which
    correctly does clear stale state. Conflating the two would let an ambiguous broker
    outcome silently look identical to "confirmed gone", which is exactly the condition
    that could let a caller believe a replacement order is safe to submit."""
    coordinator = _coordinator(tmp_path)
    coordinator.open_position_guard.register_open("777", STRATEGY_A, "EURUSD", risk_amount=100.0)

    def _raising_positions_lookup(ticket=None):
        raise RuntimeError("MT5_TIMEOUT: no response from terminal")

    results = reconcile_open_positions(
        coordinator.open_position_guard, coordinator.daily_loss_guard, coordinator.close_ledger,
        positions_lookup=_raising_positions_lookup,
        deals_lookup=lambda ticket: [],
    )

    assert results[0]["status"] == "POSITION_QUERY_FAILED"
    assert "error" in results[0]
    # Fail-closed: the record must still exist and the guard must still be blocked --
    # a query failure must never be indistinguishable from a confirmed close.
    assert coordinator.open_position_guard.store.get("777") is not None
    assert coordinator.open_position_guard.is_blocked() is True
    # No realized R was fabricated from an ambiguous outcome.
    assert coordinator.daily_loss_guard.realized_r(dt.date.today()) == 0.0


def test_broker_deals_query_failure_on_close_reports_distinct_status_not_not_found(tmp_path):
    """Same invariant as above, for reconcile_closed_position's own deals_lookup path
    (execution/lifecycle.py's DEALS_UNAVAILABLE branch) -- a deals-history query failure
    must never be reported or treated the same as "no deals exist for this close"."""
    coordinator = _coordinator(tmp_path)
    coordinator.open_position_guard.register_open("777", STRATEGY_A, "EURUSD", risk_amount=100.0)

    def _raising_deals_lookup(ticket):
        raise RuntimeError("MT5_TIMEOUT: history_deals_get unavailable")

    result = reconcile_closed_position(
        coordinator.open_position_guard, coordinator.daily_loss_guard, coordinator.close_ledger,
        "777", {"risk_amount": 100.0, "strategy_id": STRATEGY_A, "symbol": "EURUSD"},
        deals_lookup=_raising_deals_lookup,
    )

    assert result["status"] == "DEALS_UNAVAILABLE"
    assert "error" in result
    # Fail-closed: no realized R fabricated, and this ambiguous outcome is distinct from
    # a genuine "no deals" result -- a caller must not treat DEALS_UNAVAILABLE as CLOSED.
    assert coordinator.daily_loss_guard.realized_r(dt.date.today()) == 0.0


def test_restart_with_position_still_open_leaves_guard_untouched(tmp_path):
    coordinator = _coordinator(tmp_path)
    coordinator.open_position_guard.register_open("777", STRATEGY_B, "EURUSD", risk_amount=100.0)

    results = reconcile_open_positions(
        coordinator.open_position_guard, coordinator.daily_loss_guard, coordinator.close_ledger,
        positions_lookup=lambda ticket=None: [_position_row(777)] if ticket == 777 else [],
        deals_lookup=lambda ticket: [],
    )

    assert results[0]["status"] == "STILL_OPEN"
    assert coordinator.open_position_guard.store.get("777") is not None


# ============================================================================= cross-strategy daily loss via reconcile (Test 13)

def test_two_strategy_losses_via_reconciliation_block_subsequent_submission(monkeypatch, tmp_path):
    coordinator = _coordinator(tmp_path)
    day = dt.date(2026, 1, 5)
    now = dt.datetime(2026, 1, 5, 12, tzinfo=UTC)

    coordinator.open_position_guard.register_open("111", STRATEGY_A, "EURUSD", risk_amount=10.0)
    reconcile_closed_position(
        coordinator.open_position_guard, coordinator.daily_loss_guard, coordinator.close_ledger,
        "111", {"risk_amount": 10.0, "strategy_id": STRATEGY_A, "symbol": "EURUSD"},
        deals_lookup=lambda ticket: [_deal(entry=1, profit=-10.0)], now=now,
    )
    coordinator.open_position_guard.register_open("222", STRATEGY_B, "GBPUSD", risk_amount=10.0)
    reconcile_closed_position(
        coordinator.open_position_guard, coordinator.daily_loss_guard, coordinator.close_ledger,
        "222", {"risk_amount": 10.0, "strategy_id": STRATEGY_B, "symbol": "GBPUSD"},
        deals_lookup=lambda ticket: [_deal(entry=1, profit=-10.0)], now=now,
    )

    assert coordinator.daily_loss_guard.realized_r(day) == pytest.approx(-2.0)

    calls = []
    monkeypatch.setattr(executor.mt5_gateway, "order_open",
                         lambda **kwargs: calls.append(kwargs) or OrderSendResult(status="EXECUTED", reason_code="X", symbol="EURUSD"))
    result = coordinator.submit(_forex_proposal(strategy_id=STRATEGY_A), user_confirmed=True, now=now)

    assert result.status == STATUS_BLOCKED_DAILY_LOSS
    assert calls == []


# ============================================================================= crypto isolation (Tests 15, 16)

def test_crypto_proposal_does_not_affect_open_position_ledger(tmp_path):
    coordinator = _coordinator(tmp_path)
    result = coordinator.submit(_crypto_proposal(), user_confirmed=True)

    assert result.status == STATUS_PROPOSAL_ONLY
    assert coordinator.open_position_guard.store.all() == {}


def test_crypto_proposal_does_not_affect_realized_r_ledger(tmp_path):
    coordinator = _coordinator(tmp_path)
    coordinator.submit(_crypto_proposal(), user_confirmed=True)

    assert coordinator.daily_loss_guard.realized_r(dt.date.today()) == 0.0
    assert coordinator.close_ledger.store.all() == {}
