# AG V2-3A / V2-3B Adapter Implementation and Parity Status

Date: 2026-09-22
Classification: **IMPLEMENTED_AND_LOCALLY_VERIFIED** (not independently audited -- see "Audit state" below)

## Objective

Implement V2-3A (Large-SMC shadow/funnel adapter) and V2-3B (SSC shadow/replay adapter) as thin `opportunity.adapter.StrategyFunnelAdapter` implementations over each strategy's EXISTING canonical authority, then establish a semantic parity checkpoint between canonical strategy output and the V2 projection. This document records that work and the follow-on audit gate.

## Audit state

This document was produced by the implementation agent that wrote and locally ran the code/tests below. It is **IMPLEMENTED_AND_LOCALLY_VERIFIED**, not **INDEPENDENTLY_AUDITED**. Claude Audit #2 (an independent review of this exact checkpoint) has not happened yet; see "Auditor handoff" at the end of this document.

## Authority discovery

### Large-SMC (`ST_LARGE_SMC_V1`)

- Registry: `strategies/registry.yaml` -- `registered: true`, `active: false`, `research: true`, `demo_authorized: false`, `live_authorized: false`.
- Canonical decision engine: `src/large_smc_research/engine.py` + `src/large_smc_research/decision.py` (`LargeSMCResearchDecision`, states `RESEARCH_QUALIFIED`/`WATCH`/`NO_TRADE`/`EXPIRED`/`INVALIDATED`/`BLOCKED`/`DATA_ERROR`). This adapter does NOT consume `LargeSMCResearchDecision` directly (see rationale below).
- Canonical **watch-lifecycle authority** actually adapted: `src/large_smc_research/watch_lifecycle.py` -- a pre-existing, documented, TOTAL projection of `entry_confirmation.entry_models_v1.EntryModelState` (detection funnel) and `historical_replay.fill_simulator` statuses (post-READY occurrence outcome) onto a lifecycle vocabulary (`WATCHING`/`QUALIFIED`/`ENTRY_AVAILABLE`/`FILLED`/`UNFILLED`/`RESOLVED`/`EXPIRED`/`INVALIDATED`/`BLOCKED`). This is the more granular of the two available canonical authorities (LargeSMCResearchDecision has no equivalent funnel-stage granularity -- WATCH/NO_TRADE/RESEARCH_QUALIFIED only), and it is itself already a canonical, unchanged, previously-shipped projection -- adapting it a second time (to the V2 vocabulary) duplicates no strategy logic.
- Canonical occurrence identity: `historical_replay.orchestrator.SetupLedgerRow.setup_id`.
- Existing scheduled-watch consumer: `src/large_smc_research/live_watch.py` (`evaluate_increment` -> `run_replay` -> `SetupLedger.rows`, i.e. `SetupLedgerRow`s -- the exact objects this adapter consumes).
- Existing tests: `tests/test_large_smc_watch_lifecycle.py`, `tests/test_large_smc_live_watch_hardening.py`, `tests/test_large_smc_live_watch_execution_boundary.py`.
- Qualification status: RESEARCH_ONLY. FORWARD_RESEARCH lifecycle stage (owner-promoted 2026-09-07, per `strategies/STRATEGY_LEDGER.md`). Not demo/live authorized. This adapter does not change any of that.

### SSC (`ST_SESSION_SWEEP_CONTINUATION_V1`)

- Registry: `strategies/registry.yaml` -- `registered: true`, `active: false` (OFFLINE_RESEARCH), `research: true`, `demo_authorized: false`, `live_authorized: false`.
- Canonical evaluator: `src/session_sweep_continuation/replay.py::run_replay` (H1 bias gate, M15 regime classification, S1/S2/S3 setup evaluation, campaign risk allocation/state machine, outcome resolution -- unchanged, not reimplemented here).
- Canonical replay/data authority: `src/session_sweep_continuation/canonical_consumer.py::run_canonical_shadow_cycle`, which routes MARKET_BIAS/MARKET_REGIME through `trading_skills.MarketObservation` (`canonical_observations.py`) into the SAME `run_replay` call, unchanged.
- Canonical decision contract adapted: `strategy_contract.decision.from_session_sweep_continuation_replay(replay_result, observations)` -> `StrategyDecision` (a shared, pre-existing, cross-strategy contract also used by FX/BTC/Large-SMC decision adapters). This adapter consumes `StrategyDecision`, not `ReplayResult` directly, so it inherits the existing field-provenance discipline that module already enforces (verbatim copy, never recomputed).
- Existing tests: `tests/test_session_sweep_continuation_state_machine.py`, `tests/test_session_sweep_continuation_setups.py`, `tests/test_session_sweep_continuation_replay_determinism.py`, `tests/test_session_sweep_continuation_canonical_observations.py`, `tests/test_session_sweep_continuation_campaign.py`, and others in `tests/test_session_sweep_continuation_*.py`.
- Qualification status: RESEARCH_ONLY, OFFLINE_RESEARCH lifecycle stage. Not demo/live authorized, and has historical validation-negative evidence recorded separately in `strategies/STRATEGY_LEDGER.md` -- this adapter neither hides nor reinterprets that; it is out of scope for a funnel-observation adapter (see "Validation independence" in `docs/v2/AG_V2_OPPORTUNITY_STRATEGY_MODEL.md`).

## V2-3A: Large-SMC adapter

File: `src/opportunity/large_smc_adapter.py` (`LargeSMCFunnelAdapter`).

- **Canonical reuse**: calls `large_smc_research.watch_lifecycle.project_setup_row` verbatim; never re-implements EntryModelState/fill-simulator logic.
- **Duplicated strategy logic**: none. The adapter's own mapping tables (`_NONTERMINAL_STAGE_FOR`, `_NONTERMINAL_OUTCOME_FOR`, `_TERMINAL_OUTCOME_FOR`) translate an already-canonical `WatchLifecycleRecord.stage` string to a V2 stage/outcome pair -- a lookup table, not a re-derivation of detection/fill logic.
- **State mapping** (documented, total over every reachable `WatchLifecycleRecord.stage`):

  | Canonical stage (`watch_lifecycle`) | V2 stage | V2 outcome | Terminal? |
  |---|---|---|---|
  | `WATCHING` | `MARKET_ELIGIBLE` | `ACTIVE` | no |
  | `QUALIFIED` | `LOCATION_VALID` | `ACTIVE` | no |
  | `ENTRY_AVAILABLE` | `TRIGGER_ARMED` | `ACTIVE` | no |
  | `FILLED` | `OPPORTUNITY_READY` | `ACTIVE` | no (resolution pending -- P&L out of scope) |
  | `UNFILLED` | `TRIGGER_ARMED` | `WAIT` | no |
  | `INVALIDATED` | `TRIGGER_ARMED` if `ready_time` reached, else `MARKET_ELIGIBLE` | `INVALIDATED` | **yes** |
  | `EXPIRED` | same rule as `INVALIDATED` | `EXPIRED` | **yes** |
  | `BLOCKED` | same rule as `INVALIDATED` | `ERROR` | **yes** (adapter-level choice -- see Known debt) |
  | `RESOLVED` | -- | -- | fails closed (`LargeSMCUnmappedStageError`) -- unreachable today, see Known debt |

  Terminal-stage retained-stage logic is a pure function of the canonical record's own `ready_time` field only (never of adapter-side history), so it cannot corrupt the funnel engine's semantic no-op comparison (`opportunity.engine._is_semantic_no_op`, which compares `raw_strategy_state` byte-for-byte across polls).
- **Evidence mapping**: `context_evidence`/`setup_evidence`/`trigger_evidence` carry the canonical record's `canonical_state_source`, `combination`, `entry_condition`, `maneuver`, `entry_type`, `invalidation_trigger` verbatim.
- **Geometry mapping**: `direction`/`entry` (`entry_reference`)/`invalidation` (`invalidation_price`) copied verbatim from `SetupLedgerRow`; `targets` is always `()` -- `SetupLedgerRow` carries no target authority (that lives on the separate `LargeSMCResearchDecision`, not consumed here), so it is never fabricated.
- **Scheduled-watch compatibility**: the adapter is constructed from an already-produced `SetupLedgerRow` -- the exact object `live_watch.evaluate_increment` already yields via `run_replay`'s `SetupLedger.rows`. Nothing in this module calls `live_watch`, `run_replay`, MT5, or the watch state store; it is proven compatible by construction (same input type), not merely asserted.
- **Repeated-poll idempotence**: proven by `test_repeated_identical_poll_creates_exactly_one_revision` (4 identical polls -> 1 revision, 1 transition).
- **Terminal stickiness**: proven by `test_terminal_occurrence_cannot_be_reactivated`.
- **CandidateStore integration**: proven by `test_progressive_observations_produce_one_candidate_with_valid_revision_history` (WATCHING -> QUALIFIED -> ENTRY_AVAILABLE, one candidate, revisions 1/2/3) and `test_candidate_store_integration_and_restart_continuity`.
- **Restart continuity**: proven by the same restart test -- persist at revision 1, recreate `CandidateStore` from disk, reload, feed the next canonical observation, confirm revision 2 with the same `candidate_id` and exactly one stored candidate.
- **Classification**: **PASS_WITH_NON_BLOCKING_DEBT** (see Known debt).

## V2-3B: SSC adapter

File: `src/opportunity/ssc_adapter.py` (`SSCFunnelAdapter`).

- **Canonical reuse**: consumes `StrategyDecision.setup_properties`, itself already produced verbatim by `strategy_contract.decision.from_session_sweep_continuation_replay` from a `ReplayResult`/`Campaign` this adapter never recomputes.
- **Duplicated strategy logic**: none. `_project_no_campaign`/`_project_campaign` are lookup/branch logic over `campaign_status` + `entry_count`, not H1 bias, M15 regime, S1/S2/S3, or outcome-resolution logic.
- **S1/S2/S3 parity**: `accepted_setups`/`rejected_setups` (which carry each setup's `setup_model`) are copied verbatim into `setup_evidence`/`trigger_evidence`; never reclassified.
- **Outcome-resolution parity**: outcome resolution (stop/target/friction/partial/runner) lives entirely in `session_sweep_continuation.outcome_resolution` / `Campaign.entries`, which this adapter does not touch or expose (see Known debt re realized-entry geometry).
- **State mapping** (documented, total over every `CampaignStatus` member plus the no-campaign-yet case):

  | Canonical state | V2 stage | V2 outcome | Terminal? |
  |---|---|---|---|
  | no campaign, `regime is None` | `MARKET_ELIGIBLE` | `WAIT` | no |
  | no campaign, `regime == "UNKNOWN"` (state machine `NO_TRADE`) | `CONTEXT_VALID` | `INVALIDATED` | **yes** |
  | no campaign, `regime` known | `CONTEXT_VALID` | `WAIT` | no |
  | `ACTIVE`, `entry_count == 0` | `SETUP_DETECTED` | `ACTIVE` | no |
  | `ACTIVE`, `entry_count > 0` | `ENTRY_CONFIRMED` | `ACTIVE` | no |
  | `INVALIDATED` | `SETUP_DETECTED`/`ENTRY_CONFIRMED` (by `entry_count`) | `INVALIDATED` | **yes** |
  | `SESSION_EXPIRED` | `SETUP_DETECTED`/`ENTRY_CONFIRMED` (by `entry_count`) | `EXPIRED` | **yes** |
  | `RISK_EXHAUSTED` | `ENTRY_CONFIRMED` (risk exhaustion implies a prior entry) | `EXPIRED` | **yes** (adapter-level choice -- see Known debt) |
  | `COMPLETE` | `OPPORTUNITY_READY` | `ACTIVE` (deliberately not terminal -- P&L/success is out of funnel scope) | no |
  | anything else | -- | -- | fails closed (`SSCUnmappedCampaignStatusError`) |

- **Geometry parity**: `direction` copied verbatim from `StrategyDecision.direction`; `entry`/`invalidation`/`targets` are always `None`/`None`/`()` -- `StrategyDecision.setup_properties` does not carry `Campaign.entries`' realized entry/stop prices today (see Known debt), so nothing is fabricated in their place.
- **Replay authority**: the adapter never fetches data; it is constructed from an already-produced `StrategyDecision` (itself from an already-run `run_canonical_shadow_cycle`/`run_replay`).
- **`market_data_mode`**: carried on the `MarketEvent`/`StrategyObservation` the caller supplies, untouched by this adapter -- proven by `test_replay_data_mode_is_preserved_not_upgraded_to_real` / `test_ssc_parity_negative_replay_mode_cannot_become_real`.
- **Data lineage**: `MarketEvent.snapshot_fingerprint` flows through the shared `opportunity.engine.evaluate_funnel` into `OpportunityCandidate.data_lineage`, unmodified by this adapter (same mechanism every other adapter uses).
- **CandidateStore integration**: proven by `test_progression_produces_one_candidate_with_valid_revision_history` (no-regime -> regime-known -> setup-detected -> entry-confirmed, one candidate, revisions 1-4) and `test_candidate_store_integration_and_restart_continuity`.
- **Classification**: **PASS_WITH_NON_BLOCKING_DEBT** (see Known debt).

## Parity evidence

`tests/test_opportunity_adapter_parity.py` -- 6 cases:

- Large-SMC: `QUALIFIED` positive case (symbol/direction/combination/entry/invalidation preserved, no fabricated targets, non-terminal outcome matches `WatchLifecycleRecord.is_terminal == False`); `WATCHING` negative case (cannot yield `ENTRY_CONFIRMED`, no fabricated geometry); `INVALIDATED` negative case (cannot yield `ACTIVE`).
- SSC: `ACTIVE` campaign with one entry positive case (strategy identity/symbol/direction/accepted_setups/campaign_status/entry_count preserved, REPLAY mode preserved, no fabricated entry/targets); no-setup negative case (cannot yield `SETUP_DETECTED`); REPLAY-mode negative case (cannot silently become REAL).

Result: **6 passed, 0 failed**. No parity mismatch was hidden behind adapter normalization -- every case where canonical and V2 output differ in shape (e.g. `WatchLifecycleRecord.stage` string vs. V2 `stage`/`outcome` pair) is asserted against the documented mapping table above, not against object equality.

**Unsupported-state behavior**: both adapters fail closed (raise a dedicated `RuntimeError` subclass, never a silent default) for a canonical state with no documented projection -- proven by `test_resolved_stage_is_unreachable_and_fails_closed` (Large-SMC) and `test_unrecognized_campaign_status_fails_closed` (SSC).

## Test evidence

```bash
PYTHONPATH=src python -m pytest tests/test_opportunity_large_smc_adapter.py tests/test_opportunity_ssc_adapter.py tests/test_opportunity_adapter_parity.py -q
# 41 passed

PYTHONPATH=src python -m pytest tests/ -k "opportunity" -q
# 143 passed, 3751 deselected, 0 failed, 0 errors, 0 skipped

PYTHONPATH=src python -m pytest tests/test_large_smc_watch_lifecycle.py tests/test_large_smc_live_watch_hardening.py tests/test_large_smc_live_watch_execution_boundary.py -q
# 65 passed

PYTHONPATH=src python -m pytest tests/test_session_sweep_continuation_state_machine.py tests/test_session_sweep_continuation_setups.py tests/test_session_sweep_continuation_replay_determinism.py tests/test_session_sweep_continuation_canonical_observations.py tests/test_session_sweep_continuation_campaign.py -q
# 50 passed

PYTHONPATH=src python -m pytest tests/test_opportunity_import_boundaries.py -q
# 22 passed
```

## Protected-data firewall

`protected_dataset_access_count = 0`, `holdout_access_count = 0`, `OOS_access_count = 0`. All fixtures in the new test files construct `SetupLedgerRow`/`Campaign`/`ReplayResult` objects by hand; no historical dataset, holdout, or OOS artifact is read.

## Authority unchanged

`strategy_semantics_changed = NO`; `strategy_registry_authority_changed = NO`; `proposal_authority_changed = NO`; `demo_authority_changed = NO`; `live_authority_changed = NO`; `automatic_broker_execution_enabled = NO`; `broker_orders_sent = 0`; `external_alerts_sent = 0`. Confirmed by AST-level `tests/test_opportunity_import_boundaries.py` (both new adapter files pass) and by manual grep for `CanonicalProposal`/`ProposalLedger`/`ProposalEligibility`/`RiskDecision`/`ExecutionDecision`/`TradeCommand`/`execution.*`/`mt5.executor`/`mt5.mt5_gateway`/`order_send` across both new files (zero matches outside docstring prose describing the boundary itself).

## Known debt (non-blocking)

1. **Large-SMC `BLOCKED` mapped to a terminal V2 outcome (`ERROR`)** even though `WatchLifecycleRecord.is_terminal` is `False` for `BLOCKED`. Accepted because this adapter's scope is one already-recorded `SetupLedgerRow` snapshot, which will not itself re-emit further progress once fill-simulation reports `INTRABAR_AMBIGUOUS`/`NO_ENTRY_CONTRACT` for it -- but it is a genuine, documented parity divergence from the canonical non-terminal classification, not a hidden one.
2. **Large-SMC `RESOLVED` stage is unmapped (fails closed)**. It has no reachable canonical producer today (`watch_lifecycle`'s own docstring: "RESOLVED has no canonical counterpart reachable today"); resolving `FILLED` requires broker-stop-distance information (C10) this adapter does not have. Should the strategy later gain a resolution path, this adapter's `_TERMINAL_OUTCOME_FOR`/error path must be revisited explicitly rather than defaulted.
3. **SSC `RISK_EXHAUSTED` mapped to `EXPIRED`**. There is no dedicated V2 outcome for "risk budget exhausted, no further entries possible today" distinct from a structural invalidation or a session timing expiry; `EXPIRED` was chosen as the closer semantic fit and documented rather than silently folded into `INVALIDATED`.
4. **SSC realized-entry geometry (`entry`/`invalidation`/`targets`) is always unavailable.** `StrategyDecision.setup_properties` (as produced by the existing, unchanged `from_session_sweep_continuation_replay`) does not carry `Campaign.entries`' realized `entry_price`/`stop_price` -- only pre-acceptance `accepted_setups`/`rejected_setups` records. Extending that existing conversion function to also copy `Campaign.entries` was judged out of scope for a "thin adapter, reuse existing contracts" mission; direction is preserved, entry/invalidation/targets are honestly reported as unavailable rather than approximated from `accepted_setups`.
5. **Adapter identity/event construction is caller-owned.** Neither adapter builds `MarketEvent`s itself (see each module's "INTENDED EVENT-IDENTITY PATTERN" docstring section); a future scheduled-watch/canonical-consumer driver integrating these adapters into the live pipeline must follow the documented stable-`event_id`-per-occurrence pattern, which is proven correct in tests but not yet wired to `large_smc_research.live_watch` or `session_sweep_continuation.canonical_consumer` at the scheduler level (that wiring is V2-10 scheduler migration, explicitly out of scope for this mission).

None of the above changes strategy semantics, registry authorization, proposal/risk/execution authority, or `market_data_mode`/lineage propagation.

## Roadmap state after this checkpoint

```text
V2-0A   VERIFIED
V2-0B   VERIFIED
V2-1    VERIFIED
V2-1B   VERIFIED
V2-2A   VERIFIED
V2-2B   VERIFIED
V2-3A   IMPLEMENTED_AND_LOCALLY_VERIFIED
V2-3B   IMPLEMENTED_AND_LOCALLY_VERIFIED
PARITY CHECKPOINT   READY_FOR_INDEPENDENT_AUDIT
V2-4    NOT_STARTED
V2-5    NOT_STARTED
```

`AG_V2_OPERATIONAL_PROPOSAL_PLATFORM_READY` remains the current milestone target; this checkpoint does not complete it. Strategy economic validation for either strategy continues independently and is unaffected by this document.

## Auditor handoff

- `head_before` (repo HEAD at mission start): `f036f8812bf69ad4ffe18eb09db71fd5005ad4f0`
- Files changed: `src/opportunity/large_smc_adapter.py` (new), `src/opportunity/ssc_adapter.py` (new), `tests/test_opportunity_large_smc_adapter.py` (new), `tests/test_opportunity_ssc_adapter.py` (new), `tests/test_opportunity_adapter_parity.py` (new), plus this document and the doc updates listed in the commit history below.
- Test commands/results: see "Test evidence" above.
- Parity evidence: see "Parity evidence" above.
- Known debt: see "Known debt" above.
- `SAFE_TO_ADVANCE_TO_V2_4 = NO` pending independent audit of this checkpoint.
