# AG V2 Pre-Architecture Baseline + Core Contracts — Status (2026-09-21)

## Classification

`PARTIAL`. The pre-V2 baseline is identified and frozen, canonical infrastructure
is inventoried and reused (no duplication), and the additive `src/opportunity/`
core contracts (P3/P4) are implemented and tested. StrategyBinding, funnel
vocabulary, MarketEvent, OpportunityCandidate, ProposalEligibilityDecision, and
the shared evidence contracts (DataAuthority/WarmupRequirement/FrictionEvidence)
are all in place and pass focused + adjacent-surface regression tests. The
strategy adapter Protocol boundary (P19/P20) is defined with a passing static
import-boundary test. Out of scope for this mission and correctly not attempted:
any production strategy wiring, shadow-adapter implementation, funnel engine, or
authority change — see P23/"Explicitly out of scope" below.

## Repository

- branch: `main`
- head_before: `8c42cb6a2ba734399db6e6cc220578ef8573b1c5`
- head_after: `1e75e36554e841d14455a73adea1799be4cef166` (the pending SSC one-year
  replay freeze commit found already staged at session start; pushed to
  `origin/main` on explicit user confirmation mid-session — unrelated to this
  mission's own commits, which follow separately per the commit-discipline plan)
- commits_created_this_mission: recorded at the finalization commit (see repo log)
- working_tree: 2 modified operational state files
  (`state/fx_schedule/slot_ledger.json`, `state/proposal_ledger/proposal_ledger.json`
  — scheduled-runner ledger drift, not code)

## Mission-1 baseline

`MISSION1_STATE = ALREADY_COMMITTED`. The one-year replay data authority
(`ONE_YEAR_REPLAY_STACK_V1`, `manifest_sha256 = 59896fe6...1563d6ac` per
`docs/status/SSC_V1_0_1_ONE_YEAR_REPLAY_DATA_AUTHORITY_STATUS.md`) was already
fully committed at `1e75e36`, with `DATA_COVERAGE_COMPLETE`,
`CROSS_LEG_TIMEBASE_CONSISTENT` (`UTC_SINGLE_TIMEBASE`), `WARMUP_STABLE` (4371
closed H1 bars), and `PROTECTED_DATA_ACCESS_COUNT = 0`. No separate Mission-1
finalization commit was required. The two working-tree state files present at
session start are unrelated operational ledger drift, not mixed Mission-1 WIP, so
they did not block a clean baseline freeze.

## V2 baseline

See `AG_V2_BASELINE_MANIFEST_V1.json` (repo root) for the full machine-readable
manifest: baseline commit, registry/config fingerprints, replay-stack identity,
protected-data-access count (0), test baseline, and per-strategy authority
summary.

## Canonical reuse (P2)

No competing/duplicate model was created. Existing canonical authorities and
their V2-relevant mapping:

| Concept | Existing authoritative implementation |
|---|---|
| MarketSnapshot | `src/strategy_contract/market_snapshot.py::MarketSnapshot` |
| CanonicalProposal | `src/proposal_envelope/models.py::CanonicalProposal` |
| Proposal formation gate | `src/proposal_envelope/formation_gate.py::apply_formation_gate` |
| Proposal ledger | `state/proposal_ledger/proposal_ledger.json` via `proposal_envelope/ledger.py` |
| Strategy registry | `strategies/registry.yaml` |
| Strategy runtime dispatch | `src/strategy_manager/manager.py::evaluate` (SESSION_TRADE_V1 only) |
| TradeIntent / TradeCommand | `src/execution/models.py` |
| Legacy execution-layer proposal | `src/execution/adapter.py::TradeProposal` (treated as legacy adapter type, not duplicated) |
| Large-SMC research decisions | `src/large_smc_research/engine.py` (RESEARCH_ONLY) |
| SSC canonical evaluator | `src/session_sweep_continuation/`, `src/replay_evaluation/ssc.py` |
| SVOS | `src/svos/` |

`src/proposals/models.py::SMCTradeProposal` is a separate, pre-existing
Large-SMC-specific proposal model — noted, not touched, not merged.

## New contracts (`src/opportunity/`)

- `stages.py` — `FunnelStage` / `FunnelOutcome` string-constant vocabulary
  (7 stages, 6 outcomes), independent axes, no `RISK_FEASIBLE` stage.
- `contracts.py` — `MarketEvent`, `CandidateGeometry`, `OpportunityCandidate`,
  `ProposalEligibilityDecision` (+ `ELIGIBLE`/`BLOCKED`/`INCOMPLETE`),
  `DataAuthority`, `WarmupRequirement`, `FrictionEvidence`, and the
  `SYNTHETIC_DATA_NOT_PROPOSAL_ELIGIBLE` / `REPLAY_DATA_NOT_BROKER_EXECUTABLE`
  firewall reason codes.
- `transitions.py` — `FunnelTransition`, `FunnelState` (no growing history field
  on the candidate itself).
- `events.py` — `from_market_snapshot()`, a deterministic, additive wrapper
  around `MarketSnapshot` (does not replace it).
- `registry_binding.py` — `StrategyBinding`, `resolve_strategy_binding()`: reads
  `strategies/registry.yaml` only; dispatchability is hard-coded to the one fact
  established in `strategy_manager/manager.py` (`SESSION_TRADE_V1` only) rather
  than inferred from registration.
- `adapter.py` — `StrategyFunnelAdapter` Protocol, `StrategyObservation`,
  `FunnelProjection`. No `build_proposal()` on the adapter; proposal construction
  stays platform infrastructure.

All dataclasses are frozen, require timezone-aware timestamps where timestamps
exist, and fail closed on missing/invalid fields (no fabricated geometry,
lineage, or state).

## Strategy identity (P2.5)

| strategy_id | registered | manager-dispatchable | execution_authority |
|---|---|---|---|
| SESSION_TRADE_V1 | yes | **yes** (only one) | DEMO_AUTHORIZED (ASIAN_LONDON only) |
| ST_SESSION_SWEEP_CONTINUATION_V1 | yes | no | NONE |
| ST_ASIAN_SWEEP_5R_V1 | yes | no | NONE |
| ST_LARGE_SMC_V1 | yes | no | NONE |
| ST_LIQUIDITY_SWEEP_RETEST_V1 | yes | no | NONE |

Confirmed by inspection of `strategy_manager/manager.py::evaluate` (hard `if
strategy_id != "SESSION_TRADE_V1"` gate returning
`STRATEGY_ADAPTER_NOT_IMPLEMENTED`) and `strategies/registry.yaml`. No alias was
assumed identical; the registry's own identity note for
`ST_SESSION_SWEEP_CONTINUATION_V1` (distinct from a fabricated
`ST_SESSION_SWEEP_CONTINUATION` v1.1.1) is preserved verbatim in the binding.

## Safety

- strategy_semantics_changed: **false**
- strategy_parameters_changed: **false**
- proposal_authority_changed: **false**
- demo_authority_changed: **false**
- live_authority_changed: **false**
- protected_data_accessed: **false** (count = 0)
- broker_orders_sent: **false**
- telegram_sent: **false**
- `origin/main` push: one pre-existing, already-authored SSC commit (`1e75e36`)
  was pushed on explicit user confirmation via the repository's `AG_ALLOW_PUSH=1`
  guard — unrelated to and predating this mission's own contract work.

## Tests

- focused: 56 passed (`tests/test_opportunity_contracts.py`,
  `test_opportunity_events.py`, `test_opportunity_registry_binding.py`,
  `test_opportunity_import_boundaries.py`)
- regression (adjacent shared surface): 25 passed
  (`tests/test_market_snapshot_contract.py`, `test_proposal_envelope_models.py`,
  `test_proposal_envelope_execution_boundary.py`)
- broader regression (`strategy_manager`, `execution_boundary`, `registry`
  keyword group): recorded in `AG_V2_BASELINE_MANIFEST_V1.json` once complete
- broad (full suite): not run this mission (token-efficiency rule 7 — progressive
  testing; reserved for a real milestone/shared-surface change)

## Files changed

- `AG_V2_BASELINE_MANIFEST_V1.json` (new)
- `docs/status/AG_V2_PRE_ARCHITECTURE_BASELINE_STATUS.md` (new, this file)
- `src/opportunity/__init__.py`, `stages.py`, `contracts.py`, `transitions.py`,
  `events.py`, `registry_binding.py`, `adapter.py` (new)
- `tests/test_opportunity_contracts.py`, `test_opportunity_events.py`,
  `test_opportunity_registry_binding.py`, `test_opportunity_import_boundaries.py`
  (new)

## Next gate

`AG_V2_FUNNEL_CORE = READY` for the contracts layer implemented here. Wiring a
transition ledger, a candidate store, or any strategy shadow adapter is
out of scope for this mission.

## Next recommended mission

`V2-2A_PURE_FUNNEL_TRANSITION_ENGINE` — a deterministic, storage-agnostic engine
that consumes `MarketEvent` + `FunnelState` and produces `FunnelTransition` +
updated `OpportunityCandidate`, with no strategy adapter wired yet.

## Addendum (2026-09-21): Frontend freeze — non-negotiable, binding on all later phases

The owner has fixed a hard constraint on every remaining V2 phase: the existing
frontend (layout, pages, components, navigation, controls, styling, routes,
existing API calls, existing frontend-visible semantics) is frozen and out of
scope for this migration. No Opportunity Finder dashboard, no Execution Console
UI, no V2-terminology renames of existing controls. Frontend source is
read-only for this program except narrowly scoped test/config inspection.

Compatibility direction is fixed as `V2 internal object -> presentation/API
adapter -> existing API response -> existing frontend`, never the reverse
(`change API -> rewrite frontend`), unless a separately approved future mission
authorizes that migration. `RESEARCH_QUALIFIED` / research-only states must
never be presented as actionable `READY` merely to satisfy an existing UI
field; SSC must never be routed through `SESSION_TRADE_V1` merely for
presentation convenience — strategy identity stays authoritative even when
presentation is shared. Frontend execution controls stay governed by the
existing fail-closed authority model; a new `ExecutionDecision` contract must
never make a previously-blocked frontend control functional on its own.

Compliance as of this mission's own commit (`0be5bad`): no frontend, API, or
presentation-layer file was touched (`src/opportunity/`, `tests/`, and status
docs only — verified against `git show --stat`). `frontend_source_changed =
false`, `breaking_api_changes = false`. No compatibility adapter was needed
this mission because no presentation-facing work was in scope.

Updated roadmap (supersedes the "Future migration plan" section's original
V2-11/V2-12 entries): `Opportunity Finder API/UI` and `Execution Console` are
replaced by `V2-11 Existing API compatibility integration` and `V2-12 Existing
frontend regression validation` — no dedicated UI/redesign phase exists in this
program. Any future V2-4/V2-5 (ProposalEligibility, CanonicalProposal
integration) work touching a read model reachable by the existing frontend must
add API-compatibility regression tests (existing endpoints/fields/types remain
present and compatible, synthetic/replay/research states cannot become
executable or upgraded through presentation mapping, execution authority cannot
be upgraded by serialization) before merging, and must report
`BLOCKED_FRONTEND_COMPATIBILITY` with the exact endpoint/field/semantic
conflict rather than silently modifying frontend source.
