# AG Profit Trading V2 — Implementation Roadmap

Status: **PROGRAM PLAN / NON-AUTHORIZING**  
Date: 2026-09-21

This roadmap converts the V2 architecture into bounded implementation gates. It supplements the master readiness plan; it does not supersede trading/economic qualification gates and grants no execution authority.

## Current baseline

Committed baseline evidence as of this document:

- SSC one-year replay data authority freeze: `1e75e36`
- V2 core contracts: `0be5bad`
- frontend-freeze documentation: `b6e0780`
- baseline manifest: `AG_V2_BASELINE_MANIFEST_V1.json`
- status: `docs/status/AG_V2_PRE_ARCHITECTURE_BASELINE_STATUS.md`
- V2-2A/V2-2B implementation and verification: `docs/status/AG_V2_2A_2B_IMPLEMENTATION_STATUS.md` (VERIFIED, 2026-09-21)

The V2 contracts layer, the pure funnel transition engine (V2-2A), and the candidate store + transition ledger (V2-2B) are all present and verified. A Large-SMC or SSC shadow adapter (V2-3A/V2-3B) is the next implementation gate unless a newer dated status document supersedes this statement.

## Phase sequence

```text
V2-0A  Mission-1 authority finalization          COMPLETE
V2-0B  Pre-V2 baseline freeze                    COMPLETE
V2-1   Core opportunity contracts                COMPLETE / PARTIAL program gate
V2-1B  Shared evidence contracts                 COMPLETE at contract level

V2-2A  Pure funnel transition engine             VERIFIED (2026-09-21)
V2-2B  Candidate store + transition ledger       VERIFIED (2026-09-21)

V2-3A  Large-SMC shadow adapter                  NEXT
V2-3B  SSC replay/shadow adapter
        ↓
      PARITY CHECKPOINT

V2-4   ProposalEligibility bridge
V2-5   CanonicalProposal integration
V2-6   BTC + Asian/session adapters
V2-7   Portfolio RiskDecision
V2-8   ExecutionDecision + authority model
V2-9   SVOS automatic virtual execution
V2-10  Scheduler MarketEvent bridge
V2-11  Existing API compatibility integration
V2-12  Existing frontend regression validation
V2-13  Replay/live semantic parity campaign
V2-14  Economic qualification
V2-15  Per-strategy AUTO_DEMO qualification

FUTURE  Separate Live qualification
```

## V2-2A — Pure funnel transition engine

Goal: implement deterministic, storage-agnostic transition semantics.

```text
previous FunnelState
        +
normalized FunnelProjection
        +
explicit evidence/time inputs
        ↓
Pure Transition Engine
        ↓
TransitionDecision
        +
next FunnelState
        +
FunnelTransition when semantic state changed
```

Required properties:

- `NO_CHANGE` returns the previous state unchanged, revision unchanged, and `transition=None`.
- entering a terminal outcome is `STATE_CHANGED`; evaluating an already-terminal occurrence is `TERMINAL` without mutation.
- forward stage skipping may be allowed when explicitly projected, but missing intermediate evidence is never fabricated.
- backward ACTIVE progression fails closed.
- revisions change only on semantic mutation.
- transition identity is deterministic and does not require inventing persistent candidate identity.
- geometry is semantic only when the normalized projection contract explicitly treats it as semantic evidence.
- no persistence, proposal, risk, execution, broker, SVOS, scheduler, frontend, or real-strategy dependency.

Exit gate: `AG_V2_PURE_FUNNEL_ENGINE_READY`.

## V2-2B — Candidate store + transition ledger

Goal: add persistent occurrence lifecycle without changing strategy semantics.

Responsibilities:

- deterministic candidate/occurrence identity;
- append-only semantic transition ledger;
- candidate current-state materialization;
- restart/reconstruction parity;
- deduplication and idempotence;
- expiry handling;
- immutable provenance links.

This phase owns persistent identity. V2-2A must not pull it forward.

## V2-3 — Shadow strategy adapters

### Large-SMC first

Large-SMC is a strong first shadow adapter because its research lifecycle already exposes explicit watch/qualification/invalidation states. Preserve raw research states. `RESEARCH_QUALIFIED` may create/advance a research candidate but does not imply proposal eligibility or execution authority.

### SSC second

SSC must bind to its canonical evaluator, not to `SESSION_TRADE_V1` for convenience. Preserve strategy identity and current authority boundaries.

Shadow architecture:

```text
legacy/canonical strategy path
        ├── authoritative existing output
        └── V2 shadow adapter
                 ↓
           parity comparison
                 ↓
      MATCH / MISMATCH / NOT_COMPARABLE
```

No shadow adapter becomes authoritative until its parity gate passes.

## V2-4/V2-5 — Proposal bridge

Flow:

```text
OpportunityCandidate
      ↓
ProposalEligibilityDecision
      ↓
ELIGIBLE / BLOCKED / INCOMPLETE
      ↓ only ELIGIBLE
existing formation gate
      ↓
CanonicalProposal
      ↓
existing proposal ledger
```

Do not create a second canonical proposal model. Research-only, synthetic, replay-incompatible, incomplete, or unauthorized candidates fail closed.

## V2-7/V2-8 — Risk and execution authority

Risk and authority remain platform layers, not strategy-funnel stages.

```text
CanonicalProposal
    ↓
RiskDecision
    ↓
ExecutionDecision
```

The system must preserve the distinction between capability and authority. A functioning execution gateway does not authorize a strategy or environment.

## V2-9 — SVOS first automatic consumer

Target the first complete automatic flow at virtual execution:

```text
Opportunity → Proposal → Risk → Authority → AUTOMATIC + VIRTUAL → SVOS
```

This validates orchestration without requiring unresolved broker leverage/margin authority to block strategy-capacity work.

## V2-10 — Scheduler bridge

Scheduler should emit/drive common `MarketEvent` evaluation rather than contain strategy rules. Existing schedule windows and operational safety remain unchanged until separately migrated and verified.

## V2-11/V2-12 — Compatibility, not redesign

There is no V2 frontend redesign phase.

- V2-11 maps backend V2 state into existing API/read-model contracts.
- V2-12 proves the existing frontend continues to work without V2-specific knowledge.

Breaking UI/API changes are blockers, not invitations to rewrite the frontend.

## Qualification after infrastructure

Infrastructure completion does not prove edge. After replay/live semantic parity, each strategy must independently satisfy its economic qualification and environment-specific execution qualification before authority can be promoted.

## Global stop conditions

Stop and report rather than widen scope when any mission would require:

- changing strategy semantics without a separately approved research mission;
- accessing protected data outside its gate;
- upgrading proposal/Demo/Live authority implicitly;
- inventing missing market/trade/broker evidence;
- modifying the frozen frontend to hide a compatibility conflict;
- committing unrelated operational ledger drift;
- bypassing repository push/authorization safeguards.