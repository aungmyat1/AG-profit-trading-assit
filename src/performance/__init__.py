"""Read-only, version-aware performance measurement layer
(AG_LARGE_SMC_VERSION_HARDENING_PERFORMANCE_AND_POST_CHECKPOINT_ACTIVATION_V1).

This package does NOT create a shared database for FX/BTC/Large-SMC evidence -- each
strategy keeps its own native, already-working evidence store (FX:
artifacts/outcome_resolution/records/; Large-SMC:
large_smc_research.live_ledger.LargeSMCSetupLedger; BTC:
btc_sweep_research.ledger.BTCResearchLedger). `adapters/` reads each source as-is and
normalizes it into `models.ResolvedTradeSample`/`models.FunnelCounts`; `calculator.py`
computes deterministic metrics from those normalized samples. Nothing here writes back
to a strategy's own evidence store.
"""
