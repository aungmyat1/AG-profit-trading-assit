# AG Post-R4 Expansion and Delivery Plan V1

Status: **DEFERRED FOLLOW-ON PLAN — NOT CURRENT IMPLEMENTATION AUTHORITY**  
Recorded: **2026-09-11**  
Prerequisite: `AG_PROPOSAL_OPERATION_READY_V1`  
Objective: **Expand operating reach by reusing the proven canonical pipeline**

## Entry gate

Start only after R2-R4 has automated acceptance, a natural real-data `READY` proof, a
natural `NO_TRADE` proof, durable proposal identity, and zero-order evidence recorded
under `AG_PROPOSAL_OPERATION_READY_V1`.

If a shared R2-R4 invariant regresses, stop expansion and return to
`AG_CANONICAL_R2_R4_PROPOSAL_PIPELINE_V1.md`. Partial completion never changes
strategy or execution authority.

## Scope and invariants

This plan adds operator evidence/reporting, informational Telegram delivery, and
independently contracted USDJPY and XAUUSD coverage. It reuses the canonical market,
decision, proposal, ledger, API, UI, and evidence contracts; it creates no parallel
core.

- New symbols remain candidate/shadow until independently validated.
- Telegram implementation and activation are separate decisions.
- Delivery never recomputes strategy fields or reaches broker controls.
- Reporting is a read model and cannot write strategy, proposal, watch,
  authorization, or execution state.
- Frozen EURUSD/GBPUSD rules and evidence are not rewritten.

## Track A — R4 operational hardening and evidence export

1. Run a bounded observation period and reconcile evaluations, formation attempts,
   accepted/rejected proposals, corrections, and unresolved operational failures.
2. Freeze Proposal Integrity Rate inputs, exclusions, and threshold before using it.
3. Extend immutable, manifest-backed proposal evidence export and restore
   verification without persisting secrets.
4. Add operator views for feed health, freshness, formation failures, ledger health,
   recovery state, and last successful evaluation.
5. Alert only on material transitions or actionable failures; unchanged state is quiet.

Exit: the proposal population is reproducible and failures are diagnosable without
manual raw-journal reconstruction.

## Track B — Telegram informational delivery

1. Reuse archive-first identity, attempt journal, retry, deduplication, redaction, and
   destination allow-list mechanisms.
2. Map canonical proposals to messages without recomputing strategy fields.
3. Keep delivery disabled or archive-only until separate owner authorization names
   the mode and destination.
4. Prove unauthorized destination, missing configuration, timeout ambiguity, retry,
   overlap, restart, rate limit, malformed response, and payload-size behavior with
   fake transport first.
5. After separate authorization, send one synthetic non-trading operational message,
   then wait for one natural canonical proposal delivery. Never manufacture `READY`.
6. Preserve provider response identity, proposal/ticket identity, attempt IDs, timing,
   redacted failure evidence, and proof that execution was unreachable.

Exit: delivery is exactly-once and operationally evidenced, or remains truthfully
`NOT_AUTHORIZED`. A message is a proposal notification, not an order.

## Track C — USDJPY candidate coverage

1. Freeze aliases, precision, point/pip and contract semantics, sessions, spread and
   freshness limits, range/stop/sizing conventions, identity, and cost assumptions.
2. Create a new candidate strategy version or explicit symbol contract; do not extend
   frozen EURUSD/GBPUSD behavior implicitly.
3. Validate read-only data quality, closed-candle behavior, decision conformance,
   proposal identity, persistence, API/UI rendering, and evidence export.
4. Keep `RESEARCH`/`SHADOW_ONLY` and `execution_authority=NONE` until independent
   evidence and governance gates pass.

Exit: USDJPY has deterministic shadow decisions and canonical proposal evidence under
its own signed conventions, with no borrowed authority.

## Track D — XAUUSD candidate coverage

1. Freeze broker aliases, precision, tick/contract size, sessions, spread behavior,
   volatility/range limits, stop distance, sizing inputs, freshness, identity, and
   costs.
2. Create a Gold-specific candidate contract and strategy version.
3. Validate read-only feed behavior and market-specific edge cases before proposal
   formation.
4. Reuse canonical proposal, ledger, API, UI, export, and optional delivery surfaces
   only after conformance passes.
5. Keep execution authority `NONE` and evidence independent from FX cohorts.

Exit: XAUUSD has a reproducible shadow proposal path under Gold-specific conventions.

## Sequencing

```text
R4 operation hardening and export/reporting foundation
  -> Telegram fake-transport verification
  -> USDJPY and XAUUSD conventions/contracts
  -> independent read-only shadow proofs
  -> separately authorized Telegram operational proof, if authorized
  -> consolidated expansion evidence
  -> STOP
```

Tracks may overlap only after shared R4 contracts are frozen and only when they do not
change common semantics. No track inherits readiness from another.

## Completion gate

Complete when expanded evidence is reproducible, reporting is ledger-backed and
read-only, Telegram is explicitly `NOT_AUTHORIZED` or independently proven after
authorization, each new symbol has signed conventions and independent shadow evidence,
and zero broker mutation remains proven. Then **STOP** and reconcile status and dated
evidence before selecting another maturity plan.

## Deferred beyond this plan

- BTCUSDT/ETHUSDT runtime expansion and crypto venue integration;
- outcome/economic promotion decisions and portfolio selection;
- scanner-driven Demo execution;
- Live or managed execution.

These require independent contracts, evidence, eligibility, and authorization; they
are not automatic continuations of post-R4 delivery.
