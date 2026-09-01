# Strategy Ledger

Per-strategy registration history, referenced from `config/canonical_sessions.yaml`.
Each entry records when a strategy was registered, its config file, and any deviation
from canonical session windows or other repo conventions at the time of registration.

## ST_ASIAN_SWEEP_5R_V1 -- Asian Session Liquidity Sweep 5R

- **Registered:** 2026-08-26
- **Config:** `strategies/ST_ASIAN_SWEEP_5R_V1.yaml`
- **Status:** ACTIVE_INCUBATION
- **Family:** Liquidity_Sweep
- **Instruments:** EURUSD, GBPUSD, USDJPY, AUDUSD, XAUUSD
- **Timeframe:** M15
- **Magic number:** 777001
- **v1.1.0 (2026-08-26):** added a second reference/trade session pair -- the same sweep
  logic now also runs off the London range during New York session, not only off the
  Asian range during London Open. Both pairs share identical entry, risk, sizing, and
  invalidation rules; only the session windows differ.
  - `ASIAN_LONDON`: reference = Asian (00:00-06:00 UTC), trade = London_Open (07:00-11:00 UTC)
  - `LONDON_NEWYORK`: reference = London (06:00-11:00 UTC), trade = New_York_Open (12:00-15:00 UTC)
- **Session window note:** `ASIAN_LONDON.reference_session` matches canonical `asian`
  exactly. `ASIAN_LONDON.trade_session` (London_Open, 07:00-11:00 UTC) does not match
  canonical `london_am` (06:00-11:00) -- starts an hour later; see
  `legacy_session_windows` in `config/canonical_sessions.yaml`. `LONDON_NEWYORK` matches
  canonical `london_am` and `new_york_am` exactly -- no deviation.
- **Open assumption:** the 25-pip EURUSD range ceiling used for the Asian reference range
  is also applied unchanged to the London reference range, though London ranges are
  typically wider. Not separately tuned -- see the config's inline note.
- **SMC_TRAP_GUARD_V1 (2026-09-01):** additive safety declaration pins the existing
  sweep contract: reference-session liquidity only, strict penetration plus close-back-
  inside reclaim, dual-side sweep = ambiguous/no-trade, and no advisory evidence may
  bypass the strategy engine. No strategy-version or authorization change.
- **Not yet defined:** this spec covers entry/exit/risk mechanics but not a full
  causal backtest contract (data timestamps, fill model, cost model, train/validation/
  test partition, baselines, acceptance criteria) -- see the `strategy-specification`
  skill before backtesting.
- **Open gaps found building `execution/` (2026-08-26):**
  - `risk_and_money_management.risk_mode: FIXED_PERCENT_OR_CONTRACT` never states an
    actual risk-per-trade percentage or contract size. `execution/risk.py` currently
    falls back to `config/trading.yaml`'s account-wide `risk.risk_per_trade_pct: 1.0`
    default rather than inventing a strategy-specific number.
  - ~~`entry_rules.{long,short}_setup.entry_order_type: MARKET_OR_LIMIT` does not specify
    which.~~ **Resolved 2026-08-31 (AG_EXECUTION_RUNTIME_READINESS_V1, v1.1.1):** this was
    never a genuine two-case ambiguity -- `entry_level: Sweep_Candle_Body_Close` means the
    entry price is the close of the M15 candle that already produced the sweep signal
    (`strategy_engine/session/setups.py::entry_2_sweep`), a price already known and in the
    past by the time the signal fires. There is no future price to rest a LIMIT order at,
    so the only order type consistent with the frozen entry logic is MARKET. Both
    `long_setup`/`short_setup` now declare `entry_order_type: MARKET`; `execution/
    intent_builder.py` reaches `READY_FOR_ORDER_CHECK` for this strategy's real signals.
    See `tests/test_execution_runtime_readiness.py` for the real-YAML, real-path proof.

## SESSION_TRADE_V1 -- Asian/London session trend-continuation & sweep strategy

- **Registered:** 2026-08-27
- **Contract:** `strategies/session_trade/contract.yaml` (this repo) -- **by reference**, not a
  code copy. The signed implementation, its own execution ledger, and its own test suite live in
  the separate repository `D:\ddev\Session Trade Codex` (`config/strategy.yaml`,
  `strategy_id: ASIAN_SESSION_V1`, `session_strategy/engine.py`). See
  `docs/specs/SESSION_TRADE_V1_SPEC.md` for the full frozen spec and
  `Session Trade Codex\SESSION_PAIR_STABILIZATION_STATUS.md` for that repo's own
  test/authority verification (313 passed / 4 failed there, independently maintained).
- **Status:** demo-authorized for one of its two execution cycles; see spec for exact gates.
- **Family:** Session reference-box trend-continuation / sweep / range-rejection (own classifier,
  NOT `ER_ONLY_V2` -- see `docs/architecture/ARCHITECTURE_CONFLICT_AUDIT.md` for why these are two legitimately
  distinct classifiers, not a duplication bug).
- **Instruments:** EURUSD, GBPUSD, USDJPY, XAUUSD.crp
- **Timeframe:** M15
- **Magic numbers:** `ASIAN_LONDON` = 123456 (SIGNED, demo-authorized); `LONDON_NEWYORK` =
  123457 (UNSIGNED -- analysis/order_check only, `--confirm` hard-refused in the owning repo's
  `scripts/execute_session_signal.py` independent of its own env-var switches).
- **Relationship to `ST_ASIAN_SWEEP_5R_V1`:** both use an `ASIAN_LONDON`/`LONDON_NEWYORK`
  pair-naming convention and both were built from the same canonical-session migration lineage
  (`session_router` -> this repo's `strategy_engine/session/`), but they are **separate,
  independently-signed strategies** with different session windows, different classifiers, and
  different execution authority. Do not merge them.

## ST_LARGE_SMC_V1 -- Large SMC Opportunity Service

- **Registered:** 2026-09-01
- **Config:** `strategies/ST_LARGE_SMC_V1.yaml`
- **Specification:** `docs/specs/LARGE_SMC_V1_SPEC.md`
- **Status:** RESEARCH_DRAFT / inactive
- **Family:** LARGE_SMC
- **Execution authority:** none; advisory only, demo/live authorization false
- **Engine:** not implemented
- **SMC_TRAP_GUARD_V1 (2026-09-01):** additive research guard pins `sweep != signal`,
  `POI != entry`, internal/external structure separation, no hindsight/timeframe
  leakage, and `RESEARCH_QUALIFIED` as the maximum authority without an engine. It
  resolves no unsigned contract and changes no strategy version or authorization.
- **Relationship:** independent of `ST_ASIAN_SWEEP_5R_V1`, which remains the sole
  Session Day Trading authority. It also does not alias or promote `SMC_3R_V1` or
  `ST_LIQUIDITY_SWEEP_RETEST_V1`.
- **Open contract fields:** instrument eligibility, exact location qualification,
  M15/M5/M1 confirmation and entry rules, order/fill model, lifecycle, risk limits,
  costs, validation partitions, benchmarks, acceptance criteria, and falsification
  tests. Every unresolved field is explicit and fails closed.
- **v1.0.1 (2026-09-01):** owner resolved UC-001 (timeframe roles → D1/H1/M5, matching
  AG's own frozen E1/E2/E3 + M1/M2/M3 pipeline) and C11 (target model → Candidate 2,
  `HYBRID_WITH_STRUCTURAL_FALLBACK`, reusing `liquidity.hierarchy` and
  `market_structure.tiers` verbatim). Both recorded in `strategies/ST_LARGE_SMC_V1.yaml`
  as `CONTRACT_ONLY`; no engine wired, no proposal/execution authority. Still
  `RESEARCH_DRAFT`. See `docs/specs/LARGE_SMC_V1_SPEC.md` and
  `docs/status/ST_LARGE_SMC_V1_C11_CONTRACT_FINALIZATION_STATUS.md`.
- **v1.0.2 (2026-09-01):** C12 (candidate expiry/lifecycle) resolved by reuse —
  AG has no persisted research-candidate ledger, so no independent M1/M2/M3 timer was
  ever implemented; validity is governed entirely by the shared, already-coded
  `QualifiedEEvent.is_eligible_at()` E-context eligibility window. Recorded as a
  `CONTRACT_ONLY` `candidate_lifecycle:` block; no engine wired, no proposal/execution
  authority. Still `RESEARCH_DRAFT`. See
  `docs/status/ST_LARGE_SMC_V1_C12_EXPIRY_CONTRACT_RESOLUTION_STATUS.md`.
- **v1.0.3 (2026-09-01):** C14 (duplicate/re-entry, candidate identity) claimed
  resolved by reuse via `src/proposals/`'s `setup_id`/lifecycle-signature machinery.
  **Correction, same day:** overclaimed — `setup_id` is a setup-*family* identity
  only; no canonical M-candidate structural identity existed; the lifecycle store
  (keyed only by `setup_id`) overwrites terminal records rather than preserving them.
  Downgraded to `PARTIALLY_RESOLVED`, no version bump for the correction. See
  `docs/status/ST_LARGE_SMC_V1_C14_DUPLICATE_REENTRY_CONTRACT_RESOLUTION_STATUS.md`
  and `..._C14A_CANDIDATE_OCCURRENCE_IDENTITY_STATUS.md`.
- **v1.0.4 (2026-09-01, owner-selected Option B):** C14A's gap closed by
  implementation — additive `source_id` fields on `M1Result`/`M2Result`/`M3Result`
  (`src/entry_confirmation/`), computed from existing structural evidence
  (`liquidity.level_id` / new `supply_demand.zone_id`), no new detection. New
  `src/proposals/occurrence_identity.py` composes `eligibility_interval_id()` +
  `candidate_occurrence_id()` — additive, unit-tested, not wired into
  `proposals/lifecycle.py`'s live store (shared with the live
  `SMC_CONDITIONAL_ENTRY_V2` watcher; migration deferred as
  `SHARED_CHANGE_REQUIRED`). 172 pre-existing tests + golden vertical slice (7) +
  Stage1/Stage2 identity tests (21) pass unchanged. `composer.py` untouched; no
  engine wired, no proposal/execution authority. Still `RESEARCH_DRAFT`. See
  `docs/status/ST_LARGE_SMC_V1_C14B_OCCURRENCE_IDENTITY_HARDENING_STATUS.md`.
- **v1.0.5 (2026-09-02, `RESEARCH_ONLY_FUNNEL_V1`):** implemented the minimum
  research-only two-part funnel (DATA COLLECTION -> DECISION MAKING) as
  `src/large_smc_research/` (`engine.py`, `target_model.py`, `decision.py`) -- a thin
  orchestration layer over the already-frozen `historical_replay.stage2` boundary,
  zero E1/E2/E3/M1/M2/M3 redetection. Resolved: C01 (instruments -> `[EURUSD]` only),
  C16 (warmup -> reuse of `D1=60/H1=50/M5=200`), C11 target-model adapter
  (`CONTRACT_ONLY` formula now `IMPLEMENTED`, unchanged), C18 (simultaneous-combination
  selection -> `RECORD_ALL_INDEPENDENTLY`, reuse of C14's already-frozen
  `selection`/`coexistence` fields). `decision_states` dropped the placeholder `READY`
  for `RESEARCH_QUALIFIED`/`INVALIDATED`. **Deliberately left BLOCKED, per owner
  decision:** C10 (broker stop-loss distance) and post-READY pending-entry expiry --
  no formula/clock invented; the engine returns `BLOCKED` for any candidate that would
  otherwise need either, with a decision-packet document recording unselected
  candidate options for each. Still `RESEARCH_DRAFT`; no proposal, demo, live,
  execution, or risk-sizing authority added. See
  `docs/status/ST_LARGE_SMC_V1_RESEARCH_FUNNEL_V1_STATUS.md`,
  `docs/status/ST_LARGE_SMC_V1_C10_STOP_LOSS_DECISION_PACKET.md`, and
  `docs/status/ST_LARGE_SMC_V1_PENDING_ENTRY_EXPIRY_DECISION_PACKET.md`.
