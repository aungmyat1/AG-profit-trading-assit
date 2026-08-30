"""AG_DEMO_EXECUTION_SAFETY_V1 (2026-08-28): refusal-behavior tests for the execution
layer. Complements tests/test_assistant_proposal_execution.py and
tests/test_execution_mt5_gateway.py rather than duplicating their coverage --
conservative volume normalization and broker-min-volume-without-forcing are already
proven at the trade_management.sizing layer by
tests/test_trade_management_pretrade.py::test_normalization_rounds_down_never_up and
::test_normalization_below_min_is_size_unavailable; this file adds the executor-level
and broker-reconciliation behaviors those don't reach.

MT5 I/O is monkeypatched throughout -- no live terminal connection needed.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from assistant.analysis_models import PROPOSAL_READY, TradeCandidate, TradeProposal
from execution import executor
from execution.models import ExecutionSource, OrderSendResult, TradeCommand
from mt5.symbol_resolver import SymbolMeta
from trade_management.sizing import evaluate_sizing


@pytest.fixture(autouse=True)
def _isolated_execution_claim(monkeypatch):
    monkeypatch.setattr(executor.journal, "claim_command", lambda command_id: True)


def _eurusd_meta(**overrides):
    fields = dict(symbol="EURUSD", tick_size=1e-5, tick_value=1.0, contract_size=100000.0,
                  volume_min=0.01, volume_max=100.0, volume_step=0.01, digits=5, point=1e-5)
    fields.update(overrides)
    return SymbolMeta(**fields)


def _proposal(symbol="EURUSD", direction="SHORT", entry=1.16442, sl=1.16474, tp=1.16346,
              risk_percent=0.5, equity=1000.0, age_seconds=0, ttl_minutes=15, status=PROPOSAL_READY,
              symbol_meta=None):
    now = datetime.now(timezone.utc) - timedelta(seconds=age_seconds)
    candidate = TradeCandidate(
        direction=direction, entry_price=entry, stop_loss=sl, take_profit=tp,
        risk_percent=risk_percent, equity=equity, symbol_meta=symbol_meta or _eurusd_meta(),
    )
    return TradeProposal(
        proposal_id="AGP-SAFETY-1", created_at=now, expires_at=now + timedelta(minutes=ttl_minutes),
        symbol=symbol, timeframe="M15", candidate=candidate, status=status,
    )


def _fresh_store(proposal=None):
    store = executor.ProposalStore()
    if proposal is not None:
        store.put(proposal)
    return store


def _no_broker_calls(monkeypatch):
    """Ensures reconciliation never masks the assertion under test."""
    monkeypatch.setattr(executor, "get_positions", lambda **kw: [])
    monkeypatch.setattr(executor, "deals_for_symbol", lambda symbol, **kw: [])


# =============================================================== TEST 1 -- expired proposal

def test_expired_proposal_blocks_before_order_open(monkeypatch):
    # expires_at already in the past at construction time (deterministic, no sleep) --
    # age itself stays near-zero so this exercises the EXPIRED branch specifically, not
    # the separate max-age branch.
    store = _fresh_store(_proposal(ttl_minutes=-1))
    _no_broker_calls(monkeypatch)
    monkeypatch.setattr(executor, "get_tick", lambda symbol: SimpleNamespace(
        bid=1.16442, ask=1.16456, spread_points=13))
    calls = []
    monkeypatch.setattr(executor.mt5_gateway, "order_open", lambda **kw: calls.append(kw))
    monkeypatch.setattr(executor.journal, "record_event", lambda *a, **kw: None)
    monkeypatch.setattr(executor.journal, "has_executed", lambda command_id: False)

    command = TradeCommand(command_id="exp-1", action="OPEN", symbol="EURUSD",
                            source=ExecutionSource.ASSISTANT_PROPOSAL, proposal_id="AGP-SAFETY-1")
    report = executor.execute(command, user_confirmed=True, proposal_store=store)

    assert report.status == "REJECTED"
    assert report.gate_reason_code == "PROPOSAL_STALE_EXPIRED"
    assert calls == []  # order_open (and therefore order_check/order_send) never reached
    assert store.get("AGP-SAFETY-1").status == "STALE"


# =============================================================== TEST 2 -- entry deviation

@pytest.mark.parametrize("side,quote_field", [("SELL", "bid"), ("BUY", "ask")])
def test_entry_deviation_uses_correct_market_side(monkeypatch, side, quote_field):
    entry = 1.16442
    store = _fresh_store(_proposal(direction=("SHORT" if side == "SELL" else "LONG"), entry=entry))
    _no_broker_calls(monkeypatch)
    far_price = entry + 0.01  # far beyond any tolerance
    tick_kwargs = {"bid": far_price, "ask": far_price, "spread_points": 10}
    monkeypatch.setattr(executor, "get_tick", lambda symbol: SimpleNamespace(**tick_kwargs))
    calls = []
    monkeypatch.setattr(executor.mt5_gateway, "order_open", lambda **kw: calls.append(kw))
    monkeypatch.setattr(executor.journal, "record_event", lambda *a, **kw: None)
    monkeypatch.setattr(executor.journal, "has_executed", lambda command_id: False)

    command = TradeCommand(command_id=f"dev-{side}", action="OPEN", symbol="EURUSD",
                            source=ExecutionSource.ASSISTANT_PROPOSAL, proposal_id="AGP-SAFETY-1")
    report = executor.execute(command, user_confirmed=True, proposal_store=store)

    assert report.status == "REJECTED"
    assert report.gate_reason_code == "PROPOSAL_STALE_PRICE_DEVIATION"
    assert calls == []


@pytest.mark.parametrize("deviation_mult,expect_blocked", [
    (1.0, False),   # exactly at tolerance -- inclusive boundary, allowed through this gate
    (1.0001, True),  # just past tolerance -- blocked
])
def test_entry_deviation_boundary_is_inclusive_at_exact_tolerance(monkeypatch, deviation_mult, expect_blocked):
    entry = 1.16442
    spread_points, point = 10, 1e-5
    tolerance = max(5 * spread_points * point, 10 * point)  # matches executor.py's own formula
    store = _fresh_store(_proposal(direction="SHORT", entry=entry,
                                    symbol_meta=_eurusd_meta(point=point)))
    _no_broker_calls(monkeypatch)
    price = entry + tolerance * deviation_mult
    monkeypatch.setattr(executor, "get_tick", lambda symbol: SimpleNamespace(
        bid=price, ask=price, spread_points=spread_points))
    calls = []
    monkeypatch.setattr(executor.mt5_gateway, "order_open", lambda **kw: calls.append(kw) or OrderSendResult(
        status="EXECUTED", reason_code="ORDER_SEND_DONE", symbol="EURUSD", ticket=1, deal_id=2,
        filled_volume=0.01, fill_price=price))
    monkeypatch.setattr(executor.journal, "record_event", lambda *a, **kw: None)
    monkeypatch.setattr(executor.journal, "has_executed", lambda command_id: False)
    monkeypatch.setattr(executor, "evaluate_trade_management", lambda request: _ready_tm_result())

    command = TradeCommand(command_id=f"bound-{deviation_mult}", action="OPEN", symbol="EURUSD",
                            source=ExecutionSource.ASSISTANT_PROPOSAL, proposal_id="AGP-SAFETY-1",
                            volume=0.01)
    report = executor.execute(command, user_confirmed=True, proposal_store=store)

    if expect_blocked:
        assert report.status == "REJECTED"
        assert report.gate_reason_code == "PROPOSAL_STALE_PRICE_DEVIATION"
        assert calls == []
    else:
        assert calls != []  # reached order_open -- not blocked by staleness


def _ready_tm_result():
    from trade_management.models import (
        GEOMETRY_VALID, OVERALL_READY, PositionSizing, PositionStateAdvisory,
        SIZING_NOT_REQUESTED, TradeGeometry, TradeManagementResult,
    )
    return TradeManagementResult(
        symbol="EURUSD", direction="SHORT", overall_status=OVERALL_READY,
        geometry=TradeGeometry(status=GEOMETRY_VALID, direction="SHORT", entry=1.16442,
                                stop_loss=1.16474, take_profit=1.16346),
        sizing=PositionSizing(status=SIZING_NOT_REQUESTED),
        position_state=PositionStateAdvisory(status="NOT_EVALUATED"),
    )


# =============================================================== TEST 3 -- risk overshoot invariant

@pytest.mark.parametrize("entry,sl,equity,risk_pct,volume_step,tick_value,tick_size", [
    (1.17000, 1.16750, 1000.0, 1.0, 0.01, 1.0, 1e-5),
    (1.17000, 1.16999625, 1000.0, 1.0, 0.01, 1.0, 1e-5),   # raw ~0.037 -- must floor
    (996.79, 997.29, 5000.0, 0.5, 0.01, 1.0, 0.01),         # XAUUSD-shaped tick economics
    (1.17000, 1.16900, 250.0, 2.0, 0.10, 1.0, 1e-5),
    (150.123, 150.623, 10000.0, 0.25, 0.01, 6.5, 0.01),     # USDJPY-shaped (non-USD-quote tick_value)
])
def test_normalized_volume_never_exceeds_requested_risk(entry, sl, equity, risk_pct, volume_step,
                                                          tick_value, tick_size):
    meta = _eurusd_meta(volume_step=volume_step, tick_value=tick_value, tick_size=tick_size)
    result = evaluate_sizing(entry, sl, equity, risk_pct, None, meta)
    if result.status != "READY":
        return  # legitimately unavailable (e.g. below broker min) -- covered by Test 4
    requested_risk_amount = equity * (risk_pct / 100.0)
    assert result.actual_risk_amount <= requested_risk_amount + 1e-6
    assert result.actual_risk_percent <= risk_pct + 1e-6
    assert result.normalized_volume <= result.raw_volume + 1e-9  # floor, never round up


# =============================================================== TEST 4 -- min lot exceeds risk

def test_min_lot_exceeds_risk_blocks_before_order_open(monkeypatch):
    # risk_budget so small that even volume_min would overspend it -- evaluate_sizing
    # must refuse rather than force volume_min (already proven at the sizing layer by
    # tests/test_trade_management_pretrade.py::test_normalization_below_min_is_size_unavailable;
    # this proves the SAME refusal survives all the way through executor.execute()).
    store = _fresh_store(_proposal(direction="LONG", entry=1.17000, sl=1.16999, tp=None,
                                    equity=0.5, risk_percent=1.0))
    _no_broker_calls(monkeypatch)
    monkeypatch.setattr(executor, "get_tick", lambda symbol: SimpleNamespace(
        bid=1.17000, ask=1.17001, spread_points=1))
    monkeypatch.setattr(executor, "_resolve_equity_and_symbol_meta",
                         lambda symbol: (0.5, _eurusd_meta(), None))
    calls = []
    monkeypatch.setattr(executor.mt5_gateway, "order_open", lambda **kw: calls.append(kw))
    monkeypatch.setattr(executor.journal, "record_event", lambda *a, **kw: None)
    monkeypatch.setattr(executor.journal, "has_executed", lambda command_id: False)

    command = TradeCommand(command_id="minvol-1", action="OPEN", symbol="EURUSD",
                            source=ExecutionSource.ASSISTANT_PROPOSAL, proposal_id="AGP-SAFETY-1")
    report = executor.execute(command, user_confirmed=True, proposal_store=store)

    assert report.status == "REJECTED"
    assert report.gate_reason_code == "VOLUME_BELOW_MIN"
    assert calls == []


# =============================================================== TEST 5 -- duplicate matrix

def test_duplicate_matrix_a_same_command_id_same_proposal(monkeypatch):
    proposal = _proposal(status="EXECUTED")  # already executed by a prior command
    store = _fresh_store(proposal)
    _no_broker_calls(monkeypatch)
    calls = []
    monkeypatch.setattr(executor.mt5_gateway, "order_open", lambda **kw: calls.append(kw))
    monkeypatch.setattr(executor.journal, "record_event", lambda *a, **kw: None)
    monkeypatch.setattr(executor.journal, "has_executed", lambda command_id: command_id == "same-id")

    command = TradeCommand(command_id="same-id", action="OPEN", symbol="EURUSD",
                            source=ExecutionSource.ASSISTANT_PROPOSAL, proposal_id="AGP-SAFETY-1")
    report = executor.execute(command, user_confirmed=True, proposal_store=store)

    assert report.status == "REJECTED"
    assert report.gate_reason_code == "DUPLICATE_COMMAND_BLOCKED"
    assert calls == []


def test_duplicate_matrix_d_repeat_after_close_still_blocked(monkeypatch):
    # CLOSE never touches proposal state -- an executed-then-closed proposal must stay
    # permanently blocked against re-execution (broker history already shows it happened).
    proposal = _proposal(status="EXECUTED")
    store = _fresh_store(proposal)
    _no_broker_calls(monkeypatch)
    calls = []
    monkeypatch.setattr(executor.mt5_gateway, "order_open", lambda **kw: calls.append(kw))
    monkeypatch.setattr(executor.journal, "record_event", lambda *a, **kw: None)
    monkeypatch.setattr(executor.journal, "has_executed", lambda command_id: False)  # fresh command_id

    command = TradeCommand(command_id="post-close-retry", action="OPEN", symbol="EURUSD",
                            source=ExecutionSource.ASSISTANT_PROPOSAL, proposal_id="AGP-SAFETY-1")
    report = executor.execute(command, user_confirmed=True, proposal_store=store)

    assert report.status == "REJECTED"
    assert report.gate_reason_code == "DUPLICATE_COMMAND_BLOCKED"
    assert calls == []


# =============================================================== TEST 7 -- actual fill reconciliation

def test_fill_evidence_reports_slippage_and_actual_risk():
    command = TradeCommand(command_id="fill-1", action="OPEN", symbol="EURUSD",
                            source=ExecutionSource.USER_EXPLICIT_ORDER, side="SELL",
                            sl=1.16500, volume=0.10)
    # requested/estimated entry 1.16450, actual fill worse (more slippage) at 1.16460 --
    # SELL fills lower being "worse" would be 1.16440; use a BUY-shaped worse fill for
    # SELL (fill price further from SL, i.e. smaller distance) to prove the number moves.
    result = OrderSendResult(status="EXECUTED", reason_code="ORDER_SEND_DONE", symbol="EURUSD",
                              side="SELL", filled_volume=0.10, fill_price=1.16480, ticket=1, deal_id=2)
    meta = _eurusd_meta()
    evidence = executor._fill_evidence(command, result, requested_entry=1.16450,
                                        equity=1000.0, symbol_meta=meta)

    assert evidence["slippage_points"] == pytest.approx((1.16480 - 1.16450) / meta.point, abs=0.01)
    expected_distance = abs(1.16480 - 1.16500)
    assert evidence["actual_stop_distance"] == pytest.approx(expected_distance)
    expected_risk = 0.10 * expected_distance * (meta.tick_value / meta.tick_size)
    assert evidence["actual_risk_at_fill"] == pytest.approx(expected_risk, abs=0.01)
    assert evidence["actual_risk_percent_at_fill"] == pytest.approx(expected_risk / 1000.0 * 100.0, abs=0.01)


def test_fill_evidence_can_show_post_fill_risk_exceeding_pre_send_estimate():
    # Slippage that shrinks the stop distance increases risk beyond what pre-send sizing
    # assumed -- this must be reported honestly, never silently clamped to "still safe".
    command = TradeCommand(command_id="fill-2", action="OPEN", symbol="EURUSD",
                            source=ExecutionSource.USER_EXPLICIT_ORDER, side="SELL",
                            sl=1.16500, volume=0.10, risk_percent=0.1)
    # Pre-send: entry 1.16450 -> distance to SL 0.00050 -> risk $5 -> 0.5% of $1000.
    # Actual fill 1.16490 (worse) -> distance 0.00010 -> risk $1... use the OPPOSITE
    # direction of slippage to *increase* distance beyond plan instead:
    result = OrderSendResult(status="EXECUTED", reason_code="ORDER_SEND_DONE", symbol="EURUSD",
                              side="SELL", filled_volume=0.10, fill_price=1.16400, ticket=1, deal_id=2)
    meta = _eurusd_meta()
    evidence = executor._fill_evidence(command, result, requested_entry=1.16450,
                                        equity=1000.0, symbol_meta=meta)
    pre_send_estimate_pct = 0.1
    assert evidence["actual_risk_percent_at_fill"] > pre_send_estimate_pct


# =============================================================== TEST 8 -- restart/broker reconciliation

def test_restart_reconciliation_detects_broker_open_position(monkeypatch):
    command_id = "restart-1"
    tag = executor._comment_tag(command_id)
    fake_position = SimpleNamespace(symbol="EURUSD", type=1, volume=0.01, price_open=1.16450,
                                     sl=1.16500, tp=1.16400, ticket=555, comment=tag)
    monkeypatch.setattr(executor, "get_positions", lambda **kw: [fake_position])
    monkeypatch.setattr(executor, "deals_for_symbol", lambda symbol, **kw: [])
    monkeypatch.setattr(executor, "get_tick", lambda symbol: SimpleNamespace(
        bid=1.16450, ask=1.16464, spread_points=14))
    monkeypatch.setattr(executor.journal, "has_executed", lambda cid: False)  # local journal never wrote it
    monkeypatch.setattr(executor.journal, "record_event", lambda *a, **kw: None)
    send_calls = []
    monkeypatch.setattr(executor.mt5_gateway, "order_open", lambda **kw: send_calls.append(kw))

    command = TradeCommand(command_id=command_id, action="OPEN", symbol="EURUSD",
                            source=ExecutionSource.USER_EXPLICIT_ORDER, side="SELL",
                            sl=1.16500, volume=0.01)
    report = executor.execute(command, user_confirmed=True)

    assert report.status == "EXECUTED"
    assert report.gate_reason_code == "RECONCILED_FROM_BROKER_POSITION"
    assert report.result.ticket == 555
    assert send_calls == []  # order_open never called a second time


def test_restart_reconciliation_detects_broker_deal_history(monkeypatch):
    command_id = "restart-2"
    tag = executor._comment_tag(command_id)
    fake_deal = SimpleNamespace(symbol="EURUSD", type=1, volume=0.01, price=1.16450,
                                 ticket=9001, comment=tag, entry=0)
    monkeypatch.setattr(executor, "get_positions", lambda **kw: [])  # already closed
    monkeypatch.setattr(executor, "deals_for_symbol", lambda symbol, **kw: [fake_deal])
    monkeypatch.setattr(executor, "get_tick", lambda symbol: SimpleNamespace(
        bid=1.16450, ask=1.16464, spread_points=14))
    monkeypatch.setattr(executor.journal, "has_executed", lambda cid: False)
    monkeypatch.setattr(executor.journal, "record_event", lambda *a, **kw: None)
    send_calls = []
    monkeypatch.setattr(executor.mt5_gateway, "order_open", lambda **kw: send_calls.append(kw))

    command = TradeCommand(command_id=command_id, action="OPEN", symbol="EURUSD",
                            source=ExecutionSource.USER_EXPLICIT_ORDER, side="SELL",
                            sl=1.16500, volume=0.01)
    report = executor.execute(command, user_confirmed=True)

    assert report.status == "EXECUTED"
    assert report.gate_reason_code == "RECONCILED_FROM_BROKER_HISTORY"
    assert report.result.deal_id == 9001
    assert send_calls == []


def test_no_reconciliation_match_falls_through_to_normal_send(monkeypatch):
    _no_broker_calls(monkeypatch)
    monkeypatch.setattr(executor, "get_tick", lambda symbol: SimpleNamespace(
        bid=1.16450, ask=1.16464, spread_points=14))
    monkeypatch.setattr(executor.journal, "has_executed", lambda cid: False)
    monkeypatch.setattr(executor.journal, "record_event", lambda *a, **kw: None)
    sent = []

    def fake_order_open(**kwargs):
        sent.append(kwargs)
        return OrderSendResult(status="EXECUTED", reason_code="ORDER_SEND_DONE", symbol="EURUSD",
                                ticket=1, deal_id=2, filled_volume=0.01, fill_price=1.16450)

    monkeypatch.setattr(executor.mt5_gateway, "order_open", fake_order_open)

    command = TradeCommand(command_id="normal-1", action="OPEN", symbol="EURUSD",
                            source=ExecutionSource.USER_EXPLICIT_ORDER, side="SELL",
                            sl=1.16500, volume=0.01)
    report = executor.execute(command, user_confirmed=True)

    assert report.status == "EXECUTED"
    assert len(sent) == 1  # no false-positive reconciliation match blocked the real send


# =============================================================== TEST 9 -- real-account hard lock

def test_real_account_hard_lock_blocks_even_with_config_send_enabled(monkeypatch):
    # Exercises the REAL _account_authorized_for_send() logic (not a mocked reason
    # string) -- config.allow_order_send/mode are left at their real, committed-safe
    # defaults (both false / ANALYSIS), so this proves account classification is an
    # independent gate, not merely "config already blocks it anyway".
    from execution import mt5_gateway as gw

    fake_account = SimpleNamespace(is_demo=False)
    monkeypatch.setattr(gw, "get_account", lambda: fake_account)
    monkeypatch.setattr(gw, "_order_send_allowed", lambda: True)  # simulate config fully open
    send_calls = []
    import MetaTrader5 as mt5
    monkeypatch.setattr(mt5, "order_send", lambda req: send_calls.append(req))

    result = gw.order_open("EURUSD", "SELL", "MARKET", 0.01, entry=1.16450, sl=1.16500,
                            tp=None, magic_number=0, comment="test")

    assert result.status == "REJECTED"
    assert result.reason_code == "LIVE_EXECUTION_DISABLED"
    assert send_calls == []


# =============================================================== TEST 10 -- authorization recheck

def test_unauthorized_attempt_does_not_mutate_proposal_status(monkeypatch):
    store = _fresh_store(_proposal())
    _no_broker_calls(monkeypatch)
    command = TradeCommand(command_id="noauth-1", action="OPEN", symbol="EURUSD",
                            source=ExecutionSource.ASSISTANT_PROPOSAL, proposal_id="AGP-SAFETY-1")
    report = executor.execute(command, user_confirmed=False, proposal_store=store)

    assert report.status == "REJECTED"
    assert report.gate_reason_code == "EXECUTION_NOT_AUTHORIZED"
    assert store.get("AGP-SAFETY-1").status == PROPOSAL_READY  # untouched


def test_authorized_confirmation_for_nonexistent_proposal_blocked(monkeypatch):
    store = _fresh_store(_proposal())  # only AGP-SAFETY-1 exists
    _no_broker_calls(monkeypatch)
    calls = []
    monkeypatch.setattr(executor.mt5_gateway, "order_open", lambda **kw: calls.append(kw))

    command = TradeCommand(command_id="wrong-proposal", action="OPEN", symbol="EURUSD",
                            source=ExecutionSource.ASSISTANT_PROPOSAL, proposal_id="AGP-DOES-NOT-EXIST")
    report = executor.execute(command, user_confirmed=True, proposal_store=store)

    assert report.status == "REJECTED"
    assert report.gate_reason_code == "PROPOSAL_NOT_FOUND"
    assert calls == []
