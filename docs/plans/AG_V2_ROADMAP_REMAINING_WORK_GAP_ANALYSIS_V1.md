# AG V2 Roadmap — Remaining-Work Gap Analysis V1

**Status:** `READ_ONLY_ANALYSIS` / **NON-AUTHORIZING**
**Class:** ROADMAP analysis derived from existing authorities — not new milestone evidence
**Date:** 2026-09-23
**Verified against:** branch `arena/01a0cfad-ag-profit-trading-assit` @ `570e755`
(`fix(v2): WP-3 R1 -- fail closed on unknown funnel stage in ProposalEligibility`), working tree clean

**Authority boundary:** this document grants no strategy, proposal, risk, execution,
Demo, Live, broker-send, or external-delivery authority. It authors nothing new — it
maps existing repository evidence onto the forward plan. Where it disagrees with
`PROJECT_STATUS.md`, `docs/PROJECT_ROADMAP.md`,
`docs/v2/AG_V2_IMPLEMENTATION_ROADMAP.md`, or
`docs/governance/AG_MULTI_AGENT_EXECUTION_PROTOCOL_V1.md`, those sources win. Every
claim below is derived from committed files or from the read-only verification run
recorded in section 8.

---

## 1. What the project objective actually is

The objective is a **governed chain**, not a strategy runner
(`docs/PROJECT_ROADMAP.md`, `PROJECT_IMPLEMENTATION_PLAN.md` §4):

```text
Market/Data Authority -> MarketEvent -> StrategyBinding -> Strategy Adapter
  -> Universal Funnel -> OpportunityCandidate -> Proposal Eligibility
  -> CanonicalProposal -> Portfolio RiskDecision -> ExecutionDecision
  -> SVOS first / Manual execution / Broker later
```

with two **independent** success tracks that must never be collapsed:

| Track | Owner of truth | Current program vehicle |
|---|---|---|
| Platform/engineering readiness | `docs/PROJECT_ROADMAP.md` R0–R9 + WP-0..WP-11 | reaches `PLATFORM_DEMO_READY` at WP-11 |
| Strategy economic qualification | R5/R6 evidence + signed thresholds | V2-14 → V2-15 → future Live |

Governing invariants that constrain every remaining item:

```text
PLATFORM_DEMO_READY        != STRATEGY_DEMO_ELIGIBLE
IMPLEMENTED                != VALIDATED
OpportunityCandidate       != CanonicalProposal
CanonicalProposal          != RiskDecision
RiskDecision               != ExecutionDecision
ExecutionDecision          != BrokerOrder
SVOS_PASS                  != ECONOMIC_GATE_PASS
ECONOMIC_GATE_PASS         != DEMO_AUTHORIZATION
```

Current R0–R9 position (`PROJECT_STATUS.md`, unchanged by this analysis):

| Gate | Value |
|---|---|
| R0 Safe Foundation | `READY` |
| R1 Research Watch | `READY / RESEARCH_ONLY` |
| R2 Real Market Watch | `READY` |
| R3 Canonical Strategy | `READY` |
| R4 Canonical Proposal | `READY / PASS` |
| R5 Edge Validation Evidence | `NOT_PASS` (only R5 evidence on record is negative) |
| R6 Economic Qualification | `NOT_PASS / NOT_EVALUABLE_MISSING_SIGNED_THRESHOLDS` |
| R7 Controlled Demo | `BLOCKED` |
| R8 Demo Qualification | `BLOCKED` |
| R9 Controlled Live | `BLOCKED` |

---

## 2. Verified current state (WP-0 .. WP-11)

| WP | Scope | State at HEAD `570e755` | Where it lives / evidence |
|---|---|---|---|
| WP-0 | V2-3 re-audit baseline freeze | `FROZEN` (LEVEL A closed) | `PROJECT_STATUS.md` (baseline commit recorded documentarily) |
| WP-1 | V2-3C Asian Sweep shadow adapter | `GATE_PASS` (owner-accepted) | `src/opportunity/asian_sweep_adapter.py`; `tests/test_opportunity_asian_sweep_adapter.py` |
| WP-2 | SSC active-routing removal | `OWNER_ACCEPTED_FROZEN`; independent audit PASS | `strategies/registry.yaml` now shows `active: false` for `ST_SESSION_SWEEP_CONTINUATION_V1`; SSC code/tests/evidence preserved |
| WP-3 | V2-4 ProposalEligibility bridge | `IMPLEMENTATION_COMPLETE` + `R1_REMEDIATION_APPLIED`; **re-audit not recorded** | `src/opportunity/proposal_eligibility.py`; `tests/test_opportunity_proposal_eligibility.py`; audit-finding fix in HEAD commit message |
| WP-4 | V2-5 CanonicalProposal bridge | `NOT_IMPLEMENTED` | no funnel→proposal bridge exists (`src/opportunity/` has none) |
| WP-5 | V2-7 Risk engine integration | `NOT_IMPLEMENTED` (no `RiskDecision` object exists) | only docstring reference in `src/opportunity/contracts.py` |
| WP-6 | V2-8 ExecutionDecision | `NOT_IMPLEMENTED` | `grep -rn "ExecutionDecision" src web` → one docstring reference only |
| WP-7 | MT5 runtime truth + reconciliation | `NOT_IMPLEMENTED` (partially pre-existing) | canonical readers exist (`src/mt5/account.py`, `deals.py`, `market_data.py`); mock-mode runtime truth surfaces remain |
| WP-8 | Manual Demo execution gate (LEVEL C) | `NOT_STARTED` as a governed gate; prior manual/explicit-command Demo paths exist | `src/assistant/commands.py::execute_command`, `src/authorization/`, `src/execution/readiness.py`, `web/server.ts` manual-demo route |
| WP-9 | V2-10 Scheduler migration | `NOT_IMPLEMENTED` | `web`/`MarketEvent` never reaches the scheduler; `MarketEvent` is referenced only inside `src/opportunity/` and `src/svos/virtual_time.py` |
| WP-10 | V2-11/V2-12 Frontend state sync | `NOT_IMPLEMENTED` (frontend frozen, unchanged) | no V2 read-model/compat adapter exists |
| WP-11 | V2-13 System E2E qualification | `NOT_IMPLEMENTED` | — |

**Code-level facts behind the table** (all read-only checks):

- `src/opportunity/` contains: `contracts.py`, `events.py`, `stages.py`,
  `transitions.py`, `engine.py`, `candidate_store.py`, `adapter.py`,
  `registry_binding.py`, `large_smc_adapter.py`, `ssc_adapter.py`,
  `asian_sweep_adapter.py`, `proposal_eligibility.py`.
- **Nothing outside `tests/` imports `opportunity`** — no `src/`, `scripts/`, API,
  scheduler, or frontend consumer. The V2 pipeline is currently a verified island; no
  runtime route reaches it.
- The live FX operational route is still the pre-V2 path
  (`scripts/install_fx_scheduler.ps1` → `scripts/run_fx_cycle_once.py` →
  `run_post_asian_pilot.py` → `post_asian_pilot/pipeline.py`), which already forms
  canonical proposals through `proposal_envelope.adapters.fx_adapter` +
  `formation_gate.apply_formation_gate` + `ProposalLedger` — but with no
  `OpportunityCandidate`, no `ProposalEligibilityDecision`, and no `RiskDecision`.
- SVOS engineering exists (`src/svos/`, Cycles 1–6A-R) but is **not** driven by an
  `ExecutionDecision`; capacity/parity proof remains `NOT_READY` on economic inputs.
- The frontend is frozen and unchanged; `web/server.ts` still defaults to
  `VITE_AG_API_MODE = 'mock'` with an explicit real-mode switch, and its manual-demo
  route already refuses to send unless real mode + DEMO account are satisfied.

---

## 3. What still has to be implemented

Ordered by dependency. Each item states the deliverable, the reuse constraint, the gate
class, and the evidence a gate closure needs.

### 3.1 Close the open gate on already-built work (do this first)

**WP-3 R1 independent re-audit — `LEVEL B`.**
The evaluator was changed at HEAD to fail closed on an unknown funnel stage
(`REASON_UNSUPPORTED_STATE` instead of a `ValueError`). No repository document records
the outcome of an audit of that remediation. Today the tree holds *code + tests*, not a
gate decision. Required to close: a dated audit record (`docs/status/`) stating
`WP3_GATE_PASS | REMEDIATION_REQUIRED`, plus the rolling `PROJECT_STATUS.md` note. Until
then WP-4 is not formally authorized to start.

### 3.2 WP-4 — V2-5 CanonicalProposal bridge (`LEVEL B`)

```text
OpportunityCandidate + ProposalEligibilityDecision(status=ELIGIBLE)
        -> existing formation gate
        -> CanonicalProposal
        -> existing ProposalLedger
```

Must be built:

- the funnel→proposal handoff (candidate revision + eligibility reason codes as lineage
  into the existing proposal record);
- occurrence/candidate identity continuity — one logical occurrence must not fan out
  into the 69-records-for-13-setups class of defect already documented in
  `docs/status/AG_VERSIONED_PROPOSAL_OCCURRENCE_IDENTITY_STATUS.md`;
- a fail-closed path for every non-`ELIGIBLE` status.

Must **not** be built: a second proposal model (`OpportunityProposalV2`), a second
ledger, or any economic interpretation inside the bridge. `ELIGIBLE` ≠ proposal ≠ risk
approval ≠ execution readiness.

**Exit evidence:** an end-to-end test from a real admitted market event through candidate
+ eligibility into a persisted `CanonicalProposal`, plus proof that non-REAL data modes
and non-ELIGIBLE decisions cannot reach the ledger.

### 3.3 WP-5 — V2-7 Portfolio RiskDecision engine (`LEVEL B`)

Nothing today produces a portfolio-level `RiskDecision`. Required surface: risk budget,
max concurrent positions, symbol conflicts, correlated exposure, account constraints,
portfolio exposure — with missing broker-dependent authority (leverage/margin) failing
closed or following the existing `DEFERRED_EXECUTION_PARITY` convention already recorded
in `src/svos/capacity_risk_contract.py`.

Reuse rather than reinvent: `src/execution/risk.py::size_position`,
`src/execution/daily_loss_guard.py`, `src/execution/position_guard.py`, and the repo
authority capacity limits (`max_open_positions = 1`, `ENGINEERING_NORMALIZED_1`).
Risk stays outside strategy signal logic.

**Hard requirement:** `orders_dispatched = 0`.

### 3.4 WP-6 — ExecutionDecision + authority model (`LEVEL B`)

```text
CanonicalProposal -> RiskDecision(APPROVED) -> ExecutionDecision
        -> EXECUTION_READY | OWNER_CONFIRMATION_REQUIRED
```

Combine proposal validity, `RiskDecision`, registry strategy authorization, account/venue
authority, data-mode restrictions, and owner-approval requirements into one **fail-closed**
decision. `automatic_execution = false` by default; creating an `ExecutionDecision` must
never call a broker or upgrade authorization.

**Exit evidence:** tests proving each missing/blocked input yields a non-ready decision,
and a static import-boundary proof that the module reaches no order path.

### 3.5 WP-7 — MT5 runtime truth and reconciliation (`LEVEL B`)

Replace remaining mock/placeholder runtime and account truth with canonical MT5 Demo
terminal truth. Canonical read surfaces already exist to reuse —
`mt5/account.py` (`account_info`, `positions_get`), `mt5/deals.py`
(`history_deals_get`), `mt5/market_data.py` (`symbol_info`, ticks) — so this is
reconciliation/wiring work, not new authority. No strategy changes, no order authority.

This WP also covers the mismatch/ambiguity cases WP-11 later exercises end to end
(account mismatch, symbol mismatch, terminal disconnect).

### 3.6 WP-8 — Manual Demo execution gate (`LEVEL C`, owner authority)

The first work package permitted to introduce an owner-authorized Demo `order_send()`
path, driven by an `ExecutionDecision`. Existing mechanisms must be inspected and reused
before any new token architecture is proposed:

- `assistant.commands.execute_command(..., user_confirmed=True)` — the single
  non-defaulted, per-turn owner-confirmation funnel (see `AGENTS.md` Authority order);
- `src/authorization/` (approval records, atomic claim, integrity checks);
- `src/execution/readiness.py::require_demo_execution_readiness` (tick freshness, volume
  normalization, stop/freeze levels, idempotency, position guard);
- the existing frontend manual-demo route boundary in `web/server.ts`.

Required invariants: AI cannot authorize; the scheduler cannot authorize; stale
authorization cannot authorize; authorization for trade A cannot execute trade B;
authorization cannot be replayed. No Live authority at any point.

### 3.7 WP-9 — V2-10 Scheduler migration (`LEVEL B`)

```text
CLOCK -> MarketEvent -> Opportunity Finder -> Candidate Store
      -> Eligibility -> Proposal pipeline
```

Today the FX scheduler launches the strategy path directly
(`run_fx_cycle_once.py` → `run_post_asian_pilot.py`) and never emits a `MarketEvent`.
The migration must route governed scheduler windows through `MarketEvent` while
preserving existing approved operating windows, session/time authority, catch-up rules,
deduplication, and research/proposal boundaries. No strategy semantics may move into the
scheduler.

### 3.8 WP-10 — V2-11/V2-12 Frontend state synchronization (`LEVEL B`)

Map V2 internal state onto the **existing** API/read-model contracts through
compatibility adapters. The frontend is frozen: no redesign, no renamed/removed
controls, no breaking API change. The backend remains authoritative; the frontend must
not independently compute trading truth, risk, or setup state. A genuine incompatibility
is reported as `BLOCKED_FRONTEND_COMPATIBILITY` with the exact conflict — never resolved
by editing the UI.

### 3.9 V2-6 — additional strategy adapters (roadmap item with no WP number)

Independent adapters for BTC liquidity-sweep and Asian/session strategies, each with its
own contract, preserving distinct semantics. Shared platform contracts must not collapse
strategy identity. This item is listed in the V2 sequence but not assigned a WP row in
`AG_MULTI_AGENT_EXECUTION_PROTOCOL_V1.md` — it needs an explicit WP assignment and gate
class before work starts.

### 3.10 WP-11 — System E2E qualification (`LEVEL B`)

```text
MT5 market data -> MarketSnapshot -> MarketEvent -> AsianSweepAdapter
  -> OpportunityCandidate -> ProposalEligibility -> CanonicalProposal
  -> RiskDecision -> ExecutionDecision -> OWNER_CONFIRMATION_REQUIRED
```

Must cover at least: restart recovery, duplicate polling, duplicate confirmation, stale
market data, terminal disconnect, frontend reconnect, scheduler restart, candidate
expiry, proposal expiry, account mismatch, symbol mismatch, risk rejection,
authorization expiry, post-order reconciliation.

Success may establish `PLATFORM_DEMO_READY`. It must **not** imply
`STRATEGY_DEMO_ELIGIBLE`.

### 3.11 Post-infrastructure: V2-13 / V2-14 / V2-15 and Live

- **V2-13** parity campaign (replay vs SVOS/virtual vs live observation): MarketEvent,
  strategy decision, candidate, proposal, risk, temporal, friction, restart, lifecycle.
- **V2-14** economic qualification per strategy/version — development evidence → failure
  decomposition → hypothesis testing → independent replication → friction analysis →
  robustness → prospective/virtual evidence → protected holdout → qualification.
  Allowed outcomes include `VALIDATED_NEGATIVE`; never force a pass to advance
  engineering.
- **V2-15** controlled per-strategy Demo qualification under explicit owner
  authorization (not automatic promotion).
- **Future** separate Live qualification program.

---

## 4. The parallel strategy-evidence lane (independent of WP progress)

Platform completion cannot create edge. What the evidence lane requires right now:

| Strategy | Current evidence state | What is needed to progress |
|---|---|---|
| `ST_ASIAN_SWEEP_5R_V1@1.1.1` (planned active FX V2 route) | R5 negative: 13/13 losing trades, gross expectancy `-1.00R`, net `-3.38R` under the one signed cost scenario; research `PAUSED_BY_OWNER` | Owner decision to resume research; a **signed, strategy-specific** economic threshold contract (the only signed contract, `config/governance/economic_gate_contract.yaml`, covers `ST_SESSION_SWEEP_CONTINUATION_V1 v1.0.1` only) before any economic claim; robustness/OOS under existing governance. Do not modify v1.1.1 to fit negative evidence |
| `ST_SESSION_SWEEP_CONTINUATION_V1` | Preserved negative/validation history; no longer the active FX route | Nothing required by the platform program; history must not be erased or rewritten |
| `ST_LIQUIDITY_SWEEP_RETEST_V1@2.0.0` (Crypto Sweep) | `RESEARCH_DESCRIPTIVE` (Binance VISION BTC/ETH research, already peeked) | Historical evidence freeze → G3 preregistration → robustness → prospective evidence → economic qualification. Peeked data must never be re-labeled as untouched holdout |
| `ST_LARGE_SMC_V1` | `RESEARCH_ONLY`, `FORWARD_RESEARCH`; V2 adapter is architecture evidence | Continue forward-research evidence independently of platform engineering |

Registry authorization is unchanged and is not implied by any platform progress:
`ST_ASIAN_SWEEP_5R_V1` is `research: true`, `demo_authorized: false`,
`live_authorized: false` (`strategies/registry.yaml`).

---

## 5. Owner / Level C decisions currently blocking downstream steps

1. **Sign (or decline) Asian Sweep economic thresholds** — without a signed contract, R6
   for the active V2 FX strategy is formally `NOT_EVALUABLE_MISSING_SIGNED_THRESHOLDS`.
2. **Resume or keep paused Asian Sweep research** (`PAUSED_BY_OWNER`).
3. **WP-8 authorization** — the first owner-authorized Demo `order_send()` path; no agent
   may self-promote through this gate.
4. Any future Demo/Live activation and material risk-policy change.

No automated agent may close a Level C gate by passing tests.

---

## 6. Distance to the objective — summary

```text
WP-0  baseline freeze              CLOSED
WP-1  Asian Sweep adapter          CLOSED (gate PASS)
WP-2  SSC routing removal          CLOSED (owner accepted)
WP-3  ProposalEligibility          BUILD DONE + R1 FIX; AUDIT OPEN   <-- next gate
WP-4  CanonicalProposal bridge     NOT IMPLEMENTED
WP-5  RiskDecision engine          NOT IMPLEMENTED
WP-6  ExecutionDecision            NOT IMPLEMENTED
WP-7  MT5 runtime truth            NOT IMPLEMENTED
WP-8  Manual Demo execution gate   NOT STARTED (owner-gated)
WP-9  Scheduler MarketEvent bridge NOT IMPLEMENTED
WP-10 Frontend state sync          NOT IMPLEMENTED
WP-11 System E2E qualification     NOT IMPLEMENTED
V2-6  BTC/session adapters         NOT IMPLEMENTED (no WP assigned)
V2-13 parity campaign              NOT STARTED
V2-14 economic qualification       NOT PASSED (strategy-dependent)
V2-15 controlled Demo              BLOCKED
Live qualification                 BLOCKED
```

Reading this correctly: **software readiness is roughly one third done; economic
qualification has not started for the intended active FX strategy, and its only recorded
evidence is negative.** The shortest defensible path remains the roadmap's own ordering —
close the WP-3 audit, then WP-4 → WP-5 → WP-6, while the strategy-evidence lane runs in
parallel and no gate is forced.

---

## 7. Documentation drift found during this check (recorded, not silently rewritten)

1. **`DOCS_LINK_CHECK = FAIL` at HEAD.** The Phase 0 documentation exit gate
   (`BROKEN_RELATIVE_LINKS = 0`, `UNDISCOVERABLE_PRIMARY_DOC_DOMAINS = 0`,
   `DOCS_LINK_CHECK = PASS`) is **not** satisfied in the committed tree:
   `docs/README.md` linked `status/AG_SSC_V1_0_1_SEMANTIC_AND_REPLICATION_CONFOUND_AUDIT_V1.md`
   while the file is `docs/status/SSC_V1_0_1_SEMANTIC_AND_REPLICATION_CONFOUND_AUDIT_V1.md`,
   and `docs/v2/README.md` was not discoverable from `docs/README.md`. Both are repaired
   by this change set (navigation-only; no claim, authority, or historical statement
   altered).
2. **`docs/v2/README.md` "Current next gate" is stale** — it still presents V2-4 as the
   next gate and WP-0 baseline freeze as the immediate next checkpoint, while WP-0..WP-3
   have since landed and WP-3 is awaiting re-audit.
3. **`docs/README.md` status-evidence bullet is stale** — it records the parity
   checkpoint as `READY_FOR_INDEPENDENT_AUDIT`, `SAFE_TO_ADVANCE_TO_V2_4 = NO`, which the
   independent re-audit superseded (`PASS` / `YES`).
4. **`PROJECT_STATUS.md` rolling section lags HEAD** — it ends at "Next gate: independent
   audit of this WP-3 implementation" and does not record the WP-3 R1 remediation that is
   the current HEAD commit.
5. **No dated `docs/status/` evidence document exists for WP-1, WP-2, or WP-3**, although
   `docs/status/LIVE_STATUS_MAINTENANCE.md` expects a dated record for a completed
   milestone. Their status lives only in the rolling snapshot and the roadmap document.
6. **A historical (2026-09-12) `PROJECT_STATUS.md` sentence** states
   `ST_ASIAN_SWEEP_5R_V1` has `demo_authorized=true`; the current
   `strategies/registry.yaml` says `false`. The historical statement should be corrected
   by an explicit dated addendum if it is still relied on.

Items 2–6 are recorded here rather than edited, because superseding a dated status
statement requires an explicit correction record (identifying date, original statement,
new evidence, and whether implementation or authorization changed).

---

## 8. Verification basis and limits

Commands run read-only against HEAD `570e755` (working tree clean; no source, config,
strategy, or authority file modified by this analysis). Documentation navigation repairs
were applied afterwards and are listed separately.

```text
PYTHONPATH=src python -m pytest tests/test_opportunity_contracts.py
  tests/test_opportunity_events.py tests/test_opportunity_registry_binding.py
  tests/test_opportunity_import_boundaries.py tests/test_opportunity_candidate_store.py
  tests/test_opportunity_engine.py tests/test_opportunity_adapter_parity.py
  tests/test_opportunity_asian_sweep_adapter.py tests/test_opportunity_ssc_adapter.py
  tests/test_opportunity_large_smc_adapter.py tests/test_opportunity_proposal_eligibility.py -q
=> 221 passed

python scripts/check_docs_links.py     => FAIL before this change set (see 7.1)
                                          PASS after  (BROKEN_RELATIVE_LINKS = 0,
                                          UNDISCOVERABLE_PRIMARY_DOC_DOMAINS = 0)
PYTHONPATH=src python -m pytest tests/test_docs_links.py -q  => 4 passed
```

Limits of this verification:

- Local git history in this checkout is a single squashed commit; historical SHAs quoted
  in repository documents (WP-0/WP-1/WP-2 freeze commits) are **not resolvable locally**
  and were taken as documentary, not re-verified.
- MT5/Windows-only surfaces (WP-7, WP-8, WP-11) were inspected statically only; no broker
  terminal, no order call, no credential, and no protected/OOS/holdout data was touched.
- Test dependencies (`pytest`, `PyYAML`, `pandas`, `smartmoneyconcepts`) were installed
  into the analysis sandbox purely to run the existing suite; no repository file changed
  as a result.

## 9. Recommended immediate next actions

1. **Independent re-audit of WP-3 R1** (`LEVEL B`) against `570e755`, then record the
   dated status document and the rolling note. This is the single open gate.
2. **Assign a WP number and gate class to V2-6** so the multi-strategy adapter expansion
   is tracked like every other step.
3. **Reconcile the documentation drift** in section 7 as a bounded documentation-only
   work package (dated corrections, not silent rewrites).
4. Only then start **WP-4**, while the strategy-evidence lane proceeds in parallel.

---

**Non-authorizing reminder**

```text
Analysis complete   != implementation authorized
Tests passing       != validated
Validated           != strategy authorized
Platform ready      != strategy Demo eligible
Demo eligible       != Live authorized
```
