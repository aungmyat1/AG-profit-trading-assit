"""AG_DAYTRADING_RUNTIME_V1: the deterministic runtime entrypoint wiring market timing/
data -> ST_LIQUIDITY_SWEEP_RETEST_V1 strategy evaluation -> TradeProposal ->
ExecutionRuntimeContext/ExecutionCoordinator -> lifecycle reconciliation.

Orchestration only -- every capability this package calls already exists elsewhere in the
repo (mt5.market_data for candles, strategy_engine.session/strategy_engine.sweep_retest
for closed-candle/session logic, execution.runtime_context/execution.coordinator/
execution.lifecycle for the one shared guard/execution/reconciliation boundary). See
cycle.py for the per-symbol closed-bar event pipeline, startup.py for the composition-root
/ fail-closed startup sequence, and crypto_feed.py for the pluggable (currently
DISABLED-by-design) crypto data-source interface -- no crypto candle feed exists anywhere
in this repo (audited: no binance/bybit/ccxt/klines integration found), so the crypto
runtime path is wired but never fed synthetic/invented data in production use.
"""
