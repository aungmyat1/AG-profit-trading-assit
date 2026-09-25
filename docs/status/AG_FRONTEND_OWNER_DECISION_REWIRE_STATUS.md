# AG Frontend Owner-Decision Canonical Rewire — Status

**Class:** `STATUS_EVIDENCE`. **Current as of:** 2026-09-23, branch
`feat/frontend-owner-decision-rewire`, baseline `e7e9583749bebade5b89c4c53c9af97739d5f20f`
(`FINAL_DEMO_EXECUTION_GATE_INDEPENDENT_REAUDIT_PASS`). Frontend-only change set;
`src/` is unmodified.

## Summary

`web/src/components/OwnerAnalysis/OwnerAnalysisPanel.tsx` previously targeted four
endpoints that do not exist in this repo (`/api/owner-analysis/reject`,
`/prepare-demo`, `/cancel-demo`, `/confirm-demo`) — a known, already-documented gap
(`PROJECT_STATUS.md`'s prior `AG_FINAL_DEMO_EXECUTION_GATE` entry, and
`docs/status/AG_FINAL_DEMO_EXECUTION_GATE_STATUS.md`). This package rewires the panel
to the real, already-frozen backend surface instead: the canonical proposal read
model, the opportunity-analysis read model, and the authenticated owner-decision
endpoint (`owner_decision.bridge.evaluate_owner_decision`, PANEL-R3/R4/R5A). Nothing
under `src/` changed; scope is `web/`, this document, and `PROJECT_STATUS.md`.

## Old → new endpoint mapping

| Old (fictional, 404) | New (real, frozen) |
|---|---|
| `POST /api/owner-analysis/reject` | `POST /api/canonical-proposals/{id}/owner-decision` with `action: "REJECT"` |
| `POST /api/owner-analysis/prepare-demo` | `POST /api/canonical-proposals/{id}/owner-decision` with `action: "APPROVE_DEMO"` (response's `execution_decision_prepared`/`trade_command` is the "prepared" state — there is no separate prepare step) |
| `POST /api/owner-analysis/cancel-demo` | Not reproduced. There is no cancel/undo route on the real backend; a REJECT decision is terminal for the derived `decision_id`, and the panel does not claim a cancel capability it doesn't have. |
| `POST /api/owner-analysis/confirm-demo` | No separate confirm route exists — `owner-decision` with `action: "APPROVE_DEMO"` is itself the one owner-facing confirmation call; it only ever produces a PREPARED, UNCONFIRMED `TradeCommand` template, never a submitted order (AGENTS.md Authority order point 3; the actual execution call is a separate, later, explicitly-confirmed path this package does not touch). |
| (proposal data source) `proposals.find(p => p.symbol === selectedSymbol)` over `generateClientProposals()` (synthetic, `marketDataSource: 'SYNTHETIC'`) | `agApiClient.listCanonicalProposals()` filtered by symbol (real `CanonicalProposalResponse[]`, backed by `proposal_envelope.ledger.ProposalLedger`) |

## `decision_id` design and the `DECISION_ID_CONTRACT_AMBIGUOUS` finding

`OwnerDecision.decision_id`'s own docstring (`src/owner_decision/models.py:35-37`)
frames it as minted per-click/per-attempt, but `evaluate_owner_decision` checks
idempotency strictly by `decision_id` first (`bridge.py:239-246`) and neither
`src/owner_decision/` nor `proposal_envelope.ledger.ProposalLedger` enforces any
proposal-level "one decision per proposal" uniqueness anywhere. This is a genuine gap
in the frozen backend, not fixed here (out of scope: `src/` is untouched).

**Mitigation applied (frontend-only, explicit scope):** `deriveDecisionId(proposalId)`
= `` `OWNER_DECISION:${proposalId}` `` (`web/src/components/OwnerAnalysis/ownerDecisionLogic.ts`)
instead of a fresh UUID per click. This is **frontend retry/recovery defense-in-depth
from THIS panel instance only** — it is explicitly NOT a system-wide guarantee:

```
PROPOSAL_LEVEL_OWNER_DECISION_UNIQUENESS = NOT_ENFORCED_BY_BACKEND
CROSS_CLIENT_AT_MOST_ONCE = NOT_GUARANTEED
```

What the mitigation does provide, precisely: (a) a lost/retried response after
CONFIRM, from the same browser tab/session, replays safely against the same
idempotency key — no reprocessing; (b) a browser refresh in that same session can
re-derive the same key purely from the `proposal_id` already in hand — the only
recovery path available without a new backend read route (none exists to read back a
prior decision by proposal id); (c) from this UI, a second click of the *other* button
against the same proposal surfaces as `ALREADY_DECIDED_MISMATCH` (the stored,
original outcome is shown, never presented as if the new click took effect or
replaced the prior result) rather than silently appearing to succeed. It does **not**
prevent a second, independently-minted `decision_id` (a second tab, a different
device, any client not using this derivation) from producing an independent
`AUTHORIZED` outcome server-side for the same proposal.

**Recommendation for the next independent audit / a future backend change:** have the
bridge or `ProposalLedger` reject a second decision against an already-decided
proposal regardless of `decision_id` (e.g. a proposal-keyed "decided" marker checked
before `evaluate_owner_decision` re-derives a `TradeCommand`), rather than relying on
any client's `decision_id` derivation choice.

## Owner-key authentication design

Manual entry, in-memory only (`OwnerAnalysisPanel`'s local `ownerKeyInput` state).
Never written to `localStorage`/`sessionStorage`/source/bundle; never logged (error
paths render only `AgApiError.message`/`.kind`, never headers/bodies); never placed in
a URL/query parameter — it travels only as the `X-AG-Owner-Key` header on the one
`agApiClient.submitOwnerDecision` call; never exposed through `import.meta.env`.
Cleared on refresh — re-entry is required after a page reload. This is accepted
friction for a safety-critical shared secret and keeps `agApiClient.ts`'s "no secret
ever flows through this module" docstring true for every call except this one, which
takes the key as a per-call parameter rather than storing it (documented inline at the
`submitOwnerDecision` definition).

Backend auth (`require_owner_auth`, `src/api/app.py:137-162`) is unchanged: 503
`{"reason_code": "OWNER_AUTH_NOT_CONFIGURED"}` if `AG_OWNER_API_KEY` is unset, 401
`{"reason_code": "OWNER_AUTH_REJECTED"}` on a missing/incorrect header,
`hmac.compare_digest` comparison.

**Outcome-classification note (503 is not collapsed into a single "auth failed"
bucket):** `classifySubmissionOutcome` distinguishes three server-side failure kinds
that were previously conflated:
- `AUTH_FAILED` ⟵ HTTP 401 only (`OWNER_AUTH_REJECTED` — a real, distinguishable bad/
  missing owner key).
- `AUTH_NOT_CONFIGURED` ⟵ HTTP 503 **and** the response body contains
  `OWNER_AUTH_NOT_CONFIGURED` — a server misconfiguration (`AG_OWNER_API_KEY` unset),
  not a wrong key. Detected by substring match on `AgApiError.message`, which embeds
  the parsed JSON error body verbatim (see `agFetch` in `agApiClient.ts`).
- `SERVER_UNAVAILABLE` ⟵ any other 5xx, including a 503 whose body doesn't parse or
  doesn't carry that specific `reason_code` (e.g. a proxy/network-level 503) — never
  assumed to be an auth problem.

## Multi-proposal-per-symbol selection UX

`proposal_envelope.ledger.ProposalLedger` enforces no symbol-uniqueness, so
`.find(p => p.symbol === selectedSymbol)` (array order) is not a deterministic,
authoritative selection. `App.tsx` now computes
`canonicalProposalsForSymbol = canonicalProposals.filter(p => p.symbol === selectedSymbol)`
and passes the whole array to `OwnerAnalysisPanel`. The panel: zero matches → "no
proposal available" read-only state; exactly one match → used directly; more than one
→ an explicit selection list (`proposal_id`, `strategy_id`, `direction`,
`proposal_state`) is rendered and a manual selection is required before CONFIRM/REJECT
become available. `proposal_id` remains the only identity ever used for the actual API
calls — never an implicit/array-order pick.

## `CLIENT_OUTCOME_UNKNOWN` naming rationale

A browser-side `NETWORK`/`TIMEOUT` `AgApiError` means *this client* does not know
whether the server processed the request. This is named `CLIENT_OUTCOME_UNKNOWN`, not
`SUBMISSION_UNKNOWN` — `OwnerDecisionResponse` exposes no distinct server-side
"submission" lifecycle state (there is no broker submission at this endpoint at all;
`execution_decision_prepared` is the only "prepared, not submitted" signal). The name
`SUBMISSION_UNKNOWN` is reserved and unused, for if/when an authoritative server-side
execution-lifecycle state by that name is ever introduced.

## `PROVENANCE_BLOCKED` / `ACCOUNT_BLOCKED` — grep result, not implemented behavior

Grepped `src/owner_decision/bridge.py` (the full, authoritative reason_code list is
`MALFORMED_DECISION, OWNER_REJECTED, NON_DEMO_ENVIRONMENT_REJECTED,
PROPOSAL_NOT_READY, DEMO_NOT_AUTHORIZED, BROKER_MUTATION_BLOCKED, SYMBOL_MISMATCH,
PROPOSAL_STALE, PROPOSAL_MALFORMED`) and case-insensitively across `src/` for
`provenance`/`account_blocked`-shaped reason codes — **no distinct
`PROVENANCE_BLOCKED` or `ACCOUNT_BLOCKED` reason_code or route exists anywhere in this
frozen backend today.** `PROVENANCE_GATE_PRESERVED` and `DEMO_ACCOUNT_GUARD_PRESERVED`
below are therefore `NOT_APPLICABLE`, not verified/tested — the real data-provenance
gate (`proposal_envelope/formation_gate.py`) and the demo account guard
(`mt5.account_guard.verify_configured_account`, enforced in
`execution/mt5_gateway.py::order_send()`) sit downstream of this endpoint entirely (in
the separate, later, explicitly-confirmed execution path this package never reaches),
so this UI has no reachable trigger path to either today. `SubmissionOutcome` keeps
`PROVENANCE_BLOCKED`/`ACCOUNT_BLOCKED` as named, forward-compatible UI states (so a
future backend `reason_code` can be wired in without a frontend contract change) but
`classifySubmissionOutcome` never produces them from any reason_code that exists
today; any rejection reason not given a more specific bucket falls into the general
`REJECTED` outcome instead of being silently mapped to these.

## Panel state mapping (`SubmissionOutcome`, `web/src/components/OwnerAnalysis/ownerDecisionLogic.ts`)

| Outcome | Trigger | Copy behavior |
|---|---|---|
| `AUTHORIZED` | `status === 'AUTHORIZED'` | Explicitly "PREPARED but NOT submitted to any broker"; never rendered as "TRADE EXECUTED" |
| `REJECTED` | `reason_code === OWNER_REJECTED`, or any other real rejection reason_code not given a more specific bucket (`PROPOSAL_NOT_READY`, `BROKER_MUTATION_BLOCKED`, `NON_DEMO_ENVIRONMENT_REJECTED`, `MALFORMED_DECISION`) | Plain "Rejected by backend (reason_code)" |
| `EXECUTION_DENIED` | `reason_code === DEMO_NOT_AUTHORIZED` | Names strategy governance / `strategies/registry.yaml` explicitly |
| `SYMBOL_MISMATCH` / `PROPOSAL_STALE` / `PROPOSAL_MALFORMED` | matching reason_code | Distinct, plain-language copy per case |
| `ALREADY_DECIDED_MISMATCH` | replayed stored outcome's underlying action disagrees with the just-clicked action | "Already decided: ... your click did not take effect — the stored decision is authoritative and immutable" |
| `AUTH_FAILED` | HTTP 401, or the frontend's own pre-submit check when the owner key field is empty | "wrong or missing key" |
| `AUTH_NOT_CONFIGURED` | HTTP 503 with `OWNER_AUTH_NOT_CONFIGURED` body | "server misconfiguration, not your key" |
| `NOT_FOUND` / `CONFLICT` | reserved (no current backend path produces these on this route — the route never 404s; see below) | n/a today |
| `CLIENT_OUTCOME_UNKNOWN` | `AgApiError.kind` is `NETWORK`/`TIMEOUT` | Explains the request may or may not have been processed; safe to retry (same `decision_id`) |
| `SERVER_UNAVAILABLE` | other 5xx | Generic backend-unavailable copy |
| `ERROR` | anything else (PARSE, unexpected status) | Generic, but never the sole catch-all for a known case |

Note: the owner-decision route itself never returns HTTP 404 for an unknown
`proposal_id` — an unknown/missing proposal returns HTTP 200 with
`status="REJECTED", reason_code="PROPOSAL_NOT_READY"` (`bridge.py:267-271`, envelope
is `None`), which classifies to the general `REJECTED` outcome above, not `NOT_FOUND`.

## Verification

### Frontend (`web/`, from this worktree)

- `npm install` — 266 packages added (no prior `node_modules`).
- `npm run lint` (`tsc --noEmit`) — clean, no errors.
- `npm run test` — includes the new `tests/owner_decision_panel_logic.test.ts`
  (appended to `package.json`'s `test` script after the existing four files).
  **48/49 pass.** The one failure —
  `tests/wp0a_execution_route_containment.test.ts`: "server.ts source contains no
  real-mode spawn of a broker-mutating script" — is **pre-existing and unrelated to
  this package**: `web/server.ts` is untouched by this change set
  (`git diff e7e9583..HEAD -- web/server.ts` is empty) and was last modified by a
  prior commit (`74d65ea`, before this baseline) on this branch's history. On a
  second full run it and the `vantage_mt5_crypto_venue.test.ts` suite (which failed
  in a first run with "server did not become ready in time") both passed — those
  server-spawn tests are flaky on first invocation (cold-start compile time) in this
  environment, not a regression introduced here; the second run's 48/49 result is the
  representative one.
- `npm run build` (`vite build && esbuild server.ts ...`) — succeeds,
  `dist/server.cjs` produced.

### Backend regression (evidence only — `src/` unmodified)

Ran with the shared repo venv (`D:\ddev\AG profit trading\.venv`, no venv exists
inside this worktree, which is expected — venvs aren't tracked in git):

```
python -m pytest tests/test_api_owner_decision.py tests/test_api_owner_decision_auth.py \
  tests/test_owner_decision_bridge.py tests/test_owner_decision_store_persistence.py \
  tests/test_api_opportunity_analysis.py tests/test_proposal_dedup_r1.py \
  tests/test_td6_deterministic_dedup_targets.py tests/test_mt5_account_guard.py \
  tests/test_bias_provenance_e2e.py -q
```
Result: **77 passed**, 0 failed (676 warnings, all pre-existing deprecation notices
unrelated to this change).

### CONFIRM→governance-denial integration proof

Method used: **direct call to `owner_decision.bridge.evaluate_owner_decision()`**
(the acceptable substitute named in the mission brief), via the repo's own existing
fixture/test — `tests/test_owner_decision_bridge.py::test_demo_not_authorized_governance_is_never_bypassed`
(lines 209-218), which calls `evaluate_owner_decision(_decision(), _envelope(demo_authorized=False), store=OwnerDecisionStore())`
and asserts `result.status == EXECUTION_DECISION_REJECTED` and
`result.reason_code == REASON_DEMO_NOT_AUTHORIZED`. This test ran and passed as part
of the 77-test run above — no new fixture pattern was invented. Confirmed by reading
(not merely by absence of a failure): `src/owner_decision/bridge.py`'s import block
(lines 49-57) imports only `assistant.canonical_proposal_adapter`,
`assistant.commands.build_proposal_from_canonical`, `execution.models`
(`ExecutionSource`, `TradeCommand` — dataclasses only), `proposal_envelope.models`,
and `runtime_state.store` — there is no import of `execution.executor` or
`execution.mt5_gateway` anywhere in this module, so no code path in
`evaluate_owner_decision()` can reach `order_check`/`order_send`. No dev server was
started; no MT5/broker connection was made.

### Diff scope

- `git diff e7e9583..HEAD -- strategies/registry.yaml` → empty.
- `git status --short` (uncommitted at time of writing) touches only:
  `web/package.json`, `web/src/App.tsx`,
  `web/src/components/OwnerAnalysis/OwnerAnalysisPanel.tsx`,
  `web/src/utils/agApiClient.ts` (modified), plus two new files:
  `web/src/components/OwnerAnalysis/ownerDecisionLogic.ts`,
  `web/tests/owner_decision_panel_logic.test.ts`. No file under `src/`,
  `strategies/`, `config/`, `mt5/`, or `execution/` changed.

## Known limitations

- No backend GET route exists to read back a prior owner-decision's status by
  proposal/decision id. Recovery after a refresh relies entirely on the bridge's own
  idempotent replay via `deriveDecisionId`, as documented above — not a new read
  route (none was added; out of scope).
- `agApiClient.authorizeDemo` (the legacy `/api/tickets/{id}/authorize-demo` flow) was
  left untouched, including its pre-existing missing-auth-header gap (it does not send
  `X-AG-Owner-Key`) — out of scope for this package; noted here only for visibility.
- `PROVENANCE_BLOCKED`/`ACCOUNT_BLOCKED` UI states exist in code as forward-compatible
  placeholders but are not reachable today — see the dedicated section above.
- `DECISION_ID_CONTRACT_AMBIGUOUS` is mitigated client-side only, not closed — see
  the recommendation above for the next independent audit / a future backend change.

## Test commands (for reproduction)

```
cd web && npm run lint && npm run test && npm run build
python -m pytest tests/test_api_owner_decision.py tests/test_api_owner_decision_auth.py \
  tests/test_owner_decision_bridge.py tests/test_owner_decision_store_persistence.py \
  tests/test_api_opportunity_analysis.py -q
```
