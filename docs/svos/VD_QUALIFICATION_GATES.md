# VD V1 future qualification gates (unexecuted)

All gates are `NOT_EVALUATED` in Cycle 1. Gate definitions and exact economic thresholds must be frozen before sealed VD access. Gates are evaluated in order; a failed earlier gate leaves dependent gates `NOT_EVALUATED`. Passing tests or a favorable P&L alone cannot authorize Demo/Live trading.

| Gate | Predeclared evidence and failure condition |
|---|---|
| VD data integrity | Dataset hash, continuity, timezone, source and availability provenance, instrument metadata, execution-quality admission; mismatch or missing required fields fails. |
| VD temporal parity | Event-time/availability checks, no future input or same-bar fill, restart and reordered-ingest invariance; any violation fails. |
| VD strategy parity | Compare canonical `run_replay` results under identical admitted inputs with and without VD adapter; decision/state/reason mismatch fails. |
| VD execution parity | Independent hand-check fixtures for order validation, latency, spread, slippage, fees, SL/TP ambiguity, gaps, rejects, and account arithmetic; unexplained mismatch fails. |
| VD deterministic speed parity | Same manifest at several playback speeds/restart points yields identical semantic ledger root and account outcomes; mismatch fails. |
| VD economic performance | Preregistered net metrics, sample/minimum-trade criteria, uncertainty interval, costs, baseline comparison, and pass/fail thresholds; no post-access threshold edits. |
| VD stress robustness | Frozen spread/slippage/latency deterioration, missing bars, gap and ambiguity scenarios; thresholds set before access. |
| VD operational reliability | Bounded runtime, checkpoint recovery, audit completeness, access accounting, and no broker/execution imports; failures block qualification. |

Qualification decision requires a signed gate report citing manifest and ledger roots, sample counts, quality distribution, ambiguous/unresolved counts, exact tests and environment, and each gate result. Any unsupported execution-quality class or unresolved material design choice blocks campaign admission rather than being quietly estimated.
