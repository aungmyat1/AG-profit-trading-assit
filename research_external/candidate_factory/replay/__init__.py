"""AG_OSS_STRATEGY_CANDIDATE_FACTORY_R1 replay harness.

Research-only. Nothing here imports MT5, execution, or any broker-mutation path.
No file under src/ may import from this package or from research_external/ at all
(see tests/test_research_external_boundary.py). This package reads already-closed,
already-admitted DEV-partition candles from disk and calls candidate engine
functions directly; it never fetches live data and never sends orders.
"""
