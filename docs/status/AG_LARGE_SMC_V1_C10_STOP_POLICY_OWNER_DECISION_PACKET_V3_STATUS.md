# ST_LARGE_SMC_V1 -- C10 Broker Stop-Loss Distance: Owner Decision Packet V3 (SIGNED, 2026-09-07)

Status: **SIGNED_AND_LOCKED**. Supersedes
`docs/status/AG_LARGE_SMC_V1_C10_STOP_POLICY_OWNER_DECISION_PACKET_V2_STATUS.md`'s
still-pending decisions (2026-09-07, same day) with an explicit owner selection.
V2 and the original 2026-09-02 packet are preserved unchanged as historical governance
record -- this document does not erase them, it records what the owner ultimately chose.

```text
governance_contract_id  = C10_STRUCTURAL_INVALIDATION_V1
strategy_id              = ST_LARGE_SMC_V1
strategy_version_before  = 1.0.6
strategy_version_after   = 1.0.7
application_release      = AG_TRADE_ASSISTANT_V1_0_3 (unchanged)
supersedes                = AG_LARGE_SMC_V1_C10_STOP_POLICY_OWNER_DECISION_PACKET_V2_STATUS.md
implementation_authorized = YES
owner_decision_date       = 2026-09-07
```

## DECISION_1_STRUCTURAL_BUFFER -- SIGNED

```text
model       = DYNAMIC_ATR_WITH_HARD_FLOOR
formula     = max(1.5 pips, 0.35 x ATR14(M5))
ATR_source  = closed M5 candles only, fetched via the same already-patched, replay-safe
              historical_replay.stage2.get_latest_candles seam target selection already
              uses in this engine (no second MT5-access pattern introduced)
ATR_missing_or_insufficient = FAIL_CLOSED (ATR_NOT_READY) -- never silently degrades to
              the 1.5-pip floor alone
```

This supersedes V2's proposed static-1.5-pip-only option, which was never implemented
in any commit and is not active evidence.

## DECISION_2_SPREAD -- SIGNED

```text
mode          = SIDE_AWARE
long_policy   = anchor - buffer (no spread term)
short_policy  = anchor + buffer + verified live spread (ask - bid)
missing_required_spread_action = FAIL_CLOSED (SHORT only; LONG never requires spread)
double_count_guard = spread appears exactly once in the SHORT formula; unit-tested
                     (tests/test_c10_stop_policy.py::test_short_spread_not_double_counted)
```

## DECISION_3_BROKER_MIN_STOP -- SIGNED

```text
policy = REJECT
reason = preserve the strategy's own computed structural geometry and R:R; broker
         constraints normalize execution capability, they do not redefine strategy
         economics
widen_authorized = NO
```

## Implementation

```text
module            = src/large_smc_research/c10_stop_policy.py
engine_wiring      = src/large_smc_research/engine.py (_evaluate_combination's final
                     branch: RESEARCH_QUALIFIED on success, BLOCKED on
                     C10StopPolicyViolation, DATA_ERROR on MarketDataError)
strategy_contract  = strategies/ST_LARGE_SMC_V1.yaml stop_loss_contract block
tests              = tests/test_c10_stop_policy.py (23 tests: buffer floor/ATR-wins/
                     boundary, LONG/SHORT formulas, no-double-spread, all fail-closed
                     paths, determinism, no-lookahead via ATR window control),
                     tests/test_large_smc_research_engine.py (5 new/updated tests:
                     RESEARCH_QUALIFIED reachability, ATR-not-ready BLOCKED, missing-tick
                     DATA_ERROR, LONG ignores missing tick, invalid-spread BLOCKED)
min_stop_broker_metadata_wiring = NOT WIRED into the engine's live call path -- this
                     engine documents "zero MT5 access of its own" beyond the already-
                     patched stage2.get_latest_candles/.get_tick/analyze_structure_tiers
                     seams; no such seam exists for live SymbolMeta.trade_stops_level
                     that would remain replay-safe. The REJECT policy is fully
                     implemented and unit-tested in compute_c10_stop() itself
                     (min_stop_distance_price parameter); it evaluates as NOT_APPLICABLE
                     at the current engine call site until a replay-safe broker-metadata
                     seam is introduced (out of this task's scope; the check never
                     silently PASSes or WIDENs in the interim).
```

## Version/provenance

Strategy version bumped `1.0.6 -> 1.0.7`, following the same precedent already
established by `1.0.5 -> 1.0.6` (pending-entry expiry resolution): resolving a
previously-declared-`BLOCKED` unsigned contract gap that changes reachable decision
states (`RESEARCH_QUALIFIED` is now reachable) is treated as a strategy-semantic event
requiring a version bump, per `strategies/STRATEGY_LEDGER.md`'s own established
convention -- not inferred from the filename or assumed.

No historical Large-SMC evidence existed under v1.0.6 attribution (the strategy was
`BLOCKED` for every candidate that would have reached this point), so there is no
re-attribution risk: nothing is reinterpreted, nothing is overwritten.

## AG-EGSVF evidence

`C10_STOP_POLICY` gate: `UNSIGNED -> PASS`, derived by
`src/validation_framework/adapters/large_smc_adapter.py` from the signed contract +
implementation + tests above (never inferred from file existence alone). Determinism
evidence regenerated for v1.0.7
(`artifacts/validation_evidence/determinism/ST_LARGE_SMC_V1_1.0.7_*.json`, PASS,
digests equal). The canonical `AG_EGSVF_V1` evaluator -- not this document -- determines
promotion eligibility; see the regenerated portfolio ledger for its actual result.

## What this signing did NOT do

- Did not change M1/M2/M3 detection, entry, or candidate-selection semantics.
- Did not change C14 (occurrence identity/duplicate suppression) semantics.
- Did not change `proposal_generation_authorized` (`false`, unaffected) or any
  execution/demo/live authority.
- Did not send a broker order or touch execution code.
- Did not rewrite any historical evidence (none existed to rewrite).
- Did not manually set `C10_STOP_POLICY = PASS` or the strategy's lifecycle stage --
  both are evaluator-derived, from the adapter's own evidence-reading logic and
  `evaluator.evaluate_transition()` respectively.
