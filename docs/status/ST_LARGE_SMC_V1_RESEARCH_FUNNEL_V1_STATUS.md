# ST_LARGE_SMC_V1 — RESEARCH_ONLY_FUNNEL_V1 Status

Date: 2026-09-02. Strategy version: **1.0.5**. Phase: `RESEARCH_ONLY_FUNNEL_V1`.
Environment: Python 3.14.0, pytest 8.3.5, Windows, repo `D:\ddev\AG profit trading`.

## 1. Funnel architecture implemented

```
DATA COLLECTION:  MT5/broker data -> closed D1/H1/M5 candles -> market structure,
                  liquidity, OB/FVG -> E1/E2/E3 context -> M1/M2/M3 confirmation ->
                  deterministic E*M candidate occurrences
                  (100% reused: historical_replay.stage1/stage2, entry_confirmation/*)

DECISION MAKING:  candidate validity -> simultaneous-combination resolution (C18) ->
                  entry (M-model entry_price) -> broker stop (C10, BLOCKED) ->
                  target (C11, IMPLEMENTED) -> pending-entry expiry (BLOCKED) ->
                  explicit LargeSMCResearchDecision
                  (src/large_smc_research/ -- new, thin)
```

## 2. Files changed

New:
- `src/large_smc_research/__init__.py`, `decision.py`, `target_model.py`, `engine.py`
- `scripts/run_large_smc_discovery.py`
- `tests/test_large_smc_research_engine.py` (13 tests), `tests/test_large_smc_target_model.py` (7 tests) -- 20 total
- `docs/status/ST_LARGE_SMC_V1_C10_STOP_LOSS_DECISION_PACKET.md`
- `docs/status/ST_LARGE_SMC_V1_PENDING_ENTRY_EXPIRY_DECISION_PACKET.md`
- this document

Modified:
- `strategies/ST_LARGE_SMC_V1.yaml` (v1.0.4 → 1.0.5: C01/C16/C18 resolved, C11 adapter
  `IMPLEMENTED`, `decision_states` fixed, C10/pending-expiry annotated
  `BLOCKED_AWAITING_OWNER_DECISION`)
- `strategies/registry.yaml` (`engine:` field now factual, still no authorization change)
- `strategies/STRATEGY_LEDGER.md`, `docs/VERSION_HISTORY.md`,
  `docs/specs/LARGE_SMC_V1_SPEC.md` (new §36), `PROJECT_STATUS.md`, `docs/README.md`,
  `README.md`, `docs/architecture/STRATEGY_WORKFLOW_RESOURCE_MAP.md`
- `tests/test_large_smc_registration.py` — one assertion updated (see §6)

Not modified: `entry_confirmation/`, `historical_replay/stage1.py`/`stage2.py`,
`proposals/identity.py`, `proposals/lifecycle.py`, `composer.py`, any `execution/`,
`assistant/`, or `strategy_manager/` module.

## 3. Existing modules reused (zero redetection)

`historical_replay.stage2.evaluate_entry_stage_canonical_v2` (M1/M2/M3 + composer,
already golden-validated), `historical_replay.stage1.QualifiedEEvent.is_eligible_at`
(C12), `historical_replay.orchestrator.run_replay`/`FunnelTracker`/`SetupLedger`,
`proposals.identity.setup_id`/`reference_key_for`, `proposals.occurrence_identity.
eligibility_interval_id`/`candidate_occurrence_id` (implemented in C14B, wired into a
real caller for the first time here), `liquidity.hierarchy.external_swing_liquidity`,
`liquidity.status.compute_status`, `market_structure.tiers.StructureTier`/
`analyze_structure_tiers`.

## 4. Contracts frozen this phase

- **C01 (instrument list):** `[EURUSD]` only. GBPUSD deferred.
- **C16 (warmup):** `{D1: 60, H1: 50, M5: 200}`, reused from
  `historical_replay/orchestrator.py`'s own constants.
- **C11 (target model) adapter:** `IMPLEMENTED` (formula unchanged from the owner's
  2026-09-01 freeze).
- **C18 (simultaneous-combination selection):** `RECORD_ALL_INDEPENDENTLY`, reuse of
  C14's already-frozen `selection`/`coexistence` fields.
- **decision_states vocabulary:** `RESEARCH_QUALIFIED`/`WATCH`/`NO_TRADE`/`DATA_ERROR`/
  `EXPIRED`/`INVALIDATED`/`BLOCKED` (placeholder `READY` removed — never emitted).

## 5. Contracts remaining blocked (owner decision required)

- **C10 (broker stop-loss distance):** UNSIGNED. See
  `docs/status/ST_LARGE_SMC_V1_C10_STOP_LOSS_DECISION_PACKET.md`.
- **Post-READY pending-entry expiry:** UNSIGNED. See
  `docs/status/ST_LARGE_SMC_V1_PENDING_ENTRY_EXPIRY_DECISION_PACKET.md`.
- Consequence: fill simulation, invalidated-before-fill, expired-unfilled, intrabar
  ambiguity, and completed-outcome resolution were **not attempted**.

## 6. Component test commands and results

```
python -m pytest -q
```

- Baseline run (before this phase's fixes): **1215 passed, 2 failed** (0:51:43).
  - `tests/test_large_smc_registration.py::test_large_smc_is_separate_and_fail_closed`
    — failed on a literal-string assertion (`engine == "NOT_IMPLEMENTED"`) that this
    phase's own, intended change (a real research-only engine now exists) correctly
    supersedes. Fixed by asserting the actual invariant that matters instead (no
    proposal/demo/live/execution authority in the engine field's own text), not the
    stale literal.
  - `tests/test_supply_demand.py::test_order_blocks_and_fvg_live_eurusd[H1]` — a
    live-MT5-guarded test, unrelated to any file this phase touched
    (`supply_demand/`'s live order-block geometry from the currently connected demo
    feed). Confirmed non-reproducible and unrelated: passed cleanly on the very next
    full run with no code change (live market data varies between runs; this is
    pre-existing flakiness in that test, not caused by this phase). Not fixed — out of
    this phase's scope.
- Final run (after the one intentional test fix, no other code changes): **1237
  passed, 0 failed** (0:49:17).
- New tests added this phase (`test_large_smc_research_engine.py` +
  `test_large_smc_target_model.py`, run standalone and offline — no MT5, no CSV, no
  `historical_data_context`): **20 passed**, included in the 1237 total above.
- Large-SMC-adjacent suites, run standalone to confirm nothing shared broke
  (`test_candidate_occurrence_identity.py`, `test_replay_orchestrator.py`,
  `test_historical_replay_no_lookahead.py`): **37 passed**.

## 7. Discovery dataset contract

- Source: `D:\EURUSD_M5_202504211715_202607310000.csv` (real MT5 export, base
  resolution M5), the same file the prior `SMC_3X3_HISTORICAL_VALIDATION_V1` phase used.
- Full dataset range: 2025-04-21T14:15 UTC → 2026-07-30T21:00 UTC (95,393 M5 rows, 15
  unexpected gaps flagged across the whole file by the existing ingestion gap
  classifier — not new to this phase).
- Derived timeframes: M15 (31,788 bars), H1 (7,937 bars), H4 (1,976 bars, broker-day
  anchored), D1 (320 bars, broker-day anchored) — via the existing, unchanged
  `historical_replay.resampler`.
- Discovery window evaluated this phase: **2025-09-01T00:00 → 2025-09-30T00:00 UTC**
  (one month), deliberately not the reserved final validation period at the end of the
  dataset (2026, per task instruction not to inspect/tune against it).
- Command:
  ```
  python scripts/run_large_smc_discovery.py D:\EURUSD_M5_202504211715_202607310000.csv \
      EURUSD 2025-09-01T00:00:00 2025-09-30T00:00:00 \
      docs/status/large_smc_discovery_2025-09.json
  ```
  Load: 47.96s. Replay: 5327.81s (0.88s/step). Full JSON:
  `docs/status/large_smc_discovery_2025-09.json`.

## 8. Funnel counts (2025-09, one month, EURUSD)

| Stage | Count |
|---|---|
| 1. Raw M5 periods | 6,047 |
| 2. Valid-data periods | 6,047 (0 excluded for warmup — dataset history predates the window) |
| 3. E-qualified events (distinct) | 9 (E1: 2, E2: 1, E3: 6) |
| 4. M-confirmed events (distinct) | 5 (M1: 0, M2: 2, M3: 3) |
| 5. Composed candidates (distinct setup×combo) | 27 |
| 6. Selected candidates (C18: RECORD_ALL, no narrowing) | 27 |
| 7. Entry-array-created (distinct) | 5 |
| 8. READY-equivalent, BLOCKED pending C10/expiry decision | **3** (E1M2×1, E1M3×1, E3M3×1) |
| 9–13. Filled / invalidated-before-fill / expired-unfilled / intrabar-ambiguous / unambiguous-completed | **NOT_ATTEMPTED** (blocked by unsigned C10/pending-expiry — never fabricated) |

Identity: 0 collisions, 3 `LIFECYCLE_CREATED` events (matches the 3 READY-equivalent
occurrences exactly — no duplication, no missed occurrence).

Per-combination detail (full 3×3): **E1M1** 2 composed / 0 confirmed. **E1M2** 2 / 2
confirmed / 1 READY-equivalent. **E1M3** 2 / 1 confirmed / 1 READY-equivalent. **E2M1**
1 / 0. **E2M2** 1 / 0. **E2M3** 1 / 0. **E3M1** 6 / 0. **E3M2** 6 / 0. **E3M3** 6 / 2
confirmed / 1 READY-equivalent.

## 9. Intrabar ambiguity and data-quality notes

- Intrabar ambiguity: not assessable this phase (fill resolution not attempted).
- Data quality: 15 unexpected gaps flagged across the *whole* 15-month source file by
  the pre-existing ingestion gap classifier — not new to this phase, not concentrated
  in the evaluated September window, and already the accepted baseline from the prior
  `SMC_3X3_HISTORICAL_VALIDATION_V1` run against the same file.
- Causal defects: none found. `identity_collisions=0`; `LIFECYCLE_CREATED` count
  exactly matches the READY-equivalent count; the funnel is entirely closed-bar,
  no-lookahead by construction (unchanged `historical_data_context`).
- Evidence concentration: M1 produced zero READY-equivalent evidence this window (0
  across all three E-pairings) — consistent with, not a new deviation from, the
  previously documented golden-baseline finding that M1 rarely forms an entry array in
  sampled windows. The three occurrences that did form span three *different* E×M
  cells (E1M2, E1M3, E3M3), not one dominant variant.

## 10. GO / CONDITIONAL_GO / NO_GO recommendation

**CONDITIONAL_GO.**

What the evidence supports: the data-collection and candidate-composition layers are
deterministic, causal (no lookahead, no identity collisions), and produce a small but
genuinely non-degenerate, non-concentrated stream of distinct research occurrences (3
independent READY-equivalent candidates across 3 different E×M cells in one month, from
27 composed candidates, with exact identity/lifecycle agreement). Nothing here indicates
a structural defect in the funnel itself.

What blocks a plain GO: the sample is one month out of a much longer dataset — too
small on its own to judge occurrence sufficiency — and, more fundamentally, **outcome
simulation cannot begin at all** until C10 (broker stop-loss) and post-READY
pending-entry expiry are resolved. This is a structural block, not a strategy-quality
concern; nothing here suggests NO-GO (no causal defect, no evidence a single variant
dominates, no guessed contract).

**Recommended next step:** owner reviews the two decision packets
(`ST_LARGE_SMC_V1_C10_STOP_LOSS_DECISION_PACKET.md`,
`..._PENDING_ENTRY_EXPIRY_DECISION_PACKET.md`) and signs one option for each. Once
signed, re-run this same discovery script (unchanged) over a wider window (still
excluding the reserved final validation period) to assess whether fill/invalidation/
target-reachability produce enough unambiguous completed outcomes to justify full
validation — that is the next honest checkpoint, not this one.

## 11. Authority confirmation

`strategies/ST_LARGE_SMC_V1.yaml`: `active: false`, `proposal_generation_authorized:
false`, `demo_authorized: false`, `live_authorized: false` — unchanged.
`strategies/registry.yaml`: same three booleans unchanged for `ST_LARGE_SMC_V1`.
`src/large_smc_research/` calls no `execution.*`, `assistant.commands.*`, or
`order_check`/`order_send` path anywhere; `simulated_broker_stop` is always `None`.
Proposal, risk-sizing, demo, live, and execution authority remain exactly as disabled
as before this phase.
