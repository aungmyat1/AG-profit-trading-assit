# AG PROPOSAL STAGE FOUNDATION V1 — STATUS (2026-09-28)

**Classification:** PROPOSAL_STAGE_FOUNDATION_V1 (implementation checkpoint, local
commit only — no push, no PR, no merge).
**Base:** `3b89d0f772e6c1bee5c7f64a9e05052971d9bde1` (tree `580a52e7…`),
the CAPABILITY_ZERO_POST_MERGE_SMOKE_PASS main.
**Prior classification:** PROPOSAL_STAGE_FOUNDATION_DISCOVERY_PASS (2026-09-28
discovery mission — this commit implements its approved manifest).

## What this adds

A capability-zero Proposal stage on top of the live Opportunity stage:

```
OpportunityCandidate
    → ProposalEligibility (hardened)
    → CanonicalProposal (opportunity_adapter bridge)
    → Proposal ledger (persistence + read)
    → STOP
```

There is deliberately NO path onward: no OwnerDecision, no Demo/Live execution,
no broker/MT5 gateway, no order submission, no Telegram, no private exchange API.
A Proposal is DATA ONLY.

## Scope (16 files, one commit)

1. **Immutable historical restoration — 9 production files** (byte-exact blobs
   from frozen `761ede27` = tag `crypto-scanner-r2.1-audit-pass`, verified
   identical to final mainline `2b75bbf0` in discovery):
   `src/proposal_envelope/{__init__,models,ledger,strategy_authority}.py`,
   `src/proposal_envelope/adapters/{__init__,opportunity_adapter}.py`,
   `src/validation_framework/{__init__,models,lifecycle_registry}.py`.
2. **Immutable historical restoration — 4 test files** (same source):
   `tests/test_opportunity_proposal_bridge.py` (17),
   `tests/test_proposal_ledger.py` (7),
   `tests/test_proposal_envelope_models.py` (10),
   `tests/test_proposal_envelope_execution_boundary.py` (7).
3. **Eligibility hardening — 1 source file modified**
   (`src/opportunity/proposal_eligibility.py`, minimum change): after the
   existing completeness gate, malformed trade facts now fail CLOSED with
   deterministic reason codes before any ELIGIBLE decision can exist:
   - `SYMBOL_NOT_CANONICAL` — symbol must be a non-empty, whitespace-free,
     uppercase string (the proposal symbol derives from this same identity;
     no second symbol exists anywhere in the interfaces);
   - `INVALID_DIRECTION` — side must be exactly a known side: LONG/SHORT
     (canonical) or BUY/SELL (the repository's established synonyms);
   - `NON_FINITE_GEOMETRY` — entry, stop/invalidation, and every target must
     be finite (math.isfinite); NaN/Inf are never normalized or repaired;
   - `ENTRY_EQUALS_STOP` — risk distance must be positive;
   - `INVALID_STOP_GEOMETRY` — LONG/BUY requires stop < entry; SHORT/SELL
     requires stop > entry.
   No stop or target is ever invented; no failing input becomes valid.
   The Opportunity scanner itself is untouched.
4. **New bounded hardening test file**
   (`tests/test_proposal_eligibility_hardening_v1.py`, 34 tests): the full
   valid/identity/geometry/non-finite/provenance/lifecycle/persistence/security
   matrix, symbol-binding proof (no symbol parameter exists in either
   interface — proven by signature inspection + behavior), deterministic
   proposal identity, duplicate replay, corrupt-store fail-closed, and AST
   security proofs (no execution/authorization/owner_decision/broker/telegram
   imports or order calls anywhere in the Proposal stage).
5. **This status document.**

## Deliberately excluded (owner decisions for future missions)

`formation_gate.py` + `strategy_contract/market_snapshot.py` (module-level
`mt5.market_data` import — needs a decoupling mission), `fx_adapter.py`
(imports `execution.adapter`), the other research adapters,
`occurrence_identity_v1.py`/`identity_audit.py`, `api/app.py` and every HTTP
carrier, the entire denylist (execution/, authorization/, owner_decision/,
ticket_delivery/, trade_management/, svos/, entry_confirmation/,
notifications/), any scanner→proposal composition runner, and
`strategies/registry.yaml` registration for the crypto strategy (the
`strategy_authority=None` bridge path needs none; unregistered resolution is
verified fail-closed).

## Evidence (fresh, this implementation)

- Blob identity: 13/13 restored files byte-exact to frozen R2.1.
- E2E composition: REAL eligible candidate → ELIGIBLE → PROPOSAL_READY →
  ledger record; proposal id deterministic; symbol binding exact;
  execution_authority=NONE, proposal_only=True, execution_eligible=False,
  broker_mutation_blocked=True. Malformed cases (wrong-side stop, NaN entry,
  Inf stop, synthetic, expired) → BLOCKED, no READY proposal, ledger rejects.
- Static audit (39 src Python files): forbidden imports NONE; order call
  sites NONE; HTTP methods {get} only; API-key tokens NONE.
- Tests: 351 collected = 350 passed + 1 known api.app negative-control
  (preserved semantics from the capability-zero restoration); the four
  restored historical suites pass unmodified; web MCP 4/4 unchanged.

## Capability counters (unchanged)

EXCHANGE_ORDER / BROKER_ORDER / MT5_ORDER / DEMO_EXECUTION /
LIVE_EXECUTION = ZERO; OPPORTUNITY_TO_EXECUTION_PATH = NONE;
PROPOSAL_TO_EXECUTION_PATH = NONE.
