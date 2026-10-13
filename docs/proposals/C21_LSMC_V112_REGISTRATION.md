# C21 Large-SMC 1.1.2 registration proposal

Mission AGP-C21-LSMC-V112-ENGINE-R2; base b588eb6455d4f5f8ef9512450b4b572304b669e4 includes merged PR #200.

Identity: ST_LARGE_SMC_V1@1.1.2, append-only candidate, REPORT_ONLY, NOT_VERIFIED. Registry, scheduler and trading authorization remain unchanged. This proposal does not authorize registration.

OD1014-FAST D2 amended 2026-10-14: C10 pip = 10 × fields.point for all six symbols, from AG_HOST_SYMBOL_METADATA_V2 captures on VTMarkets-Demo. Schema, server, canonical/broker symbol mapping, positive finite point, capture timestamp and hashes must validate; otherwise C10_PIP_SIZE_NOT_EVIDENCED. EURUSD/GBPUSD 0.0001 must equal frozen C10 values; USDJPY 0.01, XAUUSD/BTCUSD/ETHUSD 0.1.

POI age for FX counts observed closed H1 trading dates; crypto calendar behavior remains unchanged. Committed-fixture replay and final scope matrix are being prepared under the R1 lock. All unrun checks are NOT_RUN.

Proposed registry diff: none applied. Keep v1.1.0 active; registration of v1.1.2 requires a separate owner decision after review of the scope evidence.
