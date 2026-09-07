"""Tests for mt5.account_guard: fail-closed identity verification between the
connected MT5 account and the .env-configured broker/environment. No live MT5
connection or real credentials involved -- both mt5.config.load_mt5_config and
mt5.account.account are monkeypatched.
"""
from __future__ import annotations

from types import SimpleNamespace

from mt5 import account_guard as guard
from mt5.config import MT5Config, MT5ConfigError


def _config(**overrides):
    base = dict(broker="VANTAGE", environment="DEMO", login=12345678,
                password="s3cr3t", server="VantageMarkets-Demo", terminal_path=None)
    base.update(overrides)
    return MT5Config(**base)


def _account(**overrides):
    base = dict(login=12345678, server="VantageMarkets-Demo", is_demo=True,
                balance=10000.0, equity=10000.0, trade_allowed=True, is_hedging_account=False)
    base.update(overrides)
    return SimpleNamespace(**base)


def test_matching_account_passes(monkeypatch):
    monkeypatch.setattr(guard, "load_mt5_config", lambda: _config())
    monkeypatch.setattr(guard, "get_account", lambda: _account())

    assert guard.verify_configured_account() is None


def test_login_mismatch_blocks(monkeypatch):
    monkeypatch.setattr(guard, "load_mt5_config", lambda: _config())
    monkeypatch.setattr(guard, "get_account", lambda: _account(login=99999999))

    assert guard.verify_configured_account() == guard.REASON_LOGIN_MISMATCH


def test_server_mismatch_blocks(monkeypatch):
    monkeypatch.setattr(guard, "load_mt5_config", lambda: _config())
    monkeypatch.setattr(guard, "get_account", lambda: _account(server="SomeOtherBroker-Demo"))

    assert guard.verify_configured_account() == guard.REASON_SERVER_MISMATCH


def test_environment_mismatch_blocks_when_config_says_demo_but_account_is_live(monkeypatch):
    monkeypatch.setattr(guard, "load_mt5_config", lambda: _config(environment="DEMO"))
    monkeypatch.setattr(guard, "get_account", lambda: _account(is_demo=False))

    assert guard.verify_configured_account() == guard.REASON_ENVIRONMENT_MISMATCH


def test_environment_mismatch_blocks_when_config_says_live_but_account_is_demo(monkeypatch):
    monkeypatch.setattr(guard, "load_mt5_config", lambda: _config(environment="LIVE"))
    monkeypatch.setattr(guard, "get_account", lambda: _account(is_demo=True))

    assert guard.verify_configured_account() == guard.REASON_ENVIRONMENT_MISMATCH


def test_config_error_surfaces_as_reason_code_not_exception(monkeypatch):
    def _raise():
        raise MT5ConfigError("CONFIG_ERROR: MT5_LOGIN is not set")

    monkeypatch.setattr(guard, "load_mt5_config", _raise)

    assert guard.verify_configured_account() == guard.REASON_CONFIG_ERROR


def test_account_unavailable_surfaces_as_reason_code_not_exception(monkeypatch):
    monkeypatch.setattr(guard, "load_mt5_config", lambda: _config())

    def _raise():
        raise RuntimeError("ACCOUNT_INFO_UNAVAILABLE")

    monkeypatch.setattr(guard, "get_account", _raise)

    assert guard.verify_configured_account() == guard.REASON_ACCOUNT_UNAVAILABLE
