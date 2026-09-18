# H2_FRICTION_VERIFICATION — Preregistration & Broker-Evidence Contract

Status: **PREREGISTERED, NOT EXECUTED, NOT COLLECTING.** Committed in writing before any
new friction evidence is collected and before any economic recomputation. No new data
collected, no economics recomputed, no strategy/config/execution authority modified, no
protected data accessed. This packet freezes the measurement/admission contract for a
later, separately-authorized evidence-collection and evaluation mission.

> Naming note: this experiment uses `H2_FRICTION_VERIFICATION`, the second candidate
> hypothesis from the post-HYP_001 failure diagnosis (SSC_POST_HYP001_DIAGNOSIS_V1).
> It is DISTINCT from the repository's existing `HYP_002_SETUP_SELECTIVITY`
> (artifacts/validation/ST_SESSION_SWEEP_CONTINUATION_V1/HYP_002_PREREGISTRATION/) and
> from `HYP_001_EXIT_CAPTURE` (terminal: HYPOTHESIS_NOT_SUPPORTED). No reuse of those
> experiment IDs, populations, or conclusions is implied.

## 1. Identity

```
hypothesis_id            = H2_FRICTION_VERIFICATION
parent_strategy_id       = ST_SESSION_SWEEP_CONTINUATION_V1
parent_version           = 1.0.1
parent_config_hash       = 6281b6407c748990d3b68188dafc2b6fec5aa5534dc4ce5fc82abcf53568b1fc
parent_raw_sha256        = 0a3dffb0b601cf52f36c4623ed76fe22564d6145224eee2329c8ae1dc93ed658
parent_source            = strategies/ST_SESSION_SWEEP_CONTINUATION_V1.yaml
population_source        = artifacts/validation/ST_SESSION_SWEEP_CONTINUATION_V1/HYP_001/ROUTE_B_PHASE1_RECONSTRUCTION
population_COMBINED_hash = e21ed545b076b157139eca22c03e3efdd0870eef83e3889a9b9febd317e3683e
population_N             = 88 (unique trade_ids = 86; see §11 identity defect)
population_date_range    = 2026-05-18 .. 2026-07-30
preregistered_at         = 2026-09-19
repository_HEAD          = 76330e316e4ee566dbd24e825f0480f65c24d5a4
```

Parent config hash computed with `session_sweep_continuation.config.compute_config_hash`
over the parsed YAML; raw SHA-256 over the byte-identical file. Population hash is the
frozen Phase 1 COMBINED hash, re-verified (matches CONTROL and TREATMENT).

## 2. Falsifiable claim / mechanism (H2-G1)

The current SSC v1.0.1 economic baseline depends materially on **modeled** transaction
costs (`cost_status = MODELED` for all 88 resolved occurrences). Replacing modeled
friction with independently **broker-evidenced** friction may materially change the
estimated net economics — **without changing any signal, entry, stop, exit, or
occurrence**.

This hypothesis does **NOT** assume broker-evidenced costs will improve economics.
Allowed outcomes, each equally legitimate:

- measured cost < modeled cost;
- measured cost ≈ modeled cost;
- measured cost > modeled cost;
- insufficient evidence (collection cannot reach the sufficiency gate).

No favorable direction may be assumed or baked into the collection design.

## 3. Immutable strategy firewall (H2-G2)

The following are FROZEN and must be byte/identity-identical in any later evaluation:

- `ST_SESSION_SWEEP_CONTINUATION_V1` v1.0.1 strategy YAML and engine (`src/session_sweep_continuation/`);
- the frozen 88-occurrence Route B population (hash `e21ed545…`);
- every occurrence's entry, initial stop, initial risk, setup classification, session
  classification, H1 bias, reference high/low, decision/entry timestamps;
- partial semantics (OPPOSITE_SESSION_BOUNDARY), partial/runner allocation (0.50/0.50);
- session-exit semantics; the outcome resolver (`outcome_resolution.resolve_campaign_entry`);
- the friction **formulas** (spread+commission+slippage in pips → price → R).

Only the friction **evidence/source** may change in a later authorized evaluation.
`H2-G12` safety gates apply.

## 4. Current modeled cost audit (H2-G3)

Authority: `src/session_sweep_continuation/friction.py` + `strategies/ST_SESSION_SWEEP_CONTINUATION_V1.yaml`
`friction:` block + `src/session_sweep_continuation/outcome_resolution.py::_friction_breakdown`.

Per-symbol modeled defaults (strategy YAML `friction.default_*_pips`):

| component | EURUSD | GBPUSD | SOURCE |
|---|---|---|---|
| spread_pips | 1.0 | 1.4 | MODELED (config default, no broker capture) |
| commission_pips | 0.2 | 0.2 | MODELED (config default, no broker spec/capture) |
| slippage_pips | 0.3 | 0.4 | MODELED (config default, no execution capture) |
| total_pips | 1.5 | 2.0 | sum |
| swap | n/a | n/a | UNAVAILABLE / not applicable (intraday session-bound; no overnight modeled) |

Formulas (`friction.py`):

```
total_pips   = spread + commission + slippage
total_price  = total_pips * pip_size              # pip_size = 0.0001 for both symbols
total_cash   = total_pips * pip_value_per_lot * lots
total_r      = total_price / stop_distance_price  # stop_distance_price = abs(entry - stop)
cost_status  = MODELED  (live_* all None) / KNOWN (all three live supplied) / UNAVAILABLE
```

Application (`outcome_resolution.py`):

```
spread_cost_R     = (spread_pips    * pip_size) / risk
commission_cost_R = (commission_pips* pip_size) / risk
slippage_cost_R   = (slippage_pips  * pip_size) / risk
total_friction_r  = spread_cost_R + commission_cost_R + slippage_cost_R
net_R             = gross_R - total_friction_r
```

Key facts (verified against frozen CONTROL):

- All 88 occurrences carry `cost_status = MODELED`; **zero** carry KNOWN.
- Entry vs exit cost is NOT separated: one combined round-trip-equivalent
  `spread + commission + slippage` total is subtracted once from gross_R.
- Friction total ≈ 16.005R across the 88 (≈ 46.8% of the −34.213R net loss).
- EURUSD gross ≈ +0.634R but net ≈ −5.253R (friction flips sign).
- `minimum_stop_multiple = 3.0` (stop engine) is a stop-construction guard, NOT a
  friction component; it is unchanged and out of scope here.

## 5. Existing broker-friction infrastructure audit (H2-G4)

Existing reusable machinery (verified present in the worktree):

| Component | Location | Classification |
|---|---|---|
| Spread evidence collector (read-only MT5 bid/ask) | `src/fx_friction_research/spread_evidence.py` | REUSABLE_MEASUREMENT_INFRASTRUCTURE |
| Fixed-grid campaign sampling + MISSING_GAP | `spread_evidence.collect_fixed_grid` | REUSABLE_MEASUREMENT_INFRASTRUCTURE |
| Read-only MT5 tick/account path | `mt5.market_data.get_tick`, `mt5.account` | REUSABLE_MEASUREMENT_INFRASTRUCTURE |
| Campaign runner script pattern | `scripts/run_eurusd_friction_campaign_window.py` | REUSABLE (template only) |
| Campaign manifest schema + governance | Large-SMC `campaign_manifest.json` (frozen, hash-bound) | REUSABLE (pattern/template) |
| Cost scenarios (BASE/STRESSED/SEVERE) | `src/fx_friction_research/cost_model.py` | STRATEGY_SPECIFIC_EVIDENCE (ST_ASIAN_SWEEP_5R_V1-anchored industry estimates, NOT broker-measured) |
| Collected Large-SMC spread observations | `…/ST_LARGE_SMC_V1/…/friction_campaign_wp3a1/sessions/*` | STRATEGY_SPECIFIC_EVIDENCE (EURUSD-only, Large-SMC windows; NOT SSC windows) |

Reuse decision:

- **REUSE** the collector module and the read-only MT5 path (code, not values).
- **REUSE** the campaign-governance pattern (frozen manifest, hash-bound, no deletion of
  high-spread samples, no restart, MISSING_GAP accounting).
- **DO NOT copy** Large-SMC observed spread values into SSC. SSC has different symbols
  (EURUSD + GBPUSD) and different session windows (ASIAN_LONDON / LONDON_NEWYORK).
- **DO NOT use** `cost_model.py` scenarios as SSC "broker-evidenced" cost — they are
  explicitly industry estimates, not measurements.

SSC therefore requires its **own** measurement campaign covering EURUSD and GBPUSD, in
its own ASIAN_LONDON and LONDON_NEWYORK windows (below).

## 6. Broker-evidence contract (H2-G5)

Smallest collection contract for a later authorized collection mission. Reuses
`spread_evidence`'s existing `SpreadObservation` fields, extended only where the SSC
campaign needs them.

Per-observation fields (where available):

```
timestamp_utc, symbol, bid, ask, spread_price, spread_pips,
broker_server, account_environment, source
```

Required per-campaign metadata:

```
broker_identity  = VantageMarkets-Demo (or whatever account the campaign runs under)
account_environment = DEMO (never LIVE for this research mission)
tick_size        = 1e-05 (5-digit; pip = 10 ticks = 0.0001)
pip_size         = 0.0001 (EURUSD, GBPUSD)
contract_size    = per MT5 symbol metadata (recorded, not assumed)
```

Component status (preregistered):

```
spread     = MEASURABLE (bid/ask via read-only tick path)
commission = BROKER_SPEC_OR_UNAVAILABLE — a signed Vantage FX commission spec has NOT
             been located in the repository; if none is supplied by the owner, commission
             stays UNAVAILABLE and the evaluation must report it separately, never guess.
slippage   = UNAVAILABLE — cannot be measured without submitting orders; no order is
             authorized in this research mission. SLIPPAGE_STATUS = UNAVAILABLE is the
             fail-closed default; it is never fabricated or imputed from spread.
swap       = NOT_APPLICABLE (intraday session-bound)
```

## 7. R-normalization contract (H2-G6)

Canonical repository equivalent, verified in `outcome_resolution.py::_friction_breakdown`:

```
cost_R = cost_price / initial_risk_price
cost_price = component_pips * pip_size        (per component)
initial_risk_price = abs(entry_price - stop_price)   (per occurrence)
```

- Cost is computed **per occurrence** because initial-risk geometry differs per trade.
  A single constant R-cost across all 88 trades is NOT used and must NOT be substituted.
- `net_R = gross_R - Σ cost_R` (spread + commission + slippage), applied once per trade
  (round-trip-equivalent).

Historical mapping:

```
HISTORICAL_OCCURRENCE_COST_RECONSTRUCTION  (NOT contemporaneous)
```

- The 88 occurrences span 2026-05-18 … 2026-07-30. Any broker evidence collected now
  (2026-09+) is **NOT contemporaneous** with those occurrences and must be labeled a
  **proxy/reconstruction**, never presented as historical spread.
- No mechanism exists to recover historical per-trade bid/ask; the later evaluation must
  apply the broker-evidenced cost distribution as an explicit reconstruction assumption.
- `CONTEMPORANEOUS_BROKER_MEASUREMENT` would apply only to a future forward/paper
  observation campaign, not to the frozen historical 88.

## 8. Evidence sufficiency (H2-G7)

Minimum requirements, fixed BEFORE collection (aligned with the Large-SMC campaign's
already-audited standards where they exist):

```
minimum_trading_days          = 5 (FX-open Mon-Fri UTC days; weekend/closed skipped)
minimum_samples_per_window    = 120
sampling_interval_seconds     = 5
total_minimum_observations    = 2400  (recomputed for the SSC symbol/window matrix)
symbol_coverage               = EURUSD AND GBPUSD (both required)
session_coverage              = ASIAN_LONDON (trade window 07:00-11:00) AND
                                LONDON_NEWYORK (trade window 12:00-15:00)
spread_sampling_method        = fixed-grid read-only bid/ask (existing collect_fixed_grid)
commission_unavailable_policy = report as UNAVAILABLE component; evaluation still runs,
                                but commission remains at the frozen modeled value and is
                                flagged as MODELED (not broker-evidenced)
slippage_unavailable_policy   = report as UNAVAILABLE; keep frozen modeled slippage,
                                flagged MODELED; never impute
outlier_policy                = NO deletion of high-spread samples (mirrors Large-SMC);
                                percentiles reported (min/median/mean/p75/p90/p95/max)
missing_data_policy           = MISSING_GAP rows, never interpolated/backfilled
```

Thresholds are fixed here, BEFORE any economic result is seen. They are not tunable after
collection.

## 9. Future evaluation contract (H2-G8)

A later authorized evaluation compares, over the SAME frozen 88 occurrences, with NO
signal/outcome change:

```
gross_R                 (unchanged by construction)
modeled_friction_R      (from current config defaults)
broker_evidenced_friction_R  (spread from campaign + any signed commission; slippage
                                and commission remain MODELED if unavailable)
modeled_net_R  vs broker_evidenced_net_R
modeled_expectancy vs broker_evidenced_expectancy
modeled_PF vs broker_evidenced_PF
```

Segmentation (identical to CONTROL/treatment reporting): combined; EURUSD; GBPUSD;
S1/S2/S3; ASIAN_LONDON; LONDON_NEWYORK.

Only the friction evidence/source may change. Signal, entries, stops, exits, resolver,
and population are frozen.

## 10. Interpretation firewall (H2-G9)

Preregistered, not revisable after results:

- Lower measured friction + improved economics ⇒ does **NOT** establish strategy edge.
- Economics remain negative ⇒ economic gate remains **failed**.
- Economics become positive ⇒ still requires robustness/replication under the existing
  validation lifecycle before any Demo eligibility (never automatic).
- Measured friction higher than modeled ⇒ the worse result is accepted unchanged.

## 11. Identity defect carry-forward (H2-G11)

```
population_N      = 88
unique_trade_ids  = 86
classification    = IDENTITY_SCHEMA_DEFECT  (trade_id omits symbol/generation_id;
                    two cross-symbol S1 occurrences share a trade_id: EURUSD vs GBPUSD)
```

- The frozen population is NOT modified, deduplicated, re-hashed, or regenerated.
- H2 calculations must use **stable occurrence ordering** (sort by trade_id, stable, then
  positional pairing) that preserves all 88 records — the same method the HYP_001 paired
  comparison used after its dict-keying defect was corrected.
- A separate prospective identity-remediation recommendation (add symbol/generation_id to
  the trade_id schema) is recorded for owner review; it is NOT implemented here.

## 12. Safety (H2-G12) and protected data (H2-G10)

```
STRATEGY_CHANGED            = false
POPULATION_CHANGED          = false
BROKER_MUTATION             = false
DEMO_ORDER                  = false
LIVE_ORDER                  = false
EXECUTION_AUTHORITY_CHANGED = false
OOS_ACCESS_COUNT            = 0
HOLDOUT_ACCESS_COUNT        = 0
CONFIRMATION_ACCESS_COUNT   = 0
```

## 13. Next gate

This packet resolves the preregistration gate only. The next authorized mission would be
`H2_FRICTION_VERIFICATION: EVIDENCE COLLECTION` (create a frozen SSC-specific campaign
manifest + run the read-only collector for EURUSD/GBPUSD × ASIAN_LONDON/LONDON_NEWYORK),
and only after collection reaches §8 sufficiency would a `H2_FRICTION_VERIFICATION:
EVALUATION` mission recompute economics. Neither is started here.
