# ST_LARGE_SMC_V1 — C11 Contract Finalization (2026-09-01)

Status: **C11_RESOLVED**. Owner decision (Candidate 2,
`HYBRID_WITH_STRUCTURAL_FALLBACK`) made deterministic and reproducible; strategy version
bumped `1.0.0 → 1.0.1`; `RESEARCH_DRAFT` preserved; no engine, proposal, or execution
authority added.

## Baseline gate

`git status --short` before this phase showed exactly the prior phase's accepted,
uncommitted work: `docs/specs/LARGE_SMC_V1_SPEC.md` and `strategies/ST_LARGE_SMC_V1.yaml`
modified, plus two new `docs/status/` files (3×3 reconciliation, C11 resolution). No
ambiguous or unattributed change was present. `HEAD` (`3842c6b`) is the last commit;
nothing since. Baseline accepted.

## Version policy (read from repository authority, not assumed)

`docs/VERSION_HISTORY.md:35-37`: *"A strategy version bump is required if a change
affects: setup qualification, sweep definition, direction, entry, confirmation, stop,
**targets**, session strategy logic, or intrinsic trade eligibility logic."* — `targets`
is named explicitly; C11 qualifies. `strategies/STRATEGY_LEDGER.md`'s only precedent for
resolving a previously-`UNSIGNED`/ambiguous field via already-frozen logic is
`ST_ASIAN_SWEEP_5R_V1` v1.1.0 → v1.1.1 (`entry_order_type` ambiguity resolved by showing
only one order type was ever consistent with the frozen entry logic — a **patch**
increment). A second, weaker-fit precedent (v1.0.0 → v1.1.0, adding a whole new
session/trade pair) would suggest a **minor** increment instead. Given `ST_LARGE_SMC_V1`
is not yet active/operational (no prior version-bump precedent of its own,
`RESEARCH_DRAFT` throughout, no promotion implied), the v1.1.1 precedent is the closer
analogy: **patch** — `1.0.0 → 1.0.1`. Recorded transparently in case the owner reads
this differently; not silently assumed (`docs/VERSION_HISTORY.md` itself does not name
an exact digit for this case).

`strategies/registry.yaml` stores no strategy version for any entry (verified directly)
— `registry_version_sync_required = NO`, confirming the prior phase's finding.

## Status-maintenance policy applied

Per `docs/status/LIVE_STATUS_MAINTENANCE.md`'s trigger list ("a previously documented
gap is closed" applies — C11 was `MISSING`, now `CONTRACT_ONLY`/frozen) and required
update sequence: `PROJECT_STATUS.md` updated (rolling snapshot's Large-SMC paragraph);
`docs/README.md` updated (new dated evidence documents linked); `strategies/
STRATEGY_LEDGER.md` updated (version lineage entry, historical v1.0.0 content
preserved, not rewritten); `docs/VERSION_HISTORY.md` updated (Strategy Version History
table + explanatory bullet). Top-level `README.md` was **not** touched — no
user-observable/operable capability changed (still `RESEARCH_DRAFT`, no engine, no
authority change), so it is out of scope per the maintenance doc's own rule ("update
`README.md` if users can observe or operate the changed capability").

## C11 — deterministic freeze

`C11_OWNER_SEMANTICS = RESOLVED_BY_OWNER` (Candidate 2 selected in the prior phase).
`C11_IMPLEMENTATION_SPEC = COMPLETE` — every field below was resolved by reuse of an
already-existing, already-frozen AG mechanism; nothing was invented from a blank page.

- **Target anchor**: `SELECTED_M_MODEL_CANDIDATE_ENTRY_PRICE` —
  `SMCEntryCombinationResult.entry_price` (composer's `_entry_summary()`). Decision
  timestamp reuses the M-model's own entry-availability timing; no new timestamp field.
- **Scope**: `GLOBAL` — one rule across all 9 E×M cells; inputs are only direction and
  anchor price, independent of which E or M produced the candidate.
- **Primary tier — `OPPOSING_EXTERNAL_UNSWEPT_LIQUIDITY`, timeframe M5.** Verified via
  `src/historical_replay/stage2.py:158`: `external_swing_liquidity(symbol, "M5",
  tiers.external, m5_candles)` — the frozen research pipeline itself already computes
  this on M5, not H1. Candidate universe = `market_structure.tiers.StructureTier`'s
  `latest_swing_high`/`latest_swing_low` (EXTERNAL tier, `swing_length=50`), reached via
  `liquidity.hierarchy.external_swing_liquidity()`. Required status = `UNSWEPT`
  (`liquidity.status.compute_status`). Direction: LONG → nearest qualifying `BUY_SIDE`
  candidate strictly above anchor; SHORT → nearest qualifying `SELL_SIDE` candidate
  strictly below anchor (grounded in `LiquiditySide` and the existing directional
  `_is_between` logic in `hierarchy.py`, not invented). **Tie-break: `NOT_APPLICABLE`**
  — `latest_swing_high`/`latest_swing_low` are singular fields; this candidate universe
  is structurally at most one value per side, so no lookback/tie-break parameter needed
  to be invented for the primary tier.
- **Fallback tier — `CONFIRMED_M5_SWING_EXTREMUM`.** Candidate universe =
  `StructureTier.swings` (**"ALL confirmed swings this tier, chronological"** —
  `market_structure/models.py:78`), the same list `latest_swing_high/low` are
  themselves reduced from, filtered to `UNSWEPT` + correct side, excluding whichever
  swing the primary tier already evaluated. No new swing algorithm — same detector,
  broader slice of its own already-computed output. Confirmation/no-lookahead: reuses
  market_structure's existing confirmed-swing point-in-time guarantee (previously
  verified project-wide, no future-candle dependency). **Tie-break: most recent
  `origin_time` wins** — this is not an invented rule; it is `market_structure/
  tiers.py::_build_tier`'s own existing reduction convention, copied verbatim:
  `latest_swing_high = next((p for p in reversed(labeled_swings) if p.kind in
  high_kinds), None)` (`tiers.py:111-112`) — "scan the confirmed swing list in reverse,
  take the first (most recent) match" is already how AG collapses a swing list to one
  candidate; applying the same convention to the fallback tier's own reduction is
  internally consistent reuse, not new invention.
- **Priority**: Tier 1 wins outright whenever any valid candidate exists — no
  cross-tier comparison, no "better" selection between tiers.
- **No-target**: `NO_TRADE` / `REJECT_NO_TARGET`. `READY` with a null target is
  `PROHIBITED`.
- **Mode**: `STATIC` — selected once at candidate qualification; no dynamic
  retargeting, no trailing target; any future change to this is a separate
  strategy-semantic version.
- **Provenance fields** (specification only, not implemented): `target_price,
  target_tier, target_type, target_source, target_source_id, target_side,
  target_status_at_selection, target_selected_at, target_anchor_price,
  target_anchor_source, target_evidence_timestamp`.
- **Explicitly out of scope, unchanged**: setup invalidation, broker stop-loss (C10),
  fixed-R target, TP1/TP2/partials/runner/breakeven/trailing (trade management).

No item required `OWNER_DECISION_REQUIRED_FOR_C11_DETERMINISM` — every previously-open
question (candidate universe, lookback, tie-break, chronology, no-target state, static
vs. dynamic) resolved to an existing AG mechanism once traced far enough (Stage2's exact
M5 wiring; `StructureTier`'s existing "latest wins" reduction convention).

## YAML reconciliation

`strategies/ST_LARGE_SMC_V1.yaml` — added a `target_model:` block
(`status: CONTRACT_ONLY`, `implementation: NOT_IMPLEMENTED`) directly under `entry:`;
`exit_and_lifecycle.profit_targets: UNSIGNED` replaced with
`profit_target_source: C11_TARGET_MODEL` (pointing at the new block, not claiming
implementation). No other `exit_and_lifecycle` field (`initial_stop`, `partial_profit`,
`breakeven`, `maximum_holding_period`) was touched — C10/C14/trade-management remain
separately tracked and `UNSIGNED`. `version: 1.0.0 → 1.0.1`. `purpose:` prose
synchronized from the stale "D1/H4/H1 context" wording to the UC-001-accepted "D1/H1
primary context with M5 confirmation/entry; H4-origin evidence only where an existing
E-model contract explicitly allows it" — `NARRATIVE_SYNCHRONIZATION`, not a new
semantic change (this file was already being legitimately edited for C11, so the
previously-deferred cleanup was bundled in, per the prior phase's own stated condition).
`status: RESEARCH_DRAFT` and `authority.*` block (`active: false`,
`proposal_generation_authorized: false`, `demo_authorized: false`,
`live_authorized: false`) — unchanged.

## Non-regression / authority

No file under `src/` was modified: `liquidity/`, `market_structure/`,
`entry_confirmation/`, `composer.py`, Stage1, Stage2, `trade_management`, `portfolio`,
`risk`, `execution`, `mt5` — all untouched (verified via the diff boundary check below).
`AG_TRADE_ASSISTANT_V1_0_2` and `ST_ASIAN_SWEEP_5R_V1 v1.1.1` unaffected.
`actionable_READY`, `portfolio_authority`, `risk_sizing_authority`,
`proposal_authority`, `execution_authority` remain `BLOCKED`; `order_check=0`,
`order_send=0`. A new strategy version does not imply promotion.

## Diff boundary check

```
git status --short (after this phase):
 M docs/README.md
 M docs/VERSION_HISTORY.md
 M docs/specs/LARGE_SMC_V1_SPEC.md
 M PROJECT_STATUS.md
 M strategies/ST_LARGE_SMC_V1.yaml
 M strategies/STRATEGY_LEDGER.md
?? docs/status/ST_LARGE_SMC_V1_3X3_VARIANT_AUTHORITY_RECONCILIATION_STATUS.md
?? docs/status/ST_LARGE_SMC_V1_C11_CONTRACT_FINALIZATION_STATUS.md
?? docs/status/ST_LARGE_SMC_V1_C11_TARGET_MODEL_RESOLUTION_STATUS.md
```

No `src/` file, no execution file, no Session-strategy file, and no unrelated
pre-existing change was touched or overwritten.

## Next remaining blocker

Per `docs/specs/LARGE_SMC_V1_SPEC.md` §35 (updated): completeness is now `RESOLVED=10`
(C02, C03, C04, C05, C07, C08, C09, **C11**, C13, C17), `PARTIALLY_RESOLVED=6` (C01,
C06, C10, C12, C16, C18), `UNRESOLVED_CONTRACT=2` (C14, C15). Following this project's
own expected sequence (C11 target → C12 expiry residual → C14 duplicate/re-entry):
**UC-011 — C12 (expiry) residual semantics** is next — the `EXPIRED` state mechanism is
already reused, but the exact per-model trigger (bar-count/time-horizon/weekend-close)
was never independently verified, and C11's now-frozen anchor/timing model gives it
something concrete to resolve against. **UC-013 — C14 (duplicate/re-entry)** remains
the following, fully open item.

## Tests

`pytest tests/test_large_smc_registration.py tests/test_dual_workflow_boundaries.py` —
6/6 passed (yaml changed; these are the tests that read it). Full repo suite and golden
slice not run — no `src/` or replay code changed.

## Files changed

`strategies/ST_LARGE_SMC_V1.yaml`, `docs/specs/LARGE_SMC_V1_SPEC.md`,
`docs/VERSION_HISTORY.md`, `strategies/STRATEGY_LEDGER.md`, `PROJECT_STATUS.md`,
`docs/README.md`, and this document. No production source file changed.
