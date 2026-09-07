"""Tests for mt5.config: env-driven broker/account identity, fail-closed on any missing
or invalid required variable. Never touches the real src/.env file -- _ensure_env_loaded
is monkeypatched to a no-op so tests only ever see the env vars they explicitly set.
"""
from __future__ import annotations

import pytest

from mt5 import config as cfg

_ENV_VARS = (
    "MT5_BROKER", "MT5_ENVIRONMENT", "MT5_TERMINAL_PATH",
    "VANTAGE-DEMO-LOGIN", "VANTAGE-DEMO_PASSWORD", "VANTAGE-DEMO_SERVER",
)


@pytest.fixture(autouse=True)
def _no_real_env_load(monkeypatch):
    # Prevent the real src/.env (which holds actual Vantage Demo credentials) from ever
    # being read during tests.
    monkeypatch.setattr(cfg, "_ensure_env_loaded", lambda: None)
    for var in _ENV_VARS:
        monkeypatch.delenv(var, raising=False)


def _set_valid_env(monkeypatch):
    monkeypatch.setenv("MT5_BROKER", "VANTAGE")
    monkeypatch.setenv("MT5_ENVIRONMENT", "DEMO")
    monkeypatch.setenv("VANTAGE-DEMO-LOGIN", "12345678")
    monkeypatch.setenv("VANTAGE-DEMO_PASSWORD", "s3cr3t")
    monkeypatch.setenv("VANTAGE-DEMO_SERVER", "VantageMarkets-Demo")


def test_valid_config_loads(monkeypatch):
    _set_valid_env(monkeypatch)

    config = cfg.load_mt5_config()

    assert config.broker == "VANTAGE"
    assert config.environment == "DEMO"
    assert config.login == 12345678
    assert config.password == "s3cr3t"
    assert config.server == "VantageMarkets-Demo"
    assert config.terminal_path is None


def test_terminal_path_optional_when_set(monkeypatch):
    _set_valid_env(monkeypatch)
    monkeypatch.setenv("MT5_TERMINAL_PATH", "C:/MT5/terminal64.exe")

    config = cfg.load_mt5_config()

    assert config.terminal_path == "C:/MT5/terminal64.exe"


@pytest.mark.parametrize("missing", ["MT5_BROKER", "VANTAGE-DEMO-LOGIN", "VANTAGE-DEMO_PASSWORD", "VANTAGE-DEMO_SERVER"])
def test_missing_required_variable_fails_closed(monkeypatch, missing):
    _set_valid_env(monkeypatch)
    monkeypatch.delenv(missing, raising=False)

    with pytest.raises(cfg.MT5ConfigError):
        cfg.load_mt5_config()


def test_invalid_environment_fails_closed(monkeypatch):
    _set_valid_env(monkeypatch)
    monkeypatch.setenv("MT5_ENVIRONMENT", "STAGING")

    with pytest.raises(cfg.MT5ConfigError):
        cfg.load_mt5_config()


def test_live_environment_fails_closed_no_live_credential_source(monkeypatch):
    _set_valid_env(monkeypatch)
    monkeypatch.setenv("MT5_ENVIRONMENT", "LIVE")

    with pytest.raises(cfg.MT5ConfigError):
        cfg.load_mt5_config()


def test_non_integer_login_fails_closed(monkeypatch):
    _set_valid_env(monkeypatch)
    monkeypatch.setenv("VANTAGE-DEMO-LOGIN", "not-a-number")

    with pytest.raises(cfg.MT5ConfigError):
        cfg.load_mt5_config()
