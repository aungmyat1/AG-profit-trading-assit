"""Exchange-filter interface for crypto (spec item 4). An ExchangeMetadataSource is
anything that can hand back a BinanceSymbolMeta (tick_size/step_size/min_qty/precision --
the exact shape execution_runtime/binance_usdtm_feed.py already defines and uses) for a
symbol. Two implementations in this phase:

  OfflineFixtureMetadataSource -- wraps a fixed BinanceSymbolMeta, for tests. No network.
  LiveExchangeMetadataSource   -- documented-but-unimplemented stub. Raises
                                  NotImplementedError if actually called; contains no
                                  network code at all (not even an unreachable one) --
                                  only the shape/contract a FUTURE, separately-authorized
                                  phase would fill in.

require_exchange_verified_metadata_for_crypto() does NOT duplicate
execution.adapter.require_exchange_verified_metadata(): reading that function's exact
implementation (execution/adapter.py) shows its check is
`symbol_meta.metadata_source != METADATA_SOURCE_EXCHANGE_VERIFIED` -- it only inspects the
generic mt5.symbol_resolver.SymbolMeta.metadata_source tag, nothing MT5- or FX-specific.
That makes it genuinely domain-neutral, so this module reuses it directly rather than
building a second, parallel gate.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from execution.adapter import SyntheticMetadataError, require_exchange_verified_metadata
from execution_runtime.binance_usdtm_feed import BinanceSymbolMeta, CANONICAL_SYMBOL
from mt5.symbol_resolver import METADATA_SOURCE_EXCHANGE_VERIFIED, METADATA_SOURCE_SYNTHETIC_RESEARCH, SymbolMeta

__all__ = [
    "ExchangeMetadataSource",
    "OfflineFixtureMetadataSource",
    "LiveExchangeMetadataSource",
    "binance_meta_to_symbol_meta",
    "require_exchange_verified_metadata_for_crypto",
    "SyntheticMetadataError",
]


class ExchangeMetadataSource(ABC):
    """Contract for anything that can answer "what are this symbol's current exchange
    filters" -- deliberately narrow (one method) so a future live implementation and an
    offline fixture are interchangeable to every caller in this package."""

    @abstractmethod
    def get_symbol_meta(self, symbol: str) -> BinanceSymbolMeta:
        ...


@dataclass(frozen=True)
class OfflineFixtureMetadataSource(ExchangeMetadataSource):
    """Test/offline double: always returns the same fixed BinanceSymbolMeta record for
    its one configured symbol. No network, no state, no side effects."""

    fixture: BinanceSymbolMeta

    def get_symbol_meta(self, symbol: str) -> BinanceSymbolMeta:
        if symbol != self.fixture.canonical_symbol:
            raise ValueError(
                f"OfflineFixtureMetadataSource is fixed to {self.fixture.canonical_symbol!r}, got {symbol!r}"
            )
        return self.fixture


class LiveExchangeMetadataSource(ExchangeMetadataSource):
    """Documented-but-unimplemented in THIS phase. Contains no network call, no imported
    HTTP/socket library, and no unreachable network code of any kind -- just the shape a
    future, separately-authorized phase would fill in (most likely by wrapping
    execution_runtime.binance_usdtm_feed.fetch_exchange_symbol_meta(), which already
    exists as the read-only research equivalent of this call, but is not invoked from
    here). Calling get_symbol_meta() on this class always raises NotImplementedError."""

    def get_symbol_meta(self, symbol: str) -> BinanceSymbolMeta:
        raise NotImplementedError(
            "LiveExchangeMetadataSource.get_symbol_meta is a Phase-2 stub: no live "
            "/fapi/v1/exchangeInfo fetch is implemented or reachable from this module. A "
            "future, separately-authorized phase must implement it (e.g. by wrapping "
            "execution_runtime.binance_usdtm_feed.fetch_exchange_symbol_meta) before this "
            "class can ever be used to build a real order."
        )


def binance_meta_to_symbol_meta(binance_meta: BinanceSymbolMeta, volume_max: float = 1000.0) -> SymbolMeta:
    """Crypto-execution-layer equivalent of
    execution_runtime.binance_usdtm_feed.to_symbol_meta(), but NOT the same function and
    NOT a call to it: that function always tags its output METADATA_SOURCE_SYNTHETIC_RESEARCH
    regardless of where the numbers came from (correct for its own RESEARCH-only callers,
    per its own docstring) -- this execution-layer boundary needs to distinguish a
    genuinely live-fetched filter set (source == "LIVE_EXCHANGE_INFO", i.e. a FUTURE
    LiveExchangeMetadataSource once implemented) from an offline default/fixture, so that
    require_exchange_verified_metadata_for_crypto() below can ever pass for real crypto
    metadata -- never for a fixture or the offline documented-constant default, both of
    which stay tagged SYNTHETIC_RESEARCH."""
    source_tag = (
        METADATA_SOURCE_EXCHANGE_VERIFIED
        if binance_meta.source == "LIVE_EXCHANGE_INFO"
        else METADATA_SOURCE_SYNTHETIC_RESEARCH
    )
    return SymbolMeta(
        symbol=binance_meta.canonical_symbol,
        tick_size=binance_meta.tick_size,
        tick_value=binance_meta.tick_size,
        contract_size=binance_meta.contract_size,
        volume_min=binance_meta.min_qty,
        volume_max=volume_max,
        volume_step=binance_meta.step_size,
        digits=binance_meta.price_precision,
        point=binance_meta.tick_size,
        metadata_source=source_tag,
    )


def require_exchange_verified_metadata_for_crypto(symbol_meta: SymbolMeta) -> None:
    """Fail closed: raises SyntheticMetadataError unless symbol_meta.metadata_source ==
    METADATA_SOURCE_EXCHANGE_VERIFIED. A thin, explicitly-named wrapper around
    execution.adapter.require_exchange_verified_metadata() (reused, not duplicated -- see
    module docstring) so crypto call sites can name the gate they mean without reaching
    into an FX-named module directly; behavior is identical."""
    require_exchange_verified_metadata(symbol_meta)
