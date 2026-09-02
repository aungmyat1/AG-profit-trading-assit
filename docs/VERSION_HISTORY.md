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
| `ST_LARGE_SMC_V1` | 1.0.6 | `RESEARCH_DRAFT`, advisory-only, fail-closed (`proposal_generation_authorized: false`, engine `src/large_smc_research/` RESEARCH_ONLY) | none (not used by any application release) |

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
- **v1.0.2 (2026-09-01):** C12 (candidate expiry/lifecycle) resolved by reuse — no
  independent M1/M2/M3 clock exists anywhere in AG; validity is governed entirely by
  the already-implemented, shared `QualifiedEEvent.is_eligible_at()` E-context window.
  Frozen as a `CONTRACT_ONLY` `candidate_lifecycle:` block. Still `RESEARCH_DRAFT`; no
  engine, proposal, or execution authority added. See
  `docs/status/ST_LARGE_SMC_V1_C12_EXPIRY_CONTRACT_RESOLUTION_STATUS.md`.
- **v1.0.3 (2026-09-01):** C14 (duplicate/re-entry, candidate identity) claimed
  resolved by reuse via `src/proposals/identity.py`'s `setup_id()`/`reference_key_for()`
  and `src/proposals/lifecycle.py`'s lifecycle machinery. **Correction, same day
  (`ST_LARGE_SMC_V1_C14A_CANDIDATE_OCCURRENCE_IDENTITY`):** this overclaimed —
  `setup_id` is a setup-*family* identity only (one `event_id`/`setup_id` legitimately
  spans multiple eligibility intervals); no canonical M-candidate structural identity
  existed anywhere, and the lifecycle store (keyed only by `setup_id`) was shown to
  overwrite terminal records rather than preserve them. `candidate_identity.authority`
  was downgraded to `PARTIALLY_RESOLVED`, no version bump for the correction itself.
  See `docs/status/ST_LARGE_SMC_V1_C14_DUPLICATE_REENTRY_CONTRACT_RESOLUTION_STATUS.md`
  and `..._C14A_CANDIDATE_OCCURRENCE_IDENTITY_STATUS.md`.
- **v1.0.4 (2026-09-01, `ST_LARGE_SMC_V1_C14B_OCCURRENCE_IDENTITY_HARDENING`,
  owner-selected Option B):** the C14A gap closed by implementation. Additive
  `source_id` fields added to `M1Result`/`M2Result`/`M3Result`
  (`src/entry_confirmation/`), computed from already-existing structural evidence
  (`liquidity.level_id` / new `supply_demand.zone_id` + a confirming timestamp), no
  new detection logic. New `src/proposals/occurrence_identity.py` composes
  `eligibility_interval_id()` + `candidate_occurrence_id()` — additive, unit-tested,
  **not** wired into `proposals/lifecycle.py`'s live store (that migration is shared
  with the live `SMC_CONDITIONAL_ENTRY_V2` watcher, deferred as
  `SHARED_CHANGE_REQUIRED`). 172 pre-existing tests plus the golden vertical slice
  (7) and Stage1/Stage2 identity tests (21) pass unchanged, proving backward
  compatibility. Still `RESEARCH_DRAFT`; no engine, proposal, or execution authority
  added. See
  `docs/status/ST_LARGE_SMC_V1_C14B_OCCURRENCE_IDENTITY_HARDENING_STATUS.md`.
- **v1.0.5 (2026-09-02, `RESEARCH_ONLY_FUNNEL_V1`):** minimum research-only two-part
  funnel (data collection -> decision making) implemented as `src/large_smc_research/`
  -- thin orchestration over the already-frozen `historical_replay.stage2` boundary,
  zero E/M redetection. C01 (instruments -> `[EURUSD]`), C16 (warmup -> reuse of
  `D1=60/H1=50/M5=200`), C11 target-model adapter (`IMPLEMENTED`, formula unchanged),
  and C18 (simultaneous-combination selection -> `RECORD_ALL_INDEPENDENTLY`, reuse of
  C14) all resolved. `decision_states` dropped placeholder `READY` for
  `RESEARCH_QUALIFIED`/`INVALIDATED`. C10 (broker stop-loss) and post-READY
  pending-entry expiry deliberately remain unsigned by owner decision -- the engine
  fails closed to `BLOCKED` rather than guessing either; two decision-packet documents
  record unselected candidate options. Still `RESEARCH_DRAFT`; no proposal, demo,
  live, execution, or risk-sizing authority added. See
  `docs/status/ST_LARGE_SMC_V1_RESEARCH_FUNNEL_V1_STATUS.md`.
- **v1.0.6 (2026-09-02, `OUTCOME_LIFECYCLE_V1`):** post-READY pending-entry expiry
  `RESOLVED_BY_REUSE` (`historical_replay/fill_simulator.py`, exact reuse, no new
  clock/formula). C10 remains `UNSIGNED`/`BLOCKED`. Discovered, disclosed, and worked
  around (not fixed) a separate gap: C11's target-model adapter and pre-existing M1
  inducement detection require live MT5 symbol metadata unavailable during historical
  replay -- now fails closed to `DATA_ERROR` instead of a misleading `NO_TRADE`.
  Recommendation: `HOLD`. See
  `docs/status/ST_LARGE_SMC_V1_OUTCOME_LIFECYCLE_V1_STATUS.md`.

A strategy version bump is required if a change affects: setup qualification, sweep
definition, direction, entry, confirmation, stop, targets, session strategy logic, or
intrinsic trade eligibility logic — including SMC or order-flow becoming strategy
authority. It is **not** required for logging, reporting, persistence, restart
recovery, CLI changes, journal hygiene, release manifests, or operator status views.
