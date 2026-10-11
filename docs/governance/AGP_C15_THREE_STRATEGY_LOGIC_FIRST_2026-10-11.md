# AGP-C15 — Three-strategy logic-first sequencing (owner ratified 2026-10-11)

**Decision ID:** AGP-C15-THREE-STRATEGY-LOGIC-FIRST-2026-10-11
**Status:** OWNER APPROVED; governance PR pending merge
**Authority:** This amendment changes implementation priority only. `docs/PROJECT_OBJECTIVE.md` and ratified C14 govern execution; if conflict exists, C14 and the objective win.

## Decision

Pursue L1–L6 logical verification for **one explicitly bounded scope in each of three strategy families in parallel**, while continuing S1 read-only operational acceptance:

1. `ST_ASIAN_SWEEP_5R_V1` (FX/gold)
2. `ST_LARGE_SMC_V1` (six-instrument watch)
3. `ST_CRYPTO_CFD_SWEEP_RETEST_V1` (VT Markets BTCUSD/ETHUSD CFDs)

A passing scope must bind strategy ID/version, instrument, session/timeframe, branch, dataset/fixture identity, frozen rule identity, and reproducible L1–L6 evidence. A verified lane does **not** verify other branches, symbols, sessions or venues. Do not loosen logic rules to manufacture passing cases. Missing required evidence must fail closed or remain WARN/BLOCKED according to the existing gate contract. Logic verification is distinct from EDGE_VERIFIED, READY, and execution authorization.

## Non-negotiable invariants

- C14 remains in force: automatic **Demo-only** orders require separate, scoped, revocable standing authorization and all applicable G1–G4, READY, host, runtime identity, risk, broker, order_check, idempotency, reconciliation, and emergency-stop gates. Per-order confirmation is not required once the governed executor transition and scoped authorization are effective. No live execution.
- C14 does **not** require EDGE_VERIFIED or a 10-cycle zero-order shadow soak for Demo. Soak may be performed as optional observation, not presented as a mandatory G gate.
- Preserve approved risk limits: 0.5% per trade; at most one open position per pair; five trades/day/strategy; 1% daily loss/strategy; 2% account-wide daily loss. These are ceilings, not trade quotas. All other existing safety checks remain.
- No `demo_authorized`, `live_authorized`, READY or broker mutation changes in this governance PR.
- Preserve S1 host freeze through Monday 2026-10-12 Part C (~18:00 MMT): no pull to `D:\wp3-main-integ`, no scheduled task, Telegram, MT5, or host-setting changes. Off-host PR work and merges to main are allowed. Host stays pinned at 0773a55 (host HEAD confirmed by M3 read-only report, PR #157; deb85d0 is an older ancestor) until the authorized transition.
- Investigate foreign magic-0 orders and host disk/RAM/resource_guard blockers read-only first. Do not disable unrelated EA or modify accounts without separate owner-approved host action.
- One writer per branch, separate PR per mission, evidence filed as PR, reviewed merge gate, no generated status-file churn. No unapproved horizontal orchestration project.

## Mission contracts

### M1 — C15-GOV
**Scope:** governance documentation only; no runtime/strategy/registry changes.
**Deliver:** this decision, link from authoritative objective after review, mission handoffs and verification matrix.
**Exit:** review and governance PR merge with no weakening of C14. Record final PR/commit in decision register via reviewed change.

### FX agent — C15-ASW
**Scope:** `ST_ASIAN_SWEEP_5R_V1@1.1.2`.
**Baseline:** GBPUSD × ASIAN_LONDON × SWEEP only is reported LOGIC_VERIFIED (#142); RANGE/TREND fail closed. EURUSD 60-day L2/L3 failures require root cause classification; USDJPY/XAUUSD have no conforming cases.
**Deliver:** evidence matrix per symbol/session/branch, reproducer for each EURUSD L2/L3 failure, cause classification (data, rule, implementation), explicit unchanged passing scope. No rule relaxation, no runtime promotion.
**Exit:** reproducible results and independent review; failures remain NOT_VERIFIED.

### Large-SMC agent — C15-LSMC
**Scope:** `ST_LARGE_SMC_V1@1.1.0`, off-host.
**Baseline:** 18-case fixture with L5 WARN, EURUSD detection causality and D1 host parity reported (#144/#151). No blanket six-symbol admission.
**Deliver:** choose one additional symbol from the six based on actual captured data and validate L1–L6, stop/target geometry, causality, spread provenance and frozen identity. Archive-only delivery unchanged.
**Exit:** independent per-symbol evidence; if none passes, publish BLOCKED with cause.

### Crypto agent — C15-CRYPTO
**Scope:** `ST_CRYPTO_CFD_SWEEP_RETEST_V1@1.1.0`, BTCUSD/ETHUSD VT CFDs, off-host.
**Baseline:** #126/#141 reported not on main; v1.0.0 evidence STALE_IDENTITY.
**Deliver:** L3 direction recheck on subsequent scans; append-only WITHDRAWN event for unfilled invalidated signals; never withdraw after fill; idempotency, restart, out-of-order event tests; then 60-day dataset-bound L1–L6 replay for BTCUSD/ETHUSD with venue-specific point-size, spread, and timing evidence.
**Exit:** reviewed tests, complete per-symbol verification report; no Demo admission without separate gates.

### M3 — S1-HOST
**Scope:** existing S1 Part C only; read-only until freeze ends and separately authorized host changes.
**Suite-base note:** #145 resolved by #146 (merged); combined-suite evidence is authoritative only on a base containing #146.
**Deliver:** foreign-order attribution (EA/manual/magic 0), disk/free-RAM/resource_guard evidence, symbol map and DST parity, host runtime identity, Telegram ticket proof, pass/fail checklist. Redact host paths.
**Exit:** all mandatory Part C items PASS, or BLOCKED with precise evidence. Never infer S1 acceptance from off-host CI. Optional soak does not substitute for host acceptance.

## Merge and promotion policy

C15 governance PR first; agent PRs may be developed in parallel on independent branches. Never merge solely on green CI. Require independent review, frozen identity, L1–L6 evidence, and fail-closed behavior. Runtime promotion and any G6 Demo authorization require separate owner-governed changes and gates. Do not automatically change Issue #47's C14 execution contract; link C15 as sequencing context only.
