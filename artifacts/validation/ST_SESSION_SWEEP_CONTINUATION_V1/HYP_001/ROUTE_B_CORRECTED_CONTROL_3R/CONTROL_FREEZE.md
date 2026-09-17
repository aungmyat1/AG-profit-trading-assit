# Corrected 3.0R CONTROL — Freeze Record (RB-C0 / RB-C2 / RB-C3)

`CONTROL_ID = SSC_V1_0_1_CONTROL_3R`

## Admission (RB-C0)

Verified before execution, from the frozen v1.0.1 strategy authority and the frozen
Route B population:

```
strategy          = ST_SESSION_SWEEP_CONTINUATION_V1
version           = 1.0.1
runner_target_r   = 3.0
partial_pct       = 0.50
runner_pct        = 0.50
partial_semantics = OPPOSITE_SESSION_BOUNDARY
LONG              = reference_high
SHORT             = reference_low
```

The CONTROL consumed the already-frozen Route B occurrence population. It did **not**
regenerate occurrences (no `run_replay`, no setup/H1-bias/session-box re-derivation).

## Population hash equality (RB-C0/C3)

```
GEN_001   CONTROL_POPULATION_HASH = 1b6cda1733e8d0edb2dfb90ed092ab3445543ff01bce97d52ad5d04256609285  == frozen (true)
GEN_002A  CONTROL_POPULATION_HASH = b5a77c4951b0f8ecaf4308e8421087ff3bd4f240ddf31e3326b536989d5f63e7  == frozen (true)
COMBINED  CONTROL_POPULATION_HASH = e21ed545b076b157139eca22c03e3efdd0870eef83e3889a9b9febd317e3683e  == frozen (true)
```

`POPULATION_HASH_MATCHES_PHASE1 = true` (all three).

## CONTROL economics (RB-C2) — canonical friction (`MODELED`) + corrected resolver

| Metric | GEN_001 | GEN_002A | COMBINED |
|---|---|---|---|
| N (occurrences) | 31 | 57 | 88 |
| resolved / unresolved | 31 / 0 | 57 / 0 | 88 / 0 |
| wins | 15 | 18 | 33 |
| losses | 15 | 36 | 51 |
| breakeven | 1 | 3 | 4 |
| gross_R | +0.634 | −18.842 | −18.209 |
| friction_R | 5.886 | 10.118 | 16.005 |
| net_R | −5.253 | −28.960 | −34.213 |
| gross_expectancy_R | +0.020 | −0.331 | −0.207 |
| net_expectancy_R | −0.169 | −0.508 | −0.389 |
| profit_factor (gross) | 1.054 | 0.341 | 0.547 |
| net_profit_factor | — | — | 0.332 |
| win_rate | 0.484 | 0.316 | 0.375 |
| max_drawdown_R | 4.208 | 21.499 | 23.736 |
| max_consecutive_losses | 4 | 10 | 10 |
| partial_target_hits | 8 | 7 | 15 |
| runner_target_hits | 1 | 2 | 3 |

Exit behavior (COMBINED): initial-stop exits 36, session exits 43, runner-BE exits 6,
ambiguous 0, unresolved_no_data 0. Partial activation rate 0.170.

Setup / direction / session (COMBINED): S1 = 33, S2 = 15, S3 = 40; LONG = 28,
SHORT = 60; ASIAN_LONDON = 49, LONDON_NEWYORK = 39.

Per-setup net_R (COMBINED): S1 = −13.223, S2 = −13.081, S3 = −7.909.

**No metric was reinterpreted, optimized, or repaired.** This is the raw corrected
3.0R CONTROL result.

## Frozen hashes (RB-C3)

```
CONTROL_POPULATION_HASH (COMBINED) = e21ed545b076b157139eca22c03e3efdd0870eef83e3889a9b9febd317e3683e
CONTROL_OUTCOME_HASH              = 65df2115b7e9c99e129b7e1d09c073a32283df2552c413a8e48e68b9784deefd
CONTROL_EVIDENCE_HASH             = 310e6548e87b9ac51adc989d68fad93b500d36b24e0f29ece7c22b9e6609253d
```

Implementation: `scripts/run_route_b_corrected_control_3r.py` (this mission).
Resolver: `session_sweep_continuation.outcome_resolution.resolve_campaign_entry`
(frozen v1.0.1). Metrics: `performance.calculator.compute_trade_metrics` (canonical).

Full per-occurrence outcomes: `CONTROL_OUTCOMES.json`. Full structured summary:
`CONTROL_SUMMARY.json`.
