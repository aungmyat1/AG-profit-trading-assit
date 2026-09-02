"""Tests for execution/crypto_metadata.py: ExchangeMetadataSource implementations and the
exchange-verified-metadata gate for crypto."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from execution.crypto_metadata import (
    LiveExchangeMetadataSource,
    OfflineFixtureMetadataSource,
    SyntheticMetadataError,
    binance_meta_to_symbol_meta,
    require_exchange_verified_metadata_for_crypto,
)
from execution_runtime.binance_usdtm_feed import default_symbol_meta, BinanceSymbolMeta, CANONICAL_SYMBOL
from mt5.symbol_resolver import METADATA_SOURCE_EXCHANGE_VERIFIED, METADATA_SOURCE_SYNTHETIC_RESEARCH


def test_offline_fixture_source_returns_fixed_record():
    fixture = default_symbol_meta()
    source = OfflineFixtureMetadataSource(fixture)
    assert source.get_symbol_meta(CANONICAL_SYMBOL) is fixture


def test_offline_fixture_source_rejects_mismatched_symbol():
    fixture = default_symbol_meta()
    source = OfflineFixtureMetadataSource(fixture)
    with pytest.raises(ValueError):
        source.get_symbol_meta("ETHUSDT")


def test_live_source_is_unimplemented_stub():
    source = LiveExchangeMetadataSource()
    with pytest.raises(NotImplementedError):
        source.get_symbol_meta(CANONICAL_SYMBOL)


def test_offline_default_meta_converts_to_synthetic_research_tag():
    """default_symbol_meta()'s source is the DOCUMENTED_CONSTANT default, not
    LIVE_EXCHANGE_INFO -- must convert to SYNTHETIC_RESEARCH, never EXCHANGE_VERIFIED."""
    symbol_meta = binance_meta_to_symbol_meta(default_symbol_meta())
    assert symbol_meta.metadata_source == METADATA_SOURCE_SYNTHETIC_RESEARCH


def test_live_fetched_meta_converts_to_exchange_verified_tag():
    live_meta = BinanceSymbolMeta(
        exchange="BINANCE_USDT_M_PERP", canonical_symbol="BTCUSDT", exchange_symbol="BTCUSDT",
        settlement_asset="USDT", contract_type="PERPETUAL", tick_size=0.1, step_size=0.001,
        price_precision=1, quantity_precision=3, min_qty=0.001, contract_size=1.0,
        source="LIVE_EXCHANGE_INFO", fetched_at=datetime.now(timezone.utc),
    )
    symbol_meta = binance_meta_to_symbol_meta(live_meta)
    assert symbol_meta.metadata_source == METADATA_SOURCE_EXCHANGE_VERIFIED


def test_require_exchange_verified_metadata_for_crypto_blocks_synthetic():
    symbol_meta = binance_meta_to_symbol_meta(default_symbol_meta())
    with pytest.raises(SyntheticMetadataError):
        require_exchange_verified_metadata_for_crypto(symbol_meta)


def test_require_exchange_verified_metadata_for_crypto_allows_live_tagged():
    live_meta = BinanceSymbolMeta(
        exchange="BINANCE_USDT_M_PERP", canonical_symbol="BTCUSDT", exchange_symbol="BTCUSDT",
        settlement_asset="USDT", contract_type="PERPETUAL", tick_size=0.1, step_size=0.001,
        price_precision=1, quantity_precision=3, min_qty=0.001, contract_size=1.0,
        source="LIVE_EXCHANGE_INFO", fetched_at=datetime.now(timezone.utc),
    )
    symbol_meta = binance_meta_to_symbol_meta(live_meta)
    require_exchange_verified_metadata_for_crypto(symbol_meta)  # must not raise
