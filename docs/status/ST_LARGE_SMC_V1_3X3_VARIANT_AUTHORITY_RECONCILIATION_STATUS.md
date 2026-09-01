# ST_LARGE_SMC_V1 — UC-001 Resolution + 3×3 Variant Authority Reconciliation (2026-09-01)

## Scope

Formally record the owner's UC-001 decision (Model B: D1/H1/M5) and reconcile
`ST_LARGE_SMC_V1` against AG's existing E1/E2/E3 × M1/M2/M3 research architecture. No
new SMC rule was invented; no backtest, replay, or golden-slice rerun was performed; no
strategy was activated. Full detail: `docs/specs/LARGE_SMC_V1_SPEC.md` §7, §8-§23,
§30-§35.

## Owner decision recorded

UC-001 = `RESOLVED_BY_OWNER`, selected Model B (`ADOPT_FROZEN_AG_D1_H1_M5`).
`strategies/ST_LARGE_SMC_V1.yaml`'s `timeframe_responsibilities` was updated to
`D1=MACRO_EVENT_REFERENCE`, `H1=STRUCTURE_LOCATION_LIQUIDITY_REACTION`,
`M5=CONFIRMATION_AND_ENTRY`, `H4=OPTIONAL_EVIDENCE_ORIGIN_ONLY` (E3 may accept a
caller-supplied H4-origin liquidity level; H4 is not a primary/mandatory layer),
`M15=NOT_REQUIRED`. The yaml's `M1` timeframe key (1-minute candles) is unaffected and
remains `UNSIGNED` — it is unrelated to the `M1` confirmation maneuver model, a naming
coincidence now documented inline in the yaml itself. `status=RESEARCH_DRAFT`,
`active=false` unchanged; `tests/test_large_smc_registration.py` still passes (2/2).

## What was reused (resource-first policy applied)

No new research, no new code, no external lookup beyond what earlier phases already
gathered. Verified directly against source this pass:

- `src/entry_confirmation/composer.py` — confirmed E and M are a genuinely generic,
  orthogonal cross-join (`compose(e, m)` applies identically to any pair; gated only on
  eligibility, non-excluded M-state, and matching direction). This is the evidentiary
  basis for classifying all nine E×M cells as interface-valid.
- `src/entry_confirmation/entry_models_v1.py` — confirmed `EntryModelState` (a full,
  already-implemented candidate lifecycle), `SMCEntryCombinationResult.combination`
  (variant identity already named `"E1M1".."E3M3"` — nothing to invent), and
  `SMCEntryCombinationResult`'s invalidation fields (candidate-invalidation mechanism,
  explicitly distinct from a broker stop-loss).
- `src/entry_confirmation/e3_liquidity_sweep.py` — confirmed the H4-optional-evidence
  claim precisely (`reference_timeframe` copies the caller's `LiquidityLevel.timeframe`
  verbatim; `CHECK_TIMEFRAME` is always H1).
- `docs/status/TRUE_STAGE2_ORACLE_RECONCILIATION_STATUS.md` and
  `docs/status/SMC_3X3_HISTORICAL_VALIDATION_V1_STATUS.md` — reused as-is (not rerun)
  for golden/empirical coverage per cell (3 golden `READY` setups: E1M2, E1M3, E3M3 ×2
  occurrences across two sampled windows; M1 pairings never formed an entry array in
  either sample).

## 3×3 outcome

`THREE_BY_THREE_STATUS = PARTIAL_3X3_REUSE`. All nine cells are structurally
`VALID_RESEARCH_VARIANT` (interface-confirmed via the generic composer); three have
empirical golden/sampled evidence, six have `INSUFFICIENT_EVIDENCE` (never observed
forming an entry array in either sampled window) — not `SEMANTIC_CONFLICT` and not
`NOT_SUPPORTED`. `ST_LARGE_SMC_V1` legitimately owns the full 3×3 matrix as a research
composition (`GLOBAL_RULES + E_CONTEXT_RULES + M_ENTRY_RULES`), not merely a diagonal
E1→M1/E2→M2/E3→M3 reduction. No individual E×M cell was registered as its own strategy;
`strategies/registry.yaml` is unchanged.

## Contract movement

9 contracts newly `RESOLVED` (C02, C03, C04, C05, C07, C08, C09, C13, C17 — up from 1
resolved), 6 `PARTIALLY_RESOLVED` (C01, C06, C10, C12, C16, C18), 3 still
`UNRESOLVED_CONTRACT` (C11, C14, C15, all previously unresolved and confirmed still
open — no new rule was invented to close them). Reuse tally across the required
component matrix: `EXACT_REUSE=13`, `THIN_ADAPTER=1`, `MISSING=3` (broker SL distance,
profit target, duplicate/re-entry policy), `SEMANTIC_MISMATCH=0`.

## What remains genuinely missing

- **C11 target model** — no AG implementation exists anywhere (no target field in
  `SMCEntryCombinationResult` or the composer). Two external sources converge on a
  candidate (nearest unswept liquidity → LTF swing fallback), but convergence is not
  adoption. This is the **first blocking unresolved contract** for the next phase.
- **C14 duplicate/re-entry** — confirmed, not merely inherited: `selected_combination`
  is always `None`; the composer explicitly defers this decision (spec section 21's
  "0 to 9 combinations" behavior, verified in code this pass).
- **C10's SL-distance half** and **C12's per-model expiry trigger/value** remain
  partially open (mechanisms reused, exact numbers not yet confirmed).

## Safety

`actionable_READY=BLOCKED`, `risk_sizing=BLOCKED`, `portfolio_claim=BLOCKED`,
`proposal_generation=BLOCKED`, `execution=BLOCKED`, `order_check=0`, `order_send=0`.
`AG_TRADE_ASSISTANT_V1_0_2`, `ST_ASIAN_SWEEP_5R_V1 v1.1.1`, Stage1/Stage2, and the
golden oracle are all unchanged. `smc-lss-platform` was not re-read this phase (not
needed — AG's own resources answered every question this reconciliation required, per
the resource-first policy).

## Tests

`pytest tests/test_large_smc_registration.py` — 2 passed (only test touching the
changed yaml field). No other production code changed. Repo-wide suite and golden slice
were not run (correctly, per policy — nothing that could invalidate them changed).

## Files changed

- `strategies/ST_LARGE_SMC_V1.yaml` — `timeframe_responsibilities` updated per UC-001.
- `docs/specs/LARGE_SMC_V1_SPEC.md` — UC-001 recorded resolved; C03-C13/C18 statuses
  updated; new §32-35 (3×3 reconciliation, composition contract, reuse matrix, next
  blocking item).
- `docs/status/ST_LARGE_SMC_V1_3X3_VARIANT_AUTHORITY_RECONCILIATION_STATUS.md` — this
  document.

## Next phase

`RESOLVE_FIRST_BLOCKING_STRATEGY_CONTRACT` — UC-010 (C11 target model). No AG
implementation exists to adopt; the two external candidates (ST-C1 G9, `v3.6`) converge
but require an explicit owner adoption decision, not merely a reconciliation pass.
