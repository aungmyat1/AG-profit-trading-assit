# Project Status — AG Profit Trading

AG Profit Trading is a **Trading Assistant + Strategy Execution Platform**. See
`README.md` for the folder map. The first section is the current rolling summary;
later sections preserve dated milestone evidence and may contain older test totals.

## PANEL_R5C_RECONCILIATION (2026-09-23, `panel-r5c-reconciliation` worktree branch, not merged)

Additive `execution/reconciliation.py` -- fail-closed reconciliation of a durable
execution decision (`execution.durable_idempotency`, R5B-R1, frozen) against
broker-observation evidence, `OBSERVE -> MATCH -> CLASSIFY -> RECONCILE`, never
`OBSERVE -> NOT_FOUND -> RESUBMIT`. Reuses, rather than reimplements: `execution.
crypto_reconciliation`'s typed fail-closed outcome shape (`MATCHED`/`NOT_FOUND`/
`AMBIGUOUS`/`BROKER_UNAVAILABLE`/`CONFLICT`/`EVIDENCE_INSUFFICIENT`), `execution.
lifecycle`'s injected-lookup-callable idiom (`positions_lookup`/`deals_lookup`,
never imported directly from `mt5.*`), and `execution.executor`'s own `AGT:<command_id>`
broker-comment identity tag (reproduced byte-for-byte, not imported, to keep this
module's import graph free of any write-capable code -- verified exactly
`{__future__, dataclasses, typing, execution.durable_idempotency}` by AST). Matching
requires exact tag equality (stricter than the existing substring check); more than
one distinct matching broker record yields `AMBIGUOUS`, never an arbitrary pick; a
persisted `broker_order_id` disagreeing with new evidence yields `CONFLICT`, never a
silent overwrite; absent evidence (`NOT_FOUND`) never mutates the durable record and
never triggers a resubmission -- there is no submission-capable code path in this
module to trigger one (proven statically and dynamically, including a `MagicMock`
standing in for `order_send` that a full reconciliation cycle never calls). Advances a
durable record only along edges R5B-R1's frozen `ALLOWED_TRANSITIONS` already permits
(`SUBMISSION_PENDING`/`SUBMISSION_UNKNOWN -> BROKER_ACCEPTED`,
`BROKER_ACCEPTED -> RECONCILED`) -- no lifecycle extension was needed for either
uncertain-submission recovery path the mission anticipated might require one. No HTTP
route, no scheduler wiring, no MT5 submission, no auth change, no proposal-dedup fix.
18 new focused tests pass; R5B/R5B-R1 (52 passed), R5A/R5A-R1 auth (58 passed), and
adjacent execution-boundary (23 passed) regressions all pass; the known pre-existing
proposal-dedup failure reproduces separately, unrelated, confirmed to have no
dependency relationship with this package. Explicitly does not claim broker
exactly-once execution or cross-process/cross-machine locking -- see
`docs/status/AG_PANEL_R5C_RECONCILIATION_STATUS.md`'s P14 for the precise guarantee
boundary.

## PANEL_R5B_R1_LIFECYCLE_REMEDIATION (2026-09-23, `panel-r5b-r1-lifecycle-remediation` worktree branch, not merged)

Remediates a `PANEL_R5B_INDEPENDENT_AUDIT_FAIL` finding: `DurableExecutionStore.
transition()` validated only that the requested target state was known, never that
the record's ACTUAL current state legally permitted reaching it -- the auditor
demonstrated `BROKER_ACCEPTED -> PREPARED` was silently accepted and persisted. Adds
`ALLOWED_TRANSITIONS` (an explicit, immutable current-state -> allowed-target-states
graph: `PREPARED->{AUTHORIZED,REJECTED}`,
`AUTHORIZED->{SUBMISSION_PENDING,REJECTED}`,
`SUBMISSION_PENDING->{SUBMISSION_UNKNOWN,BROKER_ACCEPTED,REJECTED}`,
`SUBMISSION_UNKNOWN->{BROKER_ACCEPTED,REJECTED}`, `BROKER_ACCEPTED->{RECONCILED}`,
`REJECTED`/`RECONCILED` terminal) and `InvalidStateTransition`, a specific domain
exception matching the module's existing `FingerprintConflict`/
`IdempotencyStateUnavailable` convention rather than a generic `ValueError`. Same-state
re-affirmation is an explicit, documented idempotent no-op, never looked up in the
graph, so a terminal state can still be safely reaffirmed. Fixes a real TOCTOU gap
(the previous `get()`-then-later-`put()` sequence held no lock across the two calls)
by serializing `transition()`'s whole read-validate-write sequence under a new
per-decision_id lock, mirroring `runtime_state.store.JsonKeyValueStore`'s own
per-path-lock design rather than inventing a different one -- proven by a real,
8-thread-style adversarial concurrency test racing two individually-legal transitions
from the same state. Durability claims corrected per the audit: explicitly documents
atomic file replacement and ordinary-restart persistence as guaranteed,
**power-loss durability as NOT guaranteed** (no `fsync` anywhere in this module or its
`JsonKeyValueStore` backend). No MT5 submission, no HTTP wiring, no auth change, no
strategy behavior change (`git diff` against `src/api/` is empty). 21 new focused
tests plus 13 original R5B tests all pass (two original tests' transition SEQUENCES
were corrected to a lifecycle-legal path per P1's own "do not invent transitions for
test convenience" instruction -- no assertion's intent changed); R5A/R5A-R1 auth
boundaries re-verified intact (58 passed). Known pre-existing proposal-dedup failure
reproduced separately, unrelated, not repaired here. See
`docs/status/AG_PANEL_R5B_R1_LIFECYCLE_REMEDIATION_STATUS.md`.

## PANEL_R5B_DURABLE_IDEMPOTENCY (2026-09-23, `panel-r5b-durable-execution-idempotency` worktree branch, not merged)

Additive `execution/durable_idempotency.py` -- durable, restart-safe execution
identity keyed by `decision_id` (owner_decision's own canonical idempotency key),
reusing `runtime_state.store.JsonKeyValueStore` (the same store
`authorization.store.ExecutionApprovalStore` already uses) and the O_EXCL claim-lock
idiom already established by that store and `execution.journal.claim_command` -- no
new persistence mechanism, no database server. `DurableExecutionRecord` (execution_id,
proposal_id, decision_id, command_id, fingerprint, state, timestamps, nullable
broker_order_id/broker_position_id/failure_reason) and a SHA-256
`compute_execution_fingerprint()` over `TradeCommand`'s own execution-critical fields
(same canonicalization convention as `authorization.integrity.compute_proposal_hash`,
never Python's `hash()`). Same decision_id + same fingerprint returns the existing
record; same decision_id + a different fingerprint fails closed
(`FingerprintConflict`) rather than silently reusing an old authorization for a
different trade -- a durable upgrade over R3's process-local
`OwnerDecisionStore.put_if_absent()`, which has no fingerprint concept at all. Defines
(but only partially activates) the `PREPARED -> AUTHORIZED -> SUBMISSION_PENDING ->
SUBMISSION_UNKNOWN -> BROKER_ACCEPTED -> REJECTED -> RECONCILED` state vocabulary R5C/
R5D/R6 will consume, plus `is_retry_safe()`, the single authoritative fail-closed
answer that `SUBMISSION_PENDING`/`SUBMISSION_UNKNOWN`/`BROKER_ACCEPTED` are never
safe to auto-retry. Wires into no HTTP route, modifies no existing file, submits no
MT5 order (`execution.executor`/`execution.mt5_gateway`/`order_send`/
`user_confirmed=True` do not appear anywhere in its import graph or executable code).
Built on independently-audited `R5A_R1_INDEPENDENT_AUDIT_PASS`
(`c94beb8e38928de25f105a086806f98ab7485c59`), which this change does not modify. 13
new focused tests pass (including 8 real concurrent threads racing one decision_id
and an explicit process-restart-parity test); both R5A/R5A-R1 auth boundaries
re-verified intact (58 passed). Explicitly does NOT claim broker exactly-once
execution -- see `docs/status/AG_PANEL_R5B_DURABLE_IDEMPOTENCY_STATUS.md`'s P15 for
the precise guarantee boundary, and R6 for the still-missing broker reconciliation.
Known pre-existing proposal-dedup failure
(`test_fx_repeated_same_setup_same_date_is_not_deduplicated_in_current_cutover`)
reproduced separately and explicitly flagged as a SEPARATE, still-unresolved defense
from this package's execution-level idempotency -- both remain required before final
broker activation.

## PANEL_R5A_R1_LEGACY_EXECUTION_AUTH (2026-09-23, `panel-r5a-r1-legacy-execution-auth` worktree branch, not merged)

Extends R5A's `require_owner_auth` (reused verbatim, no second key/header/compare
implementation) to also gate the pre-existing, separate
`POST /api/tickets/{approval_id}/authorize-demo` route -- the write surface actually
closer to a real broker call than `owner-decision` (its `execution_handler` resolves to
the real MT5 execution handler in production) and, until this change, had no auth
boundary at all. Fails closed identically to R5A: unset `AG_OWNER_API_KEY` -> `503`,
missing/wrong `X-AG-Owner-Key` -> `401`, execution handler never invoked in either
case. Authentication success is not execution authorization: a valid header with a
non-`"EXECUTE_DEMO"` action is still `400`, and against the real
`strategies/registry.yaml` (`ST_ASIAN_SWEEP_5R_V1` `demo_authorized: false`) still
blocks with `BLOCKED_STRATEGY_NOT_DEMO_AUTHORIZED` -- the existing confirmation
(explicit `action`) and every existing guard (claim, integrity, Demo authority,
DEMO-only environment) are unmodified. No GET route changed. Built on independently-
audited `PANEL_R5A_INDEPENDENT_AUDIT_PASS` (`083399df0644ebe7a38c1a2d9b0174da6dcb18ac`).
9 new focused tests pass; 91/91 of the combined R4+R5A+R5A-R1 API/execution-boundary
suite passes (the one pre-existing, out-of-scope dedup failure reproduces separately,
untouched by this diff). See `docs/status/AG_R5A_R1_LEGACY_EXECUTION_AUTH_STATUS.md`.

## PANEL_R5A_OWNER_AUTH (2026-09-23, `panel-r5a-owner-auth` worktree branch, not merged)

Additive `require_owner_auth` FastAPI dependency (`src/api/app.py`), gating only
`POST /api/canonical-proposals/{proposal_id}/owner-decision` behind an
`AG_OWNER_API_KEY` env var checked against the `X-AG-Owner-Key` request header
(`hmac.compare_digest`). This is the authenticated-owner boundary the PANEL-R4
independent audit named as a prerequisite before any broker-side-effect R5 work
(`docs/status/AG_PANEL_R4_INDEPENDENT_AUDIT_STATUS.md`: "R5 must add an authenticated
owner boundary before broker-side effects"). Fails closed: an unset key disables the
route (`503`), never opens it; missing/empty/wrong header is `401`. Every GET route
stays unauthenticated, as audited. No change to `owner_decision.bridge` (R3, frozen)
or to `OwnerDecisionStore`'s process-local idempotency (that gap is explicitly R5B's).
Built on independently-audited `PANEL_R4_INDEPENDENT_AUDIT_PASS`
(`609e92f07ef2fac6333df3d14ee91648b4e3b8d1`), which this change does not modify. 20
focused tests pass (7 new + the 13 existing PANEL-R4 tests, updated only to override
this new dependency the same way they already override the two stores); 226/227 of the
surrounding regression suite passes (the one failure is the same pre-existing,
out-of-scope `test_fx_repeated_same_setup_same_date_is_not_deduplicated_in_current_cutover`
already documented against the R3/R4 baseline). Known gap flagged, not fixed here: the
pre-existing, separate `POST /api/tickets/{approval_id}/authorize-demo` route (closer to
an actual MT5 call than this one) still has no equivalent auth boundary. See
`docs/status/AG_PANEL_R5A_OWNER_AUTH_STATUS.md`.

## PANEL_R3_OWNER_DECISION_BRIDGE (2026-09-22, `panel-r3-owner-decision-bridge` worktree branch, not merged)

Additive `src/owner_decision/` package: `OwnerDecision`/`ExecutionDecision` types and
`evaluate_owner_decision()`, bridging an explicit owner action on a
`PROPOSAL_READY` + `demo_authorized=True` `CanonicalProposal` into a prepared,
unconfirmed `execution.models.TradeCommand` template (reusing the existing, unmodified
`assistant.canonical_proposal_adapter` / `assistant.commands.build_proposal_from_canonical`).
Fails closed on: REJECT action, non-DEMO environment, non-READY/stale proposal,
`demo_authorized=False`, `broker_mutation_blocked=True`, symbol mismatch, malformed
decision, and duplicate `decision_id` replay (idempotent, never re-authorizes). Never
imports `execution.executor`/`execution.mt5_gateway` and never sets
`user_confirmed=True` — reaching an actual Demo order still requires a separate,
later, explicitly-user-confirmed `assistant.commands.execute_command()` call this
module does not make (see `docs/status/AG_PANEL_R3_OWNER_DECISION_BRIDGE_STATUS.md`
for the full investigation, including the existing separate
`authorization.store`/`api.execution_service` ticket-approval pathway this package
deliberately does not duplicate or touch). Built on frozen `PANEL_R2_AUDIT_PASS`
(`40376ce51afc819951aebc7438511421cf6fe48e`), which this change does not modify. No
new API route, no frontend change (existing frontend-freeze directive below
respected). 16 focused tests pass; 206/207 of the surrounding regression suite passes
(the one failure is the pre-existing, out-of-scope
`test_fx_repeated_same_setup_same_date_is_not_deduplicated_in_current_cutover`, already
documented against the R2 baseline).

## Current rolling classification (2026-09-21)

AG V2 pre-architecture baseline + core contracts (`PARTIAL`): the additive
`src/opportunity/` package now exists — `MarketEvent`, the strategy-neutral
funnel vocabulary (`FunnelStage`/`FunnelOutcome`/`FunnelTransition`),
`OpportunityCandidate`, `CandidateGeometry`, `ProposalEligibilityDecision`,
`StrategyBinding`, `DataAuthority`, `WarmupRequirement`, `FrictionEvidence`, and
the `StrategyFunnelAdapter` protocol boundary. No existing canonical authority
was duplicated (`MarketSnapshot`, `CanonicalProposal`, the proposal formation
gate, the strategy registry, `TradeIntent`/`TradeCommand` are all reused as-is).
`StrategyBinding` resolution confirms registry presence never implies runtime
dispatchability: only `SESSION_TRADE_V1` is wired into
`strategy_manager.manager.evaluate()`; every other registered strategy_id
(including `ST_LARGE_SMC_V1`, `ST_ASIAN_SWEEP_5R_V1`,
`ST_SESSION_SWEEP_CONTINUATION_V1`, `ST_LIQUIDITY_SWEEP_RETEST_V1`) resolves
`dispatchable=False`. 56 focused + 25 adjacent-regression tests pass; a static
import-boundary test proves the opportunity package never imports
execution/order-send code. No strategy semantics, execution authority, or
demo/live authorization changed; no protected data accessed; no broker orders
sent. See `AG_V2_BASELINE_MANIFEST_V1.json` and
`docs/status/AG_V2_PRE_ARCHITECTURE_BASELINE_STATUS.md`. **Binding constraint on
all later V2 phases (owner directive, 2026-09-21): the existing frontend is
frozen** — no redesign, no new Opportunity Finder dashboard or Execution
Console UI, no renamed/removed controls, no breaking API changes; frontend
source stays read-only except narrowly scoped inspection. Later phases must
route V2 internal state through a presentation/API compatibility adapter onto
the existing frontend contracts, and must report `BLOCKED_FRONTEND_COMPATIBILITY`
with the exact conflict rather than modify frontend source. See the status
doc's 2026-09-21 addendum for the full rule set and updated roadmap
(`V2-11 Existing API compatibility integration`, `V2-12 Existing frontend
regression validation` — no dedicated UI phase).

AG V2-2A (pure funnel transition engine) and V2-2B (candidate store + transition
ledger) are `VERIFIED` (2026-09-21, second remediation pass): `src/opportunity/engine.py::evaluate_funnel`
fails closed on strategy_id/strategy_version/engine_version/symbol/market/venue/market_data_mode
identity drift, does not create a new revision/`FunnelTransition` for a semantically
equivalent repeated observation (`stage`/`outcome`/`raw_strategy_state` unchanged), and
does not reactivate a candidate that has reached a terminal outcome
(`REJECT`/`INVALIDATED`/`EXPIRED`/`ERROR`). `src/opportunity/candidate_store.py::CandidateStore`
persists an `OpportunityCandidate` plus its append-only transition history as one atomic
`runtime_state.store.JsonKeyValueStore` write, remains distinct from `CanonicalProposal`,
fails closed on revision gaps/regressions and authority/occurrence drift, and correctly
receives only one transition across four repeated polls of an unchanged setup (proven by
a dedicated engine+store end-to-end test). 98 opportunity-scoped tests pass
(`PYTHONPATH=src python -m pytest tests/ -k "opportunity" -q`). See
`docs/status/AG_V2_2A_2B_IMPLEMENTATION_STATUS.md` for full evidence, including the two
invariants (no-op detection, terminal stickiness) that a first remediation pass had
silently dropped and that an independent re-audit caught before any strategy adapter was
allowed to depend on this layer. No strategy semantics, execution authority, or
demo/live authorization changed; no broker orders sent.

AG V2-3A (Large-SMC shadow/funnel adapter) and V2-3B (SSC shadow/replay adapter) are
`RE_AUDIT_PASS / PARITY_CHECKPOINT_PASS` (2026-09-22): `src/opportunity/large_smc_adapter.py::LargeSMCFunnelAdapter`
is a thin adapter over the pre-existing `large_smc_research.watch_lifecycle.project_setup_row`
projection (no detection/fill logic reimplemented); `src/opportunity/ssc_adapter.py::SSCFunnelAdapter`
is a thin adapter over `strategy_contract.decision.StrategyDecision` as built from the
unchanged `session_sweep_continuation.replay.run_replay` (no H1 bias/M15 regime/S1-S2-S3/
outcome-resolution logic reimplemented). An independent audit (`AG_V2_INDEPENDENT_AUDIT_02`)
against the original implementation (HEAD `6d416bc`) found one **blocking defect**: on a
terminal transition (INVALIDATED/EXPIRED/BLOCKED) the Large-SMC adapter's own terminal-stage
guess (based only on `SetupLedgerRow.ready_time`, which is stamped solely at full `READY`)
could regress a candidate's recorded funnel stage backward -- e.g. from `LOCATION_VALID`
back to `MARKET_ELIGIBLE` -- violating `docs/v2/AG_V2_SAFETY_AND_AUTHORITY_INVARIANTS.md`
invariant #9 ("terminal invalidation/expiry preserves the highest stage actually reached").
This has been fixed generically in `src/opportunity/engine.py::evaluate_funnel` (a shared,
adapter-agnostic clamp: a terminal transition's stage can never regress below the previous
candidate's stage), protecting every current and future strategy adapter, not only
Large-SMC's. SSC's own terminal-stage logic was confirmed (by the audit, and re-confirmed
during remediation) to be immune to this defect class, since it derives stage from the
monotonic `Campaign.entries` count rather than a late-set marker. Two adapter-specific
regression tests plus two generic engine-level regression tests (one parametrized over all
four `TERMINAL_OUTCOMES`) were added; the full opportunity-scoped suite is now 150 passed
(up from 143), and the narrow existing Large-SMC (65 passed) and SSC (50 passed) regression
suites remain unaffected. No strategy semantics, registry authorization, demo/live
authorization, or execution authority changed; no protected/OOS/holdout data accessed; no
broker orders sent. See `docs/status/AG_V2_3A_3B_ADAPTER_PARITY_STATUS.md` for the full
audit findings and remediation record, including remaining genuinely non-blocking debt
(Large-SMC `BLOCKED` -> terminal `ERROR`, SSC `RISK_EXHAUSTED` -> `EXPIRED`, and an SSC
S3-specific parity-fixture coverage gap). **A separate, independent re-audit
(`AG_V2_3A_REMEDIATION_REAUDIT`, 2026-09-22) then ran against this exact remediation at HEAD
`31d156f`**, independently reconstructing the defect reproduction from scratch and
re-running the same evidence commands; it found no remaining or new defect (106 focused / 150
opportunity-scoped / 65 Large-SMC / 50 SSC tests passed, 0 skipped, 0 protected-data access).
A separately circulated document claiming this same re-audit with different, unverifiable
test counts was explicitly rejected rather than applied -- see
`docs/status/AG_V2_3A_3B_ADAPTER_PARITY_STATUS.md` "Audit state" for that record. Parity
checkpoint classification: `PASS`; `SAFE_TO_ADVANCE_TO_V2_4 = YES` strictly for the bounded,
non-authorizing V2-4 ProposalEligibility bridge (no proposal, Demo, Live, broker, or
execution authority granted).

**Owner-approved multi-agent protocol and platform roadmap V3 (2026-09-22,
`DOCUMENTATION_UPDATED_PENDING_OWNER_REVIEW`):** the owner approved a multi-agent
operating model (Owner / ChatGPT Architect+Independent Auditor / Claude Builder), a
three-class engineering/audit/owner gate model, and a WP-0 through WP-11 work-package
sequence layered over the V2-x phases above — see
`docs/governance/AG_MULTI_AGENT_EXECUTION_PROTOCOL_V1.md`. The owner also decided that
`ST_ASIAN_SWEEP_5R_V1@1.1.1` becomes the planned active FX V2 integration target
(inserting a new V2-3C adapter phase, WP-1), replacing `ST_SESSION_SWEEP_CONTINUATION_V1`
in that routing role; SSC's source, V2 adapter, tests, replay, and validation evidence are
preserved unchanged, with only its active-routing role planned for later removal
(`SSC_ACTIVE_ROUTING_REMOVAL`, WP-2) once V2-3C's own gate passes. This is a platform-
integration-target decision, not an economic promotion: `ST_ASIAN_SWEEP_5R_V1` remains
`demo_authorized: false` / `live_authorized: false` in `strategies/registry.yaml`, and its
existing negative R5 evidence (13/13 losing trades, R6
`NOT_EVALUABLE_MISSING_SIGNED_THRESHOLDS`, research `PAUSED_BY_OWNER`, see below) is
unchanged by this decision. No strategy semantics, registry authorization, proposal/Demo/
Live authority, or execution authority changed; no code was implemented under this
documentation-only mission.

**WP-0 baseline frozen** (commit `c2cf33f9f353d338dbde9aece22fc2819fdf3d71`). **WP-1
(V2-3C Asian Sweep shadow adapter) builder-side implementation complete, 2026-09-22:**
`src/opportunity/asian_sweep_adapter.py` (`AsianSweepFunnelAdapter`) is a thin adapter
over the EXISTING canonical `post_asian_pilot.decision.PostAsianDecision` (built from
`strategy_engine.engine.evaluate()`'s unchanged `TradeSignal` output) -- no
reference-box, TREND/RANGE classification, or sweep-detection logic duplicated; both
`ASIAN_LONDON`/`LONDON_NEWYORK` session pairs, occurrence identity, idempotence, and
terminal stickiness (reusing the generic V2-3A-remediated engine clamp) are covered.
`ST_ASIAN_SWEEP_5R_V1` registry authority is unchanged (`research: true`,
`demo_authorized: false`, `live_authorized: false`); SSC remains unchanged active
routing (WP-2 not started); V2-4 ProposalEligibility is not implemented. Status:
**`BUILDER_IMPLEMENTATION_COMPLETE` / `INDEPENDENT_AUDIT_PENDING`** -- not
`WP1_GATE_PASS`; see `docs/v2/AG_V2_IMPLEMENTATION_ROADMAP.md` V2-3C for full evidence.
Next gate: independent architecture audit of this WP-1 implementation
(`AG_V2_3C_ASIAN_SWEEP_ADAPTER`), then WP-2 (SSC active routing removal, not started).

**WP-1 gate PASS (owner-accepted, frozen at `98457f62c75705fee870c697fea76bda05abddf0`);
WP-2 (SSC active-routing removal) `OWNER_ACCEPTED_FROZEN`, independent audit PASS, frozen at
`bcee106835623572fbb62b1fe12388a282efca6c`** -- WP-2 inventory reconfirmed
`ST_ASIAN_SWEEP_5R_V1` as the sole active FX operational route
(`scripts/install_fx_scheduler.ps1` -> `run_fx_cycle_once.py` ->
`run_post_asian_pilot.py`), zero active SSC operational routes, and no SSC fallback;
SSC code/tests/replay/evidence preserved. One bounded WP-2 commit fixed a stale-date
test in `tests/test_fx_scheduler_once.py` (unrelated to routing). **WP-3
(ProposalEligibility) implementation complete, 2026-09-22:**
`src/opportunity/proposal_eligibility.py::evaluate_proposal_eligibility` supplies the
missing evaluator for the existing `opportunity.contracts.ProposalEligibilityDecision`
contract (unmodified) -- a pure function taking an `OpportunityCandidate` and an
already-resolved `StrategyBinding` and returning `ELIGIBLE`/`BLOCKED`/`INCOMPLETE` with
machine-readable reason codes. Reuses `opportunity.engine.TERMINAL_OUTCOMES` and
`opportunity.contracts.synthetic_or_replay_block_reasons` as-is; deliberately does not
consult `StrategyBinding.dispatchable`/`.proposal_authority` (those describe
`strategy_manager.manager.evaluate()` dispatch, true only for `SESSION_TRADE_V1`, a
different call path than Asian Sweep's WP-2-established operational route). Eligibility
requires a non-terminal `ACTIVE` outcome, funnel stage at least `ENTRY_CONFIRMED`, and
fully populated trade-plan geometry (direction/entry/invalidation) -- not stage alone,
since SSC's own adapter reaches `ENTRY_CONFIRMED` mid-campaign without populating
geometry (see `docs/status/AG_V2_3A_3B_ADAPTER_PARITY_STATUS.md`). Does not construct a
`CanonicalProposal`, does not write `ProposalLedger`, does not import
`execution`/`mt5`/`proposal_envelope`. 30 new focused tests plus the full existing
opportunity-scoped regression suite (219 tests across contracts/events/registry_binding/
import_boundaries/candidate_store/engine/adapter_parity/asian_sweep/ssc/large_smc
adapters) pass. `ProposalEligibilityDecision.status == ELIGIBLE` grants no proposal,
Demo, Live, or execution authority -- WP-4 (`CanonicalProposal` bridge) is not
implemented. No strategy semantics, registry authorization, or execution authority
changed; no protected/OOS/holdout data accessed; no broker orders sent. Next gate:
independent audit of this WP-3 implementation.

**WP-4 (`CanonicalProposal` bridge) builder-side implementation complete, 2026-09-22
(local, unpushed; `BUILDER_IMPLEMENTATION_COMPLETE` / `INDEPENDENT_AUDIT_PENDING`),
branch `wp/v2-4-canonical-proposal-bridge` rooted at the frozen WP-3 checkpoint
`570e755654f9aaf3f5cbbb1a09cd47690b83c9ae`:** `src/proposal_envelope/adapters/
opportunity_adapter.py::to_canonical_proposal` maps `(OpportunityCandidate,
ProposalEligibilityDecision, strategy_authority)` onto the existing
`proposal_envelope.models.CanonicalProposal` shape -- ELIGIBLE maps only ever to
`PROPOSAL_READY` with fully-populated geometry (direction/entry/stop/targets/expected_R
copied verbatim from `candidate.geometry`); BLOCKED/INCOMPLETE never produce a
`PROPOSAL_READY` envelope, and a partial `candidate.geometry` on those paths is
surfaced only inside `setup_evidence` for audit, never as the top-level trade plan.
Reuses WP-3's `evaluate_proposal_eligibility` output as a caller-supplied input rather
than re-deriving it, and reuses `proposal_envelope.strategy_authority.StrategyAuthority`
for the optional governance fields (defaulting to the safest/most restrictive state --
`demo_authorized=False`, `live_authorized=False`, `proposal_only=True`,
`broker_mutation_blocked=True` -- when omitted). `execution_authority` is always
`AUTHORITY_NONE` regardless of what `strategy_authority` reports, matching every other
adapter in the package. `proposal_envelope_id` is composed from
`candidate.strategy_id`/`candidate.occurrence_id` (namespaced `OPP:`, distinct from
every existing family prefix), so one logical occurrence keeps one identity across its
own BLOCKED/INCOMPLETE/READY lifecycle. No risk sizing, no `TradeCommand`, no MT5/
execution import, no `ProposalLedger` write -- statically and behaviorally proven (see
`tests/test_opportunity_proposal_bridge.py` and the existing whole-package
`test_proposal_envelope_execution_boundary.py`, which already covers every module under
`proposal_envelope/`, including this new adapter). 17 new focused tests pass; the
existing WP-3/opportunity-domain regression suite (135 tests) and the
proposal_envelope-domain regression suite pass unchanged (4 pre-existing,
unrelated failures reproduce identically on the unmodified frozen checkpoint --
`state/proposal_ledger/proposal_ledger.json` has grown to 99 committed records since
those tests' original 69-record baseline was authored; not touched or caused by this
work). No strategy semantics, registry authorization, execution authority, or
Demo/Live authorization changed; no protected/OOS/holdout data accessed; zero broker
orders sent; not wired into any runtime path or the existing `ProposalLedger`. Next
gate: independent audit of this WP-4 implementation, then WP-5 (wiring into the
operational FX cycle).

Validation-system assurance is `PARTIAL`: the repo now contains a fail-closed validation contract for friction and a machine-testable assurance manifest (`AG_VALIDATION_SYSTEM_ASSURANCE_V1.md` and `artifacts/validation/AG_VALIDATION_SYSTEM_ASSURANCE_V1_manifest.json`) proving contiguous gate ordering, protected-data firewall enforcement, and unavailable-cost handling. The earliest missing concrete gate, VA1 temporal/lookahead integrity, has now been frozen as `VD_TEMPORAL_LOOKAHEAD_V1` and covered by a deterministic perturbation test proving that future continuation beyond decision time T does not change the visible closed-bar set or strategy inputs at T. The project has also signed the R6 development edge gate for `ST_SESSION_SWEEP_CONTINUATION_V1` v1.0.1 via `config/governance/economic_gate_contract.yaml`, making the validation model operational for the research-only development edge mission without granting any live or demo execution authority. VA2 warm-up stability is now proven: `ONE_YEAR_REPLAY_STACK_V1` is frozen (`manifest_sha256 = 59896fe6227a577ec588c701765c4a78277415ca70f7a6987f485ff1708de0c7`) with `DATA_COVERAGE_COMPLETE`, `CROSS_LEG_TIMEBASE_CONSISTENT` (`UTC_SINGLE_TIMEBASE`, hardened gate), `WARMUP_STABLE` (4371 closed H1 bars before the first decision, convergence proven both architecturally and empirically), and `PROTECTED_DATA_ACCESS_COUNT = 0`. See `docs/status/SSC_V1_0_1_ONE_YEAR_REPLAY_DATA_AUTHORITY_STATUS.md`. No SSC replay has been executed; R5/R6 remain a separate, not-yet-started mission. The broader validation stack remains `NOT_READY` for evidence-producing development because VA3 synthetic known-answer coverage and downstream holdout gates remain partial or unproven. Strategy semantics remain unchanged and no demo/live authority is granted.

Strategy Capacity VD Cycle 2 remains `VD_STRATEGY_CAPACITY_SIMULATOR_NOT_READY`.
Capacity mode now binds internally to SSC's canonical shadow cycle, rejects caller
decision injection, and records contract/event/dataset provenance. Virtual orders
advance only on later M1 events, with account/ledger transitions and explicit
end-of-data outcomes. A JSON checkpoint can rebuild and verify state by replaying
the admitted immutable prefix. These paths are unit-tested with engineering
fixtures; BE/partial virtual semantics and campaign contracts remain outside this
cycle's proof. The next bounded engineering gate is the frozen
`VD_CAPACITY_RISK_V1` contract in `src/svos/capacity_risk_contract.py`, which
records the repo-authority capacity limits (`max_open_positions=1`,
`ENGINEERING_NORMALIZED_1`) and explicitly defers broker leverage/margin and
friction authority as `DEFERRED_EXECUTION_PARITY`. See
`docs/status/VD_STRATEGY_CAPACITY_CYCLE2_STATUS.md`.

Strategy Capacity VD Cycle 1 is `VD_STRATEGY_CAPACITY_SIMULATOR_NOT_READY`.
The VD runner now has a unit-tested, fail-closed context-decision boundary for
capacity mode: it refuses fixture decisions and supplies a TD-8E context at each
emitted event. This does not yet establish a canonical SSC campaign. The supplied
source is not bound to the canonical SSC evaluator, pending orders are not carried
through later events, checkpoints do not restore state, and capacity friction,
risk, metrics, thresholds, and manifest are not frozen. No development or protected
capacity dataset was accessed. See
`docs/status/VD_STRATEGY_CAPACITY_CYCLE1_STATUS.md`.

Scheduler + Large SMC Watch Hardening is `FX_SCHEDULER_READY` /
`LARGE_SMC_WATCH_READY_FOR_RESEARCH`. Two pre-existing FX Task Scheduler entries were
corrected in place (no duplicates) to deterministic weekday, window-bounded `--once`
runs anchored at each M15 close + 20s, with four ordered fail-closed gates including
protection of the frozen WP3A.1 friction windows. The reported duplicate-proposal
problem was reproduced (69 ledger records for only 13 logical setups) and traced to a
proposal/observation identity-layer collapse; an additive read-only resolver was
delivered rather than modifying frozen canonical behavior. Two confirmed defects in
`run_large_smc_live_watch.py` (true-UTC input to broker-aligned D1/H4 bucketing; full
150-day re-replay per invocation) were fixed research-only with native-broker D1/H4
parity tests. Demo and live authority remain `NONE`. See
`docs/status/AG_SCHEDULER_AND_LARGE_SMC_WATCH_HARDENING_STATUS.md`.

Versioned Proposal Occurrence Identity is `OCCURRENCE_IDENTITY_CANDIDATE_READY`
(**unwired, promotion not recommended yet**). The scheduler-mission duplicate-proposal
defect was addressed by a versioned candidate
(`AG_PROPOSAL_OCCURRENCE_IDENTITY_V1`, `src/proposal_envelope/occurrence_identity_v1.py`,
`WIRED_INTO_RUNTIME = False`): occurrence identity is composed from the authoritative
`confirmation_evidence.setup_id` only, so repeated M15 observations of one unchanged
structural setup resolve to one logical occurrence while every observation's provenance
is preserved. A second confirmed defect was found and characterized: the frozen
`ProposalLedger.list_active_proposals()` returns all 69 persisted records as
`PROPOSAL_READY`, while **63 had already passed their strategy-owned expiry** — expired
proposals were still operationally presented as current. Read-time expiry presentation
and four distinct reporting metrics (OBSERVATION_COUNT / DISTINCT_SETUP_COUNT /
CURRENT_ACTIVE_PROPOSAL_COUNT / EXPIRED_PROPOSAL_COUNT) were delivered. Families
emitting no authoritative setup identity (e.g. `ssc_adapter`, 6 records) **fail closed**
rather than receiving a derived persistence key. No frozen behavior, strategy economics,
friction evidence, campaign state, or historical ledger record was modified; demo and
live authority remain `NONE`. See
`docs/status/AG_VERSIONED_PROPOSAL_OCCURRENCE_IDENTITY_STATUS.md`.

FX Occurrence Identity Promotion Readiness is
`FX_IDENTITY_PROMOTION_READY_FOR_SCOPED_WIRING`. `confirmation_evidence.setup_id` was
proven **structural** end to end through the real producers
(`strategy_engine.engine.evaluate()` → `intent_builder` → `TradeProposal` →
`build_entry_proposal` → FX adapter): its producer formula is
`{strategy_id}:{pair_id}:{symbol}:{session_date}` with **no time component**, and
`evaluation_time` enters only the observation layer. Occurrence parity was proven for all
nine required cases (repeated M15 polls, market-data-timestamp-only change, restart,
EURUSD, GBPUSD, ASIAN_LONDON, LONDON_NEWYORK, new structural setup, next trading date).
A forward-only cutover was designed with an explicit version marker
(`AG_PROPOSAL_OCCURRENCE_LEDGER_V1`) and an auditable cutover marker file; the 69 legacy
records remain byte-identical immutable raw observations. The expiry-corrected current
proposal count was promoted into the runtime status probe (which previously reported all
69 persisted records as active while 63 were expired), and six distinct metrics are
exposed with one consistent identity gate. SSC remains `FAIL_CLOSED` /
`IDENTITY_UNAVAILABLE` — no SSC setup ID was invented. The candidate is **still not wired
into FX proposal production** (`WIRED_INTO_RUNTIME = False`); demo and live authority
remain `NONE`. See
`docs/status/AG_FX_OCCURRENCE_IDENTITY_PROMOTION_READINESS_STATUS.md`.

SVOS Virtual Demo Cycle 6A-R is `VD_REALITY_REMEDIATION_READY`: one bounded read-only
EURUSD MT5 check refreshed Vantage Demo/USD identity and a stale point-in-time spread
snapshot. Volume, margin, commission, slippage, latency, and representative historical
executable spread remain unresolved; `VD_BASE` remains not ready. See
`docs/status/SVOS_VIRTUAL_DEMO_ENGINE_V1_CYCLE6A_R_STATUS.md`.

SVOS Virtual Demo Cycle 6A is `VD_REALITY_AUTHORITY_READY`: repository broker/account
evidence is inventoried, but economic inputs remain explicitly incomplete. EURUSD is
limited to `OHLC_M1`; commission, slippage, latency, volume, margin, and historical
executable spread authority remain unavailable. See
`docs/status/SVOS_VIRTUAL_DEMO_ENGINE_V1_CYCLE6A_STATUS.md`.

SVOS Virtual Demo Cycle 5 is `VD_E2E_ENGINE_READY`: deterministic orchestration now
composes the temporal feed, canonical decision boundary, bridge, exchange, account,
and ledger with auditable no-setup handling and checkpoint identity. Economic
qualification remains false and all broker economics stay unmodeled. See
`docs/status/SVOS_VIRTUAL_DEMO_ENGINE_V1_CYCLE5_STATUS.md`.

SVOS Virtual Demo Cycle 4B is `VD_LEDGER_PARITY_READY`: append-only, hash-chained
exchange/account evidence now reconstructs deterministic normalized account state,
including unresolved ambiguity handling. Ledger, strategy, and execution authority are
separate; economic qualification remains false. See
`docs/status/SVOS_VIRTUAL_DEMO_ENGINE_V1_CYCLE4B_STATUS.md`.

SVOS Virtual Demo Cycle 4A is `VD_ACCOUNT_CORE_READY`: deterministic normalized
VirtualPosition and VirtualAccount state now consumes exchange fill evidence with
idempotent snapshots and explicit ambiguity handling. Economic qualification remains
false; broker quantity, money, margin, conversion, and friction are unmodeled. See
`docs/status/SVOS_VIRTUAL_DEMO_ENGINE_V1_CYCLE4A_STATUS.md`.

SVOS Virtual Demo Cycle 3C is `VD_SSC_BRIDGE_READY`: the canonical SSC ReplayResult
now has a deterministic, non-mutating bridge to Cycle 3B virtual order intent and
causal fixture fills. Research reference entries remain distinct from executable
fills. Engineering and narrow integration readiness are true; economic qualification
remains false. See `docs/status/SVOS_VIRTUAL_DEMO_ENGINE_V1_CYCLE3C_STATUS.md`.

SVOS Virtual Demo Cycle 3B is `VD_EXCHANGE_CORE_READY` for isolated deterministic
OHLC_M1 engineering fixtures. The core preserves SSC research references separately,
enforces post-cutoff first-eligible fills, records explicit intrabar ambiguity, and has
no account/economic/broker authority. Canonical SSC integration remains intentionally
blocked. See `docs/status/SVOS_VIRTUAL_DEMO_ENGINE_V1_CYCLE3B_STATUS.md`.

SVOS Virtual Demo temporal foundation is frozen at `04a8d122682e0888d3260b103303576c887d83ee`
after a 39-test focused TD-8E/MI regression. Cycle 3A execution adjudication is
`VD_EXCHANGE_INPUTS_READY` for isolated engineering fixtures only: EURUSD data quality
is `OHLC_M1`, and SSC's legacy signal-close fill conflicts with causal next-event
VirtualExchange timing. Integrated exchange and economic qualification remain blocked
on the explicit inputs in `docs/status/SVOS_VIRTUAL_DEMO_ENGINE_V1_CYCLE3A_STATUS.md`.

SVOS Virtual Demo Engine V1 Cycle 2 is `VD_TIME_FEED_READY` (`UNIT_TESTED`): an isolated
VirtualClock and TD-8E-bound historical market feed provide deterministic M1/M15/H1
event visibility, ordering, future-isolation, speed parity, and end-of-data behavior.
This is temporal infrastructure only; execution, account, economics, and a sealed
Virtual Demo campaign remain unimplemented/unstarted. See
`docs/status/SVOS_VIRTUAL_DEMO_ENGINE_V1_CYCLE2_STATUS.md`.

Market Intelligence V1 is frozen as `MI_V1_FROZEN`. The release manifest and accumulated
117-test regression preserve the immutable MI contract, TD-8E provenance lineage, and
controlled SSC compatibility boundary. EMA and cross-strategy regime remain unavailable;
Virtual Demo and SSC production migration remain future work. See
`AG_MARKET_INTELLIGENCE_V1_FREEZE_STATUS.md` and `MI_V1_RELEASE_MANIFEST.json`.

MI V1 Cycle 4 controlled SSC integration is `MI_V1_INTEGRATION_READY`: the narrow
MI-to-SSC adapter preserves TD-8E event/provenance lineage and produces equal canonical
`run_replay` decisions on the representative complete event. Incomplete identity and
missing-evidence cases fail closed; no SSC cutover occurred. See
`AG_MARKET_INTELLIGENCE_V1_CYCLE4_STATUS.md`.

MI V1 Cycle 3 parity and temporal proof is `MI_V1_PARITY_READY` from `cbb6a43`: same
event determinism, future-only mutation invariance, incomplete evidence handling, zero
live fallback, identity and H1/M15/M1 lineage preservation, and unresolved EMA/regime
states passed against the existing core. No live/replay parity claim is made. See
`AG_MARKET_INTELLIGENCE_V1_CYCLE3_STATUS.md`.

MI V1 Cycle 2 core is `MI_V1_CORE_READY` from `93586ec`: an immutable, deterministic
snapshot/composer consumes admitted TD-8E evidence, preserves event and dataset
provenance, and fails closed on missing components. EMA and a cross-strategy regime
contract remain explicitly unavailable. No consumer migration or execution authority
changed. See `AG_MARKET_INTELLIGENCE_V1_CYCLE2_STATUS.md`.

TD-8E shared historical replay evaluation is `UNIT_TESTED` and final integration is
`MI_FOUNDATION_READY`. One context at a caller-controlled historical T fed the actual
Asian strategy engine and SSC canonical consumer with the same event identity. R4
reference completeness, future-only mutation isolation, bound-store replacement,
M1 lineage, and zero observed live candle calls passed. One consumed DEV_002 event
was used only as non-counting infrastructure evidence; no validation population or
trading authority changed. Market Intelligence has not begun. See
`docs/status/TD8E_FINAL_INTEGRATION_RESUME_STATUS.md`.

The SSC one-year cross-leg timezone blocker is **resolved**
(`CROSS_LEG_TIMEZONE_BLOCKER_RESOLVED`). Rather than splicing timezone-heterogeneous
files, authoritative H1 and M15 are now derived deterministically from the already-frozen
native MT5 M1 authority (`SSC_V1_0_1_HIST_1Y_M1_001`) using the repository's own existing
`historical_replay.resampler` convention, which was adjudicated `AUTHORIZED` (the spec
explicitly prefers M1 as base feed when sufficiently long; M1 is now the longest-reaching
leg). Derived legs pass exact reference parity **1.000000** against the independently
exactly-aligned H1/M15 sources, with zero unreproduced reference bars, and the companion
cross-leg gate returns `CROSS_LEG_TIMEZONE_CONSISTENT_FULL_WINDOW` at **zero shift** over
**365.999 days** (was 322.124). The one deliberate departure from the resampler default —
the `NATIVE_FAITHFUL_INCLUSIVE` bucket policy — was frozen and hashed before generation and
justified by native-candle parity, because the strict complete-bucket default silently drops
418 real H1 / 452 real M15 bars of the window. Pre-existing DEV_002 / GEN_002 / HYP_002
timestamp anomalies are recorded as provenance findings and were **not** rewritten; no SSC
replay ran, no strategy/parameter changed, no optimization ran, protected data untouched.
See `docs/status/SSC_ONE_YEAR_CROSS_LEG_AUTHORITY_REMEDIATION_STATUS.md`.

TD-8D canonical replay `MarketSnapshot` bridging is complete. The existing
`strategy_contract.MarketSnapshot` can now be constructed
from one TD-8 dataset and caller-controlled T, with TD-8C session facts attached, then
delivered as the same immutable object to multiple independent consumers. The bridge
is read-only and imports no strategy decision, proposal, risk, execution, frontend,
or Market Intelligence code. `MI_FOUNDATION_READY` is established as a readiness
result; Market Intelligence implementation has not begun. See
`docs/status/TD8D_CANONICAL_MARKETSNAPSHOT_REPLAY_BRIDGE_STATUS.md`.

TD-8C shared session-reference replay parity is implemented and under owner review
(uncommitted). `session_snapshot` now uses the caller's historical clock and closed
M15 range from `HistoricalCandleStore` inside replay; live calls retain the existing
MT5 range path. Missing or incomplete replay sessions fail closed, and the frozen
Asian Sweep and SSC strategy windows remain unchanged. This is shared market-context
infrastructure, with no trading authority change. See
`docs/status/TD8C_SESSION_REFERENCE_REPLAY_PARITY_STATUS.md`.

TD-8B structure-only derived caching is owner-approved and frozen. The
shared `market_structure.analyze_structure` authority now uses TD-6's bounded cache
with live/replay source identity, replay dataset fingerprint, actual visible candle
content, evaluation boundary, semantic definition, version, and behavior parameters
in its key. Liquidity, FVG, order-block, and session-reference authorities remain
uncached; session replay parity remains deferred. Cache failure recomputes the
market fact. No strategy or execution authority changes. See
`docs/status/TD8B_DERIVED_CACHE_INTEGRATION_REVIEW_STATUS.md`.

TD-8 TopDownContext replay temporal parity is `UNIT_TESTED`: caller-supplied UTC
`as_of_time` drives the six-timeframe historical composition through the existing
replay store and shared fact builders. Closed-bar filtering, content-derived dataset
identity, live MT5 fallback prevention, and live raw-cache isolation are covered by
focused replay tests. Session-based reference facts remain unavailable in replay and
fail closed (`TD8_SESSION_REFERENCE_REPLAY_PARITY`); derived fact caching remains
unwired. This grants no strategy, proposal, demo, live, or execution authority. See
`docs/status/TD8_REPLAY_TEMPORAL_PARITY_STATUS.md` for the dated evidence.

SVOS (Strategy Validation Operating System) historical→optimization→virtual-forward flow
is `UNIT_TESTED`: a new `src/svos/` package implements the canonical historical runner
contract, preregistered bounded optimization with a protected-data firewall, candidate
freeze/fingerprint, a component-state FrictionProfile, an MT5-isolated VirtualBroker
(statically proven zero reach to `order_send`/`order_check`), a chronological/restart-safe
ForwardValidationCampaign, a DEMO-ELIGIBLE prerequisite projection (never executes), and
an SSC same-strategy-authority proof. This is infrastructure only: no real forward
campaign started, no strategy or execution gateway changed, and no Demo/Live authority
granted. The mission lifecycle vocabulary is reconciled onto the canonical
`AG_VALIDATION_G0_G10_V1` gates — no new authoritative lifecycle label was introduced,
and `LifecycleStage` (via `lifecycle_registry`) remains the sole lifecycle authority. See
`docs/svos/SVOS_AUTHORITY_MAP.md`, `docs/svos/SVOS_LIFECYCLE_AND_GATES.md`, and
`docs/status/AG_SVOS_HISTORICAL_TO_VIRTUAL_FORWARD_V1_STATUS.md`.

### SSC v1.0.1 SVOS G2 population frozen (2026-09-19)

`ST_SESSION_SWEEP_CONTINUATION_V1` v1.0.1's ONE-SHOT G2 historical population replay
over the frozen development dataset `SSC_V1_0_1_G2_DEV_002` completed and froze
`SSC_V1_0_1_G2_DEV_002_POPULATION_V1`: 42 dates / 84 decision cycles, **22
occurrences**, deterministic (identical population hash across two independent runs).
Descriptive economics (DEVELOPMENT, diagnostic only): gross expectancy `-0.25R`, net
expectancy `-0.47R`, gross PF `0.56`, win rate 36.4%. The G3 economic gate remains
`NOT_EVALUATED_UNSIGNED_CONTRACT` (contract PROPOSED/unsigned); no optimization run,
no protected data (confirmation/holdout/OOS/H2) accessed, no strategy/parameter/data
change, and no broker/demo/live order or authority change. See
`docs/status/AG_SSC_V1_0_1_SVOS_G2_POPULATION_STATUS.md`.

### SSC v1.0.1 SVOS G2 failure decomposition (2026-09-19)

Read-only, evidence-first failure decomposition of the frozen `SSC_V1_0_1_G2_DEV_002_
POPULATION_V1` (22 occurrences). Gross edge is negative (`PRIMARY_ALPHA_DEFICIT`:
gross expectancy `-0.245R`, gross PF `0.56`); friction is a `SECONDARY_AMPLIFIER`
(4.92R total, 47.7% of net loss). Key excursion facts: 50% stop-first (SL trades moved
only `0.32R` favorably before stopping) and the partial target (reference boundary,
mean `1.93R`) sits beyond the typical favorable excursion (mean MFE `1.31R`) —
partial activation only 22.7%. **No hypothesis was justified** (N=22 below the
proposed 30-trade economic-gate minimum; the candidate mechanisms reduce to numeric
stop/target tuning, a closed-hypothesis duplicate, or subgroup cherry-picking). G3
remains `NOT_EVALUATED_UNSIGNED_CONTRACT`; optimization ineligible. See
`docs/status/AG_SSC_V1_0_1_SVOS_G2_FAILURE_DECOMPOSITION_STATUS.md`.

### SSC v1.0.1 independent replication admission blocked (2026-09-19)

Evidence-accumulation preflight for a fresh independent DEVELOPMENT replication
(`SSC_V1_0_1_G2_DEV_003`) returned `BLOCKED_NO_ADMISSIBLE_REPLICATION_DATA`: the
EURUSD H1+M15+M1 development timeline is fully consumed (GEN_001 05-18→06-19,
DEV_002 06-21→08-02, GEN_002 08-03→09-14) and the only fresh interval
(2026-09-15+) is calendar-reserved for CONFIRM_001 (protected). No replay, no
hypothesis, no optimization, no protected-data access. See
`docs/status/AG_SSC_V1_0_1_INDEPENDENT_REPLICATION_ADMISSION_STATUS.md`.

### SSC v1.0.1 post-G2 authority synchronization (2026-09-19)

SSC governance/context state synchronized with the frozen DEV_002 G2 population
(`AUTHORITY_SYNCHRONIZED`): the consumption registry now records DEV_002 as `CONSUMED`
(`G2_POPULATION_FROZEN`), and the repaired SVOS context generator derives G2 authority
from the frozen population artifacts (fail-closed on identity mismatch), so
`svos_context.json` reports `G2 = POPULATION_FROZEN` (population_id/n/hash verified),
`G3 = NOT_EVALUATED_UNSIGNED_CONTRACT`, `optimization_eligible = false`,
`hypothesis_status = NO_NEW_HYPOTHESIS_JUSTIFIED`, and
`independent_replication = BLOCKED_NO_ADMISSIBLE_REPLICATION_DATA`
(`furthest_verified_gate` stays `None` — G0/G1 remain PARTIAL). State remediation only;
the shared `validation_framework.svos_context_export.py` stays byte-identical. See
`docs/status/AG_SSC_V1_0_1_POST_G2_AUTHORITY_SYNC_STATUS.md`.

This supersedes the 2026-09-14 classification recorded further down in this file
(kept below as dated historical context, not corrected in place).

### AG_FX_SESSION_DAYTRADE_EURUSD_V1 book added (2026-09-21)

A new proposal-only EURUSD session book, `AG_FX_SESSION_DAYTRADE_EURUSD_V1`, is
implemented on top of the existing frozen `ST_ASIAN_SWEEP_5R_V1@1.1.1` strategy and the
existing `src/post_asian_pilot/` pilot infrastructure: two overlay configs
(`config/pilot/AG_FX_SESSION_DAYTRADE_EURUSD_ASIAN_LONDON_V1.yaml`,
`..._LONDON_NEWYORK_V1.yaml`), each EURUSD-only with its own isolated
`journal/fx_session_daytrade/{asian_london,london_newyork}/` state directory, and a thin
CLI wrapper (`scripts/run_fx_session_daytrade.py`) that delegates entirely to the
existing pipeline/preflight/report functions — no forked strategy, sizing, or journal
logic. Theoretical maximum 2 proposals/day (1 per cycle); `NO_TRADE`/`WATCH`/`DATA_ERROR`
are legitimate outcomes, not forced trades. Proposal-only throughout: `config/trading.yaml`
stays `mode: ANALYSIS`/`allow_order_send: false`; `strategies/registry.yaml`'s
`ST_ASIAN_SWEEP_5R_V1` entry stays `demo_authorized: false`/`live_authorized: false`
(hash-verified byte-identical before/after, as are both sibling pilot configs and the
frozen strategy file). 22 new focused tests pass, plus the existing sibling-pilot,
execution-boundary, and registry-gate regression suites. A real `--preflight --cycle BOTH`
run on this development machine passed against the live DEMO MT5 connection. See
`docs/status/AG_FX_SESSION_DAYTRADE_EURUSD_V1_IMPLEMENTATION_STATUS.md` for full evidence,
including a documented pre-existing gap (shared with both sibling pilots, not introduced
here): the pilot overlay's own `max_new_trades_per_day` field is parsed but not wired into
ledger capacity; this book's real 1-slot/cycle/day cap holds anyway as an emergent property
of the ledger's per-symbol cap combined with this book's EURUSD-only universe.

## Historical rolling classification (2026-09-14, superseded)

Research Factory V1 governance hardening is `UNIT_TESTED`: versioned dataset/candidate/
economic schemas, immutable package freeze/export, two independent reopen/hash passes,
cross-file identity binding, one-shot Holdout consumption, independent canonical import,
100% semantic-parity policy, and separate Demo eligibility/authorization states are
implemented in `src/external_candidate/research_factory.py`. This is infrastructure only:
no real Holdout was run, no strategy or execution gateway changed, and no Demo/Live
authority was granted. See
`docs/status/AG_RESEARCH_FACTORY_V1_GOVERNANCE_HARDENING_STATUS.md`.

This supersedes the 2026-09-10 classification recorded further down in this file
(kept below as dated historical context, not corrected in place).

### SSC HYP_002_SETUP_SELECTIVITY validated negative (2026-09-15)

`ST_SESSION_SWEEP_CONTINUATION_V1`'s first preregistered validation hypothesis,
`HYP_002_SETUP_SELECTIVITY` (exclude S3 from S1+S2+S3), completed the frozen pipeline
and was **FALSIFIED** on GEN_002 evidence: control N=21 net `-0.41R`, treatment N=11
net `-0.36R`, delta `+0.05R` — positive delta but the treatment remained net-negative,
so `FAIL` under the preregistered decision rule. Attempt 1 was `INCONCLUSIVE`
(insufficient H1 warmup); Attempt 2 (43 dates, 86 cycles) was reproducible. HYP_002 is
closed `VALIDATED_NEGATIVE` (no rerun/tuning/reclassification permitted); the strongest
follow-on mechanism (exit-capture/target-too-far) is already governed by
`HYP_001_EXIT_CAPTURE` / the V1.1.0 candidate lineage, so a duplicate HYP_003 was
declined `NOT_JUSTIFIED`. No Demo/Live authority changed and `holdout_run_count=0`. See
`docs/status/AG_SSC_HYP002_SETUP_SELECTIVITY_VALIDATION_STATUS.md`.

| Gate | Status | Evidence |
| --- | --- | --- |
| R0 Safe Foundation | `READY` | — |
| R1 Research Watch | `READY / RESEARCH_ONLY` | — |
| R2 Real Market Watch | `READY` | WP1–WP3, `docs/status/AG_CANONICAL_R2_R4_WP0_BASELINE_RECONCILIATION_STATUS.md` |
| R3 Canonical Strategy | `READY` | WP4–WP5 + WP5.2, same doc (`AG_CANONICAL_STRATEGY_RUNTIME_READY_V1 = PASS`) |
| R4 Canonical Proposal | `READY / PASS` | WP6–WP11A + WP12 natural proof, 2026-09-11 (`AG_PROPOSAL_OPERATION_READY_V1 = PASS`) |
| R5 Edge Validation Ready | `NOT_PASS` | see below |
| R6 Edge Validated | `NOT_PASS` | see below |
| R7–R9 | `BLOCKED` | unchanged |

R4 reached `PASS` on 2026-09-11: a real LONDON_NEWYORK cycle produced a GBPUSD `READY`
decision that flowed through `MarketSnapshot` (REAL) → `StrategyDecision` →
`apply_formation_gate` → `CanonicalProposal` → `ProposalLedger`, verified against the
real ledger file and `GET /api/canonical-proposals`, with `execution_eligible=false`
and zero broker mutation. Restart-reload and duplicate-protection were proven against
that real record.

R5/R6 are recorded here as `NOT_PASS` rather than green. The R5 evidence pipeline
itself is complete and reproducible, but the only resolved evidence that exists —
13 `ST_ASIAN_SWEEP_5R_V1` trades — is 13/13 losses (gross expectancy `-1.00R`, net
`-3.38R` under the one signed cost scenario), and no **signed** economic-gate
threshold exists, so R6 is formally `NOT_EVALUABLE_MISSING_SIGNED_THRESHOLDS`. A
proposed contract awaits owner review in
`config/governance/economic_gate_contract.yaml` (`status: PROPOSED`, **not signed**)
with the review package at `docs/status/AG_R6_ECONOMIC_GATE_OWNER_REVIEW_V1.md`.
Strategy research is `PAUSED_BY_OWNER`; the economic gate is `NOT_VALIDATED`.
No new Demo or Live authorization has been granted. `ST_ASIAN_SWEEP_5R_V1`'s
pre-existing `demo_authorized=true` in `strategies/registry.yaml` is unchanged.

### Platform-finalization remediation (2026-09-12)

Two platform blockers from the 2026-09-12 finalization audit are closed:

- **Position-management authority containment (WP0B).** `web/server.ts`'s real-mode
  `POST /api/execution/manage` and `POST /api/execution/claim` spawned
  `scripts/web_manage_trade.py` / `scripts/manage_trade.py` →
  `src/mt5/management_gateway.py` → real `mt5.order_check`/`order_send` against an
  existing broker position, held inert only by `config/trading.yaml` flags. Both are
  now retired with `410 EXECUTION_ROUTE_RETIRED`, the same structural convention WP0A
  applied to `POST /api/execution/execute`. Mock mode is unchanged and still reports
  `simulated: true`. `src/mt5/management_gateway.py` and all canonical
  `src/trade_management/` logic are preserved — only the alternate Node authority path
  was removed; no second authorization system was created. `web/server.ts` no longer
  references any broker-mutating script, enforced by a static assertion in the
  containment suite. Detail: `docs/status/AG_CANONICAL_R2_R4_WP0_BASELINE_RECONCILIATION_STATUS.md`
  (WP0B section).
- **Broker-side stop-loss close notification.** `src/trade_management/manager.py`'s
  reconciliation previously moved a vanished position to `STATE_CLOSED` and returned
  without notifying, so breakeven / TP1 partial / managed-exit alerted but a stop-loss
  hit did not. Reconciliation now classifies the close from authoritative MT5 deal
  history only (`src/trade_management/close_reason.py` over the existing read-only
  `src/mt5/deals.py::deals_for_position`; MT5's own `DEAL_REASON` on the closing
  `DEAL_ENTRY_OUT` deal) and emits `POSITION_CLOSED_SL` / `_TP` / `_STOP_OUT` /
  `_MANUAL` / `_EXPERT`, falling back to `POSITION_CLOSED_UNKNOWN` when the reason
  cannot be confirmed — a loss is never inferred to be a stop-loss. Delivery reuses
  the existing `src/notifications/trade_management_alerts.py` gateway (no second
  notification path). Idempotency is journal-backed via a durable
  `BROKER_SIDE_CLOSE_DETECTED` event written before the send, so restart or
  re-reconcile of an already-notified ticket sends nothing, and a self-managed
  `CLOSE_CONFIRMED` exit is not double-reported. A Telegram failure cannot affect the
  reconciled state transition.
- **Full `pytest -q` no longer appears to hang.** Root cause was not an MT5, network
  or subprocess dependency: `tests/test_golden_vertical_slice.py::test_case_c_e1m2_ready`
  is an exhaustive historical walk that runs a full canonical V2 entry evaluation at
  each of the CASE_C event's 1151 eligible M5 timestamps, on top of a ~26s load of the
  95,393-candle EURUSD M5 export — genuinely slow but finite, and correct. It is now
  marked `@pytest.mark.slow` and deselected by default via `addopts = "-m 'not slow'"`
  in `pyproject.toml`; it still runs on demand with `pytest -m slow`. Its module also
  gained a skip guard for the machine-local MT5 CSV export it depends on
  (`D:\EURUSD_M5_*.csv`, outside the repo). Two unrelated real failures were also
  fixed: `test_bias_provenance_e2e.py::test_resolver_invoked_exactly_once_per_cycle`
  patched a name `daytrading.decision.market_bias` never binds (it imports the
  resolver lazily to avoid an import cycle) — a test-only defect, production code
  correct; and `test_mtf_context.py::test_live_closed_candle_and_timezone_sanity` now
  skips its bar-freshness assertion during the spot-FX weekend closure instead of
  failing on the correctly-served last bar of the trading week. No strategy rule,
  parameter, threshold or authorization flag was touched by any of this.

### Readiness validation infrastructure (2026-09-12)

A repeatable readiness gate now exists so R-gate status is re-verifiable on demand
instead of re-derived by hand each time.

| Field | Value |
| --- | --- |
| `frontend_config` | `PASS` — 17/17 client routes in `web/src/utils/agApiClient.ts` map 1:1 onto real `src/api/app.py` routes (`/api/health`, `/api/system/status`, `/api/broker/{status,account,history}`, `/api/strategies[/{id}]`, `/api/validation/{id}`, `/api/proposals[/{hash}]`, `/api/canonical-proposals[/{id}]`, `/api/tickets[/{id}][/authorize-demo]`, `/api/executions/{id}`, `/api/market-data/candles`); no orphan client call, no invented route. `VITE_AG_API_MODE` / `VITE_API_BASE_URL` documented in `web/.env.example`; CORS allow-list is `http://localhost:3000` + `http://127.0.0.1:3000` (matching Vite's port 3000), never `*`, `allow_credentials=false`. |
| `FAST_validation` | `PASS` — `scripts/validate_readiness.ps1 -Mode Fast` |
| `FULL_validation` | `PASS` — `-Mode Full`, 2026-09-12: **2666 passed, 7 skipped, 1 deselected, 0 failed, 0 errors** in 586.52s. `unexplained_failures = []`. All 7 skips are the pre-existing spot-FX weekend-closure / live-MT5-trading-day guards (the run fell on Saturday 2026-09-12); the 1 deselection is the `@pytest.mark.slow` exhaustive historical walk. |
| `WP3` | `PASS` — fail-closed guards in `src/mt5/market_data.py`: `DUPLICATE_TIMESTAMPS`, `NON_MONOTONIC_TIMESTAMPS` (`_validate_monotonic`), `INVALID_OHLC`, `NONFINITE_PRICE` (`_validate_ohlc`), plus `DATA_MISSING`, `INSUFFICIENT_CANDLES`, `SYMBOL_NOT_FOUND`, `UNSUPPORTED_TIMEFRAME`, `MT5_NOT_CONNECTED`, `NAIVE_DATETIME_REJECTED`, `TIME_NORMALIZATION_ERROR`. Every one raises `MarketDataError`; none degrades to synthetic data. |
| `WP11` | `PASS` — `tests/test_pipeline_canonical_wiring.py` (10 cases) covers duplicate evaluation → one logical proposal, restart-reload → identical id/geometry/provenance, missing snapshot → fail closed, synthetic snapshot → fail closed, and formation never touching execution; `tests/test_proposal_ledger.py` (7) and `tests/test_ticket_delivery_concurrency_and_restart.py` cover durability and concurrency. |
| `WP12` | `SATISFIED` — prior natural evidence **re-verified**, not re-attempted. `FX:DECISION-GBPUSD-6175099562eae0c6` is present in the real ledger `state/proposal_ledger/proposal_ledger.json` (10 entries) with `market_data_mode: REAL`, `source: MT5`, `complete_candle_evidence: true`, `execution_authority: NONE`. No new live capture was forced and no synthetic data was injected. |
| `economic_validation` | `NOT_VALIDATED` — unchanged. R5/R6 remain `NOT_PASS`; no signed economic-gate threshold exists. Software readiness is **not** economic edge. |
| `Demo_authority` | `UNCHANGED` — no strategy promoted, no `strategies/registry.yaml` flag altered. |
| `Live_authority` | `UNCHANGED` — none granted; no order was ever submitted (`orders_submitted = 0`). |

`scripts/validate_readiness.ps1` supports `-Mode Fast` (repo sanity, frontend
deps/typecheck/build/safety-tests/config/containment checks, backend collection,
focused R0–R4 gate tests) and `-Mode Full` (Fast + the complete backend suite). It
records `PASS` / `SKIP_ENVIRONMENT` / `KNOWN_ENVIRONMENT_GAP` / `FAIL` per check —
only explicitly classified checks may receive environment treatment; anything
unclassified that fails is `FAIL`. No individual check can exit the run, so the
summary always prints and only the final overall verdict sets the exit code. Each
run writes `artifacts/readiness/latest.json` (`schema_version`, `timestamp_utc`,
`commit`, `mode`, `overall`, `frontend{}`, `backend{}`, `r4{}`,
`unexplained_failures[]`).

`tests/conftest.py` adds a collection-time-only MetaTrader5 portability shim so the
suite can be *collected* on a non-Windows machine. It is a **no-op on this dev box**
(real MetaTrader5 5.0.5735 installed). It is deliberately stricter than a
`MagicMock`: MT5 constants are real values, but every other attribute resolves to a
callable that raises `MT5StubOperationAttempted` when invoked — importing never calls
these, so collection succeeds, while a test that reaches a genuine MT5 operation
fails loudly instead of being fed a fake success. A `live_mt5` marker is registered
in `pyproject.toml` and is **not** deselected by default: these tests run for real
here and skip only where the genuine package is absent.

Frontend bundle: `vite.config.ts` splits `vendor-recharts` out of the app chunk.
Chunks are **not** all under 500 kB — `vendor-recharts` is ~730 kB and the app chunk
~912 kB, so Rollup's >500 kB advisory still fires. That is a load-time performance
characteristic, not a readiness gate, and is recorded here so no document claims
otherwise.

### Deterministic Trading Skills architecture (2026-09-11)

Deterministic market-analysis capabilities now have a canonical data-only registry and
an authority-limited `TradingSkill.evaluate(context) -> MarketObservation` interface.
They may observe/classify but cannot decide or propose trades, modify strategy or risk
rules, promote strategies, authorize trades, or execute. Existing implementations,
strategy engines, replay surfaces, lifecycle state, risk, and execution paths are
unchanged. See `docs/architecture/DETERMINISTIC_TRADING_SKILLS.md`.

### Frontend Demo-ticket authorization surface (2026-09-09)

The real-mode AG Backend panel now lists durable backend execution tickets and exposes
`Authorize Demo` only for `PENDING` `DEMO` tickets. Every click requires a fresh browser
confirmation and calls the existing identifier-only
`POST /api/tickets/{approval_id}/authorize-demo` route; order fields never come from the
browser. Mock mode, non-Demo tickets, and non-pending tickets remain disabled. Local
VS Code runtime verification passed with FastAPI, Vite, MT5, and the configured Vantage
Demo account connected; frontend TypeScript validation passed (`npm run lint`). No
order was sent during this milestone: current `SESSION_TRADE_V1` evaluations produced
no eligible setup, and the backend had no actionable proposal or pending ticket. The
known persistent proposal-ingestion gap remains open.

### Live MT5 account and history synchronization (2026-09-09)

Read-only validation confirmed the active terminal is account `25972746` on
`VantageMarkets-Demo`, MT5 account trade mode `DEMO`, with trading permitted. The local
FastAPI status endpoint independently returned the same identity as `****2746`. Added
`GET /api/broker/history` and a real-mode `MT5 Trade History` panel backed directly by
MT5 `history_deals_get`; it exposes sanitized closing-deal fields only and performs no
broker mutation. Live 90-day evidence at validation time: 11 closing deals, net
`-5.43 USD`, balance/equity `994.57 USD`, zero open positions, zero pending orders.
Verification: `python -m pytest tests/test_api.py -q` = 26 passed; `npm run lint` passed;
browser rendering verified against the live local API. No trade or setting changed.

### VS Code supervised frontend/backend startup (2026-09-09)

The primary VS Code task `AG: Start Dev` now directly invokes
`scripts/run_dev.ps1` instead of depending on two background tasks without readiness
problem matchers. It is the default `Ctrl+Shift+B` task, opens in one dedicated terminal,
starts FastAPI and Vite together, and stops both child jobs when terminated. Separate
backend/frontend tasks remain for debugging. Existing real-mode environment verified:
`VITE_API_BASE_URL=http://127.0.0.1:8000`, `VITE_AG_API_MODE=real`; live runtime ports
8000 and 3000 were listening at validation time. No trading authority changed.

### Frontend simulation-boundary correction (2026-09-08)

The React workspace now displays a persistent mode banner. Its default `mock` mode
identifies candles, proposals, positions, execution, and management as generated
fixtures, and mock API successes explicitly state that no broker action occurred.
When `VITE_AG_API_MODE=real`, the legacy manual-order and direct-management controls
fail closed because they are not wired to the authoritative backend workflows.
Malformed mock orders and unsupported management actions are rejected. This is a
user-interface safety correction only: it adds no strategy, Demo, LIVE, or trade-
management authorization. See
`docs/status/AG_FRONTEND_SIMULATION_BOUNDARY_V1_STATUS.md`.

## Master capability-gated readiness plan (owner adopted 2026-09-10)

The owner adopted `AG Profit Trading — Master Project Readiness Plan V3` as the
authoritative roadmap. Readiness is now tracked through independent capability gates:
R0 Safe Foundation, R1 Research Watch, R2 Real Market Watch, R3 Canonical Strategy, R4
Canonical Proposal, R5 Edge Validation Ready, R6 Edge Validated, R7 Demo Execution
Ready, R8 Demo Auto-Execution Validated, and R9 Controlled Live.

Classification as recorded on 2026-09-10 (**superseded** — see "Current rolling
classification (2026-09-12)" at the top of this file; preserved here as dated
historical context): R0 `READY`; R1 `READY / RESEARCH_ONLY`; R2 `PARTIAL`; R3
`PARTIAL`; R4 `NOT_READY` and the primary product target; R5 `PARTIAL`; R6
`INCOMPLETE`; R7–R9 `BLOCKED`. R2 was partial because Vantage Demo MT5 read-only
connectivity and closed M15 candles are verified for the current EURUSD/GBPUSD backend
path, while the guarded end-to-end scanner/watch path is not yet proven. Existing
execution infrastructure and separately authorized strategy paths do not advance
scanner-driven execution readiness.

The current engineering program is `AG_CANONICAL_SCANNER_PROPOSAL_PIPELINE_V1`: R2
real-market data and fail-closed guards → R3 canonical Python decisions and
renderer-only UI → R4 immutable persistent proposals, API, scanner integration,
focused tests, and natural read-only end-to-end proof → **STOP**. R4 proposals must
carry `execution_eligible=false` and `execution_authority=NONE`. Edge validation
follows proposal operation; scanner-driven Demo execution follows a strategy-specific
validated edge and separate authorization; Live remains separately blocked. This is a
planning/governance change only: no strategy, registry, risk, account, or execution
configuration changed.

The authoritative master plan is `docs/PROJECT_ROADMAP.md`. The existing
`docs/plans/AG_STAGE1_EXACTLY_ONCE_FX_TICKET_DELIVERY_V1.md` is retained as supporting
R4 delivery work, not the master milestone. Earlier roadmap text below remains dated
historical context where it conflicts with this 2026-09-10 owner direction.

The owner-approved hardening amendment on 2026-09-10 added six explicit contracts:
end-to-end `REAL`/`REPLAY`/`SYNTHETIC` market-data provenance; distinct
`StrategyDecision.READY` and `Proposal.ACTIVE` states; a non-economic Proposal
Formation Gate; deterministic occurrence identity; freshness independent from proposal
expiry; and separate Demo eligibility, authorization, and execution gates. It also
decomposed the current program into WP0–WP12 and added Proposal Integrity Rate as the
primary R4 quality KPI. These are roadmap requirements only; schemas and thresholds
remain to be frozen during implementation, and no runtime or trading authority changed.

## Historical owner-directed profit-seeking objective (regenerated 2026-09-07; superseded as master ordering)

The current product objective is proposal-first trade assistance:

- produce an informational trade ticket after the Asian session and after the London
  session for three major FX pairs plus gold (target universe: EURUSD, GBPUSD, USDJPY,
  XAUUSD, pending final contract freeze);
- produce scheduled informational tickets for two crypto instruments (BTCUSDT and
  ETHUSDT) at preset time(s);
- watch a preset Large-SMC pair universe, expose persistent funnel status, and alert
  when the current frozen strategy reaches entry confirmation.
- assist owner-led top-down chart analysis through the relevant advisory skill chain,
  resolve a compatible registered strategy, identify strategy-eligible opportunities,
  and monitor the strategy-defined higher-to-lower-timeframe entry confirmation.

Delivery is now sequenced as **proposal delivery and persistent watch setup first,
strategy validation second**. Formal validation starts per strategy cohort after its
proposal/watch path passes deterministic-state, archive/deduplication, restart-
recovery, evidence-integrity, outcome/cost-contract, and execution-isolation gates;
EURUSD/GBPUSD and BTCUSDT may therefore enter separate validation cohorts without
waiting for unsigned expansion instruments. This sequencing does not change any frozen
strategy behavior or claim that an unvalidated strategy has trading edge. The ticket
layer may publish only values returned by the current deterministic strategy and must
preserve `NO_TRADE`, `WATCH`, and fail-closed outcomes. All tickets and Large-SMC alerts
remain informational; Demo/live execution authority is unchanged.

In the interactive workflow, skills may describe structure, zones, liquidity, and
confirmation evidence, but only the matched strategy engine can emit `READY` or a
`TradeSignal`. If no signed strategy matches, the required result is
`NO_REGISTERED_STRATEGY_MATCH`; rules must not be borrowed from another strategy.

At the time of this 2026-09-07 plan, the milestone was
`docs/plans/AG_STAGE1_EXACTLY_ONCE_FX_TICKET_DELIVERY_V1.md`. Two installed FX
scheduler tasks had been read-only verified as enabled and successfully fired, while
overlap, restart, and missed-run recovery were then unverified and external message
delivery was the stated blocker. These claims are preserved as dated historical
context; the rolling 2026-09-10 classification and `docs/PROJECT_ROADMAP.md` now govern.

The owner-directed commercialization choices and end-to-end delivery/evidence plan are
recorded in
`docs/plans/BEST_MONEY_MAKING_PATHS_AND_TICKET_DELIVERY_ACTION_PLAN_V1.md`. It defines
Major FX V1 delivery as EURUSD/GBPUSD, sequences BTCUSDT next and XAUUSD delivery only
after the first pipeline passes its reliability gate, and adds a parallel expanded
research/watch surface for FX Major Three, Gold, and Crypto Two. USDJPY, XAUUSD, and
ETHUSDT may appear there only under explicit candidate/shadow status until their own
contracts and gates pass. The plan now freezes watcher state, proposal state, and
execution authority as three independent dimensions; preserves compatible research
setups as `STRATEGY_UNMATCHED`; requires lifecycle timestamps and
`next_required_evidence`; and places the Opportunity Board strictly after persisted
watcher-state/recovery proof. It is non-authorizing: it does not change strategy,
Demo/LIVE, message-delivery, or broker-execution authority.

## Two-section capability model (2026-09-06)

The project is organized into two capability sections, audited in full in
`docs/PROJECT_CAPABILITY_COMPLETENESS.md` (state matrices, execution-authority matrix,
qualification counters, priorities, owner decisions — do not duplicate those matrices
here). **SECTION A — Trading Edge & Decision Core** (market data, session logic,
strategy rules, decision classification, proposals, risk/sizing, shadow/observation
evidence) and **SECTION B — Operations, Execution & Platform** (Telegram, MT5
execution infra, persistence, CLI, scheduler, release management) are governed by one
rule: Section B must never silently change Section A's direction/entry/SL/TP/risk.

Current one-liners, from actual evidence as of `main`
`651ade619c2c2df9a973d45cea37ae6599c2b9eb`:

- **FX**: Series `AG_V1_0_3_FX_SHADOW_SERIES_002` — valid=0/20, invalid=1, excluded=0,
  pending=0; next eligible trading day 2026-09-07.
- **BTC**: Bybit production market-data connectivity confirmed (HTTP 200/retCode 0) —
  data access only, not trade execution or profitability; daily-decision CLI ready;
  30-valid-observation campaign is 0/30 and **OWNER_AUTHORIZED to start** as of
  2026-09-06T06:52:42Z. No observation has been counted yet; prior diagnostics and
  missed report windows do not count retroactively. Crypto execution remains disabled.
- **Execution**: MT5 Demo infrastructure implemented and DEMO_VERIFIED generically
  (a real MT5 Demo-account order round trip, 2026-08-28; not real-money execution
  evidence); `ST_ASIAN_SWEEP_5R_V1`, the active V1.0.3 FX pilot strategy, is not
  `demo_authorized`, so it cannot use it yet (a registry gate, not a missing
  capability). `SESSION_TRADE_V1` is independently `demo_authorized: true` for its
  `ASIAN_LONDON` cycle only (`LONDON_NEWYORK` is `false`), but it is a separate
  strategy on a separate engine — this does not grant, share, or imply execution
  authority for `ST_ASIAN_SWEEP_5R_V1` or any other strategy. Strategy authorization
  and execution-channel authorization are independent gates; authority is never
  inherited across strategies. Live trading remains disabled by default.
- **Telegram**: Phases A, B, C, D1 are fully committed on feature branch
  `feature/telegram-demo-execution-gateway-v1` at commit `740512b`
  ("AG_TELEGRAM_DEMO_EXECUTION_GATEWAY_V1_PHASE_D1_BROKER_UNREACHABLE_BASELINE"). The
  feature-branch working tree is clean (no uncommitted changes) as of this audit. It
  has not been merged into `main`, and development remains **paused** by owner
  directive; broker wiring absent by design.
- **Large-SMC**: `RESEARCH_DRAFT` v1.0.7 -- C10 (broker stop-loss) SIGNED and
  implemented 2026-09-07 (`DYNAMIC_ATR_WITH_HARD_FLOOR`, frozen); AG-EGSVF lifecycle
  stage owner-promoted `OFFLINE_RESEARCH -> FORWARD_RESEARCH` the same day. Next
  transition (`-> OPERATIONAL_SHADOW`) is evaluated, not executed, and blocks on an
  unresolved shadow-entry-evidence gate. No proposal/demo/live authority (unchanged).

## Current operational snapshot (2026-09-05)

This section is the rolling summary. Test totals elsewhere in this document belong to
the dated milestone that introduced the surrounding feature.

```text
ANALYSIS                      AVAILABLE
DAILY SESSION/SMC RUNTIME     READ-ONLY, restart-persistent
DEMO OPEN/CLOSE EXECUTION     IMPLEMENTED, explicit-command-gated
LIVE TRADING                  DISABLED BY DEFAULT
MANUAL TRADE MANAGEMENT       BUILT, independently gated, live validation deferred
FX LONDON->NEW YORK CYCLE     UNIT_TESTED, ST_ASIAN_SWEEP_5R_V1 LONDON_NEWYORK pilot (AG_POST_LONDON_NEWYORK_PILOT_V1_0_1), proposal-only, isolated ledger from ASIAN_LONDON, no live/demo verification yet
CRYPTO SIGNAL CONTRACT        IMPLEMENTED (incubation)
CRYPTO DATA ADAPTER           LIVE-VALIDATED, Bybit production public/read-only BTCUSDT linear perpetual: server time/instrument/M5 endpoints HTTP 200 retCode=0; frozen adapter validated complete closed H1/M5 evidence on 2026-09-05. No credentials/private endpoints.
CRYPTO DAILY DECISION         OPERATIONAL CLI READY, scripts/run_btc_daily_report.py enforces the owner-adjusted 06:30-06:45 UTC next-day window (13:00-13:15 MMT), previous-UTC-date evaluation, complete 24 H1 reference + 288 M5 observation audit, immutable archive, and informational proposal ticket on READY. Campaign is owner-authorized (2026-09-06T06:52:42Z) and the Windows Task Scheduler daily task ("AG Profit Trading - BTC Daily Decision", 13:05 MMT/06:35 UTC, State=Ready) is now installed and enabled; campaign_status=ACTIVE_0_OF_30 -- remains 0/30 until the first in-window observation is actually archived (no diagnostic or scheduler-installation event counts by itself).
CRYPTO STRATEGY SKILL         REGISTERED, btc-sweep-retest-analysis (owner_strategy=ST_LIQUIDITY_SWEEP_RETEST_V1, ADVISORY_ONLY -- explains the shared sweep/retest engine's CRYPTO_PERP contract and cost model, never places/authorizes orders or changes thresholds), mirrored in .claude/skills/SKILL_REGISTRY.yaml and .agents/skills/SKILL_REGISTRY.yaml.
CRYPTO RESEARCH RUNTIME       LIVE-DATA-VALIDATED, RESEARCH_ONLY/PROPOSAL_ONLY, execution_domain=CRYPTO_RESEARCH/execution_authority=DISABLED, statically and behaviorally verified never to reach execution.executor/mt5.management_gateway
CRYPTO EXECUTION              NOT IMPLEMENTED, fail-closed (execution.adapter.CryptoExecutionAdapter remains NOT_IMPLEMENTED; execution.executor now explicitly rejects any non-TradeCommand object, not just BTC proposals)
LARGE SMC STRATEGY            RESEARCH_DRAFT v1.0.7, C10 (broker stop-loss) SIGNED and implemented 2026-09-07 (DYNAMIC_ATR_WITH_HARD_FLOOR, frozen); AG-EGSVF lifecycle owner-promoted OFFLINE_RESEARCH -> FORWARD_RESEARCH same day; next transition (-> OPERATIONAL_SHADOW) evaluated-not-executed, blocked on unresolved shadow-entry-evidence gate; no proposal/execution authority
SMC SEMANTIC TRAP GUARD       UNIT_TESTED, additive evidence validation for Asian Sweep + Large SMC
MULTI-TIMEFRAME CONTEXT SKILL  ADVISORY_ONLY, added 2026-09-07 (multi-timeframe-market-context; canonical source .agents/skills/, mirrored read-only to .claude/skills/ for Claude Code runtime discovery -- see docs/architecture/TRADE_ASSISTANT_ARCHITECTURE.md "Universal skill contract"). Orchestrates existing market-structure-analysis/supply-demand-analysis/liquidity-analysis/entry-confirmation-analysis across a caller-supplied timeframe profile (role-based: MACRO/BIAS/WORKING/SETUP/EXECUTION/MANAGEMENT, not a fixed D1/H4/H1/M15 hierarchy); introduces no new detection package. No strategy YAML declares a multi_timeframe_context/usage block yet -- no strategy/risk/execution behavior changed by its addition. Closed-candle/no-lookahead behavior verified by code inspection 2026-09-07 (mt5.market_data.get_latest_candles excludes the forming bar at every timeframe; BOS/CHoCH reported by confirmation time, not swing-point time) -- see the skill's own "No-lookahead / data quality" section for the itemized evidence.
HISTORICAL REPLAY             LIVE-MT5 ACCESS BLOCKED
FULL REGRESSION               1356 passed / 1 skipped / 0 failed (2026-09-02/03, `python -m pytest -q`, AG_COMPLETE_TRADE_OPPORTUNITY_V1 remediation milestone -- see docs/status/AG_COMPLETE_TRADE_OPPORTUNITY_V1_REMEDIATION_STATUS.md); previous dated milestone baseline: 979 passed / 5 skipped / 0 failed, 2026-08-30 -- see dated sections below
RELEASE MANIFEST               AG_TRADE_ASSISTANT_V1_0_3 frozen as RELEASE_CANDIDATE (2026-09-03, config/releases/AG_TRADE_ASSISTANT_V1_0_3.yaml) -- pins the source baseline described above; V1.0.2 remains the current documented/operational release (config/releases/AG_TRADE_ASSISTANT_V1_0_2.yaml is still the default consumed by src/post_asian_pilot/pilot_config.py and preflight.py). Owner decisions recorded 2026-09-03: credential rotation OWNER_CONFIRMED_COMPLETE (Binance/MEXC/Bybit); withdrawal permission OWNER_CONFIRMED_RESTRICTED (2026-09-03); IP-restriction status still UNRESOLVED; BTC production market-data authority FROZEN as Bybit (adapter NOT_IMPLEMENTED, environment-blocked HTTP 403 from here, same class as Binance's HTTP 451); Large-SMC C10 conceptual stop model FROZEN as AG_NATIVE_INVALIDATION (implementation/contract-freeze still PENDING, engine unchanged/still BLOCKED). Release qualification (20-day FX shadow, 30-day BTC observation) remains pending, not started -- see docs/status/AG_TRADE_ASSISTANT_V1_0_3_RELEASE_MANIFEST_FREEZE_STATUS.md.
OPERATIONAL PREFLIGHT          AG_TRADE_ASSISTANT_V1_0_3 preflight: PREFLIGHT_PASS_SHADOW_READY (closed 2026-09-03). Initial run (same date, prior environment) returned HOLD solely on MT5 connectivity ("No IPC connection" -- no terminal reachable from that tool environment; all other categories PASS'd there already, see docs/status/AG_TRADE_ASSISTANT_V1_0_3_OPERATIONAL_PREFLIGHT_STATUS.md, preserved as historically accurate for that environment). Re-run from the intended operator environment (MT5 terminal connected, demo account confirmed) closed that blocker: EURUSD/GBPUSD both resolve with exchange-verified metadata and 24 well-formed, correctly-ordered M15 closed bars each (the pipeline's only required timeframe -- strategies/ST_ASIAN_SWEEP_5R_V1.yaml, src/post_asian_pilot/pipeline.py), session/clock contract validates, no broker mutation performed -- see docs/status/AG_TRADE_ASSISTANT_V1_0_3_MT5_DATA_READINESS_AND_PREFLIGHT_CLOSURE_STATUS.md. Release remains RELEASE_CANDIDATE, not RELEASED; FX shadow/BTC observation collection not started (0/20, 0/30).
FX SHADOW EVIDENCE CONTRACT    AG_TRADE_ASSISTANT_V1_0_3 FX shadow-validation evidence contract frozen 2026-09-03: SHADOW_EVIDENCE_CONTRACT_READY (series AG_V1_0_3_FX_SHADOW_SERIES_001, contract AG_V1_0_3_FX_SHADOW_EVIDENCE_CONTRACT_V1). Freezes VALID_DAY/EXCLUDED_DAY/INVALID_DAY/PENDING_RECONCILIATION definitions, per-unit evidence fields (trading_date x cycle x symbol), immutable-evidence, duplicate, cross-cycle-isolation, restart, and data-error contracts -- every field mapped onto existing, already-tested components (governor.DailyTradeLedger, report.cycle_to_dict, store.py idempotent writes/immutable snapshots); no new shadow runtime built. Large-SMC/C10 remain independent: PARTIALLY_RESOLVED_REQUIREMENTS, three owner decisions (exact buffer, spread/bid-ask policy, broker minimum-distance policy) still UNSIGNED, engine still BLOCKED.
FX SHADOW DAY 001 (2026-09-02)  EXCLUDED_DAY. Shadow-validation authorization for AG_V1_0_3_FX_SHADOW_SERIES_001 arrived after both ASIAN_LONDON (07:00-11:00 UTC) and LONDON_NEWYORK (12:00-15:00 UTC) execution windows for 2026-09-02 had already closed, and after both cycles' ledgers already held real pre-existing claimed slots (4/4) from ordinary V1.0.2-labeled operation predating this series -- no uncontaminated window remained to fairly test the frozen runtime today. Not a strategy/runtime defect. One read-only --once probe was run to confirm live state (proposal-only, order_send unreachable, confirmed). Counters after this entry: valid_days=0/20, excluded_days=1, invalid_days=0, pending_days=0 -- see docs/status/AG_TRADE_ASSISTANT_V1_0_3_FX_SHADOW_DAY_001_STATUS.md.
FX SHADOW DAY 002 (2026-09-03 attempt)  PENDING_RECONCILIATION. Authorized re-run attempted for trading_date 2026-09-03, but at time of run (2026-09-02T22:51Z system / 2026-09-03T01:51Z broker) Thursday's asian reference session (00:00-06:00 UTC) had not yet started and both execution windows were 8+ hours away -- no unit was yet eligible for evaluation (not a failure, not an exclusion of the day itself, just premature timing). One read-only probe confirmed this returns the same already-excluded 2026-09-02 state, not new evidence. Not resolved to VALID/INVALID; re-run required at/after 11:00 UTC (ASIAN_LONDON) and 15:00 UTC (LONDON_NEWYORK) on 2026-09-03, under separate authorization. Counters: valid_days=0/20, excluded_days=1, invalid_days=0, pending_reconciliation=1 -- see docs/status/AG_TRADE_ASSISTANT_V1_0_3_FX_SHADOW_DAY_002_STATUS.md. Continuation same day (10:36 UTC): a further read-only probe produced a real, non-synthesized GBPUSD ASIAN_LONDON proposal (SHORT, reason UPPER_SWEEP_STRICT_PENETRATION); EURUSD stayed WATCH. Confirmed FX_SESSION_GATE = VERIFIED_CORRECT (10:36 UTC is legally inside the 07:00-11:00 UTC window, not an early-evaluation defect) and FX_RELEASE_IDENTITY = PRESENTATION_ONLY_METADATA_DRIFT (pilot_config.DEFAULT_RELEASE_CONFIG_PATH is hardcoded to V1.0.2; release_id is metadata-only, never selects strategy/pilot/risk/session behavior) -- remediation diff fully defined but held, not applied, pending explicit owner go-ahead. Day 002 still does not count toward 20/20 pending that reconciliation. BTC's Bybit-adapter release-qualification gate conflicts with V1.0.3's own scope-freeze invariant -- classified QUALIFICATION_REMEDIATION_REQUIRES_OWNER_AUTHORIZATION, no Bybit code written. See docs/status/AG_TRADE_ASSISTANT_V1_0_3_RELEASE_QUALIFICATION_BLOCKERS_STATUS.md.
FX DAILY REPORTING INFRASTRUCTURE (2026-09-03)  PARTIAL_REPORTING_INFRASTRUCTURE_READY. Added a combined FX daily decision-report builder (src/post_asian_pilot/daily_fx_report.py) that aggregates the existing, unchanged per-cycle report.render_pilot_end_report() for ASIAN_LONDON and LONDON_NEWYORK into one canonical JSON artifact, plus a generic append-only/immutable archive (src/post_asian_pilot/report_archive.py, idempotent re-generation, numbered correction records on genuine change, original never overwritten) and a scheduler-ready CLI (scripts/run_fx_daily_report.py -- no OS scheduler job installed). No strategy/risk/execution semantics changed; 6 new focused tests plus the existing 66 FX pilot tests all pass. BTC daily reporting, a scheduler install, READY notifications, and outcome/broker-trade history remain not built (out of this narrowed slice's scope). Still blocked on the same FX release-identity and BTC Bybit-scope items above. See docs/status/AG_TRADE_ASSISTANT_V1_0_3_DAILY_REPORTING_HISTORY_AND_SCHEDULER_STATUS.md.
FX RELEASE-IDENTITY REMEDIATION (2026-09-04)  FX_RELEASE_IDENTITY_REMEDIATION_COMPLETE. Applied the previously-defined, now owner-authorized 5-file metadata-only fix so active FX pilot/reporting output self-identifies as AG_TRADE_ASSISTANT_V1_0_3 instead of V1.0.2 (pilot_config.DEFAULT_RELEASE_CONFIG_PATH, preflight.py's default/assertion, report.py's label/docstring, run_post_asian_pilot.py's CLI strings, 2 of the 5 originally-flagged test assertions -- config/releases/AG_TRADE_ASSISTANT_V1_0_2.yaml itself untouched). No strategy/risk/session/quota/execution semantics changed; affected suite 72 passed / 0 failed. Re-ran the FX daily-report CLI read-only against 2026-09-03: decisions/proposals byte-identical to the pre-remediation run, only the release label changed -- the archive correctly preserved the original V1.0.2-labeled record and wrote a numbered correction (journal/reports/fx/2026/2026-09-03.correction-001.json) rather than overwriting it, confirming the immutability policy works with real evidence. Day 001/Day 002 (Series 001) preserved unchanged, still non-counting; recommend a clean AG_V1_0_3_FX_SHADOW_SERIES_002 (0/20) for future collection -- not started. See docs/status/AG_TRADE_ASSISTANT_V1_0_3_FX_RELEASE_IDENTITY_REMEDIATION_STATUS.md.
BASELINE FREEZE BEFORE FX SERIES 002 (2026-09-04)  BASELINE_FROZEN_SERIES_002_READY. Series 002 was blocked (BASELINE_NOT_READY) because the release-identity remediation and daily-reporting infrastructure existed only in the uncommitted working tree -- owner authorized commit-and-freeze (not an uncommitted-tree exception). Reviewed and classified every dirty path (5 remediation files, 4 new reporting files, 7 status docs, PROJECT_STATUS.md as intended; journal/reports/ runtime evidence explicitly excluded, left untracked); confirmed no strategy/session/risk/quota/proposal/execution semantic change; ran the affected suite fresh (72 passed/0 failed) before staging explicit paths only (no `git add -A`). Committed as SOURCE_BASELINE_COMMIT 68d76f6b1982f2b2936e12128151a308ba153a13 ("Freeze V1.0.3 FX identity and daily reporting baseline"). config/releases/AG_TRADE_ASSISTANT_V1_0_3.yaml's own frozen source_baseline.git_head (be5d31a, from the earlier manifest-freeze milestone) was deliberately left untouched -- it describes when the manifest itself was frozen, not a live pointer; this new hash is recorded only in status docs/PROJECT_STATUS.md instead. SERIES_002_COUNTING_READY = YES; AG_V1_0_3_FX_SHADOW_SERIES_002 (0/20) was not initialized or started this milestone. Not pushed. See docs/status/AG_TRADE_ASSISTANT_V1_0_3_BASELINE_FREEZE_BEFORE_FX_SERIES_002_STATUS.md.
FX SHADOW SERIES 002 DAY 001 (2026-09-04)  INVALID_DAY. First Series 002 evaluation attempt under SOURCE_BASELINE_COMMIT 68d76f6, read-only (no strategy cycle re-run, no order sent). Discovered a real, pre-existing material defect: report.render_pilot_end_report() looks up decisions using the pilot config's reference_session_name ("asian"/"london_am", lowercase), but a real post-close decision from the strategy engine is saved under TradeSignal.reference_session ("Asian"/"London", capitalized, from strategies/ST_ASIAN_SWEEP_5R_V1.yaml's session_pairs) -- a key-casing mismatch that made today's canonical report falsely show NO_RECORD for both ASIAN_LONDON symbols despite two real, legitimately-claimed READY proposals (EURUSD, GBPUSD, ready_at 07:45 UTC) actually existing in the ledger/decision journal. Confirmed by reading the raw journal files directly, not inferred. Preserved all evidence, made no source changes (defect not fixed inside the countable day, per instruction), classified INVALID_DAY. Counters: valid_days=0/20, excluded_days=0, invalid_days=1, pending_days=0. Next step: a separate owner-authorized remediation milestone must fix the reference_session key-casing mismatch before Series 002 can produce trustworthy daily evidence. See docs/status/AG_TRADE_ASSISTANT_V1_0_3_FX_SHADOW_SERIES_002_DAY_001_STATUS.md.
FX REPORT DECISION-KEY REMEDIATION (2026-09-04)  REPORT_KEY_REMEDIATION_COMPLETE. Fixed the Day 001 defect: render_pilot_end_report() now looks up decisions via a new post_asian_pilot.store.find_decision() helper matching on (strategy_id, symbol, trading_date) within each already-isolated per-cycle decision store, picking the latest-evaluated record when more than one candidate exists, instead of building a reference_session-cased dict key. Also found and fixed a second instance while reproducing: LONDON_NEWYORK's mismatch is not mere casing ("London" vs "london_am" differ by more than case), so the initial case-insensitive-only approach was replaced with this cycle-isolation-based fix. No persisted journal file was rewritten; no strategy/session/risk/quota/execution semantics changed. 6 new/updated focused tests; affected suite 78 passed/0 failed. Re-ran the existing report against the same 2026-09-04 journals: ASIAN_LONDON EURUSD/GBPUSD now correctly show READY with their real proposal IDs, LONDON_NEWYORK correctly shows WATCH -- archived as a numbered correction, original preserved, per the append-only archive's own design. Day 001 remains INVALID_DAY (not retroactively counted); counters unchanged: valid_days=0/20, invalid_days=1. Series 002 continues (no new series required by the frozen evidence contract). See docs/status/AG_TRADE_ASSISTANT_V1_0_3_FX_REPORT_DECISION_KEY_REMEDIATION_STATUS.md.
FX SHADOW SERIES 002 DAY 002 (checked 2026-09-04, re-checked 2026-09-05)  BASELINE_VERIFIED_AWAITING_NEXT_ELIGIBLE_DAY. Verified HEAD matches validation_source_baseline 3b2eeed (updated from 30b63f8 after the Entry Ticket wiring commit), no source drift (only journal/reports/ dirty), fresh affected-suite run 92 passed/0 failed. 2026-09-04/05/06 cannot be Day 002 -- 09-04 is already Day 001's (INVALID_DAY) trading date, 09-05/06 are weekend; next eligible trading date is Monday 2026-09-07. No FX cycle invoked, no report generated, no source touched -- pure verify-and-stop, twice now. Counters unchanged: valid_days=0/20, invalid_days=1. See docs/status/AG_TRADE_ASSISTANT_V1_0_3_FX_SHADOW_SERIES_002_DAY_002_STATUS.md.
FX COMPLETE ENTRY TICKET WIRING (2026-09-04)  FX_COMPLETE_ENTRY_TICKET_WIRING_COMPLETE. Wired the existing, unchanged report.render_entry_ticket() into the per-cycle operational output of scripts/run_post_asian_pilot.py (--once/--status/--watch): a READY proposal now gets an additive `entry_ticket` JSON field / "ENTRY TICKET" human-readable section, sourced verbatim from the same decision/proposal/ledger already produced by run_pilot_cycle() (pipeline.py untouched). Non-READY states get no ticket (entry_ticket=null, status=NOT_APPLICABLE); a render failure degrades to entry_ticket=null/status=RENDER_ERROR with a safe error code without changing the underlying decision/proposal/ledger claim. The canonical AG_FX_DAILY_REPORT_V1 schema is explicitly untouched (verified by test). 14 new focused tests (JSON, human-output, render-error, both cycles, both symbols, execution firewall, daily-schema compatibility); affected suite 92 passed/0 failed. No strategy/session/risk/quota/proposal-generation/execution-authority change. See docs/status/AG_TRADE_ASSISTANT_V1_0_3_FX_COMPLETE_ENTRY_TICKET_WIRING_STATUS.md.
AG_BYBIT_BTC_MARKET_DATA_AND_DAILY_DECISION_V1 (2026-09-05)  OWNER_APPROVAL_REQUIRED. Stopped at the milestone's own governance gate before any implementation: searched the manifest and every V1.0.3 status document and found only forward-references ("next milestone: AG_BYBIT_BTC_MARKET_DATA_V1") to this work, never an actual owner sign-off on the read-only Bybit scope exception the V1.0.3 scope freeze requires -- consistent with the earlier release-qualification-blockers finding (QUALIFICATION_REMEDIATION_REQUIRES_OWNER_AUTHORIZATION). No branch/worktree created, no adapter/registry/test code written, FX baseline (3b2eeed) and all protected FX surfaces untouched (confirmed by git status). Also confirmed, read-only: ST_LIQUIDITY_SWEEP_RETEST_V1 is documented in strategies/STRATEGY_LEDGER.md but has no real entry in strategies/registry.yaml (comment-only mention) -- a real inconsistency, not fixed. BTC evidence remains 0/30. See docs/status/AG_BYBIT_BTC_MARKET_DATA_AND_DAILY_DECISION_V1_STATUS.md.
AG_BTC_DAILY_OBSERVATION_TIME_CONTRACT_V1 (2026-09-05)  BTC_OBSERVATION_TIME_CONTRACT_FROZEN. Owner approved the read-only Bybit qualification exception (explicit direct instruction, this session); work proceeds on isolated branch/worktree btc/bybit-qualification-v3 (source_HEAD 759e2cb), never touching the active FX workspace. Froze docs/contracts/AG_BTC_DAILY_OBSERVATION_CONTRACT_V1.md: UTC calendar day, half-open [00:00:00Z, next-day 00:00:00Z), daily report target 00:05-00:15 UTC next day (06:35-06:45 MMT), late-data/correction policy (fail-closed DATA_ERROR at cutoff, additive-correction-only, no overwrite, no automatic retroactive VALID_DAY counting). Verified against strategies/ST_LIQUIDITY_SWEEP_RETEST_V1.yaml's own CRYPTO_PERP profile (PREVIOUS_DAY reference already documented as "strict UTC midnight-to-midnight"; execution_windows 13:30-16:00 UTC) -- no strategy timing conflict, 8+ hour margin before the report target. FX timing/protected surfaces confirmed unchanged. BTC evidence remains 0/30, campaign not started. See docs/status/AG_BTC_DAILY_OBSERVATION_TIME_CONTRACT_V1_STATUS.md and docs/contracts/AG_BTC_DAILY_OBSERVATION_CONTRACT_V1.md.
AG_V1_0_3_BYBIT_QUALIFICATION_EXCEPTION_AND_BTC_DAILY_DECISION_V3 -- GOVERNANCE (2026-09-05)  Owner explicitly approved V1_0_3_BYBIT_QUALIFICATION_EXCEPTION=APPROVED_READ_ONLY_ONLY (direct instruction, this session, exact scope list recorded in config/releases/AG_TRADE_ASSISTANT_V1_0_3.yaml's new qualification_exception block). Reconciled the known ST_LIQUIDITY_SWEEP_RETEST_V1 v2.0.0 registration inconsistency: added its entry to strategies/registry.yaml using the existing schema exactly (registered/research=true, demo_authorized/live_authorized=false, no unsupported fields) -- registration only, no authority change (STRATEGY_LEDGER.md already documented ACTIVE_INCUBATION/RESEARCH_ONLY since 2026-08-30). Updated the manifest's btc_market_data_authority/release_qualification_gates.btc fields to reflect the now-implemented adapter (see IMPLEMENTATION entry below) without touching unrelated FX gates or the scope_freeze block. 6 focused tests (registration/ledger identity, no-unsupported-fields, no-execution-authority) pass. FX protected surfaces confirmed unchanged. Work isolated on branch/worktree btc/bybit-qualification-v3. See docs/status/AG_V1_0_3_BYBIT_QUALIFICATION_EXCEPTION_AND_BTC_DAILY_DECISION_V3_STATUS.md.
AG_V1_0_3_BYBIT_QUALIFICATION_EXCEPTION_AND_BTC_DAILY_DECISION_V3 -- IMPLEMENTATION + PROVENANCE (2026-09-05)  BTC_IMPLEMENTED_PRODUCTION_VALIDATION_BLOCKED. Implemented BybitLinearPerpFeed (src/execution_runtime/bybit_linear_perp_feed.py) against Bybit's official V5 API (verified via WebFetch, not memory): category=linear BTCUSDT, public/unauthenticated only, handles Bybit's descending kline order and retCode envelope, mirrors the existing Binance adapter's fail-closed validation contract exactly. Added additive exchange_id/symbol_meta parameters to btc_sweep_research.pipeline.run_research_cycle (72 pre-existing BTC tests unaffected) and a new btc_sweep_research.daily_report module (AG_BTC_DAILY_REPORT_V1: READY/WATCH/NO_TRADE/DATA_ERROR, reusing post_asian_pilot.report_archive unchanged for immutable/idempotent/correction archiving). 33 new focused tests; combined BTC suite 111 passed/1 pre-existing skip/0 failed. Freshly re-tested Bybit connectivity from this environment post-implementation: still HTTP 403 (CloudFront country-block, unchanged from 2026-09-03) -- BTC_PRODUCTION_VALIDATION=BLOCKED_ENVIRONMENT, no circumvention attempted. Code ready (BTC_DAILY_DECISION_CODE_READY=YES) but not operational; observation NOT started, BTC evidence remains 0/30. FX protected surfaces confirmed unchanged at every stage. Three commits on isolated branch btc/bybit-qualification-v3 (governance 705a790, implementation 0c5cda1, provenance freeze this commit), none pushed. Next: VALIDATE_BYBIT_BTC_PATH_IN_PERMITTED_ENVIRONMENT. See docs/status/AG_V1_0_3_BYBIT_QUALIFICATION_EXCEPTION_AND_BTC_DAILY_DECISION_V3_STATUS.md.
AG_V1_0_3_BTC_DAILY_OPERATIONALIZATION_V1 (2026-09-05)  BTC_PRODUCTION_DATA_PATH_PASS_SCHEDULER_READY. Merged the frozen BTC qualification lineage into main without changing the seven protected FX behavioral paths. Bybit production public endpoints recovered from the earlier environment-specific HTTP 403 and returned HTTP 200/retCode 0. Added strict scheduler-ready CLI scripts/run_btc_daily_report.py, complete closed-candle audit (24 prior-day H1 + 288 observation-day M5), observation-date/future-candle guards, clean machine JSON, immutable archive, and human READY proposal ticket explicitly labeled NOT A BROKER TICKET. Live diagnostic against observation date 2026-09-04 returned WATCH/NO_QUALIFIED_SWEEP_YET with complete data-quality PASS; deliberately outside the report window, unarchived, disposable state, and non-counting. Local Task Scheduler installer added for 06:37 MMT. Crypto execution remains unimplemented/disabled; campaign remains not started at 0/30 pending separate owner authorization. See docs/status/AG_V1_0_3_BTC_DAILY_OPERATIONALIZATION_V1_STATUS.md.
AG_UNIFIED_VANTAGE_MARKETS_DEMO_MT5_ACCOUNT_MIGRATION_V1 (2026-09-07)  BROKER_CONFIG_UNIFIED_EXECUTION_UNCHANGED. The connected MT5 terminal was already Vantage Markets Demo (server VantageMarkets-Demo); this milestone made that identity explicit, config-driven, and verified instead of implicit. Added src/mt5/config.py (env-only broker/account identity: MT5_BROKER/MT5_ENVIRONMENT/MT5_LOGIN/MT5_PASSWORD/MT5_SERVER/MT5_TERMINAL_PATH, fail-closed on any missing/invalid required variable) and src/mt5/account_guard.py (verify_configured_account(): blocks with a reason_code on login/server/demo-vs-live mismatch), wired into execution/mt5_gateway.py::_account_authorized_for_send() ahead of the existing is_demo/allow_live_trading gate -- a real, previously-absent "prevent accidental terminal-session leakage" check. Renamed src/.env's Demo-section keys off invalid space-containing names ("MT5 Login=" etc., unparseable by any env loader) to MT5_LOGIN/PASSWORD/SERVER, with explicit user confirmation before editing (values never read back into any output); renamed a colliding, empty, previously-unused legacy MT5_LOGIN/PASSWORD/SERVER block to MT5_LEGACY_METAAPI_* to remove a last-wins override hazard. The Live section (VANTAGE-LIVE*) was left untouched. Captured real, read-only Vantage Demo symbol_info() for EURUSD/GBPUSD/BTCUSD/ETHUSD -- all trade_mode=FULL on the single Demo login (VANTAGE_UNIFIED_FX_CRYPTO_ACCOUNT_SUPPORTED); added config/mt5.yaml's symbol_map + src/mt5/broker_symbol_resolver.py (canonical->broker symbol, fails closed on an unmapped pair) as additive, currently-unused-by-execution infrastructure (crypto execution remains NOT_IMPLEMENTED). execution/risk.py sizing and mt5_gateway.py's existing ORDER_FILLING_IOC were both verified compatible against the real captured Vantage crypto metadata (stops_level=freeze_level=0, filling_mode=IOC-only for all four symbols) -- no change needed to either. BTC market-data authority was explicitly NOT migrated off Bybit: a preliminary 30-bar Vantage BTCUSD H1 read-only equivalence check (continuous, no gaps across a weekend) is recorded as evidence only in artifacts/readiness/AG_VANTAGE_UNIFIED_BROKER_MIGRATION_V1_*.json, not treated as sufficient to reverse the existing dated 2026-09-03 owner freeze of Bybit as BTC market-data authority -- that remains a separate, explicitly-scoped owner decision. No strategy file, strategy version, EGSVF gate, or execution authority changed; FX shadow/BTC research-only postures unchanged; mt5/connection.py's widely-used bare connect() was deliberately left untouched (used by ~25 read-only callers) rather than broadly redesigned. 30 new focused tests plus the full FX/execution regression subset (244 passed/0 failed) after the mt5_gateway.py change; full suite not run (targeted broker/account-config change). No broker order sent. See artifacts/readiness/AG_VANTAGE_UNIFIED_BROKER_MIGRATION_V1_5b0d246cfa7d_20260907T071622.280811+0000.json.
AG_CURRENT_ROADMAP_PHASE_0_BASELINE_RECONCILIATION_V1 (2026-09-08)  STATUS_CORRECTED_NO_AUTHORITY_CHANGE. Corrects a stale claim below (Telegram/API section, "Authority Reconciliation matrix" and "not part of the current operational codebase"): as of this HEAD, `src/authorization/{store,models,config,integrity,strategy_authority,proposal_source,telegram_gateway,mt5_execution_handler}.py`, `src/notifications/{telegram_client,trade_ticket_formatter}.py`, and a new `src/api/{app,execution_service,schemas}.py` (FastAPI) ARE present and committed on `main` -- not isolated to `.claude/worktrees/telegram-execution-gateway-v1` as previously documented, and not "PAUSED." Verified read-only, live, this session: `python scripts/run_api.py` starts a real local FastAPI process; `GET /api/health` and `GET /api/broker/status` both return real sanitized Vantage Demo data (connected=true, environment=DEMO, server=VantageMarkets-Demo). None of this grants new authority: no strategy is `demo_authorized` that wasn't before, no UI/API path can submit a broker order (grep-verified: no `order_send`/`execution.executor` reference outside `execution/`, `mt5_execution_handler.py`'s single sanctioned call into `execution.executor.execute()`), the Telegram bot process itself is not running, and `authorize-demo` was never invoked outside mocked tests. Correct current characterization: IMPLEMENTED_AND_TESTED (112 focused backend tests passing across `test_api.py`/`test_authorization_core.py`/`test_telegram_client.py`/`test_telegram_gateway.py`/`test_mt5_execution_handler.py`/`test_runtime_state_store.py`), NOT OPERATIONALLY WIRED (no persistent proposal registry -- `InMemoryProposalRegistry` only; no live Telegram bot; no frontend `authorize-demo` UI). See docs/plans/AG_CURRENT_ROADMAP_IMPLEMENTATION_ACTION_PLAN_V1.md Phase 0.
AG_STAGE1_EXACTLY_ONCE_FX_TICKET_FOUNDATION_V1 (2026-09-08)  WP1_WP3_WP6_CORE_IMPLEMENTED_NOT_INTEGRATED. New standalone package `src/ticket_delivery/` (identity.py/archive.py/models.py/delivery_store.py): deterministic logical ticket identity (`strategy_id|strategy_version|symbol|cycle|trading_date`, extending the existing `post_asian_pilot` setup_id shape by one field rather than competing with it), per-cycle durable archive for all five cycle states (READY/WATCH/NO_TRADE/DATA_ERROR/BLOCKED, reusing `post_asian_pilot.report_archive.write_report()` unchanged for its existing idempotent/append-only-correction/atomic-write guarantees), and a durable delivery journal with atomic O_EXCL claim (reusing `authorization/store.py`'s proven claim pattern) implementing NOT_APPLICABLE/READY_TO_DELIVER/DELIVERY_CLAIMED/DELIVERED/DELIVERY_FAILED_RETRYABLE/DELIVERY_FAILED_TERMINAL/DELIVERY_AMBIGUOUS states -- ambiguous outcomes are never auto-resent, only resolved via an explicit `resolve_ambiguous_outcome()` reconciliation call. 31 new focused tests (identity/archive: 14, concurrency/restart: 13 incl. 10-way concurrent claim and 5x-repeated flake check, static execution-boundary guard: 4), all passing; affected suite 149 passed/0 failed. NOT integrated into the live FX cycle/report orchestration yet -- no scheduler/CLI/report path calls this package. WP2 (canonical renderer), WP4 (scheduler recovery), WP5 (Telegram transport port), WP7 (operational proof with a real send) not started. No strategy/execution/authorization file modified; zero broker order-submission calls (statically verified). See docs/status/AG_STAGE1_EXACTLY_ONCE_FX_TICKET_FOUNDATION_V1_STATUS.md and docs/plans/AG_STAGE1_EXACTLY_ONCE_FX_TICKET_DELIVERY_V1.md's updated checklist.
AG_STAGE1_WP2_WP5_V1 (2026-09-08)  WP2_WP5_IMPLEMENTED_NOT_INTEGRATED. Continues the ticket_delivery foundation above (HEAD fecc32b, same package). Added `renderer.py` (WP2): wraps the existing `post_asian_pilot.report.render_entry_ticket()`-shaped dict verbatim (14 mandatory dotted-path fields checked, none recomputed), renders only READY decisions, fails closed with the exact missing field paths on any gap, labels every payload `INFORMATIONAL PROPOSAL -- NOT A BROKER ORDER`, deterministic SHA-256 payload hash. Added `telegram_adapter.py` (WP5): reuses `notifications.telegram_client.TelegramClient.send_message()` only (no polling/callback/keyboard methods), explicitly excludes `notifications.trade_ticket_formatter` and `authorization.telegram_gateway` (both now in the AST execution-boundary scan's forbidden-import list); `TelegramDestinationConfig` has no default token/chat-id and requires an explicit authorized-destination allow-list; bot token is redacted from every piece of persisted failure evidence (proven by reading the actual on-disk journal file, not just the in-memory object); outcomes classified to DELIVERED/DELIVERY_FAILED_RETRYABLE(429)/DELIVERY_FAILED_TERMINAL(other ok=false)/DELIVERY_AMBIGUOUS(timeout/connection-failure/malformed-response -- all three treated as unprovable, never assumed unsent), with DELIVERY_AMBIGUOUS keeping the foundation's existing never-auto-reclaimed guarantee end-to-end. 45 new focused tests (renderer 25, telegram adapter 17, execution-boundary +1 forbidden-import addition read as 4 total), all passing; combined affected suite (new package + existing Telegram client/gateway/authorization-core tests) 164 passed/0 failed. Not wired into the live FX cycle/report/scheduler path -- WP4 (scheduler recovery) and WP7 (real Telegram send) remain out of scope, explicitly not attempted. No strategy/execution/authorization/scheduler file modified; zero broker order-submission calls (statically verified); zero real Telegram sends (every test uses an injected fake HTTP session). See docs/status/AG_STAGE1_EXACTLY_ONCE_FX_TICKET_FOUNDATION_V1_STATUS.md's addendum section.
AG_STAGE1_WP4_FX_DELIVERY_INTEGRATION_V1 (2026-09-08)  WP4_1_TO_4_3_COMPLETE_WP4_4_AND_WP6_RETRY_MECHANISM_COMPLETE_OPERATIONALLY_UNSIGNED. Continues the ticket_delivery package (HEAD 05ddd00). Gate 1: read-only scheduler inspection confirmed both installed tasks (scripts/scheduled/run_asian_london_once.bat, run_london_newyork_once.bat) invoke `python scripts/run_post_asian_pilot.py --once --json` (the second with --pilot-config for LONDON_NEWYORK) -> post_asian_pilot.pipeline.run_pilot_cycle() -> PilotCycleResult; neither task modified; live Task Scheduler state NOT_EVALUATED (code-level verification substituted, per this task's own allowance). Added `fx_cycle_integration.py` (WP4.1/4.2): `process_pair_result()` consumes one already-computed PairResult, maps decision.status/portfolio_state to the 5-state archive vocabulary via an exhaustive fail-closed mapping (a READY decision that never became actionable correctly archives as BLOCKED, not READY), archives unconditionally before any render/register/claim/transport call (proven: simulated archive failure -> zero further calls), records NOT_APPLICABLE with zero Telegram calls for all 4 non-READY states, and for READY renders/registers/delivers via caller-injected closures (config absence fails closed AFTER the archive already happened). WP4.3 overlap protection proven by composition of already-atomic primitives, not a new lock: 10 concurrent identical invocations -> exactly 1 DELIVERED + 1 real transport call; independent symbols deliver independently; a simulated restart (fresh store instance, same state_dir) resumes safely with the same logical_ticket_id and archive_path. Added `policy.py` (WP4.4 catch-up + WP6 bounded retry): resource-first search of docs/plans/docs/contracts/config/governance found no signed FX ticket-delivery catch-up duration or retry bound (only an unrelated, still-unauthorized BTC-specific proposal) -- both CatchUpPolicy and RetryPolicy implemented as mechanism-complete, fail-closed interfaces (zero-argument construction = unconfigured = every evaluation refused; explicit injected values exercise full deterministic logic incl. exponential backoff capped at max_delay, no wall-clock/sleep in any test). Added `scripts/run_ticket_delivery_status.py` (WP4.5): read-only diagnostic CLI over the delivery journal, no execution/approval/broker flag, documents required env var names without reading/printing values. 27 new focused tests (fx_cycle_integration 11, fx_cycle_overlap 3, policy 13), all passing; combined affected suite 271 passed/0 failed. Correction to prior documentation: archive-before-send is now proven at the orchestration layer (previously only the primitive was tested) but nothing in run_post_asian_pilot.py yet calls this new orchestration -- a real scheduled run still only produces the existing decision/proposal journals until a follow-up task wires the call site. No strategy/execution/authorization/scheduler-task file modified; zero broker order-submission calls (statically verified, boundary scan extended to the 2 new modules); zero real Telegram sends. Stage 1 remains NOT complete: WP7 (operational proof) not started; WP4.4/WP6-retry remain operationally unsigned. See docs/status/AG_STAGE1_EXACTLY_ONCE_FX_TICKET_FOUNDATION_V1_STATUS.md's second addendum.
AG_CURRENT_ROADMAP_PHASE_1_STAGE_0_SAFETY_V1 (2026-09-08)  STAGE_0_PARTIAL_TWO_DEFECTS_FIXED_ONE_CONFIRMED_CLEAN. Verified against `docs/plans/AG_CURRENT_ROADMAP_IMPLEMENTATION_ACTION_PLAN_V1.md` Phase 1: (1) FIXED a real drawdown-baseline defect in `src/performance/calculator.py::compute_trade_metrics()` -- `running_peak` was seeded at `float("-inf")` so a lone first resolved loss always reported `max_drawdown_R=0.0` instead of the loss itself (reproduced with a minimal repro before fixing: single -1R trade -> 0.0R drawdown); fixed by seeding the peak at the pre-trade zero baseline instead. 2 new regression tests added (`test_drawdown_baseline_starts_at_zero_not_at_first_sample`, `test_drawdown_baseline_zero_does_not_affect_a_winning_first_trade`); the pre-existing 13-loss historical regression (`test_fx_adapter_reproduces_the_13_record_negative_baseline`, reading `artifacts/outcome_resolution/records`) re-ran unaffected (does not assert on drawdown) and still passes -- historical evidence untouched, not recalculated, not relabeled. (2) VERIFIED missing-`resolved_at` ordering (`performance/calculator.py::_ordered()`) already correctly sorts timestamped records first (chronologically) and missing-timestamp records last (by immutable `source_record_id`, never dropped) -- code was already correct; only its own docstring incorrectly described the opposite behavior, corrected in place; added `test_missing_timestamps_sort_last_by_source_record_id` to lock the real behavior in. (3) VERIFIED broker-reconciliation fail-closed behavior (`execution/lifecycle.py::reconcile_open_positions`/`reconcile_closed_position`) already distinguishes a genuine empty broker result (NOT_FOUND-equivalent, correctly clears stale state) from a query exception (`POSITION_QUERY_FAILED`/`DEALS_UNAVAILABLE`, correctly leaves state untouched and fabricates no realized R) -- this existing fail-closed branch was previously untested; added 2 new focused tests (`test_broker_query_failure_fails_closed_and_never_removes_open_state`, `test_broker_deals_query_failure_on_close_reports_distinct_status_not_not_found`) proving it, and confirming no code path treats an ambiguous/failed broker query as grounds for a replacement submission (reconciliation is read-only relative to `execution.executor.execute()`; nothing in the reconcile path calls it). 6 new tests total, all passing; affected suite (`test_performance_calculator.py` + `test_execution_lifecycle.py` + `test_execution_coordinator.py` + `test_execution_runtime_readiness.py` + `test_performance_large_smc_adapter.py`) 65 passed/0 failed. No strategy/risk/session/execution-authority semantics changed. Stage 1 (exactly-once FX ticket delivery, Phase 2 of the roadmap) not started this pass -- see the roadmap doc for its own separate scope.
AG_STAGE1_SCHEDULED_CALLSITE_INTEGRATION_V1 (2026-09-08)  SCHEDULED_ARCHIVE_ONLY_INTEGRATION_COMPLETE_ACTIVATION_UNSIGNED. Final pre-operational Stage 1 slice: continues the ticket_delivery package (HEAD at the WP4 addendum-2 commit above). Gate 1 re-inspection (live `Get-ScheduledTask`) reconfirmed `AG_FX_ASIAN_LONDON_SHADOW`/`AG_FX_LONDON_NEWYORK_SHADOW` are `State=Ready`, 15-minute triggers, `MultipleInstances: IgnoreNew`, invoking `python scripts/run_post_asian_pilot.py --once --json [--pilot-config ...]` -- the exact real entry point. Added `src/ticket_delivery/scheduler_integration.py` (the call site: `load_integration_config()` reads `config/ticket_delivery.yaml`, fails closed to `DISABLED` on any missing/malformed/unrecognized value; `process_cycle_result()` derives the cycle label from the existing `--pilot-config` argument and loops the WP4 orchestration over every pair; both `ARCHIVE_ONLY` and still-inert `MESSAGE_DELIVERY` pass `deliver=None` unconditionally -- a structural, statically-verified zero-network guarantee, not merely a config gate). Added `config/ticket_delivery.yaml` shipping `mode: DISABLED` -- the real, committed repository default; archive-only activation remains a distinct, one-line, still-pending operator decision. Modified `scripts/run_post_asian_pilot.py::_run_once()` to additively call the new `_process_ticket_delivery()` after the existing frozen `cycle_to_dict()`/`human_readable_report()` output (that schema untouched); an archive failure now produces a nonzero scheduler exit code, any other unexpected error degrades to a caught no-op logged to stderr, never crashing the already-printed strategy report. 23 new tests (`test_ticket_delivery_scheduler_integration.py` 16, `test_run_post_asian_pilot_ticket_delivery_wiring.py` 7 -- the latter loading the real script module via `importlib.util`, no live MT5 needed) prove, through the actual CLI function: disabled-by-default is silent; `ARCHIVE_ONLY` archives every cycle state with zero network calls; repeated and two-simultaneous invocations converge on exactly one archive/logical-ticket (verified by reading the persisted store directly, not racing stdout); a simulated archive failure surfaces correctly without crashing; `MESSAGE_DELIVERY` config makes zero network calls; a READY pair without ledger context reports `RENDER_BLOCKED`, never fabricated. Found and fixed two real bugs surfaced by these tests: a Python default-argument binding bug in `load_integration_config()` that silently defeated test/config overrides (fixed by reading the module constant dynamically inside the function body instead of binding it at definition time), and a thread-unsafe `contextlib.redirect_stdout` usage in the original concurrency test (a test-harness race, not a production defect; fixed by asserting against the persisted store directly). Combined affected suite (all `ticket_delivery` test files + `test_telegram_client.py`/`test_telegram_gateway.py`/`test_authorization_core.py`/`test_post_asian_pilot.py`) 294 passed/0 failed; `git diff --check` clean. Produced `docs/status/AG_STAGE1_CATCHUP_AND_RETRY_POLICY_DECISION_PACKET_V1.md` proposing (not activating) `FX_MAX_CATCH_UP_AGE`/`DELIVERY_MAX_ATTEMPTS`/`DELIVERY_RETRY_BASE_DELAY`/`DELIVERY_RETRY_MAX_DELAY` values for owner sign-off, each with a recommended default, conservative alternative, unsigned fail-closed behavior, and confirmation of no retroactive effect on historical identity; `policy.py` itself unmodified, still zero production defaults. No strategy YAML, installed scheduler task, or execution/broker configuration file modified; zero real Telegram sends; zero broker calls. Corrected `docs/plans/AG_CURRENT_ROADMAP_IMPLEMENTATION_ACTION_PLAN_V1.md`'s stale top-level "PLANNED — NOT IMPLEMENTED" status to a phase-by-phase table (Phases 0/1 DONE, Phase 2 implemented/archive-only-proven-but-not-activated, Phases 3-8 not started). One local checkpoint commit made (`feat(ticket_delivery): wire archive-only FX scheduler integration`), not pushed. See `docs/status/AG_STAGE1_EXACTLY_ONCE_FX_TICKET_FOUNDATION_V1_STATUS.md`'s Addendum 3 and `docs/plans/AG_STAGE1_EXACTLY_ONCE_FX_TICKET_DELIVERY_V1.md`'s updated status/checklist. A follow-up same-day fix (HEAD `d7ab190`) corrected `_process_ticket_delivery()` to surface an unexpected integration exception as a nonzero scheduler exit (previously silently returned exit 0), proven by a new test calling the real `_run_once()` and asserting `SystemExit(1)`.
AG_STAGE1_ARCHIVE_ONLY_ACTIVATION_V1 (2026-09-08)  ARCHIVE_ONLY_ACTIVATED_AND_VERIFIED. Continues from HEAD `d7ab190` under explicit owner authorization: signed catch-up/retry policy values (`fx_max_catch_up_age_minutes: 60`, `delivery_max_attempts: 3`, `delivery_retry_base_delay_seconds: 30`, `delivery_retry_max_delay_seconds: 300`) and explicit permission to flip `config/ticket_delivery.yaml`'s `mode` from `DISABLED` to `ARCHIVE_ONLY`. Gate 2: `scheduler_integration.py` gained `TicketDeliveryConfigError` and a strict `_parse_policy()` validator (missing block/field, non-numeric, bool-as-numeric, zero/negative, `base>max`, unknown extra field all raise, never silently default) applied only when `mode != DISABLED` -- `DISABLED` remains the unconditional one-line rollback, never reading or requiring the policy block; the pre-existing fail-closed-to-DISABLED behavior for a missing file/malformed YAML/unrecognized mode is deliberately preserved, documented as an explicit interpretation choice. `run_post_asian_pilot.py` gained a specific `TicketDeliveryConfigError` handler producing a normalized nonzero exit, distinct from the generic exception handler. Catch-up integration (previously confirmed unwired via `grep`): `fx_cycle_integration.process_pair_result()` gained an optional `catch_up_policy` parameter, evaluated only for READY pairs against `pair.decision.ready_at` (the real, restart-frozen strategy-signal timestamp, confirmed by reading `post_asian_pilot`'s cache-reconstruction code -- not an invented "expected tick" time) and an injectable `now`; a rejected catch-up archives the decision but creates no ticket; `None` (default) skips the gate, so every pre-existing caller/test is unaffected. Retry policy wired (constructed from signed config) but not yet exercised by any live path -- `MESSAGE_DELIVERY` remains inert. Gate 3: `config/ticket_delivery.yaml` now ships `mode: ARCHIVE_ONLY` with the signed `policy:` block and status-history header comments distinguishing integration-introduced/archive-only-activated/message-delivery-not-authorized. 33 new tests across `test_ticket_delivery_scheduler_integration.py` (+19, now 35), `test_ticket_delivery_fx_cycle_integration.py` (+9), `test_ticket_delivery_policy.py` (+8, incl. a signed-contract-exact-values section), `test_run_post_asian_pilot_ticket_delivery_wiring.py` (updated for the new real shipped ARCHIVE_ONLY default); combined affected suite 334 passed/0 failed; `git diff --check` clean (one pre-existing, non-reproducible concurrency-test flake observed once under full-suite load, confirmed unrelated to this change and non-reproducing across 4 subsequent runs). Read-only re-inspection of both live scheduled tasks (`Get-ScheduledTask`) confirmed `State=Ready`, unmodified. **Real operational evidence obtained**: the actual OS-scheduled trigger fired unprompted at 2026-09-08T08:30:00Z (`LastTaskResult=0`) and produced a genuine, naturally-occurring GBPUSD READY signal (`ready_at` 07:15:00Z, real sweep/entry/stop/targets) that the newly-wired catch-up gate correctly rejected for ticket registration (75 minutes stale, past the signed 60-minute bound, `CATCH_UP_REJECTED`/`OUTSIDE_CATCH_UP_WINDOW`) while still archiving the decision -- confirmed directly from the real `journal/ticket_delivery/` archive/delivery-journal files on disk (no `READY_TO_DELIVER` record for that ticket exists) and the real `%TEMP%\ag_shadow_*.log` files the scheduled tasks append to. Zero network/Telegram/broker calls at any point (`deliver=None` unconditionally, execution-boundary AST scan re-passed). No strategy YAML, scheduler task, or execution/broker file modified; no position modified; no push. One local checkpoint commit authorized and made, not pushed. See `docs/status/AG_STAGE1_EXACTLY_ONCE_FX_TICKET_FOUNDATION_V1_STATUS.md`'s Addendum 5 and `docs/status/AG_STAGE1_CATCHUP_AND_RETRY_POLICY_DECISION_PACKET_V1.md`'s approval addendum for full detail.
AG_STAGE1_GOVERNANCE_RECONCILIATION_AND_WP7_PREFLIGHT_V1 (2026-09-08)  M0_GOVERNANCE_RECONCILED / WP7_PREFLIGHT_COMPLETE / MESSAGE_DELIVERY_NOT_ACTIVATED. Continues from HEAD `6ed1cfb` (verified synchronized with `origin/main`, working tree clean). Does NOT activate `MESSAGE_DELIVERY`, send any Telegram message, or begin Stage 2/Demo. **M0A governance anomaly investigated**: the prior task's report of commits/pushes reaching `origin/main` without explicit `git commit`/`git push` was traced to environment-level causes, not this repository -- no repo-local git hook or config was responsible (`.git/hooks/` holds only inert `.sample` files; no `postCommitCommand`/auto-sync in any git config tier). Root cause identified in the VS Code user profile: `git.enableSmartCommit: true` (stages+commits everything when "Commit" runs with nothing staged) plus a global `chat.tools.terminal.autoApprove` setting that pre-approves `git push` for any chat/agent tool, combined with several OTHER agent-capable extensions installed in this same workspace with independent terminal/git access (notably Tongyi Lingma, which explicitly allowlists `git` for its own autonomous agent mode) -- any of which could commit/push using the same shared local git identity, indistinguishable by author from this session. Corroborating evidence this session was never the source: this session's own `git push` attempt was independently blocked by Claude Code's own permission classifier. Neither root cause (a global VS Code setting, other installed extensions) can be safely changed from within this repository, so a repository-local mitigation was implemented instead: `scripts/git-hooks/pre-push` blocks every push through this clone unless `AG_ALLOW_PUSH=1` is explicitly set, wired via a repo-local `git config core.hooksPath scripts/git-hooks` (no global setting touched, no extension disabled) -- tested: an unauthorized `git push` was blocked (exit 1, nothing reached origin, confirmed by identical `HEAD`/`origin/main` before and after). **M0B roadmap reconciliation**: `docs/plans/AG_CURRENT_ROADMAP_IMPLEMENTATION_ACTION_PLAN_V1.md`'s "Current baseline" section still described Stage 0 items and FX scheduler recovery as open/unproven despite the phase table above it already saying DONE/ACTIVATED -- moved the stale bullets to a new "Historical baseline (superseded)" subsection (preserved verbatim, not deleted) and replaced "Current baseline" with present-state prose plus the requested exact `STAGE_N = ...` classification block, each line verified against real evidence (e.g. `STAGE_3A_CHART_ASSISTANCE = PARTIAL` confirmed via `grep` showing `NO_REGISTERED_STRATEGY_MATCH` exists only in docs, not code, while the underlying analysis-chain advisory skills do exist). **M0C runtime evidence retention**: defined a minimal retention architecture (mutable `journal/ticket_delivery/`, gitignored, unchanged → periodic immutable export under `artifacts/ticket_delivery_evidence_exports/<UTC-timestamp>/` with a SHA-256+size manifest, reusing this repo's existing `artifacts/` convention rather than a new subsystem) and implemented it: new `scripts/ticket_delivery_evidence.py` (`export()`/`verify_restore()`, read-only relative to the source journal, zero network calls, never persists a secret -- test-verified), 14 new tests (`tests/test_ticket_delivery_evidence_export.py`) covering fail-closed-on-missing/empty-source, mid-copy failure cleanup, immutability-on-timestamp-collision (clock frozen in test), and corruption/missing-file detection on restore. Ran ONE real export against the live journal (20 files, `application_release=AG_TRADE_ASSISTANT_V1_0_3`, `repository_head=6ed1cfb`, `ticket_delivery.mode=ARCHIVE_ONLY`) and one real restore-verification against it (`passed: true`, 0 mismatches) -- confirmed the source journal was unchanged by the export (byte-identical before/after). Off-machine/off-box backup destination explicitly deferred (owner infrastructure decision, out of "smallest safe capability" scope). **M1-preflight WP7 architecture review** (verified from code, documented in a new `docs/status/AG_STAGE1_WP7_MESSAGE_DELIVERY_PREFLIGHT_AND_AUTHORIZATION_PACKET_V1.md`, indexed in `docs/README.md`): confirmed `RetryPolicy` is constructed from signed config but never consumed by any runtime path -- the one open architecture question WP7 must resolve is where retries will actually be scheduled, since the only existing re-trigger mechanism (the next ~15-minute scheduler tick) does not match the signed 30s/60s cadence; the packet lays out both candidate designs (in-process wait-and-retry vs. coarser tick-driven retry) without choosing between them. Confirmed the existing `TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID` env-var convention (already used by the separate, forbidden-import `authorization.config.TelegramGatewayConfig`) should be reused for WP7's destination, and that `TicketDeliveryDestinationConfig` has no `from_env()` yet. Freshness-gate ordering (READY → catch-up check → registration → delivery) and the zero-broker-execution boundary were re-verified unchanged. **Caution recorded**: an overly broad `grep` during the env-var-naming check echoed the real, live Telegram bot token/chat ID from `src/.env` into this session's own tool output -- confirmed `src/.env` remains `.gitignore`d and untracked (no leak into version control), and the actual values are not reproduced in any file this task touched; noted as a reminder to scope future greps away from `.env` files. Tests this task: 14 new (`test_ticket_delivery_evidence_export.py`) + re-verified 4 (`test_ticket_delivery_execution_boundary.py`), all passing; `git diff --check` clean; no production `src/ticket_delivery/` behavior changed (additive tooling + documentation only). No strategy/execution/broker file touched; zero real or synthetic Telegram sends; zero broker calls; `MESSAGE_DELIVERY` remains inert/unauthorized. Stage 1 explicitly NOT closed. See `docs/status/AG_STAGE1_EXACTLY_ONCE_FX_TICKET_FOUNDATION_V1_STATUS.md`'s Addendum 6 and `docs/status/AG_STAGE1_WP7_MESSAGE_DELIVERY_PREFLIGHT_AND_AUTHORIZATION_PACKET_V1.md` for full detail.
AG_STAGE1_WP7_READINESS_RECONCILIATION_V1 (2026-09-09)  WP7_RUNTIME_VERIFIED_READY_FOR_SEPARATE_OWNER_ACTIVATION_ARCHIVE_ONLY_UNCHANGED. Preflight/reconciliation pass only -- no activation. HEAD 934ce15 (== origin/main), working tree clean before and after, `git diff --check` clean. Corrects a stale claim in the preflight packet above and in `docs/plans/AG_STAGE1_EXACTLY_ONCE_FX_TICKET_DELIVERY_V1.md`'s top banner ("WP7 NOT STARTED"/"`RetryPolicy` NOT YET CONSUMED (dead config)"): both are superseded by WP7 message-delivery work landed after that reconciliation pass (commits through `d1b14e8`), which this task verified against the actual code rather than trusting the docs. Confirmed by direct code inspection: `deliver_informational_ticket_with_retry()` (`src/ticket_delivery/telegram_adapter.py`) implements Design A (in-process wait-and-retry, chosen and recorded per the preflight packet's own open question) with 30s/60s backoff matching the signed `delivery_max_attempts=3`/`base=30s`/`max=300s` policy exactly; a new append-only `AttemptJournal` (`attempt_journal.py`) records one entry per attempt; `scheduler_integration.py::_build_message_delivery_closure()` is called only from the `MODE_MESSAGE_DELIVERY` branch (`deliver=None` unconditionally on every other path, structural not merely config-gated). Confirmed `config/ticket_delivery.yaml`: `mode: ARCHIVE_ONLY` (unchanged), `telegram_destination.authorized_chat_ids: []` (empty, unchanged). Confirmed zero real or synthetic Telegram sends have ever occurred for Stage 1 ticket delivery (the live `journal/ticket_delivery/state/attempt_journal.jsonl` file does not exist at all; the live delivery-records journal holds only `NOT_APPLICABLE` states from real WATCH/NO_TRADE archiving) -- distinct and separate from the newer general Telegram backend service (`src/api/telegram_service.py`, commits `4a12d96`/`b03a7a3`/`934ce15`) used for trade-management alerts, which imports `authorization.config.TelegramGatewayConfig` directly and never imports `ticket_delivery`; no document reviewed conflates the two. Execution firewall re-verified: no import of any execution/broker/MT5/ExecutionApproval/authorize-demo/Telegram-callback symbol anywhere in `src/ticket_delivery/` or `scripts/run_post_asian_pilot.py` (grep-verified, matches the existing AST-based `test_ticket_delivery_execution_boundary.py`). Ran the full focused ticket-delivery suite (13 files, 219 tests): 218 passed, 1 failed on first run under combined load, passed 3/3 on isolated reruns -- confirmed pre-existing, load-dependent, not a regression from this pass. Investigated the flake's root cause without fixing it: `deliver_informational_ticket()`'s lost-claim-race branch (`telegram_adapter.py` ~line 129-130) mirrors an already-DELIVERED record's raw state back to every losing concurrent caller, so `fx_cycle_integration.PairOutcome.delivery_state` cannot distinguish "I delivered it" from "I observed it already delivered" under high contention; a `tests/test_ticket_delivery_wp7_scheduler_message_delivery.py` test separately and deliberately asserts the current mirrored-state behavior is correct for a *sequential* idempotent re-invocation, so a source fix was NOT made this pass (it would need to reconcile that test's locked-in semantics with the concurrency test's stricter one first, which is a design decision, not a "smallest correction") -- flagged for a future owner-scoped fix, not treated as a WP7 blocker since the underlying dedup/transport-call-count/execution-boundary guarantees all hold regardless (`session.send_count==1` never varies). No code changed this pass. Documentation only: added a dated correction to the plan doc's top banner (original text preserved verbatim below it), added a dated "Addendum (2026-09-09)" resolving the preflight packet's open retry-scheduling question, added this entry. Known gap, not remediated this pass: this rolling summary itself lags several commits unrelated to WP7 (`e5f9ed3` proposal-envelope M1A freeze, the Telegram backend service feature, two Demo-gateway/Stage-0 test-hardening fixes) -- out of this task's WP7-specific scope, flagged here rather than silently left undiscovered. See `docs/status/AG_STAGE1_WP7_READINESS_RECONCILIATION_V1_STATUS.md`.
AG_STAGE1_WP7_READINESS_RECONCILIATION_V1 -- FLAKE ROOT-CAUSE FIX (2026-09-09)  WP7_RUNTIME_VERIFIED_219_OF_219_TESTS_PASS_ARCHIVE_ONLY_UNCHANGED. Follow-up to the entry directly above, same task, per explicit owner direction to resolve the flake rather than leave it open. Root cause: `DeliveryOutcome.final_state`/`PairOutcome.delivery_state` had two conflated meanings -- "the durable ticket's current state" (what `tests/test_ticket_delivery_wp7_scheduler_message_delivery.py::test_second_identical_invocation_is_idempotent_zero_provider_calls` deliberately relies on for a sequential re-invocation) and "what this invocation itself did" (what the concurrency test needed) -- so under thread contention more than one of 10 concurrent callers could correctly report `"DELIVERED"`, and a test built on the second meaning failed intermittently. Fixed by freezing the semantics explicitly rather than picking a side that breaks the other test: `final_state`/`delivery_state` now unambiguously means "the durable ticket state, regardless of caller ownership" (unchanged from before, matches the sequential test as-is); a new field `delivery_performed_by_this_invocation: bool` was added to `DeliveryOutcome` (`src/ticket_delivery/telegram_adapter.py`, `True` only from the `mark_delivered()` branch) and threaded through `PairOutcome` (`src/ticket_delivery/fx_cycle_integration.py`) and the scheduler's per-pair output dict (`src/ticket_delivery/scheduler_integration.py`, additive key, does not change `mode`/`config/ticket_delivery.yaml`/any activation state). `tests/test_ticket_delivery_fx_cycle_overlap.py`'s concurrency test now asserts `delivery_performed_by_this_invocation` count instead of counting `delivery_state == "DELIVERED"` occurrences, and no longer asserts a specific `delivery_state` per losing caller (a loser can correctly observe either the terminal `"DELIVERED"` or the transient `"DELIVERY_CLAIMED"` depending on scheduling -- both correct; only the transport-call count (`session.send_count == 1`) and record count matter and are still asserted, deterministically). Ran the full 219-test focused ticket-delivery suite 3 consecutive times: 219 passed / 0 failed each time -- the flake is resolved, not hidden (the real invariant, exactly one real transport call, is still checked every run). No `mode`, destination allow-list, or execution-authority change; `config/ticket_delivery.yaml` untouched; zero real/synthetic Telegram sends; zero broker/MT5 calls; `git diff --check` clean. Updated `docs/status/AG_STAGE1_WP7_READINESS_RECONCILIATION_V1_STATUS.md` in place to record the fix (its dated content, not deleted, corrected to reflect final state since it documents this same still-open task rather than a separately closed historical milestone). See that document for full before/after test evidence.
```

## Capability & Roadmap Reconciliation (dated 2026-09-06)

This section is additive — it does not replace or rewrite the rolling summary above or
any dated evidence below. It exists to answer, from current evidence, seven standing
questions: what AG can do now; what is implemented but not integrated; what is
verified; what is actually enabled/authorized; what is research-only; the current
core-completion path; and where Telegram, MT5 Demo, BTC/Bybit, and Large-SMC sit
relative to that path. No strategy semantics, risk settings, execution authority,
broker routing, or release state were changed while writing this section.

**Core principle.** `IMPLEMENTED ≠ VERIFIED ≠ ENABLED ≠ AUTHORIZED`. Historical release
state (`docs/VERSION_HISTORY.md`) is distinct from current project state (this
document). Execution infrastructure (can a component send an order) is distinct from
strategy execution authority (is a specific strategy allowed to use it). A component
being able to place an MT5 order does not mean a strategy is authorized to use it.

**Authority sources used to build this section** (verified, not assumed):
`docs/VERSION_HISTORY.md` = historical application/version authority.
`PROJECT_STATUS.md` (this file, rolling summary above) = current operational
authority. `strategies/registry.yaml` + `strategies/ST_ASIAN_SWEEP_5R_V1.yaml` +
`strategies/STRATEGY_LEDGER.md` = strategy authorization authority. `AGENTS.md`'s
"Authority order" section = execution authority — confirmed the sole approved
execution funnel is `assistant.commands.execute_command(command, user_confirmed=True)`
(`AGENTS.md`, "Authority order" / PROJECT_STATUS.md "Execution authority restructure
(2026-08-28)" below).

### AUTHORITY_RECONCILIATION matrix

| Capability | Historical (VERSION_HISTORY, 2026-09-03) | Current (PROJECT_STATUS, 2026-09-05/06) | Registry authority | Implemented | Verified | Enabled | Notes |
|---|---|---|---|---|---|---|---|
| EURUSD/GBPUSD Asian→London proposals | IMPLEMENTED, PROPOSAL_ONLY | unchanged, PROPOSAL_ONLY, Series 002 in progress | `ST_ASIAN_SWEEP_5R_V1` demo_authorized=false | Yes | Runtime evidence exists | PROPOSAL_ONLY |  |
| EURUSD/GBPUSD London→New York proposals | IMPLEMENTED, unit-tested only, shadow pending | unchanged, PROPOSAL_ONLY, still no live/demo verification | same strategy, `LONDON_NEWYORK` pair | Yes | Unit-tested only | PROPOSAL_ONLY |  |
| `ST_ASIAN_SWEEP_5R_V1` | v1.1.1 ACTIVE, SOLE_DAY_TRADING_AUTHORITY (pilot-scoped) | unchanged | registered=true active=true research=true demo_authorized=false live_authorized=false | Yes (signal engine) | Live runtime evidence exists | PROPOSAL_ONLY only | `entry_order_type` resolved to MARKET (2026-08-31); `risk_per_trade_pct` still absent from the strategy YAML itself |
| MT5 Demo execution subsystem | IMPLEMENTED, disabled by default, every send requires a fresh explicit user command | unchanged | N/A — application infrastructure, not strategy-scoped | Yes (`execution/executor.py`, `execution/mt5_gateway.py`) | DEMO_VERIFIED 2026-08-28 (ticket 1879685149; a real MT5 Demo-account round trip, not real-money execution evidence) | Disabled by default; explicit-command-gated |  |
| FX proposal→MT5 integration | not separately called out | Generic `ASSISTANT_PROPOSAL` plumbing exists and was DEMO_VERIFIED 2026-08-28 (ticket 1880212783); see architecture note below | not strategy-scoped by itself | Yes, generically | DEMO_VERIFIED, but from the assistant's own analysis-derived `TradeProposal`, not from an `ST_ASIAN_SWEEP_5R_V1` pilot-cycle proposal | Requires fresh explicit command AND the specific strategy to be `demo_authorized` | `ST_ASIAN_SWEEP_5R_V1` is not `demo_authorized`, so its pilot proposals cannot use this path as of 2026-09-06 even though the generic plumbing works |
| MT5 live execution | IMPLEMENTED behind gates, not authorized as a live service | unchanged | N/A | Yes (behind gates) | Not exercised live | DISABLED (`config/trading.yaml` `account.allow_live_trading: false`) |  |
| BTC market-data runtime | IMPLEMENTED (Binance adapter), production blocked (HTTP 451/403) | Bybit adapter IMPLEMENTED and production market-data connectivity confirmed (HTTP 200/retCode 0, 2026-09-05) — data access only, not trade execution; supersedes 2026-09-03 blocked claim | `ST_LIQUIDITY_SWEEP_RETEST_V1` v2.0.0 registry entry, research=true | Yes | Production-data-verified 2026-09-05 | Read-only market data only |  |
| Bybit production market-data connectivity | BLOCKED (HTTP 403, CloudFront country-block, 2026-09-03) | RECOVERED — HTTP 200/retCode=0 confirmed 2026-09-05 (`config/releases/AG_TRADE_ASSISTANT_V1_0_3.yaml`, `qualification_exception`/`btc_market_data_authority` blocks) | N/A (infrastructure) | Yes | Production-data-verified 2026-09-05 — data access only, not trade execution | Read-only public endpoint only, no credentials |  |
| BTC sweep/retest proposals | IMPLEMENTED, unit-tested, RESEARCH_ONLY | unchanged, RESEARCH_ONLY, `execution_domain=CRYPTO_RESEARCH`/`execution_authority=DISABLED`, statically+behaviorally verified never to reach `execution.executor`/`mt5.management_gateway` | `ST_LIQUIDITY_SWEEP_RETEST_V1` registered=true active=false research=true demo_authorized=false live_authorized=false | Yes | Unit-tested + production-data-verified | RESEARCH_ONLY |  |
| BTC daily report | not present (predates 2026-09-05 milestone) | OPERATIONAL CLI READY (`scripts/run_btc_daily_report.py`), immutable archive, informational proposal ticket labeled NOT A BROKER TICKET | inherits `ST_LIQUIDITY_SWEEP_RETEST_V1`'s RESEARCH_ONLY authority | Yes | Diagnostic run against production data 2026-09-05, evaluated 2026-09-04 (WATCH, disposable, non-counting) | Scheduler-ready, not yet scheduled to run in-window |  |
| BTC scheduler | not present | Installed and enabled: "AG Profit Trading - BTC Daily Decision" (13:05 MMT/06:35 UTC), State=Ready, next run 2026-09-07T06:35Z | same | Yes | `Get-ScheduledTask`/`Get-ScheduledTaskInfo` confirmed installed this session | Installed and authorized (campaign authorized 2026-09-06T06:52:42Z); 0 valid observations archived yet |  |
| BTC execution | NOT IMPLEMENTED, DISABLED | unchanged | `execution_authority=DISABLED`, `crypto_execution_adapter: NOT_IMPLEMENTED` | No | N/A | DISABLED |  |
| Large-SMC research | IMPLEMENTED (research funnel + replay infra), RESEARCH_ONLY, C10 blocked | unchanged, v1.0.6 RESEARCH_DRAFT, C10 sole blocker | `ST_LARGE_SMC_V1` research=true, no demo/live | Yes (research engine) | Corrected replay baseline recorded | RESEARCH_ONLY; engine fails closed to BLOCKED |  |
| Large-SMC proposal authority | none | unchanged, none | `proposal_generation_authorized: false` | No | N/A | NONE |  |
| Telegram approval module | not covered by VERSION_HISTORY (VERSION_HISTORY never mentions Telegram) | Committed as a frozen baseline in an isolated worktree only (`.claude/worktrees/telegram-execution-gateway-v1`, branch `feature/telegram-demo-execution-gateway-v1`, commit `740512b` "AG_TELEGRAM_DEMO_EXECUTION_GATEWAY_V1_PHASE_D1_BROKER_UNREACHABLE_BASELINE", branched from `main` at `63938cc`); not merged into `main`, not pushed; `src/authorization/`, `src/notifications/` still do not exist on `main` | not registered as a strategy; not a strategy-authority concept | Phases A/B/C/D1 all present and committed on the feature branch (`authorization/{store,models,config,integrity,strategy_authority,proposal_source,telegram_gateway}.py`, `notifications/{telegram_client,trade_ticket_formatter}.py`, matching tests) | 117 focused tests passing (all HTTP mocked); not verified against `main` — none of it is part of the current operational codebase | PAUSED (owner directive) | See `docs/status/AG_TELEGRAM_DEMO_EXECUTION_GATEWAY_V1_PHASE_D1_FROZEN_STATUS.md` (on the feature branch) and Telegram section below |
| Telegram→real proposal integration | not covered | COMPLETE and committed, worktree-only (`proposal_source.py` reads real `post_asian_pilot` proposal journals read-only) — not merged, not part of current operational state | N/A | Complete, committed on feature branch | Verified (8 focused tests) | Not integrated into `main` | Do not treat as core-project evidence |
| Telegram→MT5 execution integration | not covered | Not present anywhere in the branch's file set (no code calls `execution.executor` or `assistant.commands.execute_command`) | N/A | No | N/A | Not integrated | |

### Corrected architecture description

Do **not** publish "FX Trade Proposal → Risk/Safety Gates → Execution System → MT5
Demo" as one seamless, strategy-authorized pipeline for `ST_ASIAN_SWEEP_5R_V1` — the
repository does not prove that exact integration exists for it (`demo_authorized:
false`). `SESSION_TRADE_V1` is separately `demo_authorized: true` for its
`ASIAN_LONDON` cycle, but it runs on a different engine in a different repository and
does not use this repository's FX proposal/execution pipeline — its authorization does
not extend to `ST_ASIAN_SWEEP_5R_V1` or vice versa; strategy authority is never
inherited across strategies. The accurate picture for this repository's own pipeline is
two separated domains plus a documented, narrower bridge:

```text
CORE FX PROPOSAL RUNTIME (proposal-only, strategy-scoped)
  FX deterministic runtime (strategy_engine/, ST_ASIAN_SWEEP_5R_V1)
    -> TradeIntent / TradeProposal (execution/intent_builder.py, post_asian_pilot/proposal.py)
    -> proposal persistence + reporting (journal/post_asian_pilot/, journal/post_london_newyork_pilot/,
       report_archive.py, AG_FX_DAILY_REPORT_V1)
    -> PROPOSAL-ONLY OPERATIONAL OUTPUT (CLI --once/--status/--watch, Entry Ticket)
  ST_ASIAN_SWEEP_5R_V1 stops here as of 2026-09-06: demo_authorized=false, live_authorized=false.

SEPARATE EXECUTION SUBSYSTEM (application infrastructure, not strategy-scoped)
  explicit fresh user command
    -> execution safety gates (execution/validator.py, execution/risk.py, journal.py atomic claim)
    -> assistant.commands.execute_command(command, user_confirmed=True)
    -> MT5 Demo (execution/executor.py, execution/mt5_gateway.py)
    -> journal / reconciliation

DOCUMENTED BRIDGE BETWEEN THEM (generic, infrastructure-level, demo-verified once)
  A TradeProposal built from the assistant's own ASSISTANT_PROPOSAL analysis path CAN
  be resolved ("execute it") into a TradeCommand and sent through the execution
  subsystem above — AG_ASSISTANT_PROPOSAL_EXECUTION_V1, 2026-08-28, ticket 1880212783,
  a real MT5 Demo-account order_send -> real close, fully verified (not real-money
  execution evidence). This bridge is strategy-agnostic
  infrastructure: it does not, by itself, authorize any specific strategy. No evidence
  was found of this bridge ever being exercised specifically with an
  ST_ASIAN_SWEEP_5R_V1 pilot-cycle-origin proposal — the 2026-08-28 evidence describes
  a proposal from the assistant's own live analysis, not a post_asian_pilot journal
  entry. ST_ASIAN_SWEEP_5R_V1 proposals cannot use this bridge as of 2026-09-06 because
  the strategy itself is not demo_authorized (a registry-level gate, independent of
  whether the bridge code works).

PARALLEL RESEARCH DOMAINS (independent strategy families, no execution authority)
  BTC:        Bybit market data (production connectivity confirmed, data access only) -> ST_LIQUIDITY_SWEEP_RETEST_V1 research
              engine -> btc_sweep_research proposals -> RESEARCH_ONLY, never reaches
              execution.executor / mt5.management_gateway (verified statically+behaviorally)
  Large-SMC:  ST_LARGE_SMC_V1 v1.0.6 RESEARCH_DRAFT -> large_smc_research engine ->
              fails closed to BLOCKED on any C10-dependent candidate; no proposal
              authority

PAUSED OPTIONAL INTERFACE (not part of the core path, not merged)
  Telegram approval module (Phases A/B/C/D1 all built and committed as a frozen
  baseline, commit 740512b) lives only in an isolated feature-branch worktree; it is
  not connected to MT5 execution anywhere in its own file set, and it is not part of
  main. Development is PAUSED by owner directive.
```

### Current capability classification table

| Capability | Implementation | Verification | Integration | Authority | Current operational state |
|---|---|---|---|---|---|
| MT5 Demo execution subsystem | IMPLEMENTED | DEMO_VERIFIED (2026-08-28; a real MT5 Demo-account round trip, not real-money execution evidence) | Standalone, explicit-command-only | Application infrastructure, not strategy-gated | ENABLED, explicit-command-gated, disabled by default absent a fresh command |
| FX proposal→MT5 execution (generic bridge) | IMPLEMENTED | DEMO_VERIFIED (2026-08-28), generically, not for `ST_ASIAN_SWEEP_5R_V1` specifically | NOT_GENERALLY_WIRED to any pilot-cycle proposal | Requires per-strategy `demo_authorized` in addition | PARTIAL — infrastructure works, no strategy authorized to use this repository's execution path can use it (`SESSION_TRADE_V1`'s separate `demo_authorized: true` is on a different engine and does not apply here) |
| `ST_ASIAN_SWEEP_5R_V1` Demo authority | N/A (strategy has no execution code of its own) | N/A | N/A | `demo_authorized: false`, `live_authorized: false` (registry) | BLOCKED — proposal-only by explicit authorization gate, independent of infrastructure readiness |
| BTC execution | NOT_IMPLEMENTED (`CryptoExecutionAdapter`) | N/A | N/A | `execution_authority: DISABLED` | NOT_OPERATIONAL, fail-closed |
| BTC market data | IMPLEMENTED (Bybit adapter) | PRODUCTION_DATA_VERIFIED (2026-09-05, HTTP 200/retCode 0) — data access confirmed only, not trade execution or profitability | Wired into `btc_sweep_research` and `run_btc_daily_report.py` | Read-only, no execution implication | OPERATIONAL for data/reporting only |
| Large-SMC | IMPLEMENTED (research engine) | Corrected replay baseline recorded | Standalone research pipeline, no execution/broker call anywhere | `proposal_generation_authorized: false`, C10 UNSIGNED | RESEARCH_ONLY, BLOCKED at C10 for any candidate needing it |

### Historical vs. current — stale-claim correction

`docs/VERSION_HISTORY.md`'s "Current Capability and Upgrade Report (2026-09-03)" is
preserved unchanged as historical record — it was accurate for that date. Two of its
claims are now superseded by later evidence in this file's rolling summary and by
`config/releases/AG_TRADE_ASSISTANT_V1_0_3.yaml`'s `qualification_exception` block:

- "BTC ... production market-data authority is owner-frozen as Bybit (2026-09-03),
  adapter not yet implemented, environment-blocked (HTTP 403)" — **superseded**: the
  adapter is now implemented (`src/execution_runtime/bybit_linear_perp_feed.py`) and
  production market-data connectivity is confirmed (HTTP 200/retCode 0, 2026-09-05) —
  data access only, not trade execution or profitability. Historical
  state as of 2026-09-03; see this file's rolling summary (`CRYPTO DATA ADAPTER` line,
  2026-09-05) for current operational status.
- "Shadow-day/observation-day collection has not started" — **superseded** for FX:
  Series 002 has one classified day (Day 001, INVALID_DAY, defect found+fixed, not
  counted) and one verified-baseline pending day (Day 002, next eligible trading date
  2026-09-07). See `FX_VALIDATION` below for the current counters. BTC observation
  (0/30) genuinely has not started and that portion of the historical claim still holds.

`README.md` and `docs/README.md` are reconciled against this same current state (see
their own edits, dated 2026-09-06).

### BTC/Bybit current status (verify market data ≠ execution)

Market-data connectivity and trade-execution capability are independent facts. Current
truth, from `config/releases/AG_TRADE_ASSISTANT_V1_0_3.yaml`'s `qualification_exception`
and `btc_market_data_authority` blocks (owner-approved 2026-09-05,
`V1_0_3_BYBIT_QUALIFICATION_EXCEPTION`, `APPROVED_READ_ONLY_ONLY`):

- Feed: `BybitLinearPerpFeed` (`src/execution_runtime/bybit_linear_perp_feed.py`),
  public/read-only only, no authenticated or order/wallet endpoint anywhere in it;
  111 BTC tests passing.
- Production connectivity: last recorded authoritative PASS is `PRODUCTION_PUBLIC_READ_PASS`
  (HTTP 200/retCode 0, verified 2026-09-05, per the release manifest) — supersedes the
  2026-09-03 HTTP 403 CloudFront country-block finding, preserved as historical evidence
  in the same manifest, not deleted. **This is a dated record, not a live status**: a
  fresh check from this development session on 2026-09-06 again returned HTTP 403
  ("configured to block access from your country"), the same class of environment-
  specific restriction documented since 2026-08-31/09-03 — an expected, known condition
  for this environment, not a code defect or a reversal of the owner's Bybit
  market-data-authority decision. The scheduled daily task performs its own live check
  at each real invocation and fails closed to a non-counting `DATA_ERROR` if still
  blocked at that moment.
- Reporting: `scripts/run_btc_daily_report.py`, scheduler-ready, one disposable/
  non-counting diagnostic run completed 2026-09-05 (WATCH/NO_QUALIFIED_SWEEP_YET
  against 2026-09-04).
- Skill: `btc-sweep-retest-analysis` (owner_strategy=`ST_LIQUIDITY_SWEEP_RETEST_V1`,
  `ADVISORY_ONLY`) registered in both `.claude/skills/SKILL_REGISTRY.yaml` and
  `.agents/skills/SKILL_REGISTRY.yaml` — explains the shared sweep/retest engine's
  `CRYPTO_PERP` contract; never places orders, changes thresholds, or overrides a
  strategy decision.
- Scheduler: `scripts/install_btc_daily_task.ps1` installed and enabled this session --
  "AG Profit Trading - BTC Daily Decision", 13:05 MMT/06:35 UTC (inside the 06:30-06:45
  UTC window), `State=Ready`, next run 2026-09-07T06:35Z.
- Observation campaign: owner-authorized (`observation_campaign_authorized: true`,
  2026-09-06T06:52:42Z, `config/releases/AG_TRADE_ASSISTANT_V1_0_3.yaml`).
  `campaign_status = ACTIVE_0_OF_30` — scheduler installation and campaign authorization
  are each necessary but neither alone is sufficient: `observation_campaign_started`
  remains `false` until the first eligible in-window observation is actually archived;
  no diagnostic or prior date counts retroactively. The 06:30-06:45 UTC report-window
  amendment itself is already committed and pinned as the frozen operational baseline
  (`btc_operational_qualification_baseline = d5e1538...`, see
  `docs/status/AG_BTC_DAILY_REPORT_WINDOW_AMENDMENT_V1_STATUS.md`) — it is not the
  pending item. Separately, and NOT yet authorized: a proposed catch-up/delayed-reporting
  contract amendment (`docs/contracts/AG_BTC_CATCHUP_CONTRACT_AMENDMENT_V1_PROPOSED.md`,
  audited in `docs/status/AG_INTERMITTENT_PC_CATCHUP_CONTRACT_AUDIT_V1_STATUS.md`) remains
  documentation-only and does not change the current 06:30-06:45 UTC observation
  contract unless/until the owner approves it.
- Execution: forbidden_scope explicitly excludes order creation/checking/submission/
  modification/cancellation and wallet operations. `BTC_EXECUTION: NOT_IMPLEMENTED`.
  BTC research proposal capability never implies BTC execution authorization.

### FX validation current status

Do not report "shadow validation pending" or "collection has not started" without
citing the actual counters. Current series is `AG_V1_0_3_FX_SHADOW_SERIES_002`
(Series 001 — Day 001 EXCLUDED_DAY, Day 002 PENDING_RECONCILIATION — was left
unresolved and superseded by a fresh series, not retroactively fixed):

- `valid_days = 0/20`, `invalid_days = 1`, `excluded_days = 0`, `pending_days = 0`.
- Day 001 (2026-09-04): `INVALID_DAY` — a real reference-session key-casing defect was
  found and fixed (not retroactively counted as valid).
- Day 002: checked 2026-09-04, re-checked 2026-09-05 —
  `BASELINE_VERIFIED_AWAITING_NEXT_ELIGIBLE_DAY`. 2026-09-05/06 are weekend; next
  eligible trading date is Monday 2026-09-07.
- Baseline: source HEAD `3b2eeed` (validation_source_baseline), affected suite 92
  passed/0 failed at last verification.

### Strategy authority correction — `ST_ASIAN_SWEEP_5R_V1`

Values below are read as-is from `strategies/registry.yaml` and
`strategies/ST_ASIAN_SWEEP_5R_V1.yaml`; none were changed while writing this section.

- `demo_authorized: false`, `live_authorized: false` (registry).
- `entry_order_type: MARKET` for both `long_setup`/`short_setup` — resolved
  2026-08-31 (`AG_EXECUTION_RUNTIME_READINESS_V1`, strategy v1.1.1); the prior
  "dual-mode ambiguity" was determined to have never been a genuine two-case choice.
- `risk_per_trade_pct`: **UNSPECIFIED in the strategy YAML** — the
  `risk_and_money_management` block only declares `risk_mode:
  FIXED_PERCENT_OR_CONTRACT`, `stop_loss_mode: PERCENT_OF_SESSION_RANGE`,
  `stop_loss_range_pct: 0.25`. This is a real, current, unresolved gap, not a stale
  historical claim.
- **Account-level risk fallback — verified from code, not assumed.** Contrary to
  `strategies/STRATEGY_LEDGER.md`'s comment ("`execution/risk.py` currently falls back
  to `config/trading.yaml`'s account-wide `risk.risk_per_trade_pct: 1.0` default"),
  reading the actual call chain shows no code path performs that fallback as of 2026-09-06:
  `execution/risk.py::size_position()` and `execution/intent_builder.py::build_intent()`
  both take `risk_per_trade_pct` as a required parameter with no default and never read
  `config/trading.yaml` themselves; `execution/validator.py::validate_account_and_config()`
  only checks that whatever value it is handed is a finite number in `(0, 100]` — it
  does not supply one. `config/trading.yaml`'s own comment ("Not read by any code yet
  except execution/risk.py") is itself stale — `risk.py` does not read the file. The
  value that actually reaches the FX proposal path as of 2026-09-06 comes from the pilot-config
  layer (`config/pilot/AG_POST_ASIAN_LONDON_PILOT_V1_0_1.yaml` /
  `..._LONDON_NEWYORK_PILOT_V1_0_1.yaml`'s own `risk_per_trade_pct`), deliberately kept
  outside the strategy YAML (`post_asian_pilot/pilot_config.py`'s own docstring). There
  is currently no automatic code-level fallback from an unset strategy
  `risk_per_trade_pct` to `config/trading.yaml`'s account-wide default for the direct
  `execution.executor` path (`ASSISTANT_PROPOSAL`/`USER_EXPLICIT_ORDER`) — a caller must
  supply an explicit value every time. This is reported as a finding, not resolved; no
  risk value was changed.

### Telegram — current owner directive

The owner has explicitly decided: **PAUSE further Telegram-related development,
finish the core project first.** This is a current project-management directive from
this session, not derived from `docs/VERSION_HISTORY.md` (which never mentions
Telegram at all). Verified against the actual worktree, not assumed:

- `implemented_phases`: A+B+C+D1 all committed as a frozen, broker-unreachable
  baseline in `.claude/worktrees/telegram-execution-gateway-v1` (branch
  `feature/telegram-demo-execution-gateway-v1`, commit `740512b`
  "AG_TELEGRAM_DEMO_EXECUTION_GATEWAY_V1_PHASE_D1_BROKER_UNREACHABLE_BASELINE",
  branched from `main` at `63938cc` — this is the branch's only Telegram-related
  commit; `main` itself remains at `63938cc`, unchanged). Not merged into `main`, not
  pushed. `authorization_core` (`src/authorization/{store,models,config,integrity,strategy_authority,proposal_source,telegram_gateway}.py`)
  and the transport/callback gateway (`src/notifications/{telegram_client,trade_ticket_formatter}.py`)
  are present with matching tests (`tests/test_authorization_core.py`,
  `tests/test_telegram_client.py`, `tests/test_telegram_gateway.py`,
  `tests/test_trade_ticket_formatter.py`, `tests/test_phase_d1_proposal_and_authority.py`,
  `tests/test_phase_d1_gateway_execution_flow.py` — 117 tests, all passing, all
  Telegram HTTP mocked).
- Phase D1 (real proposal integration) is **complete and committed**:
  `src/authorization/proposal_source.py` (its own docstring: "Phase D1: the real,
  authoritative TradeProposal source ... replaces Phase C's placeholder JSON-file
  lookup") reads real `post_asian_pilot` proposal journals read-only; a live strategy
  demo-authorization recheck (`src/authorization/strategy_authority.py`, reads
  `strategies/registry.yaml` directly on every Execute Demo click) blocks execution
  with `BLOCKED_STRATEGY_NOT_DEMO_AUTHORIZED` for `ST_ASIAN_SWEEP_5R_V1`
  (`demo_authorized: false`, verified from the registry file, unchanged). `main` still
  has zero Telegram files (`src/authorization/`, `src/notifications/` do not exist
  there) — this is a preservation commit on an isolated branch, not an integration.
- MT5/Bybit broker wiring: not present anywhere in the branch's file set — no
  Telegram module calls `execution.executor`, `execution.coordinator`, or
  `assistant.commands.execute_command`; verified by an AST-based import scan plus
  grep, both clean. See `docs/status/AG_TELEGRAM_DEMO_EXECUTION_GATEWAY_V1_PHASE_D1_FROZEN_STATUS.md`
  (on the feature branch) for full detail, including a known pre-existing Windows
  `JsonKeyValueStore` concurrency race under heavy combined-suite parallel test load
  (`WINDOWS_APPROVAL_STORE_CONCURRENCY = MUST_FIX_BEFORE_EXECUTION_AUTHORIZATION`) —
  does not affect FX/BTC qualification, which never touches this store; must be fixed
  before any future Telegram/MT5/Bybit execution work resumes.
- `development_state = PAUSED`. `reason = core-project (V1.0.3) qualification
  prioritized`. `resume_condition = explicit owner authorization after the V1.0.3
  release qualification decision`.
- No Telegram feature work was added, refactored, or continued this milestone beyond
  the preservation commit itself. Telegram is not a core-completion dependency.

### Core project objective

AG Profit Trading should become a deterministic trading assistant that can: (1)
produce an immutable deterministic `TradeProposal`; (2) persist it; (3) obtain fresh
explicit owner authorization through an approved interface; (4) enforce strategy
authority; (5) execute exactly once through the canonical command funnel; (6) operate
only against a positively verified MT5 Demo environment; (7) journal broker actions;
(8) reconcile against broker truth; (9) survive restart/crash boundaries safely; (10)
keep live trading disabled unless separately authorized. Telegram is one possible
future approval interface, not the definition of the core system.

### CORE-FIRST roadmap (replaces the old Telegram-centric Phase D roadmap)

- **CORE-D1 — Real deterministic proposal persistence.** Status: **substantially
  already implemented for FX**, not NOT_STARTED. `strategy_engine` → `TradeIntent` →
  `TradeProposal` (`execution/intent_builder.py`, `post_asian_pilot/proposal.py`) →
  durable per-cycle journal (`journal/post_asian_pilot/`,
  `journal/post_london_newyork_pilot/`) → append-only immutable archive
  (`post_asian_pilot/report_archive.py`, `AG_FX_DAILY_REPORT_V1`) → CLI inspection
  (`--once`/`--status`/`--watch`, Entry Ticket). Deterministic identity, strategy/
  version recording, restart-safe lookup, and no-broker-call are already evidenced by
  the FX shadow-series work above. Not yet formally re-verified against this
  milestone's exact acceptance-criteria wording (immutable execution fields, expiry
  recorded) — that re-verification, not the underlying capability, is what remains
  open.
- **CORE-D2 — Strategy execution contract.** OPEN, unresolved by design. Before
  connecting `ST_ASIAN_SWEEP_5R_V1` to MT5 Demo, an explicit owner decision is required
  among: (A) add a strategy-specific `risk_per_trade_pct` to the strategy YAML; (B)
  explicitly authorize the pilot-config/account-level risk value as the strategy's
  real contract; (C) remain proposal-only. This task reports the gap (see "Strategy
  authority correction" above) and does not choose for the owner.
- **CORE-D3 — Approved command funnel.** Status: **substantially already implemented**
  at the infrastructure level (see "Corrected architecture description" bridge above) —
  stored `TradeProposal` → "execute it" resolution
  (`assistant.commands.resolve_active_proposal()`) → freshness/integrity revalidation →
  `TradeCommand` → `assistant.commands.execute_command(command, user_confirmed=True)`
  → execution subsystem, DEMO_VERIFIED 2026-08-28 (a real MT5 Demo-account round trip,
  not real-money execution evidence). What remains open is strategy-level
  gating: `ST_ASIAN_SWEEP_5R_V1` pilot proposals cannot reach this funnel as of
  2026-09-06 because the strategy is not `demo_authorized` — that is CORE-D2's
  decision, not a missing funnel capability.
- **CORE-D4 — MT5 Demo firewall.** Status: implemented and DEMO_VERIFIED for the
  existing OPEN/CLOSE path (`config/trading.yaml` `account.allow_live_trading: false`,
  explicit `user_confirmed=True` required every call, DEMO round trip verified
  2026-08-28). Not independently re-audited in this task against every firewall
  condition listed in the task protocol (unknown environment, analysis-mode leakage,
  etc.) — flagged for a dedicated review, not claimed complete here.
- **CORE-D5 — Controlled Demo verification gate.** Defined by this task only (offline
  tests → mocked end-to-end → real `order_check` → one minimum-size Demo order →
  verify broker ticket/journal/reconciliation; one authorization = one command = at
  most one broker submission = one reconciled broker result). No broker smoke test was
  performed by this task.
- **CORE-D6 — Recovery/concurrency hardening.** `execution/journal.py` already
  implements its own independent atomic-claim mechanism (O_EXCL exclusive-create,
  restart-safe, cross-process/cross-thread safe per the 2026-08-30 hardening notes
  referenced in this file's "Authority order" section) — separate from, and not
  affected by, the Telegram approval store's own concurrency implementation. The
  Telegram-specific approval store (`.claude/worktrees/telegram-execution-gateway-v1/
  src/authorization/store.py`) reuses the same O_EXCL idiom by its own docstring; no
  Windows-specific concurrency-race defect document was found under `docs/status/` for
  it in this pass. Flag clearly: **this pattern must not be re-implemented or weakened
  when Telegram resumes** — the core execution path's own atomic claim in
  `execution/journal.py` must remain the reference implementation.
- **CORE-D7 — Release/validation closure.** FX Series 002 in progress (0/20 valid, 1
  invalid, next eligible day 2026-09-07); BTC observation not started (0/30). Execution
  capability (MT5 Demo works) and evidence qualification (shadow/observation days) are
  separate — MT5 Demo working does not imply release completion.

```text
AG PROFIT TRADING -- CORE COMPLETION ROADMAP

CURRENT (2026-09-06)
  |
  v
CORE-D1  Real deterministic proposal persistence  [substantially already done for FX]
  |
  v
CORE-D2  Strategy execution contract (risk_per_trade_pct decision)  [OPEN -- owner decision required]
  |
  v
CORE-D3  Approved command funnel  [infrastructure already done; strategy-gate blocked on D2]
  |
  v
CORE-D4  MT5 Demo firewall  [implemented; not independently re-audited this pass]
  |
  v
CORE-D5  Controlled Demo verification gate  [DEFINED only, not run]
  |
  v
CORE-D6  Recovery/concurrency hardening  [core path already has its own atomic claim]
  |
  v
CORE-D7  Release/validation closure  [FX Series 002 0/20, BTC 0/30, in progress]
  |
  v
CORE PROJECT OPERATIONALLY READY
  |
  +--> OPTIONAL: Telegram integration resumes (resume_condition: core ready or owner reactivation)
  +--> OPTIONAL: Bybit Demo execution work (BYBIT-DEMO-1..6, not started)
  +--> OPTIONAL: Large-SMC evidence progression (C10 -> causal outcomes -> robustness -> proposal-authority decision)
```

**Large-SMC roadmap** (unchanged, preserved): research → C10 contract resolution
(owner-selected `AG_NATIVE_INVALIDATION` conceptual model, implementation still
`PENDING`) → causal outcomes → wider robustness → evidence review → separate
proposal-authorization decision. Demo/live execution remains independently
authorized and is not implied by any research progress. `ST_LARGE_SMC_V1` stays
`RESEARCH_DRAFT` — not promoted by this section.

### Current-state summary

```text
FX_SESSION_ANALYSIS             IMPLEMENTED, VERIFIED
FX_PROPOSALS                    PROPOSAL_ONLY (ASIAN_LONDON verified runtime evidence; LONDON_NEWYORK unit-tested, shadow pending)
FX_PROPOSAL_TO_MT5               PARTIAL (generic bridge IMPLEMENTED + VERIFIED 2026-08-28; NOT_WIRED for ST_ASIAN_SWEEP_5R_V1 specifically -- strategy not demo_authorized)
ST_ASIAN_SWEEP_DEMO_AUTHORITY    DISABLED (registry: demo_authorized=false)
ST_ASIAN_SWEEP_LIVE_AUTHORITY    DISABLED (registry: live_authorized=false)
MT5_DEMO_SUBSYSTEM               IMPLEMENTED, VERIFIED, explicit-command-gated
MT5_LIVE_SERVICE                 IMPLEMENTED behind gates, DISABLED
BTC_MARKET_DATA                  IMPLEMENTED, VERIFIED (Bybit, HTTP 200/retCode 0, 2026-09-05)
BTC_PROPOSALS                    RESEARCH_ONLY
BTC_EXECUTION                    NOT_IMPLEMENTED, DISABLED
LARGE_SMC_RESEARCH                IMPLEMENTED, RESEARCH_ONLY, BLOCKED at C10
LARGE_SMC_PROPOSALS               NOT_AUTHORIZED
LARGE_SMC_EXECUTION               NOT_IMPLEMENTED, NONE
TELEGRAM_INTERFACE                Phases A+B+C+D1 all committed on feature branch
                                   feature/telegram-demo-execution-gateway-v1 @ 740512b;
                                   feature-branch working tree clean; not merged to main
TELEGRAM_REAL_PROPOSAL_INTEGRATION  COMPLETE and committed on feature branch (not merged)
TELEGRAM_MT5_INTEGRATION          NOT_WIRED, not present anywhere in the feature branch
TELEGRAM_DEVELOPMENT_STATE        PAUSED (owner directive, 2026-09-06)
```

### Product objective

The target product produces two deterministic decision services: recurring intraday
**Session Trade** proposals and selective higher-timeframe **Large-SMC Trade** proposals.
Each evaluation must end in an explicit actionable or non-actionable state; the system
guarantees a daily decision report, not a forced trade. A proposal is not a broker
ticket. Broker execution remains a separate, freshly validated, explicitly
human-authorized action.

The current implementation is FX/MT5-first. `scripts/run_daytrading_runtime.py` provides
a read-only, closed-bar runtime for completed-session evaluation and SMC conditional
surveillance with restart-persistent state and idempotent alert records. The execution
runtime provides explicit-confirmation FX routing and restart reconciliation. These are
real runtime paths, superseding older documents that described the registry as having
no caller or orchestrator.

`ST_LIQUIDITY_SWEEP_RETEST_V1` contains parameterized Forex and crypto-perpetual signal
profiles. Crypto remains research/proposal-only: `execution_runtime.binance_usdtm_feed`
(added 2026-09-02) implements `execution_runtime.crypto_feed.CryptoCandleFeed` for
Binance USDT-M perpetual BTCUSDT public market data (fail-closed candle validation,
UNIT_TESTED offline; live connectivity from this environment is currently BLOCKED --
Binance returns HTTP 451 -- see the dated status document below), and
`execution.adapter.CryptoExecutionAdapter` still cannot send orders. The BTC research
runtime (`src/btc_sweep_research/`) enumerates every qualifying same-day occurrence (not
capped at one), separates strategy qualification from tradability-guard state, and builds
a `BTCSweepResearchProposal` explicitly tagged `execution_domain=CRYPTO_RESEARCH` /
`execution_authority=DISABLED`; `execution.executor.execute()` now rejects any object
that is not `execution.models.TradeCommand` before reading any of its fields, so this
proposal type cannot reach the FX order path even by accident. Its own exchange-specific
metadata (tick size, quantity step, minimum quantity) is sourced from the Binance adapter,
not the crypto_symbols.py synthetic defaults.

Documentation live-status changes follow
`docs/status/LIVE_STATUS_MAINTENANCE.md`. Dated milestone documents remain evidence of
their date and are not rewritten merely because later implementation superseded them.
The 2026-08-31 documentation refresh started a new full regression run, but it was
operator-interrupted after passing 64% with no reported failures because
environment-sensitive checks were taking an extended time; it therefore does not
replace the last completed baseline above.

Execution safety was reverified and hardened on 2026-08-30:

- OPEN and CLOSE share duplicate-command protection.
- An atomic, restart-persistent command claim permits only one worker to own a
  `command_id`; crash recovery fails closed rather than risking a duplicate send.
- Journal filenames use a deterministic hash of `command_id`, while entries retain the
  original ID. Existing safe legacy journal filenames remain readable.
- CLOSE volume rejects non-finite, non-positive, excessive, below-minimum, above-maximum,
  and unsafe remainder cases; off-step requests are floored to the broker step and are
  never rounded upward.
- Missing or malformed Session Trade adapter analysis fails closed.
- Historical replay explicitly blocks live MT5 candle/tick access even if a terminal
  was initialized earlier in the test or process. Historical session-box reconstruction
  remains a completeness gap and reports `HISTORICAL_SESSION_DATA_UNAVAILABLE`.
- Live FX tests skip closed-market days instead of weakening stale-data protection or
  fabricating candles.

Current default gates remain safe in `config/trading.yaml`: `mode: ANALYSIS`,
`allow_order_check: false`, `allow_order_send: false`, `allow_live_trading: false`, and
manual trade management in `DRY_RUN` with `allow_live_management: false`.

`SMC_TRAP_GUARD_V1` is an additive, deterministic evidence validator shared by
`ST_ASIAN_SWEEP_5R_V1` and `ST_LARGE_SMC_V1`. It rejects future/retrospective evidence,
direction claims made below strategy authority, and lower-timeframe attempts to
override higher-timeframe context. Strategy contracts also pin existing invariants
such as liquidity-event != trade-signal, penetration-without-reclaim = no trade, and
E3 sweep-without-reclaim = not eligible. It adds no entry filter, changes no strategy
version, and grants no proposal/demo/live authority. See
`docs/status/SMC_TRAP_GUARD_V1_STATUS.md`.

`ST_LARGE_SMC_V1 v1.0.6` is registered as an independent `RESEARCH_DRAFT` strategy
contract. It shares advisory Market Structure, Supply/Demand, Liquidity, Entry
Confirmation, and Trade Management capabilities, but shares no strategy authority or
validation evidence with `ST_ASIAN_SWEEP_5R_V1`. UC-001 (timeframe roles: D1/H1/M5),
C11 (target model: `HYBRID_WITH_STRUCTURAL_FALLBACK`), and C12 (candidate expiry:
shared `is_eligible_at()` window, no independent M1/M2/M3 timer) are resolved. C14
(duplicate/re-entry) is `PARTIALLY_RESOLVED`: setup-family identity reuses
`proposals/`'s existing `setup_id`, and candidate-occurrence/M-candidate identity is
deterministic and unit-tested via additive `source_id` fields on `M1Result`/
`M2Result`/`M3Result` and `proposals/occurrence_identity.py` — not wired into
`proposals/lifecycle.py`'s live store (shared with the live `SMC_CONDITIONAL_ENTRY_V2`
watcher; migration `SHARED_CHANGE_REQUIRED`); post-fill re-entry separately `DEFERRED`.

As of v1.0.5 (2026-09-02, `RESEARCH_ONLY_FUNNEL_V1`), a research-only engine exists:
`src/large_smc_research/` composes the already-frozen E1/E2/E3 + M1/M2/M3 pipeline
(`historical_replay.stage2`, zero redetection) into explicit
`LargeSMCResearchDecision`s. C01 (instruments → `[EURUSD]` only), C16 (warmup → reuse
of `D1=60/H1=50/M5=200`), the C11 target-model adapter (formula unchanged, now
`IMPLEMENTED`), and C18 (simultaneous-combination selection →
`RECORD_ALL_INDEPENDENTLY`, reuse of C14) are resolved. `decision_states` dropped the
placeholder `READY` for `RESEARCH_QUALIFIED`/`INVALIDATED`. **C10 (broker stop-loss)
remains deliberately `UNSIGNED`** — an explicit owner decision to block outcome
simulation rather than guess; the engine fails closed to `BLOCKED` for any candidate
that would otherwise need it, with a decision-packet document. No proposal, demo,
live, execution, or risk-sizing authority was added. See
`docs/status/LARGE_SMC_V1_REGISTRATION_STATUS.md`,
`docs/status/ST_LARGE_SMC_V1_C14B_OCCURRENCE_IDENTITY_HARDENING_STATUS.md`, and
`docs/status/ST_LARGE_SMC_V1_RESEARCH_FUNNEL_V1_STATUS.md`.

As of v1.0.6 (2026-09-02, `OUTCOME_LIFECYCLE_V1`), post-READY pending-entry expiry is
`RESOLVED_BY_REUSE`: `historical_replay/fill_simulator.py` (pre-existing, tested, never
previously wired here) already establishes no time-based expiry exists for this
pipeline — a pending entry terminates only via fill or structural invalidation, reused
verbatim by new `src/large_smc_research/pending_entry.py`. This phase also **discovered
and disclosed** (not fixed) a separate, pre-existing gap: C11's target-model adapter
and the project's own M1 inducement-candidate detection both silently fail during
historical replay because `market_structure.tiers.analyze_structure_tiers` requires a
live MT5 terminal for symbol metadata that `historical_replay/data_source_patch.py`
never patches — this likely explains the long-standing "M1 forms zero entry arrays"
finding as at least partly a data-source-patching artifact, not purely a strategy
result. The engine now fails closed to `DATA_ERROR` in this case rather than a
misleading `NO_TRADE`. See `docs/status/ST_LARGE_SMC_V1_OUTCOME_LIFECYCLE_V1_STATUS.md`.

**Resolved same day (`REPLAY_METADATA_DECOUPLING_V1`):** the owner authorized a
dataset-fingerprint-bound historical `tick_size=0.00001` for
`EURUSD_M5_202504211715_202607310000` only (`HISTORICAL_ANALYSIS_ONLY` scope, tagged
`SYNTHETIC_RESEARCH`, never usable for execution — `config/historical_datasets/`,
`historical_replay/symbol_metadata_manifest.py`). Wired as an opt-in parameter into
`historical_data_context`, fixing both C11's target adapter and M1's inducement
detection at their one shared call site, with no live-behavior change (verified) and
no formula change. A corrected September 2025 replay isolates the effect to exactly
one combination cell (E1M1, previously starved) — every other cell byte-identical to
the pre-fix run. C10 (broker stop-loss) remains the sole open blocker.
Recommendation: `GO_TO_C10_DECISION`. See
`docs/status/ST_LARGE_SMC_V1_MT5_SYMBOL_METADATA_REPLAY_GAP.md` and
`docs/status/ST_LARGE_SMC_V1_REPLAY_METADATA_DECOUPLING_V1_STATUS.md`.

The strategy/skill workflow is organized conceptually in
`docs/architecture/STRATEGY_WORKFLOW_RESOURCE_MAP.md`: local contracts and engines retain
authority; D-drive SMC repositories are classified as separate authorities, research
references, locked work, or historical safety evidence. `.agents/skills` and
`.claude/skills` remain path-for-path mirrors; no skill or strategy code was moved.

## Repository reorganization (2026-08-28)

All 11 Python packages + `session_clock.py` moved from repo root into `src/` (flat --
package names unchanged, so no import statement anywhere needed to change; see
`pyproject.toml`'s `pythonpath`/packaging config). 14 of 17 root-level `.md` docs moved
into `docs/{architecture,specs,status,setup}/`; `README.md`/`AGENTS.md`/
`PROJECT_STATUS.md` stay at root. `cleanup_mbt.ps1`/`setup_mbt.ps1` moved into
`scripts/`. Fixed three real `__file__`-relative config-path bugs this move exposed
(`execution/mt5_gateway.py`, `mt5/management_gateway.py`, `session_clock.py` all
assumed a fixed distance to repo root that changed by one level) plus five hardcoded
test-fixture paths (`tests/test_five_skill_runtime.py`,
`tests/test_entry_confirmation.py`, `tests/test_trade_management_pretrade.py`).
`config/`, `scripts/`, `tests/`, `strategies/`, `journal/`, `.claude/`, `.agents/` are
unchanged in place. First-ever git commits made as part of this pass (repo previously
had zero history). 448 passed / 0 failed, unchanged from pre-move baseline.

## Authority order (permanent project principle)

```
Strategy YAML -> Strategy Engine -> Execution Engine -> MT5
Agent skills / Trading Assistant capabilities -> ADVISORY ONLY
```

Trading Assistant capabilities (market-data, structure, supply/demand, liquidity,
entry-confirmation, trade-management) advise, inspect, explain. They have no
*independent* execution authority and never call `execution.executor`/
`execution.mt5_gateway`/`order_check`/`order_send` directly, and never override a
`strategy_engine.evaluate()` result — if a capability's read disagrees with the engine,
the engine's result stands; the capability may explain the disagreement, not act on it.
Actual broker execution is delegated to the central Trade Assistant execution layer
(`execution/executor.py`, reached only via `assistant/commands.py`) and requires
explicit user authorization every time — see "Execution authority restructure" below.

Exception, added 2026-08-27: `trade_management/` (Phase 6, manual-entry only) is a
third pathway, independent of both the above. It manages a position a human already
opened by hand and explicitly claimed by ticket — it never opens a position itself, and
its writes go only through `mt5.management_gateway` (modify SL / partial close / close),
gated by `config/trading.yaml`'s own `trade_management:` block, separate from
`execution/`'s gates.

## Execution authority restructure (2026-08-28)

```
EXECUTION DEVELOPMENT   = ACTIVE (entry-side OPEN, explicit-command-gated)
ANALYSIS                = AVAILABLE
ORDER_CHECK              = IMPLEMENTED (execution/mt5_gateway.py)
ORDER_SEND               = ENABLED for DEMO accounts, gated by config/trading.yaml AND
                            a required, non-defaulted user_confirmed=True per call
LIVE TRADING             = DISABLED (config/trading.yaml account.allow_live_trading: false)
```

`execution/mt5_gateway.py` and `execution/executor.py` (previously `NotImplementedError`
stubs) now implement OPEN for a new position, modeled directly on
`mt5.management_gateway.py`'s existing dry-run/live pattern. `execution/intent_builder.py`,
`risk.py`, `validator.py` are unchanged (still the strategy-signal path). CLOSE routes
through the existing, unmodified `mt5.management_gateway.close_position()` — no second
MT5 gateway.

Two `ExecutionSource`s (`execution/models.py`):
- `USER_EXPLICIT_ORDER` — a fully user-specified order (e.g. "sell EURUSD 0.31 lots SL
  ... TP ..."). Validated for geometry/sizing/broker constraints only
  (`trade_management.pretrade_engine.evaluate_trade_management()`) — never blocked for
  lacking a strategy signal or entry-confirmation.
- `ASSISTANT_PROPOSAL` — a `TradeProposal` the assistant generated from its own
  analysis, executed only on a later, separate explicit user command; refreshed and
  re-validated against live price at execution time, rejected as `PROPOSAL_STALE` if
  price/age has drifted past a documented tolerance rather than silently reused.

Both paths require `execution.executor.execute(command, user_confirmed=True)` — a
Python-level invariant, not a config flag: no code path reaches `order_send` without the
caller having just received an explicit user instruction that turn. Duplicate protection
via `execution/journal.py` uses an atomic persistent claim plus append-only hashed
journal files. It blocks concurrent workers, process-restart retries, and re-sending an
already-`EXECUTED` `command_id` without putting caller-controlled IDs into paths. CLI:
`scripts/execute_trade.py open|close ... [--confirm]`
(omit `--confirm` for a dry-run report of the exact broker request).

**AG_DEMO_EXECUTION_V1 (2026-08-28): PASSED.** One real, explicit-user-command DEMO
round trip verified live: order_check -> order_send -> broker-confirmed open (ticket
1879685149) -> live duplicate-command rejection -> close -> broker/deal-history-confirmed
closure -> config restored to safe defaults. Found and fixed one real defect during this
pass: MARKET-order geometry validation was defaulting `entry_price` to `0.0` instead of
resolving a fresh tick when `--entry` was omitted (`execution/executor.py::
_resolve_entry_price`). Full suite: 412 passed, 0 failed, unchanged count (bugfix, not
new functionality).

**AG_ASSISTANT_PROPOSAL_EXECUTION_V1 + AG_RISK_PERCENT_SIZING_LIVE_V1 (2026-08-28):
PASSED.** `TradeProposal` (`assistant/analysis_models.py`) is now execution-linked: an
`ASSISTANT_PROPOSAL` `TradeCommand` resolves side/SL/TP/risk_percent FROM the stored
proposal (never re-typed by the caller), and `assistant.commands.resolve_active_proposal()`
gives deterministic "execute it" resolution (`NO_ACTIVE_PROPOSAL` / `AMBIGUOUS_PROPOSAL`
/ resolved). Risk-percent sizing now actually works end-to-end: `execution/executor.py`
fetches fresh equity + symbol_meta at execution time (previously never populated at all --
every risk_percent order would have failed `ACCOUNT_DATA_MISSING`) and adds a defensive
final-risk-revalidation check before `order_open`. An already-`EXECUTED` proposal now
blocks re-execution by proposal identity, independent of `command_id` — closes a real gap
where a fresh CLI invocation ("execute it again") would have bypassed the command_id-keyed
journal check and sent a genuine second order. Also fixed: the default order comment
(`f"AG_TRADE_ASSISTANT:{source}"`, 38 chars) exceeded MT5's ~31-char comment limit and
would have rejected every unlabeled order — found live via a real `order_check` failure.
Live-verified: real analysis -> proposal -> "Execute it" -> risk-percent-derived volume
(0.5% of $997.06 equity -> raw 0.0997 lots -> floored to 0.09, actual risk 0.4513%) ->
real order_send (ticket 1880212783) -> live duplicate-proposal rejection -> real close ->
deal-history-confirmed -> config restored. Full suite: 427 passed (412 + 15 new), 0 failed.

## ASSISTANT_RUNTIME_V1 (2026-08-27)

`strategy_manager/` + `assistant/runtime.py` now let the Trade Assistant coordinate
`SESSION_TRADE_V1` / `ASIAN_LONDON` end-to-end in three explicit modes (`ANALYZE_ONLY`
live-verified; `SHADOW_DEMO`/`DEMO_EXECUTION` gating unit-tested, not yet exercised
live). `LONDON_NEWYORK` and `LIVE` both hard-blocked, independent of any flag. Full
architecture: `docs/status/ASSISTANT_RUNTIME_V1.md`; live evidence: `docs/status/ASSISTANT_RUNTIME_V1_STATUS.md`.
278 passed / 0 failed (was 252 before this pass).

## SMC foundational skills validation pass (2026-08-27)

A dedicated validation pass added external/internal structure tiers
(`market_structure/tiers.py`, `swing_length` 5/50), HH/HL/LH/LL labeling, a matplotlib
`chart_renderer/` package, external/internal liquidity scoping + Inducement Candidate
detection (`liquidity/hierarchy.py`), and engineered/retail liquidity classification
(`liquidity/proxies.py`) on top of Phases 2-4 below — all additive, nothing here changed
or broke the frozen `analyze_structure()`/`AG_ORDER_BLOCK_V1`/existing `liquidity/`
behavior. Full results, capability matrix, and verdicts: `docs/status/SMC_SKILL_VALIDATION.md`.
252 passed / 0 failed (was 213 before this pass).

## Trading Assistant capability roadmap

```
PHASE 1 — MARKET DATA          COMPLETE / VERIFIED (AG_TIME_NORMALIZATION_V1, 2026-08-27)
PHASE 2 — STRUCTURE            COMPLETE / FROZEN
PHASE 3 — SUPPLY & DEMAND      COMPLETE / FROZEN (AG_ORDER_BLOCK_V1, frozen 2026-08-26, verified 2026-08-27)
ORDER BLOCK CONTRACT           AG_ORDER_BLOCK_V1 FROZEN -- L1/L2 + inside-bar still UNSIGNED
PHASE 4 — LIQUIDITY            COMPLETE / FROZEN (AG_LIQUIDITY_V1, frozen 2026-08-27)
PHASE 5 — ENTRY & CONFIRMATION VERIFIED / FROZEN (AG_ENTRY_CONFIRMATION_V1, frozen 2026-08-28)
PHASE 6 — TRADE MANAGEMENT     BUILT (manual-entry only, 2026-08-27) -- see below
```

### PHASE 6 — TRADE MANAGEMENT (manual-entry only): BUILT (2026-08-27)

Owner-requested, out of the bottom-up phase order above: manages *already open,
manually entered* MT5 positions. It was implemented independently of Phase 5 and
remains separate from the later entry-side `execution/` pathway. New top-level
`trade_management/` package
(`models.py`, `claims.py`, `state.py`, `risk.py`, `rules.py`, `validator.py`,
`journal.py`, `manager.py`, `position_monitor.py`), plus `mt5.account.positions()`
(implemented; was `NotImplementedError`), `mt5/deals.py` (new), and
`mt5/management_gateway.py` (new -- the only module allowed to call
order_check/order_send for modify/partial-close/close on an existing position).

**Authority addendum (extends, does not replace, the section below):** this subsystem
is a third, independently-gated pathway -- distinct from both the advisory-only skills
and entry-side `execution/`. It never opens a position (structurally: every
gateway function requires an existing ticket) and is gated by
`config/trading.yaml`'s own `trade_management: {mode, allow_live_management}` block,
default `DRY_RUN`/`false`. `.claude/skills/trade_management/*` /
`.agents/skills/trade_management/*` (`position-monitor`, `risk-manager`,
`partial-profit-manager`, `breakeven-manager`, `exit-manager`) are thin advisory
wrappers that delegate to `trade_management.rules`, not reimplementations.

Baseline V1 rules (frozen, not user-configurable without a new owner-signed rule): 75%
partial close at an explicitly-supplied TP1, breakeven only after that partial is
broker-confirmed, 25% runner closed at 5R from the frozen initial risk distance. Never
enlarges risk or volume; fails closed (`MANAGEMENT_BLOCKED`) on any ambiguity,
including a manual SL/volume change made outside this system.

Workflow: `python scripts/manage_trade.py claim <ticket> --tp1 X --final-r 5`, then
`python scripts/manage_positions.py --once` or `--watch`.

Tests: `tests/test_trade_management_*.py`, `tests/test_management_gateway.py` -- 56
passed, all offline (mocked MT5 positions/ticks, no live connection needed except the
gateway's own live-mode integration is monkeypatched too). Full suite: 211 passed, 0
failed (155 prior + 56 new).

**Not done in this pass (deferred, needs an explicit follow-up request):** live DEMO
validation against a real manually-opened position (spec's own "one intentionally small
DEMO trade" controlled-progression requirement) -- `allow_live_management` stays `false`
until that's explicitly run. Netting-vs-hedging broker mechanics
(`mt5.account.Account.is_hedging_account`) is wired but not yet exercised live.

See `docs/status/PHASE_1_4_FREEZE_STATUS.md` for the 2026-08-27 stabilization pass: root-caused and
fixed a generic (not symbol-specific) tie-break defect in `mt5.broker_time`'s weekly-
reopen-gap detection, established `AG_TIME_NORMALIZATION_V1` (`mt5/time_contract.py`),
and validated all four phases as a regression baseline (154 passed / 1 skipped / 0
failed) before Phase 5 begins. `FROZEN` means no silent semantic changes to
`AG_ORDER_BLOCK_V1` / `AG_LIQUIDITY_V1` going forward -- a behavior change requires a new
contract version or explicit owner instruction.

Each phase implemented bottom-up; owner approves before the next one starts.

### PHASE 5 — ENTRY & CONFIRMATION: VERIFIED / FROZEN (2026-08-28)

`AG_ENTRY_CONFIRMATION_V1` (`entry_confirmation/`) consumes `market_structure.StructureResult`
and `liquidity.LiquidityResult` verbatim -- no redetection of pivots, CHoCH, BOS, sweeps,
or reclaims. Canonical chain: `LIQUIDITY EVENT -> STRUCTURE_SHIFT (CHoCH) -> DISPLACEMENT
-> EVENT_SEQUENCE -> CONFIRMATION_STATE` (`CONFIRMED` / `PARTIAL` / `NOT_CONFIRMED` /
`INDETERMINATE`, no numeric score). Displacement is now signed as
`AG_ENTRY_DISPLACEMENT_V1`: `body_ratio >= 0.60 AND body >= 1.30 x median_body_20 AND`
direction matches the candidate. `event_sequence` enforces
`liquidity_time < structure_time <= displacement_time` (same-candle structure/displacement
allowed). `rejection` qualification, POI alignment, FVG-as-entry-trigger, and
BOS-as-structure_shift remain explicitly DEFERRED, not missing. See
`docs/status/PHASE_5_ENTRY_CONFIRMATION_FREEZE_STATUS.md` for full evidence: fixed a
circular import (`entry_confirmation <-> liquidity <-> supply_demand <-> assistant`,
rooted in `supply_demand/native_zones.py` importing `assistant.market_data`), added 19
focused tests, ran read-only live MT5 validation on EURUSD (both examples correctly
resolved to `INDETERMINATE`/`NOT_CONFIRMED`-shaped evidence, not manufactured). Full
suite: 467 passed, 0 failed. `order_send` not used; `REAL_MONEY_TRADING` /
`AUTONOMOUS_TRADING` remain `DISABLED`, untouched by this phase.

### PHASE 1 — MARKET DATA: COMPLETE

Implemented in `mt5/`:
- `connection.py` — `connect()`/`is_connected()`, real, live-tested
- `broker_time.py` — UTC-offset detection via weekly-reopen-gap
- `market_data.py` — `get_candles()` (range), `get_latest_candles()` (position-based),
  `get_tick()` (Bid/Ask), `check_freshness()`; canonical `Candle` now carries `volume`
- `account.py` — `account()` (login/server/equity/demo flag)
- `symbol_resolver.py` — `get_symbol_meta()` (tick/contract/volume-step, generic across
  symbol types), `available_symbols()`

Fail-closed reason codes in use: `MT5_NOT_CONNECTED`, `SYMBOL_NOT_FOUND`, `DATA_MISSING`,
`INSUFFICIENT_CANDLES`, `STALE_DATA`, `DUPLICATE_TIMESTAMPS`, `NON_MONOTONIC_TIMESTAMPS`,
`SESSION_INCOMPLETE`, `TIME_NORMALIZATION_ERROR`, `UNSUPPORTED_TIMEFRAME`.

Report tool: `scripts/check_mt5.py --symbol X [--candles N] [--session asian] [--json]`.

Tests: `tests/test_broker_time.py` (7), `tests/test_market_data.py` (7, live-guarded).

**Fixed a real bug found live:** `get_candles()` passed naive datetimes to
`copy_rates_range`; MT5 silently reinterpreted them via this host's own system timezone
(UTC+6:30), shifting every session query by 6.5h. Fixed by passing epoch integers
instead — see `market_data.py`'s `_to_broker_epoch()`.

**Live examples (2026-08-26, VantageMarkets-Demo):**
- EURUSD: tick 1.16499/1.16512, 24/24 Asian bars, session high/low correct, freshness OK
- XAUUSD: tick 4592.92/4593.21, 24/24 Asian bars, freshness correctly flagged `STALE_DATA`

**Known gap:** `symbol_resolver.resolve()` (broker-suffix resolution, e.g.
`XAUUSD.crp`) still `NotImplementedError` — not hit yet since the connected account's
symbols are unsuffixed; revisit if a broker/symbol needs it.

### PHASE 2 — MARKET STRUCTURE: COMPLETE

`market_structure/` (new top-level package): `analyzer.py` (`analyze_structure()`,
public entry point), `smc_adapter.py` (the ONLY module allowed to import
`smartmoneyconcepts`; verified against installed v0.0.27's actual API, not an assumed
one), `models.py` (`StructureResult`, `StructurePoint`), `config.py` (reads
`config/market_structure.yaml`: `swing_length: 5`, `close_break: true`).

Capabilities: swing highs/lows, BOS, CHoCH, previous high/low, and a deterministic
`state` (`BULLISH`/`BEARISH`/`STRUCTURE_STATE_UNDEFINED` — no invented `RANGE`; see
`analyzer._structure_state()`'s docstring for why). Explicit per-call timeframe
(M1/M5/M15/M30/H1/H4/D1 — `mt5/market_data.py`'s `_TIMEFRAMES` extended beyond M1/M5/M15
for this). Closed candles only (`get_latest_candles` excludes the forming bar).
Warm-up (`max(swing_length*20, 100)` extra candles) fetched but not exposed as separate
"requested vs. total" ranges — reported provenance is the full fetched range.

**Dependency verification (required before coding against it):** `smartmoneyconcepts`
0.0.27's `swing_highs_lows`/`bos_choch` ignore the input DataFrame's own index and
return a fresh positional `RangeIndex`; `previous_high_low` instead calls
`pd.to_datetime(ohlc.index)` internally, so a positional `RangeIndex` there would be
silently reinterpreted as epoch-nanosecond garbage. Resolved by standardizing on one
canonical DataFrame (real UTC `DatetimeIndex`) for all three calls — verified live that
all three tolerate it correctly. Documented in `smc_adapter.py`'s module docstring.

Report tool: `scripts/analyze_structure.py --symbol X --timeframe Y [--count N] [--json]`.

Tests: `tests/test_market_structure.py` — 3 synthetic fixtures (ascending zigzag ->
BULLISH, descending -> BEARISH, range oscillation -> swings present but
`STRUCTURE_STATE_UNDEFINED`, no invented break), 1 adapter-shape test, 2 live EURUSD
(H1, M15) — all real data, both returned `BEARISH` with a live-confirmed BOS.

Added `requirements.txt` (didn't exist before) pinning the verified versions.

### Market Data Assistant layer: COMPLETE

`assistant/market_data.py` — the five user-facing capabilities on top of `mt5/` and
`market_structure/`, each returning a compact dataclass (never raw candle dumps to an
LLM): `market_snapshot()`, `historical_candles()` (UTC range or count), `session_snapshot()`
(open/high/low/close/range/midpoint/completeness), `data_health()` (per-check reason
codes, including new gap detection — `UNEXPECTED_DATA_GAP` vs. weekend closures, which
are not flagged), `multi_timeframe_snapshot()` (reuses `StructureResult` per timeframe).

Tests: `tests/test_assistant_market_data.py` — 10 passed (4 pure gap-logic, 6 live).

### PHASE 3 — SUPPLY & DEMAND: COMPLETE

New top-level package `supply_demand/`: `smc_adapter.py` (ONLY module here allowed to
import `smartmoneyconcepts`; reuses `market_structure.smc_adapter.candles_to_dataframe`),
`native_zones.py` (no smc import), `analyzer.py` (fail-closed batch entry points),
`models.py` (`ZoneResult`, `ZoneQueryResult`).

- **Order Blocks / FVG** (`order_blocks_for()`, `fair_value_gaps_for()`): bullish →
  `ZoneRole.DEMAND`, bearish → `ZoneRole.SUPPLY`. `MitigatedIndex == 0` verified from
  `smc` 0.0.27's own source to be an unambiguous "not mitigated" sentinel (never a real
  position) → `FRESH`; nonzero → `MITIGATED`. A fully invalidated OB is *deleted* from
  the library's internal state and never appears as an output row at all — this adapter
  therefore never reports `INVALIDATED` for these two families (not guessed). `Percentage`
  (OB) exposed only as `raw_strength_metric`, documented as a volume-symmetry ratio, not
  a probability/confidence.
- **Native session zones** (`session_zone()`): wraps `assistant.market_data.session_snapshot()`
  — no new session math. `status` is always `UNKNOWN` here (reason code
  `STATUS_LIFECYCLE_NOT_MODELED_IN_SUPPLY_DEMAND_PHASE`) — sweep/reclaim is a Liquidity-
  phase question.
- **Previous Day High/Low** (`previous_day_high_low()`): project-owned, no smc — the
  last CLOSED D1 bar via `mt5.market_data.get_latest_candles(symbol, "D1", 1)`.
  `TOUCHED` only reflects the *current* tick vs. the level, not the whole day's path
  (reason code names this limitation explicitly).
- **Premium/Equilibrium/Discount** (`dealing_range_zones()`): pure function, takes an
  **explicit** low/high + a caller-named `source` string — never picks a range itself.
  `premium_discount_from_previous_day()` / `premium_discount_from_session()` are the
  only two named convenience sources wired up so far.

Tests: `tests/test_supply_demand.py` — 8 passed (2 real-`smc.fvg()` fixtures for
bullish-fresh/bearish-mitigated, 1 mocked-`smc.ob()` fixture for OB mapping — `smc.ob()`'s
own trigger conditions are too stateful to hand-construct reliably, so its *output* is
mocked to test our mapping, which is the boundary we own; 1 pure premium/discount test;
4 live).

**Live examples (EURUSD, 2026-08-26):** H1 — 9 order blocks (mix of FRESH/MITIGATED),
36 FVGs; M15 — 3 order blocks, 28 FVGs; previous-day H/L 1.16506/1.16790 (`FRESH`);
premium/discount from both previous-day and Asian-session ranges classified current
price as `DISCOUNT`.

### PHASE 4 — LIQUIDITY: BUILT, PAUSED (2026-08-26)

Built and tested (below), then paused by owner request — no further liquidity work
until Order Blocks are resolved. Nothing here changed or broken; simply not being
extended further right now.

New top-level package `liquidity/`: `status.py` (pure sweep/reclaim state machine, no
MT5/smc import — see its module docstring for exact UNSWEPT/SWEPT/RECLAIMED/CONSUMED
semantics, deliberately independent of `strategy_engine.session.setups.entry_2_sweep`'s
strategy-specific strict-penetration contract), `equal_levels.py` (own local-extreme +
tolerance-clustering method, independent of `market_structure`'s smc-swing detection),
`analyzer.py` (`liquidity_result()`, reuses `market_structure.analyze_structure()`,
`supply_demand.session_zone()`, `supply_demand.previous_day_high_low()` rather than
recalculating any of them), `models.py` (`LiquidityLevel`, `LiquidityResult`).

Sources: structural swings (from `StructureResult`), session highs/lows (Asian/London/
New York), PDH/PDL, equal highs/lows (`config/liquidity.yaml`:
`equal_level_tolerance_points: 5`, symbol-tick-size-based, explicit default — no prior
project authority defined one). `SWEPT` is reported only for a live-tick penetration not
yet confirmed by a closed candle; closed-candle history always resolves to `RECLAIMED`
or `CONSUMED`.

Tests: `tests/test_liquidity.py` — 12 passed (7 pure state-machine, 3 pure equal-level
clustering, 2 live).

**Live examples (EURUSD, 2026-08-26):** H1 — 13 levels across all 4 sources; swing high
UNSWEPT, Asian High RECLAIMED, Asian Low CONSUMED, PDH UNSWEPT, PDL CONSUMED, one
EQUAL_HIGHS cluster. M15 — swing high caught mid-sweep as `SWEPT` (live tick trading
through it, not yet closed-candle-confirmed) — a real, not simulated, demonstration of
that status.

### ORDER BLOCK CONTRACT: AG_ORDER_BLOCK_V1 FROZEN AND IMPLEMENTED (2026-08-27)

The owner froze the baseline contract `AG_ORDER_BLOCK_V1` (superseding the prior
"everything stays CANDIDATE forever" placeholder from 2026-08-26). `supply_demand/ob_contract.py`
now implements it fully:

- **PIVOT_OB** (zone = full candle high/low) vs. **SHADOW_OB** (zone = wick tip to body
  edge): split by the origin candle's body-to-range ratio (≥0.5 → PIVOT, <0.5 → SHADOW)
  — an explicit, documented interpretation of the owner's wording, not a frozen number;
  flagged in `ob_contract.py`'s module docstring for confirmation.
- **FLIP_OB** (zone = full candle) is frozen but **never assigned** — its identification
  rule needs a lookback/proximity definition the contract doesn't give (unlike FVG's
  explicit `MAX_CANDLES_TO_FVG=3`). Every candidate resolves to PIVOT_OB or SHADOW_OB.
- **STRUCTURE**: requires a matching-direction BOS or CHoCH confirmed at/after the OB's
  origin — reuses `market_structure`'s real `bos_choch` output via a new
  `market_structure.structural_breaks_for_candles()` (exposes ALL confirmed breaks, not
  just the latest, so a batch of historical OB candidates can each find their own).
  `source=INTERNAL_OR_EXTERNAL` preserved as a placeholder field (`structure_source`) —
  `market_structure/` has one swing-length classifier, no internal/external tiering yet.
- **FVG**: requires a same-direction FVG within `MAX_CANDLES_TO_FVG=3` candles of the OB
  (positional distance, computed from the same fetched candle set as the OB — added
  `validated_order_blocks_for()` fetches OB+FVG candidates together for this reason). No
  literal price overlap required, per the frozen contract.
- **MITIGATION** (`WICK_TOUCH_BOUNDARY`) and **INVALIDATION** (close beyond the zone,
  bullish=below-low / bearish=above-high) scanned forward candle-by-candle; a wick that
  pierces the whole zone but closes back on the original side is `MITIGATED`, not
  `INVALIDATED` — verified live and by a dedicated test.

Lifecycle now real: `CANDIDATE` / `VALID` / `MITIGATED` / `INVALIDATED` / `REJECTED`, all
reachable. Reason codes: `VALID_OB`, `REQUIRED_STRUCTURE_MISSING`, `REQUIRED_FVG_MISSING`,
`FVG_DIRECTION_MISMATCH`, `FVG_TOO_LATE`, `INVALID_OB_GEOMETRY`, `OB_MITIGATED`,
`OB_INVALIDATED`.

**Still explicitly UNSIGNED** (owner instruction — not inferred from the reference
image): `supply_demand.L1_L2_CLASSIFICATION`, `supply_demand.INSIDE_BAR_FLIP_RULE`. See
`supply_demand.ORDER_BLOCK_CONTRACT_GAPS` for the remaining open items (FLIP_OB
identification, the PIVOT/SHADOW split interpretation, structure internal/external
tiering).

Existing generic OB/FVG functionality (`order_blocks_for()`, `fair_value_gaps_for()`) is
unchanged — `validated_order_blocks_for()` is additive.

Tests: `tests/test_ob_contract.py` — 13 passed (valid bullish/bearish PIVOT+FVG, missing
FVG, opposite-direction FVG, FVG too late, missing structure, SHADOW_OB wick-zone
geometry, mitigation by touch, bullish/bearish invalidation, wick-without-invalidation,
contract-gap coverage, 1 live). Full suite: 122 passed.

**Live examples (EURUSD, 2026-08-27):** H1 — 9 candidates, real mix of `VALID`
(2×SHADOW_OB bullish), `MITIGATED` (4), `INVALIDATED` (3, all SHADOW_OB); M15 — 3
candidates, all `MITIGATED` (2×PIVOT_OB, 1×SHADOW_OB). No `FLIP_OB` ever assigned, as
designed.

`supply-demand-analysis` skill updated for `SMC_CANDIDATE_OB` vs. `AG_VALID_ORDER_BLOCK`
terminology and the full lifecycle — see that skill's revised section.

## Strategy-config gaps (found building Phase B, still open)

See `strategies/STRATEGY_LEDGER.md`: `ST_ASIAN_SWEEP_5R_V1`'s `entry_order_type:
MARKET_OR_LIMIT` is ambiguous (blocks `READY_FOR_ORDER_CHECK`) and
`risk_and_money_management` never states an actual risk-per-trade percentage (a
`config/trading.yaml` account-wide default is used instead). Strategy-authorship
decisions, not something to invent while building the Assistant.

## Next owner decision

AG_ORDER_BLOCK_V1 and AG_LIQUIDITY_V1 are both implemented, validated, and now FROZEN
(see `docs/status/PHASE_1_4_FREEZE_STATUS.md`, 2026-08-27). Remaining open items (not blocking, but
unresolved): confirm/replace the PIVOT/SHADOW body-ratio split interpretation; decide
FLIP_OB's identification rule (lookback + proximity to a prior failed zone); L1/L2 and
inside-bar D2S/S2D remain explicitly UNSIGNED, not to be inferred; liquidity's
SWING_HIGH/SWING_LOW scope (latest-only) and its reuse of `equal_level_tolerance_points`
as the cross-source dedup tolerance are documented, non-blocking V1 gaps. Phase 5 — Entry
& Confirmation is now `VERIFIED` / `FROZEN` (`AG_ENTRY_CONFIRMATION_V1`, 2026-08-28; see
`docs/status/PHASE_5_ENTRY_CONFIRMATION_FREEZE_STATUS.md`). Next phase:
`AG_TRADE_MANAGEMENT_V1`'s entry-side dependency on Phase 5 (Phase 6's manual-entry-only
subsystem already ships independently of Phase 5 -- see PHASE 6 above) -- not started
in this pass.
# Web-to-MT5 Vantage Demo bridge (2026-09-10)

Status: **UNIT_TESTED / VANTAGE DEMO CONNECTION VERIFIED — ORDER SEND NOT EXERCISED.** The real-mode web
execution endpoint now invokes `scripts/web_execute_trade.py`, which constructs a
`USER_EXPLICIT_ORDER` and calls the sole authority boundary
`assistant.commands.execute_command()` with the UI's explicit confirmation. The bridge
uses `config/trading.demo.yaml`: order-check/send are enabled only for this bridge while
`allow_live_trading: false` keeps real accounts blocked. The repository default
`config/trading.yaml` remains fail-closed in `ANALYSIS`. The bridge now uses an explicit
configured-terminal initialization with a bounded timeout, eliminating ambiguous MT5
auto-discovery. Read-only web position synchronization returned HTTP 200 from the
configured Vantage Demo terminal. No order was sent during this change, so broker-level
frontend order submission remains not re-verified in the current session.

Follow-up: MT5 subsequently connected successfully to the configured Vantage Demo
account with fresh EURUSD data. Real-mode frontend positions now come from the terminal,
and manual breakeven/partial-close/close controls delegate to the claimed-position
`trade_management.manager` with requested-action eligibility enforcement. The dedicated
demo profile enables management while a new gateway guard rejects any non-Demo account
before `order_check` or `order_send`. No execution or management order was sent during
verification.
