# AG Final Demo Execution Gate — Status (2026-09-23)

Branch: `feat/demo-execution-bridge` (off `wp/v2-3c-asian-sweep-remediation`,
HEAD `d3d4399`). Not merged, not pushed.

## Scope actually found vs. the prior read-only assessment

A prior read-only assessment (background evidence in this mission's brief) classified
the remaining work as a narrow final execution gate and named two frozen candidate
fixes plus a "materialize_execution_ticket" bridge as the missing piece. Re-verification
against the current repo showed the assessment was materially stale in three ways:

1. **The two frozen fixes were real but not yet integrated onto this line.**
   `R5C_R1_FROZEN_SHA=1c5bbf578daa8c4773a7bf6e50c6ae5fd375595c` (fail-closed broker
   reconciliation + broker-identity validation) and
   `PROPOSAL_DEDUP_R1_FROZEN_SHA=cbdf786f3c37e57adc514d033cb17277ac26bb85` (stable
   `setup_id`-based `proposal_envelope_id`, superseding `decision.decision_id`) both
   descend from `570e755` (common ancestor already in this branch's own history) and
   merged with **zero file-level conflicts** — no other work on this line touched any
   file either commit chain touches.
2. **The bridge already exists and is already production-wired**, contributed by the
   same merged chain (`panel-r3-owner-decision-bridge` .. `panel-r5c-r1-broker-identity`
   lineage): `src/owner_decision/bridge.py::evaluate_owner_decision()` +
   `src/owner_decision/models.py` (`OwnerDecision` / `ExecutionDecision`), fed by
   `proposal_envelope.ledger.ProposalLedger` (already durable, JSON-backed) and exposed
   at `POST /api/canonical-proposals/{proposal_id}/owner-decision`
   (`src/api/app.py:424-471`), gated by `require_owner_auth` (X-AG-Owner-Key). This
   satisfied nearly all of work packages P3-P8 and P13-P17 (mandatory Demo-account
   guard, real-data provenance, strategy-authorization respect) before this session
   started. See CALL_GRAPH below.
3. **`ExecutionApprovalStore`/`InMemoryProposalRegistry`/`authorize_demo_execution()`**
   (the mechanism the assessment named) genuinely does have zero production callers —
   confirmed by `grep -rn "proposal_registry\.register\|store\.create(" src/` finding
   only a code comment — but it is a *separate, older, orphaned* execution-ticket
   pathway (its own HTTP routes exist: `/api/tickets/*`, `/api/executions/*`,
   `/api/tickets/{id}/authorize-demo`) that nothing in production ever populates. It is
   NOT the pathway a real proposal reaches today; the newer `owner_decision` +
   `ProposalLedger` pathway above is. This session did not wire proposals into the
   older store, since doing so would build a second, redundant proposal→ticket path —
   forbidden by the mission's own "do not build a second execution engine" constraint.
   `ExecutionApprovalStore` itself is also *not* in-memory-only as the assessment
   claimed — `src/authorization/store.py:95-97` backs it with
   `runtime_state.store.JsonKeyValueStore` under `journal/` by default.

## What this session actually built

The one genuine remaining gap, once the above was verified: **`OwnerDecisionStore`
(`src/owner_decision/bridge.py`) was in-memory-only** ("a restart loses it" — its own
prior docstring), unlike every other durable primitive in this chain
(`ProposalLedger`, `ExecutionApprovalStore`, `execution.durable_idempotency.
DurableExecutionStore`). An ordinary process restart between "owner clicked Confirm"
and the separate, later, explicitly-confirmed `execute_command()` call could silently
lose the PREPARED `TradeCommand` template, or let an HTTP retry after restart
re-derive a decision against a since-changed proposal envelope instead of returning
the original durable outcome.

Fix (additive, `src/owner_decision/bridge.py` + `src/api/app.py`):

- `OwnerDecisionStore.__init__` gained an optional `path` parameter. `path=None`
  (every existing test's default) is byte-for-byte the original in-memory behavior —
  zero behavior change for any existing caller. Passing a path backs the store with
  `runtime_state.store.JsonKeyValueStore` (the same atomic temp-file + `os.replace`
  convention already used by `ProposalLedger`, `ExecutionApprovalStore`, and
  `DurableExecutionStore` — no new persistence mechanism introduced).
- `src/api/app.py`'s production singleton now reads
  `OwnerDecisionStore(path=DEFAULT_OWNER_DECISION_STORE_PATH)` where
  `DEFAULT_OWNER_DECISION_STORE_PATH = "state/owner_decisions/owner_decisions.json"`.
- A corrupt/unreadable on-disk ledger fails closed (`OwnerDecisionStoreUnavailable`),
  never silently starts empty — matching this repo's established fail-closed
  persistence convention (`StateStoreCorrupted` → `IdempotencyStateUnavailable` in
  `execution.durable_idempotency`, the same shape).
- Concurrency: `OwnerDecisionStore`'s own lock plus `JsonKeyValueStore`'s per-path
  lock (shared across independently-constructed instances pointed at the same path)
  serialize concurrent writers within one process — new test proves 8 threads racing
  the identical `decision_id` converge on exactly one durable record. Explicitly
  NOT cross-process/cross-machine safe (nothing in this repo runs more than one
  process against this store today — same documented boundary as
  `DurableExecutionStore`).

New test file: `tests/test_owner_decision_store_persistence.py` (5 tests): restart
survival for AUTHORIZED and REJECTED outcomes, unchanged in-memory default behavior,
fail-closed corrupt-file handling, and the 8-thread concurrent-confirm race.

## Real-data provenance and strategy authorization (verified, not built)

`src/proposal_envelope/formation_gate.py` already blocks any envelope whose
`market_snapshot.market_data_mode != MARKET_DATA_MODE_REAL` from ever reaching
`PROPOSAL_READY` (`REASON_NON_REAL_MARKET_MODE`), and is already wired into the actual
production pipelines (`post_asian_pilot/pipeline.py`, `opportunity/adapter.py`).
`evaluate_owner_decision()` requires `envelope.proposal_state == PROPOSAL_READY`
before it will ever authorize anything, so a SYNTHETIC/REPLAY/mode-less proposal is
already unreachable through this bridge — existing coverage:
`tests/test_proposal_formation_gate.py`. No new provenance field or check was added;
none was needed.

`demo_authorized` / `broker_mutation_blocked` governance flags on `CanonicalProposal`
(sourced from `strategies/registry.yaml` via `proposal_envelope.strategy_authority`)
are enforced verbatim and unbypassed in `evaluate_owner_decision()` (`REASON_
DEMO_NOT_AUTHORIZED`, `REASON_BROKER_MUTATION_BLOCKED`) —
`git diff cbdf786f..HEAD -- strategies/registry.yaml` is empty; no registry value was
touched by this session.

## Demo account guard (verified, not built)

`execution/mt5_gateway.py::order_send()` already calls `_account_authorized_for_send()`
→ `mt5.account_guard.verify_configured_account()` unconditionally before
`mt5.order_check`/`mt5.order_send` (`src/execution/mt5_gateway.py:180-187`) — not
gated behind the opt-in `AG_DEMO_READINESS_AUDIT` env var the prior assessment
described. That opt-in path (`execution/readiness.py`) is a separate pre-flight audit
tool, additive to, not a substitute for, the mandatory gate in `mt5_gateway.py`.
Existing coverage: `tests/test_execution_mt5_gateway.py::
test_account_authorized_for_send_blocks_on_identity_mismatch`.

## Known limitation — frontend not wired to the real endpoint

`web/src/components/OwnerAnalysis/OwnerAnalysisPanel.tsx` (added on this branch's own
prior commit, `d3d4399`, for the WP3A1 friction-campaign work) is UI-only scaffolding:
it targets a `TradeProposal` shape from `web/src/types/trading.ts` and calls
fictional endpoints (`/api/owner-analysis/reject`, `/prepare-demo`, `/confirm-demo`,
`/cancel-demo`, `/{id}/chart.png`) that do not exist in `src/api/app.py`. The real,
audited, production-wired confirmation surface is
`POST /api/canonical-proposals/{proposal_id}/owner-decision`
(`OwnerDecisionRequest`/`OwnerDecisionResponse` in `src/api/schemas.py`), gated by
`X-AG-Owner-Key`. `web/src/components/Execution/ExecutionCockpit.tsx` has its own,
separate, pre-existing Confirm modal wired to the legacy `/api/execution/claim` path
(`ExecutionApprovalStore`/`InMemoryProposalRegistry` — see above, not fed by any
producer). Rewiring `OwnerAnalysisPanel.tsx` to the real `owner-decision` contract is
a genuine remaining frontend task, but it is a data-model rewrite (different proposal
shape, different two-call vs. one-call flow), not a small adjustment — attempting it
without full context on the component's intended WP3A1 role risked scope creep and an
unreviewed UI regression, so this session left it unchanged and reports it here as the
next concrete follow-up rather than guessing at a rewrite. No second execution UI was
created.

## Tests

- Frozen R5C-R1 + dedup R1 focused suites: 35/35 passed (pre-integration check, P2).
- Combined frozen-fix + bridge + persistence + opportunity + post-Asian regression
  (17 files, 217 tests): 217/217 passed.
- New: `tests/test_owner_decision_store_persistence.py` — 5/5 passed.
- Zero MetaTrader5/order_check/order_send calls reachable from any new or modified
  code path: `owner_decision.bridge` has an existing structural test
  (`test_bridge_module_never_imports_execution_executor_or_mt5_gateway`) and the new
  persistence tests import neither `mt5` nor `MetaTrader5`.
- Full `tests/` suite: see PROJECT_STATUS.md rolling snapshot for the exact count
  recorded at commit time.

## Safety

`strategies/registry.yaml` unchanged. No `execution/`, `mt5/`, or lifecycle-graph
files touched. `config/trading.yaml` untouched. No LIVE authorization added or
implied. `state/fx_schedule/slot_ledger.json` (pre-existing uncommitted modification,
unrelated to this work) was left untouched and is not part of this change set.

## Files changed (working set, on top of the frozen-fix merge commit)

- `src/owner_decision/bridge.py` — `OwnerDecisionStore` persistence extension.
- `src/api/app.py` — production singleton now durable.
- `tests/test_owner_decision_store_persistence.py` — new.
- `docs/status/AG_FINAL_DEMO_EXECUTION_GATE_STATUS.md` — this file.
- `PROJECT_STATUS.md` — rolling snapshot updated.

## Next action

Independent re-audit of this package, then (owner decision, out of scope here):
rewire `OwnerAnalysisPanel.tsx` to the real `owner-decision` contract, and decide
whether any in-repo strategy should move to `demo_authorized: true` in
`strategies/registry.yaml` (currently none are — this session verified but did not
change that).
