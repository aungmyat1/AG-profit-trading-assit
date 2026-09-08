"""Tests for execution.executor: TradeCommand -> gate -> mt5_gateway/management_gateway
-> journal -> ExecutionReport. mt5_gateway.order_open / mt5.management_gateway.close_position
/ mt5 account+tick reads are monkeypatched at the point executor.py imports them -- no
live MT5 terminal connection needed, matching tests/test_management_gateway.py's own
convention.
"""
from __future__ import annotations

import ast
import inspect
from types import SimpleNamespace

import pytest

import assistant.commands as commands_module
from execution import executor
from execution.models import ExecutionSource, OrderSendResult, TradeCommand
from mt5.management_gateway import GatewayResult
from trade_management.models import TradeGeometry, PositionSizing, PositionStateAdvisory
from trade_management.models import GEOMETRY_VALID, OVERALL_READY, SIZING_NOT_REQUESTED


@pytest.fixture(autouse=True)
def _isolated_execution_claim(monkeypatch):
    monkeypatch.setattr(executor.journal, "claim_command", lambda command_id: True)


def _fake_tm_result():
    from trade_management.models import TradeManagementResult
    return TradeManagementResult(
        symbol="EURUSD", direction="SHORT", overall_status=OVERALL_READY,
        geometry=TradeGeometry(status=GEOMETRY_VALID, direction="SHORT", entry=1.16442,
                                stop_loss=1.16474, take_profit=1.16346),
        sizing=PositionSizing(status=SIZING_NOT_REQUESTED),
        position_state=PositionStateAdvisory(status="NOT_EVALUATED"),
    )


def _open_command(command_id="cmd-1", source=ExecutionSource.USER_EXPLICIT_ORDER, **overrides):
    fields = dict(
        command_id=command_id, action="OPEN", symbol="EURUSD", source=source,
        side="SELL", order_type="MARKET", volume=0.31, entry=1.16442, sl=1.16474, tp=1.16346,
    )
    fields.update(overrides)
    return TradeCommand(**fields)


def test_no_authorization_blocks_order_send(monkeypatch):
    calls = []
    monkeypatch.setattr(executor.mt5_gateway, "order_open", lambda **kw: calls.append(kw))

    report = executor.execute(_open_command(), user_confirmed=False)

    assert report.status == "REJECTED"
    assert report.gate_reason_code == "EXECUTION_NOT_AUTHORIZED"
    assert calls == []


def test_direct_user_order_allowed_without_strategy_signal(monkeypatch):
    # USER_EXPLICIT_ORDER must never require entry-confirmation/strategy validation --
    # only geometry/sizing (trade_management.pretrade_engine).
    monkeypatch.setattr(executor, "evaluate_trade_management", lambda request: _fake_tm_result())
    monkeypatch.setattr(executor.journal, "has_executed", lambda command_id: False)
    monkeypatch.setattr(executor, "get_positions", lambda **kw: [])
    monkeypatch.setattr(executor, "deals_for_symbol", lambda symbol, **kw: [])
    events = []
    monkeypatch.setattr(executor.journal, "record_event", lambda command_id, event, **kw: events.append(event))

    sent = {}

    def fake_order_open(**kwargs):
        sent.update(kwargs)
        return OrderSendResult(status="EXECUTED", reason_code="ORDER_SEND_DONE", symbol="EURUSD",
                                side="SELL", requested_volume=0.31, filled_volume=0.31,
                                ticket=555, deal_id=999, broker_retcode=10009)

    monkeypatch.setattr(executor.mt5_gateway, "order_open", fake_order_open)

    report = executor.execute(_open_command(), user_confirmed=True)

    assert report.status == "EXECUTED"
    assert sent["symbol"] == "EURUSD"
    assert "ORDER_EXECUTED" in events


def test_explicit_execute_sends_order_exactly_once(monkeypatch):
    monkeypatch.setattr(executor, "evaluate_trade_management", lambda request: _fake_tm_result())
    monkeypatch.setattr(executor.journal, "has_executed", lambda command_id: False)
    monkeypatch.setattr(executor.journal, "record_event", lambda *a, **kw: None)
    monkeypatch.setattr(executor, "get_positions", lambda **kw: [])
    monkeypatch.setattr(executor, "deals_for_symbol", lambda symbol, **kw: [])

    call_count = {"n": 0}

    def fake_order_open(**kwargs):
        call_count["n"] += 1
        return OrderSendResult(status="EXECUTED", reason_code="ORDER_SEND_DONE", symbol="EURUSD",
                                side="SELL", requested_volume=0.31, ticket=1, deal_id=2)

    monkeypatch.setattr(executor.mt5_gateway, "order_open", fake_order_open)

    report = executor.execute(_open_command(), user_confirmed=True)

    assert report.status == "EXECUTED"
    assert call_count["n"] == 1


def test_broker_rejection_never_reports_executed(monkeypatch):
    monkeypatch.setattr(executor, "evaluate_trade_management", lambda request: _fake_tm_result())
    monkeypatch.setattr(executor.journal, "has_executed", lambda command_id: False)
    monkeypatch.setattr(executor, "get_positions", lambda **kw: [])
    monkeypatch.setattr(executor, "deals_for_symbol", lambda symbol, **kw: [])
    events = []
    monkeypatch.setattr(executor.journal, "record_event", lambda command_id, event, **kw: events.append(event))
    monkeypatch.setattr(
        executor.mt5_gateway, "order_open",
        lambda **kw: OrderSendResult(status="REJECTED", reason_code="ORDER_CHECK_FAILED", symbol="EURUSD"),
    )

    report = executor.execute(_open_command(), user_confirmed=True)

    assert report.status == "REJECTED"
    assert "ORDER_EXECUTED" not in events
    assert "ORDER_REJECTED" in events


def test_live_safety_block_surfaced_as_rejection(monkeypatch):
    monkeypatch.setattr(executor, "evaluate_trade_management", lambda request: _fake_tm_result())
    monkeypatch.setattr(executor.journal, "has_executed", lambda command_id: False)
    monkeypatch.setattr(executor.journal, "record_event", lambda *a, **kw: None)
    monkeypatch.setattr(executor, "get_positions", lambda **kw: [])
    monkeypatch.setattr(executor, "deals_for_symbol", lambda symbol, **kw: [])
    monkeypatch.setattr(
        executor.mt5_gateway, "order_open",
        lambda **kw: OrderSendResult(status="REJECTED", reason_code="LIVE_EXECUTION_DISABLED", symbol="EURUSD"),
    )

    report = executor.execute(_open_command(), user_confirmed=True)

    assert report.status == "REJECTED"
    assert report.gate_reason_code == "LIVE_EXECUTION_DISABLED"


def test_duplicate_command_id_blocked_second_time(monkeypatch):
    monkeypatch.setattr(executor, "evaluate_trade_management", lambda request: _fake_tm_result())
    monkeypatch.setattr(executor.journal, "record_event", lambda *a, **kw: None)
    monkeypatch.setattr(executor.journal, "has_executed", lambda command_id: command_id == "dup-1")

    calls = []
    monkeypatch.setattr(executor.mt5_gateway, "order_open", lambda **kw: calls.append(kw))

    report = executor.execute(_open_command(command_id="dup-1"), user_confirmed=True)

    assert report.status == "REJECTED"
    assert report.gate_reason_code == "DUPLICATE_COMMAND_BLOCKED"
    assert calls == []


def test_new_command_id_for_another_order_still_succeeds(monkeypatch):
    # "open another 0.31 lot SELL" -- a fresh command_id must not be blocked by an
    # unrelated already-executed command_id.
    monkeypatch.setattr(executor, "evaluate_trade_management", lambda request: _fake_tm_result())
    monkeypatch.setattr(executor.journal, "has_executed", lambda command_id: command_id == "dup-1")
    monkeypatch.setattr(executor.journal, "record_event", lambda *a, **kw: None)
    monkeypatch.setattr(executor, "get_positions", lambda **kw: [])
    monkeypatch.setattr(executor, "deals_for_symbol", lambda symbol, **kw: [])
    monkeypatch.setattr(
        executor.mt5_gateway, "order_open",
        lambda **kw: OrderSendResult(status="EXECUTED", reason_code="ORDER_SEND_DONE", symbol="EURUSD",
                                      ticket=2, deal_id=3),
    )

    report = executor.execute(_open_command(command_id="dup-2"), user_confirmed=True)

    assert report.status == "EXECUTED"


def test_close_delegates_to_management_gateway(monkeypatch):
    fake_row = SimpleNamespace(symbol="EURUSD", type=1, volume=0.31)  # type 1 == SELL position
    monkeypatch.setattr(executor, "get_positions", lambda ticket=None: [fake_row])
    monkeypatch.setattr(executor, "get_symbol_meta", lambda symbol: SimpleNamespace(
        volume_min=0.01, volume_max=100.0, volume_step=0.01))
    monkeypatch.setattr(executor, "get_tick", lambda symbol: SimpleNamespace(bid=1.16400, ask=1.16414, spread_points=14))
    monkeypatch.setattr(executor.journal, "record_event", lambda *a, **kw: None)

    close_calls = []

    def fake_close_position(ticket, symbol, direction, volume, price):
        close_calls.append((ticket, symbol, direction, volume, price))
        return GatewayResult(dry_run=False, request={}, executed=True, retcode=10009, comment="ok")

    monkeypatch.setattr(executor, "close_position", fake_close_position)

    command = TradeCommand(command_id="close-1", action="CLOSE", symbol="EURUSD",
                            source=ExecutionSource.USER_EXPLICIT_ORDER, position_ticket=987654321)
    report = executor.execute(command, user_confirmed=True)

    assert report.status == "EXECUTED"
    assert len(close_calls) == 1
    # SELL position (type==1) closes by buying back -- management_gateway itself flips
    # this again internally, executor just passes the position's own side through.
    assert close_calls[0][2] == "SELL"


def test_close_without_confirmation_blocked(monkeypatch):
    calls = []
    monkeypatch.setattr(executor, "close_position", lambda *a, **kw: calls.append(a))

    command = TradeCommand(command_id="close-2", action="CLOSE", symbol="EURUSD",
                            source=ExecutionSource.USER_EXPLICIT_ORDER, position_ticket=987654321)
    report = executor.execute(command, user_confirmed=False)

    assert report.status == "REJECTED"
    assert report.gate_reason_code == "EXECUTION_NOT_AUTHORIZED"
    assert calls == []


def test_build_proposal_never_calls_order_send_or_order_check():
    # Static check, no live MT5 needed -- same style as
    # tests/test_five_skill_runtime.py's own AST guardrail test.
    source = inspect.getsource(commands_module.build_proposal)
    tree = ast.parse(source)
    forbidden_calls = {"order_send", "order_check"}
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr in forbidden_calls:
            found.add(node.attr)
        if isinstance(node, ast.Name) and node.id in forbidden_calls:
            found.add(node.id)
    assert not found, f"build_proposal must never call {found}"
