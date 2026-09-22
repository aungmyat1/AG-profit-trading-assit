# Panel-R3 Owner Decision Bridge -- Status (2026-09-22)

PANEL_R2_FROZEN_SHA = `40376ce51afc819951aebc7438511421cf6fe48e`
AUDIT = PANEL_R2_AUDIT_PASS (diff shape independently reconfirmed this pass: 5 files,
235 insertions, 0 deletions, matching `feat/panel-r2-opportunity-analysis` /
`remotes/origin/audit/panel-r2`; `tests/test_api_opportunity_analysis.py` 5/5 passing
unmodified).

R2 is treated as immutable from this work package onward. No file under R2's own diff
(`src/api/opportunity_analysis.py`, `src/api/schemas.py`'s R2 additions, `src/api/app.py`'s
R2 additions, `tests/test_api_opportunity_analysis.py`,
`docs/status/AG_PANEL_R2_OPPORTUNITY_ANALYSIS_READ_MODEL.md`) was modified by this change.

## Integration state

`origin/main` (`570e755`) is an ancestor of the R2 SHA -- R2 already carries every
commit on `origin/main` plus `729a4a6`/`cf9941d` (the `wp/v2-4-canonical-proposal-bridge`
CanonicalProposal bridge work) and the post-Asian observe-only/status-readonly fixes.
R2 itself is NOT yet reachable from `origin/main` (`PANEL_R2_INTEGRATION=NOT_YET_ON_MAIN`
from `origin/main`'s perspective; a fast-forward would be safe if/when someone chooses
to push it, but nothing here pushes). This R3 branch is based directly on the R2 SHA, so
it carries the correct integration lineage without a synthetic merge commit.

## What already existed (investigated before writing anything new)

Before adding any new type, this pass grepped for existing `OwnerDecision`/
`ExecutionDecision`/`TradeTicket`/`CanonicalProposal` shapes (mission P5) and found:

- `proposal_envelope.models.CanonicalProposal` -- already carries governance fields
  `demo_authorized`, `live_authorized`, `demo_eligible`, `proposal_only`,
  `broker_mutation_blocked`, `execution_eligible`, `lifecycle_stage`, sourced from
  `strategies/registry.yaml` via `proposal_envelope.strategy_authority` -- never
  invented here.
- `assistant.canonical_proposal_adapter` -- already implements
  `CanonicalProposal -> TradeCandidate -> TradeProposal -> TradeCommand template`
  (an unconfirmed `execution.models.TradeCommand`, `source=ASSISTANT_PROPOSAL`), and
  explicitly documents that execution stops there pending
  `assistant.commands.execute_command()`.
- `assistant.commands.build_proposal_from_canonical` -- persists that `TradeProposal`
  into the same store `execute_command()` reads.
- A SEPARATE, already-audited execution-approval pathway also exists:
  `authorization.store.ExecutionApprovalStore` + `api.execution_service.
  authorize_demo_execution` + `authorization.mt5_execution_handler`, wired to
  `POST /api/tickets/{approval_id}/authorize-demo`. This pathway is keyed on
  `execution.adapter.TradeProposal` (a `strategy_engine.sweep_retest.SetupState`-sourced
  shape used by the crypto/BTC sweep-retest vertical) -- a DIFFERENT proposal-identity
  scheme from `proposal_envelope.models.CanonicalProposal` (consistent with the
  previously-recorded WP0 finding of multiple parallel proposal-identity schemes).
  Reconciling those two schemes is explicitly out of this work package's scope
  (mission P11); PANEL_R3 does not touch or duplicate that pathway.

Given the above, the smallest correct PANEL_R3 deliverable is a thin, new
`owner_decision` package that adds the one piece that did not already exist for the
CanonicalProposal vertical: a typed, idempotent, explicit `OwnerDecision ->
ExecutionDecision` step in front of the already-built (but previously unreachable by
any explicit owner action) `TradeCommand template` step.

## New module: `src/owner_decision/`

- `models.py` -- `OwnerDecision` (decision_id, proposal_envelope_id, action, symbol,
  environment, decided_at, actor) and `ExecutionDecision` (decision_id,
  proposal_envelope_id, status, reason_code, reasons, trade_command).
- `bridge.py` -- `evaluate_owner_decision(decision, envelope, *, store, now)`, the
  single evaluation function, plus `OwnerDecisionStore` (process-local, lock-protected,
  idempotent by `decision_id`).

Fail-closed checks, in order: idempotency replay -> malformed decision/action ->
REJECT (terminal, never authorizes) -> environment must equal `"DEMO"` -> envelope
present -> envelope identity matches decision -> symbol matches -> `proposal_state ==
PROPOSAL_READY` -> `demo_authorized is True` -> `broker_mutation_blocked is False` ->
`plan_expires_at` not already passed -> build the `TradeCommand` template (no I/O beyond
the existing, already-execution-free `build_proposal_from_canonical` proposal-store
write).

The module imports only `assistant.canonical_proposal_adapter`,
`assistant.commands.build_proposal_from_canonical`, and `proposal_envelope.models`. It
does not import `execution.executor` or `execution.mt5_gateway`, and it never sets
`user_confirmed=True` -- see `tests/test_owner_decision_bridge.py::
test_bridge_module_never_imports_execution_executor_or_mt5_gateway` (AST-based import
check, not a string grep).

## What AUTHORIZED means here -- and what it does not

An `AUTHORIZED` `ExecutionDecision` carries a PREPARED, UNCONFIRMED
`execution.models.TradeCommand`. Constructing/returning it performs no
`order_check`/`order_send` (this is `TradeCommand`'s own pre-existing contract).
Reaching an actual Demo broker order still requires a SEPARATE, later call this module
never makes: `assistant.commands.execute_command(trade_command, user_confirmed=True)`,
where `user_confirmed` must be derived from an explicit user instruction that same turn
(AGENTS.md Authority order point 3). No HTTP endpoint was added in this pass that could
turn an owner's panel click directly into that confirmed call -- see
"Next recommended package" below for why that boundary needs its own design pass rather
than being punched through here.

## Tests

`tests/test_owner_decision_bridge.py` -- 16 tests covering all 10 mission-required
semantic points (valid approval -> AUTHORIZED; reject -> never AUTHORIZED;
view/select structurally cannot reach the bridge; missing decision fails closed; stale
proposal fails closed; malformed decision fails closed x3; duplicate decision_id
returns the same prior outcome, never re-derives; LIVE environment rejected;
demo_authorized=False / broker_mutation_blocked=True governance never bypassed;
scheduler/alerting modules structurally never import `owner_decision`; the bridge
module itself never imports `execution.executor`/`execution.mt5_gateway`).

Command: `python -m pytest tests/test_owner_decision_bridge.py -q` -> 16 passed.

Regression (same suite P1 ran against frozen R2, now including the two new test
files): `python -m pytest tests/test_api_opportunity_analysis.py tests/test_api.py
tests/test_api_canonical_proposals.py tests/test_post_asian_observe_only_remediation.py
tests/test_post_asian_status_readonly_remediation.py tests/test_post_asian_pilot.py
tests/test_proposal_envelope_execution_boundary.py tests/test_proposal_envelope_adapters.py
tests/test_assistant_canonical_proposal_adapter.py tests/test_owner_decision_bridge.py -q`
-> 206 passed, 1 failed (the same pre-existing, out-of-scope
`test_fx_repeated_same_setup_same_date_is_not_deduplicated_in_current_cutover` failure
already documented against the R2 baseline; unrelated to this change and not
introduced by it).

## Safety

No strategy economics, SSC/Asian-Sweep/Large-SMC rules, backtest thresholds,
validation datasets, or scheduler behavior were touched. `config/trading.yaml`'s
`account.allow_live_trading` gate and `mt5.account`'s live `is_demo` gate are untouched
and remain the authoritative Demo/Live boundary; this bridge's own `environment ==
"DEMO"` check is additive, never a replacement for them.

## Next recommended package

An HTTP surface (e.g. `POST /api/canonical-proposals/{proposal_id}/owner-decision`)
that lets the Owner Analysis Panel actually call `evaluate_owner_decision` and, on
`AUTHORIZED`, a SEPARATE explicitly-confirmed call to `execute_command(...,
user_confirmed=True)`. The open design question this package must resolve first: what
about a given HTTP request legitimately constitutes "the user's own message this turn
was an explicit execution instruction" (AGENTS.md Authority order point 3) for a
panel-driven (not conversational-assistant-driven) flow -- e.g. a required second
confirmation step, session/auth binding, and replay protection at the transport layer
-- so that reaching `user_confirmed=True` from an HTTP POST is a deliberate, reviewed
decision rather than an implicit one made by wiring an endpoint.
