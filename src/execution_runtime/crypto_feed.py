"""Pluggable crypto candle-data interface -- DISABLED by design (spec CRYPTO FLOW: "if
none exists, the crypto runtime path must be built pluggable ... but left DISABLED, not
fed fake/invented data").

Audited before adding: no crypto/exchange candle-data source exists anywhere in this repo
(searched for binance/bybit/ccxt/klines/BTCUSDT outside strategy_engine.sweep_retest's own
test fixtures and crypto_symbols.py's synthetic tick-size table -- none found; only
mt5.market_data exists, and it is MT5/Forex-CFD-shaped, not a crypto venue). Building a
live feed here would mean either inventing exchange integration (explicitly out of scope)
or feeding the runtime fabricated candles under the guise of "crypto works end-to-end"
(explicitly forbidden). Neither is acceptable, so this module defines ONLY the shape a
future concrete adapter would implement, and the runtime's own crypto path stays
`enabled=False` unless a caller explicitly constructs one.
"""
from __future__ import annotations

from typing import List, Protocol

from strategy_engine.session import Candle


class CryptoCandleFeed(Protocol):
    """Whatever a future live/historical crypto data adapter would implement. Shaped to
    mirror mt5.market_data.get_latest_candles's own (symbol, timeframe, count) ->
    List[Candle] contract, oldest-first, closed-bars-only -- so a future concrete
    implementation slots into execution_runtime.cycle.evaluate_and_route without that
    module needing to know or care where the candles actually came from."""

    def get_latest_candles(self, symbol: str, timeframe: str, count: int) -> List[Candle]:
        ...


class NoCryptoFeedConfigured(RuntimeError):
    """Raised if crypto evaluation is ever attempted without a real feed wired in. The
    runtime's own startup/CLI never constructs one -- see scripts/run_ag_execution_runtime.py
    --enable-crypto, which refuses to turn on the crypto path without an explicit feed."""
