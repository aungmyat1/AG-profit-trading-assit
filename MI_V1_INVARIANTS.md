# MI V1 invariants and test plan

1. Same-event identity: all component evidence carries the caller event ID; mixed IDs
   fail closed. Test two consumers on one `ReplayEvaluationContext`.
2. Closed-data-only: every bar satisfies `open + timeframe duration <= T`. Test forming
   and future bars are excluded at every timeframe.
3. Future-mutation invariance: changing only data after T cannot change snapshot
   semantics at T, though full dataset identity may differ.
4. Zero-live fallback: replay builds fail loudly if MT5 candle APIs are reached. Patch
   both consumer imports and raw SDK calls.
5. Timeframe lineage: participating series are explicit; setup-only H1/M15 identity
   differs from H1/M15/M1 identity. M1 cannot appear merely because it is loaded.
6. Determinism: identical event, identities, inputs, and versions yield identical
   component values and snapshot fingerprint.
7. Historical/live semantic parity: the same canonical authority and boundary rules
   are used; only source, clock, and execution simulator differ.
8. Quality honesty: missing, incomplete, or degraded components remain represented as
   such; no neutral/default value is promoted to valid evidence silently.
9. Strategy firewall: MI imports no execution, risk, proposal, or strategy decision
   authority and cannot emit a TradeSignal.
10. Provenance completeness: each component records source identity, timeframe,
    feature version, and cutoff used.

Required gates: unit tests for each invariant, property tests for future mutation and
determinism, replay integration with Asian and SSC actual consumers, and import/firewall
guards. Live broker checks are deferred and cannot be inferred from replay tests.
