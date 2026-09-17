# Corrected 3.0R CONTROL — Audit (RB-C4)

Independent audit of the frozen CONTROL evidence. Read-only; no economic repair, no
parameter change.

## Audit points

1. **3.0R only** — `runner_target_r = 3.0` throughout; the 1.5R treatment was never
   computed. **Pass.**
2. **Corrected opposite-session-boundary semantics** — LONG → `reference_high`,
   SHORT → `reference_low`, from the frozen v1.0.1 resolver. **Pass.**
3. **Frozen occurrence population reused** — loaded from
   `ROUTE_B_PHASE1_RECONSTRUCTION/{GEN_001,GEN_002A}/reconstructed_occurrence_population.json`;
   population hashes re-verified against the frozen authority before resolution.
   **Pass.**
4. **No occurrence regeneration** — no `run_replay`/setup/H1-bias/session-box call in
   the CONTROL path; only `resolve_campaign_entry` over the frozen identity fields.
   **Pass.**
5. **No treatment execution** — no code path computes `runner_target_r = 1.5`.
   **Pass.**
6. **No holdout access** — only the hash-admitted historical M1 legs
   (`D:\EURUSD_M1_202605180946_202607312356.csv`,
   `D:\GBPUSD_M1_202606080533_202607302357.csv`), both fingerprint-verified against the
   Route B admission hashes. **Pass.**
7. **Friction methodology unchanged** — `estimate_friction` with the frozen config
   defaults (EURUSD 1.0/0.2/0.3, GBPUSD 1.4/0.2/0.4 pips, `MODELED`). **Pass.**
8. **Economic calculations reproducible** — `compute_trade_metrics` (canonical)
   over `ResolvedTradeSample` records; `gross_R`/`net_R` come from the frozen resolver.
   **Pass.**
9. **Artifact hashes consistent** — `CONTROL_SUMMARY.json` internal hashes match the
   stored outcome/evidence hashes (recomputed below). **Pass.**

## Hash re-verification

```
CONTROL_OUTCOME_HASH  = 65df2115b7e9c99e129b7e1d09c073a32283df2552c413a8e48e68b9784deefd
CONTROL_EVIDENCE_HASH = 310e6548e87b9ac51adc989d68fad93b500d36b24e0f29ece7c22b9e6609253d
CONTROL_POPULATION_HASH (COMBINED) == FROZEN_ROUTE_B_POPULATION_HASH  -> true
```

## Result

```
CONTROL_AUDIT = PASS
```

The corrected 3.0R CONTROL evidence is frozen and audited. Per the mission's hard rule,
execution stops here — the 1.5R HYP_001 treatment is **not** executed and its
economics are **not** computed or compared. That requires a separate owner-authorized
mission.
