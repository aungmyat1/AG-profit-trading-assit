"""Tests for strategy_manager.context_builder.build_context: success + fail-closed
paths. mt5.account/mt5.market_data calls are monkeypatched -- no live connection."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from mt5.account import Account, AccountError
from mt5.market_data import MarketDataError, Tick
from strategy_manager import context_builder
from assistant.models import CONTEXT_FAILED, CONTEXT_READY

_ACCOUNT = Account(login=123, server="Test-Demo", is_demo=True, balance=1000.0, equity=1000.0,
                    trade_allowed=True, is_hedging_account=True)


def _tick(age_seconds=0) -> Tick:
    now = datetime.now(timezone.utc) - timedelta(seconds=age_seconds)
    return Tick(symbol="EURUSD", time_utc=now, bid=1.1700, ask=1.1702, spread_points=2)


def test_build_context_success(monkeypatch):
    monkeypatch.setattr(context_builder, "get_account", lambda: _ACCOUNT)
    monkeypatch.setattr(context_builder, "get_tick", lambda symbol: _tick())

    ctx = context_builder.build_context("EURUSD")

    assert ctx.status == CONTEXT_READY
    assert ctx.account_login == 123 and ctx.account_is_demo is True
    assert ctx.current_bid == 1.1700


def test_build_context_account_unavailable(monkeypatch):
    def _raise():
        raise AccountError("ACCOUNT_INFO_UNAVAILABLE: (0) no info")
    monkeypatch.setattr(context_builder, "get_account", _raise)

    ctx = context_builder.build_context("EURUSD")
    assert ctx.status == CONTEXT_FAILED
    assert "ACCOUNT_INFO_UNAVAILABLE" in ctx.reason_codes


def test_build_context_tick_missing(monkeypatch):
    monkeypatch.setattr(context_builder, "get_account", lambda: _ACCOUNT)

    def _raise(symbol):
        raise MarketDataError("SYMBOL_NOT_FOUND", "symbol not found")
    monkeypatch.setattr(context_builder, "get_tick", _raise)

    ctx = context_builder.build_context("EURUSD")
    assert ctx.status == CONTEXT_FAILED


def test_build_context_stale_tick(monkeypatch):
    monkeypatch.setattr(context_builder, "get_account", lambda: _ACCOUNT)
    monkeypatch.setattr(context_builder, "get_tick", lambda symbol: _tick(age_seconds=99999))

    ctx = context_builder.build_context("EURUSD")
    assert ctx.status == CONTEXT_FAILED
