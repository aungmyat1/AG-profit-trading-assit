# AG V2-2A / V2-2B Implementation Status

Date: 2026-09-21
Classification: **VERIFIED** (V2-2A and V2-2B, pending only the still-open items under "Known limitations" below)

## Objective

Close Audit #1 remediation for candidate authority continuity and implement the V2-2B candidate store + transition ledger using existing repository persistence primitives.

## History (superseded content below kept for lineage, not re-stated as current)

The first remediation pass (commits `4955abe`, `8c2018c`, `10ce589`, `7bbcbc3`, `aa2def0`) fixed candidate authority continuity but, because it replaced the engine's core transition function rather than extending it, silently dropped two properties the original (pre-remediation) engine had and that this project's own safety invariants require:

- **Semantic no-op detection** (Safety Invariant #8): a repeated observation with unchanged `stage`/`outcome`/`raw_strategy_state` was incorrectly advancing `revision` and minting a new `FunnelTransition` on every poll.
- **Terminal stickiness** (Safety Invariant #9): a candidate that had reached a terminal outcome (`REJECT`/`INVALIDATED`/`EXPIRED`/`ERROR`) could be silently reactivated to a non-terminal outcome by an ordinary later observation.

An independent re-audit (`AG_V2_INDEPENDENT_REAUDIT_01`) reproduced both defects with a direct script against the running code (not just a test-suite read) and classified the checkpoint `AUDIT_REQUIRES_REMEDIATION` / `SAFE_TO_ADVANCE = NO`. This document now records the second remediation pass that restores both properties.

## V2-2A: current state

`src/opportunity/engine.py::evaluate_funnel` now has three independent fail-closed/no-op layers, applied in this order:

1. **Identity continuity** (unchanged from the first remediation): adapter-vs-binding and, when a previous candidate is supplied, candidate-vs-binding/event mismatches on `strategy_id`, `strategy_version` (when the binding provides one), `strategy_engine_version` (when the binding provides one), `symbol`, `market`, `venue`, and `market_data_mode` all raise `CandidateIdentityMismatchError`/`AdapterIdentityMismatchError`/`ObservationIdentityMismatchError`.
2. **Terminal stickiness** (restored): if `previous_candidate.outcome` is in `TERMINAL_OUTCOMES` (`REJECT`, `INVALIDATED`, `EXPIRED`, `ERROR` -- the same terminal dispositions `stages.py`'s `FUNNEL_OUTCOMES` vocabulary defines, not a second/competing outcome model), the adapter is not even invoked and `evaluate_funnel` returns `(previous_candidate, None)` unchanged. A genuinely new setup after termination must become a new occurrence via the candidate-store/identity layer; this engine does not attempt that reinterpretation itself.
3. **Semantic no-op detection** (restored): after the adapter's `project()` call, if `(stage, outcome, raw_strategy_state)` is unchanged from the previous state, `evaluate_funnel` returns `(previous_candidate, None)` -- no new revision, no new `FunnelTransition`. Per-cycle-only fields (`reason_codes`, evidence maps) and strategy-owned geometry remain intentionally excluded from this comparison, matching the original engine's documented rationale (they are not part of `FunnelState`/`FunnelProjection`'s persisted semantic vocabulary).

`evaluate_funnel`'s return type is now `Tuple[OpportunityCandidate, Optional[FunnelTransition]]`. A `None` transition means the caller has nothing new to persist; the caller must not synthesize or persist a placeholder transition for scheduler polling activity.

## V2-2B: current state

`src/opportunity/candidate_store.py::CandidateStore` is unchanged from the first remediation pass (no code changes were required here -- the defect was entirely upstream in the engine). It:

- reuses `runtime_state.store.JsonKeyValueStore` directly (no duplicate persistence primitive);
- stores one candidate's current materialization plus its full append-only transition history under one key, written via a single `JsonKeyValueStore.put()` call, so a candidate-state update and its transition append cannot be torn across two writes;
- fails closed (raises `CandidateConflictError`) on revision gaps, revision regression, transition/candidate identity mismatches, and occurrence/strategy/symbol/market/venue/data-mode drift between persisted revisions;
- is idempotent on exact-identity replay (same `transition_id` + same content is a no-op);
- inherits `JsonKeyValueStore`'s documented corruption behavior (`StateStoreCorrupted` propagates unhandled -- never silently resets to `{}`) and its documented concurrency boundary (thread-safe within one process, not cross-process).

Because the engine now correctly suppresses transitions for genuine no-op polls (see V2-2A above), the store's contiguous-revision/idempotence checks now receive the right signal end-to-end: four repeated polls of one unchanged logical setup produce exactly one persisted candidate revision and one persisted transition, not four -- proven by a new end-to-end test (see Tests below).

## Tests

New/extended coverage added in this remediation pass:

- `tests/test_opportunity_engine.py`: fixed one test that had been asserting the buggy always-increment behavior; added `test_equivalent_projection_is_no_change`, `test_repeated_equivalent_projection_remains_stable_across_polls` (4 polls), `test_terminal_candidate_cannot_be_reactivated` and `test_repeated_terminal_observation_remains_stable` (both parametrized over the full `TERMINAL_OUTCOMES` set), `test_terminal_set_matches_authoritative_outcome_vocabulary`, parametrized continuity coverage extended to `engine_version`/`market`/`venue` (previously only `strategy`/`version`/`symbol`/`mode` were covered), and a mandatory engine+store end-to-end dedup test (`test_engine_and_store_deduplicate_repeated_unchanged_polls`) simulating 4 scheduler polls through both `evaluate_funnel()` and `CandidateStore.persist()` together.
- `tests/test_opportunity_candidate_store.py`: added `test_geometry_and_evidence_round_trip_through_restart` (non-default `raw_strategy_state`, `context_evidence`, `setup_evidence`, `trigger_evidence`, and a populated `CandidateGeometry` including multi-value `targets`, round-tripped through a fresh `CandidateStore` instance), `test_corrupted_store_fails_closed_not_empty`, and `test_corrupted_store_non_dict_json_fails_closed` (both asserting `StateStoreCorrupted` propagates rather than the store silently resetting to empty).

Executed results (this pass, local run):

```bash
PYTHONPATH=src python -m pytest tests/test_opportunity_engine.py tests/test_opportunity_candidate_store.py -q
# 36 passed

PYTHONPATH=src python -m pytest tests/ -k "opportunity" -q
# 98 passed, 3729 deselected, 0 failed, 0 errors, 0 skipped

PYTHONPATH=src python -m pytest tests/test_runtime_state_store.py -q
# 7 passed
```

Direct behavioral proof (independent of pytest, per the re-audit's own bar for evidence):

```text
4 identical polls of one unchanged setup:
  poll 1: revision=1, transition=YES
  poll 2: revision=1, transition=NO
  poll 3: revision=1, transition=NO
  poll 4: revision=1, transition=NO
  total semantic transitions across 4 polls: 1

terminal candidate (INVALIDATED) + ordinary later poll:
  outcome remains INVALIDATED, revision unchanged, transition=NO
```

## Authority

No strategy semantics changed. No proposal authority, Demo authority, Live authority, broker execution, Telegram delivery, or frontend authority is granted or touched by this remediation. No broker order was placed.

## Known limitations (not blocking, recorded for lineage)

- `strategy_version`/`strategy_engine_version` continuity checks remain no-ops whenever the resolved `StrategyBinding` does not itself carry a value for that field (currently true for every registry-resolved binding, since `registry_binding.py` never populates `semantic_version`). This is intentional (never fabricate a value to compare against) but means the guarantee is currently vacuous in practice for real registered strategies.
- `CandidateStore.all_candidates()` restart reconstruction is tested for the single-candidate case; multi-candidate restart reconstruction and a crash-mid-write scenario (as opposed to a store that is already fully corrupted) are not separately tested.
- The pre-remediation `decide_transition`/`TransitionDecision` implementation that originally had these properties was never committed to git history (confirmed via `git log --all` / history grep across every branch); this remediation restores the same semantics from the previous audit record rather than recovering a prior commit.

## Next gate

Both V2-2A and V2-2B now have executed, passing evidence for identity continuity, semantic no-op detection, terminal stickiness, and engine+store end-to-end deduplication. Subject to independent re-audit confirming this record:

1. V2-3A Large-SMC shadow adapter
2. V2-3B SSC shadow/replay adapter
3. semantic parity checkpoint

Do not advance strategy adapters on the basis of this document alone -- independent verification should re-run the commands above against the actual committed state.
