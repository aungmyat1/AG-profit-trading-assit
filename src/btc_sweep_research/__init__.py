"""BTC (Binance USDT-M perpetual, BTCUSDT) research runtime for
ST_LIQUIDITY_SWEEP_RETEST_V1's CRYPTO_PERP profile.

RESEARCH_ONLY / PROPOSAL_ONLY / SHADOW: nothing in this package ever imports
execution.executor, mt5.management_gateway, execution.coordinator, or execution.adapter
(see pipeline.py's module docstring for why execution_runtime/cycle.py is deliberately NOT
reused) -- no code path here can ever submit a real or demo order. See
tests/test_btc_proposal_execution_boundary.py for the enforced boundary.
"""
