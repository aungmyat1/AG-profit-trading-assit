"""Tests for mt5.management_gateway: the only module allowed to call
order_check/order_send for modify/partial-close/close (spec section 17-18). MT5's own
I/O functions are monkeypatched -- no live terminal connection needed -- but the real
`MetaTrader5` module (and its retcode/action constants) is used as-is.
"""
from __future__ import annotations

from types import SimpleNamespace

import MetaTrader5 as mt5

from mt5 import management_gateway as gw


def _authorize_demo(monkeypatch):
    monkeypatch.setattr(gw, "verify_configured_account", lambda: None)
    monkeypatch.setattr(gw, "get_account", lambda: SimpleNamespace(is_demo=True))


def test_default_config_is_dry_run_and_makes_no_broker_calls(monkeypatch):
    calls = []
    monkeypatch.setattr(mt5, "order_check", lambda req: calls.append("order_check"))
    monkeypatch.setattr(mt5, "order_send", lambda req: calls.append("order_send"))

    result = gw.modify_position_sl(123456789, "EURUSD", 1.17000)

    assert result.dry_run is True
    assert result.executed is False
    assert calls == []  # config/trading.yaml default is DRY_RUN -- must not touch the broker
    assert result.request["action"] == mt5.TRADE_ACTION_SLTP
    assert result.request["sl"] == 1.17000


def test_partial_close_dry_run_needs_no_connection(monkeypatch):
    # price is caller-supplied (spec: caller already knows current_price) -- must not
    # require mt5.symbol_info_tick, so a dry-run preview works with no live terminal.
    calls = []
    monkeypatch.setattr(mt5, "order_check", lambda req: calls.append("order_check"))
    monkeypatch.setattr(mt5, "order_send", lambda req: calls.append("order_send"))

    result = gw.partial_close_position(123456789, "EURUSD", "BUY", 0.30, price=1.1760)

    assert result.dry_run is True
    assert calls == []
    assert result.request["volume"] == 0.30
    assert result.request["price"] == 1.1760


def test_live_modify_sl_success(monkeypatch):
    monkeypatch.setattr(gw, "_live_management_allowed", lambda: True)
    _authorize_demo(monkeypatch)
    monkeypatch.setattr(gw, "_current_volume", lambda ticket: 0.10)
    monkeypatch.setattr(mt5, "order_check", lambda req: SimpleNamespace(retcode=0))
    monkeypatch.setattr(mt5, "order_send", lambda req: SimpleNamespace(retcode=mt5.TRADE_RETCODE_DONE, comment="ok"))

    result = gw.modify_position_sl(123456789, "EURUSD", 1.17000)

    assert result.dry_run is False
    assert result.executed is True
    assert result.violation is None


def test_live_partial_close_detects_volume_increase_violation(monkeypatch):
    # Simulate a broker anomaly where volume goes UP after a requested partial close --
    # the hard no-new-exposure guard (spec section 18) must catch this.
    monkeypatch.setattr(gw, "_live_management_allowed", lambda: True)
    _authorize_demo(monkeypatch)
    volumes = iter([0.40, 0.50])
    monkeypatch.setattr(gw, "_current_volume", lambda ticket: next(volumes))
    monkeypatch.setattr(mt5, "order_check", lambda req: SimpleNamespace(retcode=0))
    monkeypatch.setattr(mt5, "order_send", lambda req: SimpleNamespace(retcode=mt5.TRADE_RETCODE_DONE, comment="ok"))

    result = gw.partial_close_position(123456789, "EURUSD", "BUY", 0.30, price=1.1760)

    assert result.violation is not None
    assert "CRITICAL_MANAGEMENT_VIOLATION" in result.violation


def test_live_order_send_rejected(monkeypatch):
    monkeypatch.setattr(gw, "_live_management_allowed", lambda: True)
    _authorize_demo(monkeypatch)
    monkeypatch.setattr(gw, "_current_volume", lambda ticket: 0.40)
    monkeypatch.setattr(mt5, "order_check", lambda req: SimpleNamespace(retcode=0))
    monkeypatch.setattr(mt5, "order_send", lambda req: SimpleNamespace(retcode=10004, comment="requote"))

    result = gw.modify_position_sl(123456789, "EURUSD", 1.17000)

    assert result.executed is False
    assert result.retcode == 10004


def test_live_account_is_blocked_before_broker_calls(monkeypatch):
    calls = []
    monkeypatch.setattr(gw, "_live_management_allowed", lambda: True)
    monkeypatch.setattr(gw, "verify_configured_account", lambda: None)
    monkeypatch.setattr(gw, "get_account", lambda: SimpleNamespace(is_demo=False))
    monkeypatch.setattr(mt5, "order_check", lambda req: calls.append("order_check"))
    monkeypatch.setattr(mt5, "order_send", lambda req: calls.append("order_send"))

    result = gw.modify_position_sl(123456789, "EURUSD", 1.17000)

    assert result.executed is False
    assert result.comment == "LIVE_MANAGEMENT_DISABLED"
    assert calls == []
