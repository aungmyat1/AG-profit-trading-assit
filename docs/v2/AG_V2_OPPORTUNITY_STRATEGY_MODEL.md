# AG V2 — Opportunity Finder and Strategy Model

Status: **DESIGN CONTRACT / NON-AUTHORIZING**  
Date: 2026-09-21

## Purpose

This document defines the relationship between strategies and the V2 Opportunity Finder.

The core rule is:

```text
STRATEGY
What constitutes my setup?

OPPORTUNITY FINDER
Where is each setup occurrence now, and how far has it progressed?

EXECUTION ENGINE
Is an eligible proposal allowed to be acted on, in which environment, and under what risk?
```

The Opportunity Finder is not a strategy and must not contain duplicated strategy rules.

## Event routing

```text
Authoritative market data
        ↓
MarketSnapshot
        ↓
MarketEvent
        ↓
StrategyBinding
        ↓
zero or more eligible strategy adapters
```

A binding describes actual identity/capability facts: strategy/version, engine/adapter identity, dispatchability, supported symbols/timeframes, lifecycle, proposal/execution authority, replay/live-observation support, and configuration fingerprint where available.

Registry presence alone does not imply runtime dispatchability or authority.

## Adapter boundary

Each strategy remains authoritative for its own trading logic.

An adapter may:

- determine whether the strategy supports an event;
- call/observe the canonical strategy engine;
- preserve raw strategy state;
- project observed strategy evidence into the common funnel vocabulary;
- expose source-owned candidate geometry when available.

An adapter must not:

- build a canonical proposal;
- size portfolio risk;
- mutate strategy/registry authority;
- send broker orders;
- invent missing entry/stop/target values;
- invent lineage or broker evidence;
- use AI to make authority decisions.

## Universal funnel

The common funnel is intentionally small:

```text
MARKET_ELIGIBLE
      ↓
CONTEXT_VALID
      ↓
LOCATION_VALID
      ↓
SETUP_DETECTED
      ↓
TRIGGER_ARMED
      ↓
ENTRY_CONFIRMED
      ↓
OPPORTUNITY_READY
```

Strategies do not have to use every stage. A normalized projection may advance to a later stage without fabricating intermediate observations.

Outcomes are independent:

```text
ACTIVE | WAIT | REJECT | INVALIDATED | EXPIRED | ERROR
```

Examples:

- `TRIGGER_ARMED + WAIT`: the trigger condition has been reached but entry evidence is incomplete.
- `SETUP_DETECTED + INVALIDATED`: a setup existed and was later invalidated.
- `CONTEXT_VALID + EXPIRED`: the occurrence expired before progressing further.

## Pure transition semantics

The V2-2A engine is expected to enforce these rules:

- equivalent semantic projection → `NO_CHANGE`, same state/revision, `transition=None`;
- accepted nonterminal → terminal outcome → `STATE_CHANGED`, revision +1, transition exists;
- already-terminal occurrence evaluated again → `TERMINAL`, no mutation;
- backward ACTIVE stage movement is illegal;
- terminal invalidation preserves the highest stage actually reached;
- provenance-only changes such as poll time/event retrieval do not create semantic mutation;
- strategy-owned geometry changes are semantic only when the normalized projection explicitly marks them as semantic evidence;
- persistent candidate/occurrence identity is reused if already authoritative, otherwise deferred to V2-2B rather than invented in V2-2A.

## Strategy examples

### SSC

Conceptual mapping only; canonical SSC semantics remain authoritative:

```text
H1 directional/context evidence       → CONTEXT_VALID
M15 session/reference evidence        → LOCATION_VALID
S1/S2/S3 setup evidence               → SETUP_DETECTED
lower-timeframe trigger/confirmation  → TRIGGER_ARMED / ENTRY_CONFIRMED
complete strategy-owned opportunity   → OPPORTUNITY_READY
```

The V2 adapter must not alter S1/S2/S3 rules or route SSC through `SESSION_TRADE_V1` merely because that path is manager-dispatchable.

### Large SMC

Large-SMC currently has research lifecycle semantics. A future adapter may map its structural/context/POI/setup/trigger evidence into the common funnel while preserving the raw state.

A raw state such as `RESEARCH_QUALIFIED` can support a research opportunity occurrence and evidence collection. It does **not** automatically mean proposal eligible, Demo authorized, or executable.

### BTC liquidity sweep/retest

The strategy remains responsible for liquidity level, sweep, retest, confirmation, invalidation, and strategy-owned geometry. The common finder supplies occurrence lifecycle, persistence, deduplication, expiry, and later proposal handoff.

### Asian/session strategy

Session range, sweep/breakout logic, timing, confirmation, invalidation, and targets remain strategy-owned. The finder must not copy these rules into scheduler or common funnel code.

## Multiple strategies on one market

Multiple strategies may produce independent candidates for the same symbol:

```text
EURUSD
├── SSC candidate          LONG / OPPORTUNITY_READY
└── Large-SMC candidate    LONG / TRIGGER_ARMED + WAIT
```

They remain separate occurrences with separate evidence and validation status. Agreement is not a new synthetic strategy and disagreement is not automatically resolved by the Opportunity Finder.

Future confluence/ranking work, if any, must remain downstream and must not corrupt per-strategy evidence.

## Candidate versus proposal

A candidate means the system has normalized an opportunity occurrence according to strategy evidence. It is not automatically actionable.

```text
OpportunityCandidate
        ↓
ProposalEligibilityDecision
        ├── BLOCKED
        ├── INCOMPLETE
        └── ELIGIBLE
                 ↓
          CanonicalProposal
```

Only `ELIGIBLE` may enter the existing canonical proposal formation path.

## Alerts

Future alerts should be transition-driven rather than repeated polling messages. Examples include setup detected, trigger armed, entry confirmed, invalidated, or expired. This permits deduplication and restart-safe behavior once V2-2B persistence exists.

## Validation independence

A strategy may be operationally observable while its economic edge remains unproven. The Opportunity Finder can collect deterministic occurrence evidence during validation without upgrading strategy authority.

Therefore:

```text
OPPORTUNITY_READY
≠ profitable
≠ proposal-authorized
≠ Demo-authorized
≠ Live-authorized
```

That separation is a permanent V2 invariant.