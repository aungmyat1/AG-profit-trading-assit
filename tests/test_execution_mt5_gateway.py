"""Tests for execution.mt5_gateway: the only module in execution/ allowed to call
order_check/order_send for OPENING a new position. Same mocking convention as
tests/test_management_gateway.py -- MT5's own I/O functions are monkeypatched, no live
terminal connection needed, but the real `MetaTrader5` module/constants are used as-is.
"""
from __future__ import annotations

from types import SimpleNamespace

import MetaTrader5 as mt5

from execution import mt5_gateway as gw


def test_default_config_is_dry_run_and_makes_no_broker_calls(monkeypatch):
    calls = []
    monkeypatch.setattr(mt5, "symbol_info_tick", lambda symbol: SimpleNamespace(bid=1.16442, ask=1.16456))
    monkeypatch.setattr(mt5, "order_check", lambda req: calls.append("order_check"))
    monkeypatch.setattr(mt5, "order_send", lambda req: calls.append("order_send"))

    result = gw.order_open("EURUSD", "SELL", "MARKET", 0.31, sl=1.16474, tp=1.16346,
                            magic_number=0, comment="test")

    assert result.status == "REJECTED"
    assert result.reason_code == "DRY_RUN"
    assert calls == []  # config/trading.yaml default (mode: ANALYSIS) -- must not touch the broker
    assert result.request["symbol"] == "EURUSD"
    assert result.request["sl"] == 1.16474


def test_order_check_not_allowed_by_default():
    result = gw.order_check({"action": mt5.TRADE_ACTION_DEAL})
    assert result.passed is False
    assert result.reason_code == "ORDER_CHECK_NOT_ALLOWED"


def test_live_order_open_success(monkeypatch):
    monkeypatch.setattr(gw, "_order_send_allowed", lambda: True)
    monkeypatch.setattr(gw, "_account_authorized_for_send", lambda: None)
    monkeypatch.setattr(mt5, "symbol_info_tick", lambda symbol: SimpleNamespace(bid=1.16442, ask=1.16456))
    monkeypatch.setattr(mt5, "order_check", lambda req: SimpleNamespace(retcode=0))
    monkeypatch.setattr(
        mt5, "order_send",
        lambda req: SimpleNamespace(retcode=mt5.TRADE_RETCODE_DONE, comment="ok",
                                     order=555, deal=999, volume=0.31, price=1.16442),
    )

    result = gw.order_open("EURUSD", "SELL", "MARKET", 0.31, sl=1.16474, tp=1.16346,
                            magic_number=0, comment="test")

    assert result.status == "EXECUTED"
    assert result.ticket == 555
    assert result.deal_id == 999
    assert result.filled_volume == 0.31


def test_order_check_failure_blocks_order_send(monkeypatch):
    monkeypatch.setattr(gw, "_order_send_allowed", lambda: True)
    monkeypatch.setattr(gw, "_account_authorized_for_send", lambda: None)
    monkeypatch.setattr(mt5, "symbol_info_tick", lambda symbol: SimpleNamespace(bid=1.16442, ask=1.16456))
    monkeypatch.setattr(mt5, "order_check", lambda req: SimpleNamespace(retcode=10013))
    send_calls = []
    monkeypatch.setattr(mt5, "order_send", lambda req: send_calls.append(req))

    result = gw.order_open("EURUSD", "SELL", "MARKET", 0.31, sl=1.16474, tp=1.16346,
                            magic_number=0, comment="test")

    assert result.status == "REJECTED"
    assert result.reason_code == "ORDER_CHECK_FAILED"
    assert send_calls == []


def test_live_execution_disabled_when_account_not_authorized(monkeypatch):
    # order_send_allowed (config) is True but the account gate says no -- e.g. connected
    # account is not demo and allow_live_trading is false.
    monkeypatch.setattr(gw, "_order_send_allowed", lambda: True)
    monkeypatch.setattr(gw, "_account_authorized_for_send", lambda: "LIVE_EXECUTION_DISABLED")
    send_calls = []
    monkeypatch.setattr(mt5, "order_send", lambda req: send_calls.append(req))

    result = gw.order_open("EURUSD", "SELL", "MARKET", 0.31, entry=1.16442, sl=1.16474,
                            tp=1.16346, magic_number=0, comment="test")

    assert result.status == "REJECTED"
    assert result.reason_code == "LIVE_EXECUTION_DISABLED"
    assert send_calls == []


def test_account_authorized_for_send_blocks_on_identity_mismatch(monkeypatch):
    # Real _account_authorized_for_send (not monkeypatched away) must consult
    # mt5.account_guard.verify_configured_account before its own demo/live check --
    # AG_UNIFIED_VANTAGE_MARKETS_DEMO_MT5_ACCOUNT_MIGRATION_V1.
    monkeypatch.setattr(gw, "verify_configured_account", lambda: "ACCOUNT_LOGIN_MISMATCH")

    assert gw._account_authorized_for_send() == "ACCOUNT_LOGIN_MISMATCH"


def test_account_authorized_for_send_proceeds_when_identity_matches(monkeypatch):
    monkeypatch.setattr(gw, "verify_configured_account", lambda: None)
    monkeypatch.setattr(gw, "get_account", lambda: SimpleNamespace(is_demo=True))

    assert gw._account_authorized_for_send() is None


def test_broker_rejected_order_send(monkeypatch):
    monkeypatch.setattr(gw, "_order_send_allowed", lambda: True)
    monkeypatch.setattr(gw, "_account_authorized_for_send", lambda: None)
    monkeypatch.setattr(mt5, "symbol_info_tick", lambda symbol: SimpleNamespace(bid=1.16442, ask=1.16456))
    monkeypatch.setattr(mt5, "order_check", lambda req: SimpleNamespace(retcode=0))
    monkeypatch.setattr(mt5, "order_send", lambda req: SimpleNamespace(retcode=10004, comment="requote"))

    result = gw.order_open("EURUSD", "SELL", "MARKET", 0.31, sl=1.16474, tp=1.16346,
                            magic_number=0, comment="test")

    assert result.status == "REJECTED"
    assert result.reason_code == "BROKER_REJECTED"
    assert result.broker_retcode == 10004
