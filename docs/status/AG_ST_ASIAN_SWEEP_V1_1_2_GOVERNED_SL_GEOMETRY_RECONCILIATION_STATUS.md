# AG_ST_ASIAN_SWEEP_V1_1_2_GOVERNED_SL_GEOMETRY_RECONCILIATION

RESEARCH_CANDIDATE work only. `ST_ASIAN_SWEEP_5R_V1` v1.1.1 remains
`CURRENT_FROZEN_AUTHORITY` (`proposal_only=TRUE`, `demo_authorized=FALSE`,
`live_authorized=FALSE`), unmodified. This document does not promote a strategy and
does not authorize demo/live execution.

## Root-cause verification (independent, from source -- no prior report existed)

No prior SL-provenance report artifact was found anywhere in the repository (checked
`docs/status/`, `PROJECT_STATUS.md`, `docs/VERSION_HISTORY.md`,
`strategies/STRATEGY_LEDGER.md`, git log). The root cause was therefore verified fresh,
directly from source and from the frozen 13-event forward-shadow dataset already present
(uncommitted) in `artifacts/outcome_resolution/records/`:

- `strategies/ST_ASIAN_SWEEP_5R_V1.yaml` declares `stop_loss_mode:
  PERCENT_OF_SESSION_RANGE`, `stop_loss_range_pct: 0.25`.
- `src/strategy_engine/loader.py:33` parses `stop_loss_range_pct` into
  `RiskConfig`/`StrategyConfig.risk` -- confirmed parsed and stored.
- Repo-wide grep for `.stop_loss_range_pct` / `config.risk` under `src/` finds **zero**
  consumption sites (only the loader that writes it, and one unrelated test constructing
  a `RiskConfig` fixture). The value is parsed but never read by any calculation.
- `src/strategy_engine/session/setups.py::entry_2_sweep` sets `stop_reference =
  candle.high` (upper sweep) / `candle.low` (lower sweep) -- the sweep candle's own wick,
  entirely independent of `stop_loss_range_pct` or the reference-session range.
- `src/strategy_engine/engine.py:67` passes `stop_loss=decision.stop_reference` straight
  through into `TradeSignal`, unmodified.
- Empirically, the 13 frozen `READY` proposals show stop distances of 0.4-8.4 pips,
  several sub-pip (0.4, 0.6, 0.8, 1.0, 1.2 pips) -- consistent with wick-based geometry,
  inconsistent with 25% of real 9-38 pip session ranges seen in the same data.

`ROOT_CAUSE_VERIFIED = ENGINE_GEOMETRY_DEFECT`. Confidence: HIGH (verified against
current source and empirical evidence directly, not assumed from a prior claim).
`candidate_work_allowed = YES`.

## Model A -- SESSION_RANGE_25

Implemented in isolation as `src/strategy_engine/session/candidate_stop_models.py`
(`session_range_25_stop`) -- a pure function, not wired into
`strategy_engine.engine.evaluate` or `session.setups.entry_2_sweep`, which remain
byte-for-byte unchanged (v1.1.1's live wick-based geometry is preserved exactly).

Contract: `SL distance = (box_high - box_low) * stop_loss_range_pct`. Fails closed
(`CandidateStopModelError`) on missing/invalid `stop_loss_range_pct`, non-positive
session range, non-positive resulting distance, or an unrecognized direction.

14 focused tests in `tests/test_candidate_sl_model_session_range_25.py` (A-G from the
governing prompt, plus an explicit unrecognized-direction case) -- all pass. Parameter
propagation proven directly (0.20/0.25/0.30 -> 4/5/6 pips on a fixed 20-pip range) and
determinism proven (identical inputs -> identical `CandidateStopResult`).

## Risk-sizing investigation

Reused `execution/risk.py::size_position` unmodified (existing fail-closed protections:
`INVALID_STOP_DISTANCE`, `VOLUME_BELOW_MIN`, `VOLUME_ABOVE_MAX`, `RISK_EXCEEDS_BUDGET`
already present, none duplicated). Reproduced the pathological comparison against the 13
real frozen legacy stop distances, using the same illustrative EURUSD/GBPUSD
`SymbolMeta` shape already used in `tests/test_execution_coordinator.py`
(`tick_size=0.00001`, `tick_value=1.0`), a $10,000 research-equity assumption, and 1%
risk per trade:

- Legacy geometry: lot sizes ranged **1.19 - 24.99** lots (median 6.25) -- none rejected
  by the existing `volume_max=50` guard, i.e. the guard alone does not catch this
  pathology; risk stayed pinned near the $100 budget only because position size scaled
  up to match the tiny stop, producing extreme effective leverage.
- Model A geometry: lot sizes ranged **1.06 - 3.73** lots (median 2.17), zero risk-guard
  rejections, all within existing broker bounds.

## 13-event controlled counterfactual replay

`scripts/replay_candidate_model_a_session_range_25.py` -- read-only against
`journal/post_asian_pilot/` and `journal/post_london_newyork_pilot/` (for `box_high`/
`box_low`, not otherwise in the original outcome record) and the existing MT5 M1 feed
(same source/method as the original resolver). Never writes to any original evidence
path; output isolated under `artifacts/candidate_research/model_a_session_range_25/`.
Original `artifacts/outcome_resolution/records/*.json` (13 events, 0 wins, -13R) are
read-only inputs and remain byte-for-byte unchanged on disk.

Every derived record carries `original_proposal_id`, `original_strategy_version`,
`original_entry`, `original_direction`, `original_SL`, `original_result`, `original_R`
alongside the candidate fields, and is labeled `COUNTERFACTUAL_REPLAY` /
`NOT_ORIGINAL_EVIDENCE` / `NOT_LIVE_OBSERVATION` / `NOT_PROMOTION_EVIDENCE`.

Result snapshot (`AG_CANDIDATE_MODEL_A_COUNTERFACTUAL_REPLAY_SNAPSHOT_V1.json`):

```text
events_evaluated=13   events_blocked=0   resolved=13   ambiguous=0
wins=3   losses=10   net_R=0.8629   expectancy_R=0.0664
min_SL_pips=2.675   median_SL_pips=4.6   max_SL_pips=9.375   sub_pip_stops_remaining=0
candidate_lot: min=1.06 max=3.73 median=2.17   (legacy: min=1.19 max=24.99 median=6.25)
candidate_risk_guard_rejections=0
```

This is diagnostic-only evidence about whether Model A implements the declared
contract, removes sub-pip geometry, and bounds risk -- not a profitability claim. The
original 13-event -13R evidence for v1.1.1 remains the permanent historical record.

## Model A sufficiency checkpoint

| Question | Answer |
|---|---|
| Faithfully implements the declared `stop_loss_range_pct` contract? | YES |
| Removes the sub-pip pathology? | YES -- `sub_pip_stops_remaining=0` (min 2.675 pips), vs several legacy events under 1 pip |
| Eliminates/reduces the extreme lot-size spike? | YES -- max lot 24.99 -> 3.73 |
| Deterministic and reproducible? | YES -- pure function, test G |
| Compatible with existing risk/broker safety rules? | YES -- 0 risk-guard rejections, `execution/risk.py` unmodified and reused as-is |
| Introduces any new invalid geometry? | NO -- 0 events blocked, 0 `CandidateStopModelError`s across all 13 |

All six conditions in the governing prompt's mandatory STOP gate are satisfied.

`FINAL_CLASSIFICATION = MODEL_A_SUFFICIENT_FOR_CANDIDATE_RECONCILIATION`

Model B was not attempted -- no non-performance justification exists (Model A does not
produce broker-invalid geometry, does not violate any confirmed structural-invalidation
contract, does not permit near-zero effective risk in a valid case, and satisfies all
existing broker/spread constraints reused unmodified from `execution/risk.py`). The
counterfactual net_R improvement is explicitly not a valid justification for Model B
per the governing prompt's anti-overfitting rule and is not being treated as one.

## Scope discipline

No change to: application release (`AG_TRADE_ASSISTANT_V1_0_3` unchanged), the frozen
`ST_ASIAN_SWEEP_5R_V1` v1.1.1 strategy file or its live engine code
(`session/setups.py`, `strategy_engine/engine.py`), FX Series 002 evidence/counters, BTC
strategy/qualification/execution, session windows/symbols/quotas, or any execution/order
path. `order_send`/`order_check`/exchange-order calls: 0 (verified by design -- this
work never imports `execution.executor`, `execution.coordinator`, or any broker mutation
path; only read-only MT5 candle fetches, identical to the pre-existing resolver script).

See the top-level structured report for the full field-by-field checklist.
