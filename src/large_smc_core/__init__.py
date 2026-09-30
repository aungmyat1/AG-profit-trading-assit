"""Large-SMC research core (AG V1 T4, 2026-09-30) -- RESEARCH ONLY.

Byte-exact copies of the self-contained modules of src/large_smc_research @ 2b75bbf:
c10_stop_policy.py (C10 stop policy), target_model.py (C11 target model) and
decision.py. They live in a new package because the original package's __init__
imports large_smc_research.engine, and that engine reaches the forbidden
trade_management package through historical_replay.stage2 -> daytrading_runtime ->
daytrading.risk_management. The v1.0.7 engine, live_watch, watch_lifecycle, live_ledger
and pending_entry are therefore NOT restored (see docs/status/AG_V1_TWO_GOALS_CLOUD_STATUS.md).

No proposal, demo, live, execution, risk-sizing or order authority. No imports of
execution/, trade_management/ or mt5 management/order modules (enforced by
tests/test_v1_large_smc_import_boundary.py).
"""
