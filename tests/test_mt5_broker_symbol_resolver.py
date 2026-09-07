"""Tests for mt5.broker_symbol_resolver: canonical strategy symbol -> broker MT5 symbol
name, fail-closed on any unmapped (broker, symbol) pair.
"""
from __future__ import annotations

import pytest

from mt5 import broker_symbol_resolver as resolver


def test_unit_resolution_uses_configured_map(monkeypatch):
    monkeypatch.setattr(resolver, "_load_symbol_map", lambda: {"VANTAGE": {"EURUSD": "EURUSD.a"}})

    assert resolver.resolve_broker_symbol("EURUSD", "VANTAGE") == "EURUSD.a"


def test_unmapped_broker_fails_closed(monkeypatch):
    monkeypatch.setattr(resolver, "_load_symbol_map", lambda: {"VANTAGE": {"EURUSD": "EURUSD"}})

    with pytest.raises(resolver.BrokerSymbolMapError):
        resolver.resolve_broker_symbol("EURUSD", "SOME_OTHER_BROKER")


def test_unmapped_symbol_fails_closed(monkeypatch):
    monkeypatch.setattr(resolver, "_load_symbol_map", lambda: {"VANTAGE": {"EURUSD": "EURUSD"}})

    with pytest.raises(resolver.BrokerSymbolMapError):
        resolver.resolve_broker_symbol("XAUUSD", "VANTAGE")


# Integration: the real config/mt5.yaml symbol_map, captured read-only from the
# connected Vantage Demo account's live symbol_info() (2026-09-07) -- see PROJECT_STATUS.md.
@pytest.mark.parametrize("canonical,expected_broker_symbol", [
    ("EURUSD", "EURUSD"),
    ("GBPUSD", "GBPUSD"),
    ("BTCUSDT", "BTCUSD"),
    ("ETHUSDT", "ETHUSD"),
])
def test_real_vantage_symbol_map(canonical, expected_broker_symbol):
    assert resolver.resolve_broker_symbol(canonical, "VANTAGE") == expected_broker_symbol
