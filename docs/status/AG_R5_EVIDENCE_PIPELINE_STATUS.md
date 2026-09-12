# R5 — Trustworthy Evidence Pipeline Status

Recorded: 2026-09-11
Scope: ST_ASIAN_SWEEP_5R_V1 (the only strategy with resolvable outcomes today).
Method: audit-first. Every component below was found already built, tested, and
correct from a prior milestone (`AG_MONEY_MAKING_EVIDENCE_PIPELINE_M1`, phases
P5-P14) — nothing new was built for R5 itself. This entry verifies it, runs it fresh,
and reports the real current numbers.

## Reuse inventory (confirmed, not rebuilt)

| Component | Path | Status |
|---|---|---|
| FX outcome resolver | `scripts/resolve_forward_shadow_outcomes.py` | REUSE — signed `AG_OUTCOME_RESOLUTION_CONTRACT_V1_SIGNED`, no-lookahead (resolves strictly forward from `ready_at` to session cutoff, session-isolated, `AMBIGUOUS_SEQUENCE` fail-closed on same-candle SL+TP1/BE+TP2 collisions), immutable output |
| Canonical trade model | `src/performance/models.py::ResolvedTradeSample`, `calculator.py::compute_trade_metrics` | REUSE — deterministic, `NOT_EVALUATED` convention already correct |
| FX performance adapter | `src/performance/adapters/fx_adapter.py::load_fx_resolved_samples` | REUSE — reads immutable records only, skips AMBIGUOUS/UNRESOLVED rather than fabricating |
| Cost model | `src/performance/cost_model.py` | REUSE — one signed scenario (`CONTRACT_CEILING`, derived from the strategy's own `max_spread_allowed_pips`/`slippage_limit_points`); BASE/SEVERE explicitly `NOT_AVAILABLE_NO_SIGNED_ASSUMPTION`; additive only, never mutates source records |
| Validation framework | `src/validation_framework/` | REUSE — `AG_EGSVF_V1`, ledger snapshots in `artifacts/validation_ledger/` |
| End-to-end report generator | `scripts/generate_economic_evidence_report.py` | REUSE — already wires all of the above together per-strategy, already declares `ECONOMIC_GATE_THRESHOLD_UNDEFINED` rather than self-authoring a threshold |
| Large-SMC resolver | none | **MISSING** (unchanged) — `tests/test_performance_large_smc_adapter.py::test_no_resolved_trade_samples_until_an_outcome_resolver_exists` proves this is enforced, not silently absent |

## Immutability and no-lookahead audit

- All 13 records in `artifacts/outcome_resolution/records/` conform to the schema and
  carry `resolution_contract_version: AG_OUTCOME_RESOLUTION_CONTRACT_V1_SIGNED` (verified
  programmatically, zero missing fields, zero malformed records).
- `resolve_proposal()` reads candles only from `ready_at` forward to the pair's own
  session-exit cutoff (11:00Z ASIAN_LONDON / 15:00Z LONDON_NEWYORK) — never earlier data,
  never crosses into the other cycle's window. Existing `tests/test_resolve_forward_shadow_outcomes.py`
  covers this boundary.
- `src/performance/cost_model.py::to_resolved_trade_samples` returns new dataclass
  instances; the source `ResolvedTradeSample`/outcome-resolution JSON files are never
  written to by this layer.

## Fresh run — actual current evidence (2026-09-11)

```
$ python scripts/generate_economic_evidence_report.py
```

### ST_ASIAN_SWEEP_5R_V1

```
resolved_trade_count = 13
lifecycle_stage = OPERATIONAL_SHADOW

GROSS (cost_status: NOT_INCLUDED)
  wins=0 losses=13 win_rate=0.0
  gross_total_R=-13.0  gross_expectancy_R=-1.0
  max_drawdown_R=13.0  max_consecutive_losses=13
  profit_factor=UNDEFINED_NO_WINS

NET (CONTRACT_CEILING scenario -- the only evidence-backed cost scenario)
  net_total_R=-44.00  net_expectancy_R=-3.38
  (friction_evidence_complete=true: cost overlay applied to all 13 records)

economic_gate_threshold = ECONOMIC_GATE_THRESHOLD_UNDEFINED
economic_gate_pass      = ECONOMIC_GATE_THRESHOLD_UNDEFINED
economic_status         = NEGATIVE_EXPECTANCY
kill_continue_advisory  = PAUSE_FOR_RESEARCH
sample_sufficiency      = INSUFFICIENT_SAMPLE (13 < 30, a repository-neutral
                          descriptive floor, not a governance threshold)
oos_status              = NOT_VERIFIED
```

**Read plainly**: every one of the 13 resolved trades lost (-1.0R each, gross). Once the
strategy's own worst-case-still-permitted spread/slippage ceiling is applied, the picture
gets meaningfully worse, not better (-3.38R/trade net vs -1.0R/trade gross) — friction is
not a rounding error for this setup's tight geometry. This is real signal from real
resolved trades, not a placeholder or synthetic result, and it is reported here exactly
as computed, per section 15/27's "do not cherry-pick only favorable observations" rule.

### ST_LARGE_SMC_V1
```
resolved_trade_count = 0 (proposal_generation_authorized=false; no resolver exists)
economic_status = INSUFFICIENT_EVIDENCE
```
Correct and expected — `R5 outcome evidence = BLOCKED_BY_MISSING_OUTCOME_RESOLVER`.

### ST_LIQUIDITY_SWEEP_RETEST_V1 (BTC)
```
resolved_trade_count = 0 (research-only, no execution path)
valid_campaign_days = 0 / target 30
economic_status = INSUFFICIENT_EVIDENCE
```

## Tests (regression, existing suite, none written this task)

```
tests/test_economic_evidence_report.py
tests/test_performance_calculator.py
tests/test_performance_cost_model.py
tests/test_performance_large_smc_adapter.py
tests/test_resolve_forward_shadow_outcomes.py
tests/test_validation_framework.py

79/79 PASS
```

## Validation ledger / readiness artifact currency

`artifacts/validation_ledger/` and `artifacts/readiness/` were last generated
2026-09-07/08 — four days stale relative to today, but **no new FX evidence has been
added since** (still exactly 13 resolved records, unchanged since 2026-09-06). Did not
regenerate this session: `scripts/generate_readiness_baseline.py` reads the latest
portfolio ledger rather than computing one itself, and the ledger's own generator
wasn't identified within this task's scope (not one of the scripts inventoried).
Recommend a future task locate/run the actual `AG_EGSVF_V1` ledger evaluator directly
(likely inside `src/validation_framework/evaluator.py`) to produce a same-day snapshot
once new evidence exists — regenerating now would only reproduce the same 09-07 numbers.

## R6 precondition — economic thresholds

Confirmed (again) no signed numeric threshold exists anywhere in `config/` or `docs/`.
Per section 27, this session does **not** choose one. `scripts/generate_economic_evidence_report.py`
already encodes this discipline correctly (`ECONOMIC_GATE_THRESHOLD_UNDEFINED` for every
strategy, regardless of how the numbers look).

### Advisory threshold proposal (PROPOSED — NOT_SIGNED — NOT_AUTHORITY)

Offered for owner review only; not written into any active governance file; not derived
to make `ST_ASIAN_SWEEP_5R_V1` pass (it fails all of these badly regardless of where the
bar is set, which is itself evidence the proposal isn't tailored):

```
minimum_resolved_sample       = 30   (matches the descriptive floor already used
                                       in generate_economic_evidence_report.py)
minimum_net_expectancy_R      = > 0.0, computed under CONTRACT_CEILING costs
minimum_profit_factor         = >= 1.3, net
maximum_drawdown_R            = <= 15R or 3x average risk-per-trade, whichever is smaller
out_of_sample_requirement     = at least one walk-forward or held-out period confirming
                                 the in-sample expectancy sign
```

## Final classification

```
ST_ASIAN_SWEEP_5R_V1
  R5 evidence = PASS  (technically complete, reproducible, no-lookahead, cost-transparent)
  R6 economics = NOT_EVALUABLE_MISSING_SIGNED_THRESHOLDS
  (net evidence is strongly negative: -3.38R/trade net expectancy, 13/13 losses)

ST_LARGE_SMC_V1
  R5 = BLOCKED_BY_MISSING_OUTCOME_RESOLVER

ST_LIQUIDITY_SWEEP_RETEST_V1
  R5 = INSUFFICIENT_DATA (0 resolved trades, 0/30 campaign days)

Demo promotion = BLOCKED (no strategy has both R5 PASS and a signed R6 gate)
Live promotion = BLOCKED
```
