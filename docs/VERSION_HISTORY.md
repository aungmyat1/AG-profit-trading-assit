# AG Profit Trading — Version History

Two independent version histories are maintained. **Application/release version
changes (reporting, persistence, runtime operations, recovery, CLI, journaling,
monitoring, execution plumbing) do NOT imply a strategy semantics change, and vice
versa.** A strategy version bump is required only when setup qualification, sweep
definition, direction, entry, confirmation, stop, targets, or session strategy logic
itself changes — never for logging, reporting, persistence, restart recovery, CLI
changes, journal hygiene, or release manifests.

## Application Release History

| Release | Status | Purpose | Manifest |
|---|---|---|---|
| `AG_TRADE_ASSISTANT_V1_0` | FROZEN | First operational release: post-Asian London pilot for EURUSD+GBPUSD, single-slot selection, PROPOSAL_ONLY. | `config/releases/AG_TRADE_ASSISTANT_V1_0.yaml` |
| `AG_TRADE_ASSISTANT_V1_0_1` | IMPLEMENTED | Portfolio/daily-ledger hardening: `ready_at` (qualifying closed M15, never wall-clock) selection ordering, two-slot daily opportunity ledger (max 2/day, 1/symbol) with cross-process atomic claims, `max_open_positions=2` with a 1.0% aggregate-open-risk gate, `-1R` realized strategy loss lock layered on the unmodified project-wide `-2R` guard. | `config/releases/AG_TRADE_ASSISTANT_V1_0_1.yaml` |
| `AG_TRADE_ASSISTANT_V1_0_2` | CURRENT DEVELOPMENT | Operational observability + restart recovery: fixed READY-decision restart reconstruction (previously downgraded to NOT_READY on reload), immutable Asian snapshots (fail-closed on conflicting rewrite), a dedicated `--preflight` CLI, event-driven `--watch` output, a complete Entry Ticket renderer, a journal-grounded end-of-window report, and lightweight monitoring counters. Execution integration remains `NOT_WIRED`. | `config/releases/AG_TRADE_ASSISTANT_V1_0_2.yaml` |
| `AG_TRADE_ASSISTANT_V1_1` | DEFERRED | SMC advisory context (not started). | — |

Every release above runs **`ST_ASIAN_SWEEP_5R_V1` v1.1.1** — application releases never
imply a strategy semantic change.

## Strategy Version History

| Strategy | Version | Status | Used by application releases |
|---|---|---|---|
| `ST_ASIAN_SWEEP_5R_V1` | 1.1.1 | ACTIVE, `SOLE_DAY_TRADING_AUTHORITY` (pilot-scoped) | V1.0, V1.0.1, V1.0.2 |
| `ST_LARGE_SMC_V1` | 1.0.1 | `RESEARCH_DRAFT`, advisory-only, fail-closed (`proposal_generation_authorized: false`, engine `NOT_IMPLEMENTED`) | none (not used by any application release) |

`ST_LARGE_SMC_V1` is a fully independent strategy family (`strategies/ST_LARGE_SMC_V1.yaml`,
spec `docs/specs/LARGE_SMC_V1_SPEC.md`) — it does not inherit `ST_ASIAN_SWEEP_5R_V1`'s,
`SMC_3R_V1`'s, or `ST_LIQUIDITY_SWEEP_RETEST_V1`'s rules, authorization, or validation
evidence, and it does not appear in any `AG_TRADE_ASSISTANT_V1_0*` release manifest.

- **v1.0.1 (2026-09-01):** UC-001 (timeframe roles) resolved by owner to D1/H1/M5,
  matching AG's own frozen E1/E2/E3 + M1/M2/M3 research pipeline; C11 (target model)
  resolved by owner (Candidate 2, `HYBRID_WITH_STRUCTURAL_FALLBACK`) and frozen as a
  `CONTRACT_ONLY` `target_model:` block. Still `RESEARCH_DRAFT`; no engine, proposal,
  or execution authority added. See `docs/specs/LARGE_SMC_V1_SPEC.md` and
  `docs/status/ST_LARGE_SMC_V1_C11_CONTRACT_FINALIZATION_STATUS.md`.

A strategy version bump is required if a change affects: setup qualification, sweep
definition, direction, entry, confirmation, stop, targets, session strategy logic, or
intrinsic trade eligibility logic — including SMC or order-flow becoming strategy
authority. It is **not** required for logging, reporting, persistence, restart
recovery, CLI changes, journal hygiene, release manifests, or operator status views.
