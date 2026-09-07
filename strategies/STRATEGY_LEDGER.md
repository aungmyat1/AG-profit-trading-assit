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
  - **`LONDON_NEWYORK` pilot activated (2026-09-02):** the `LONDON_NEWYORK` session pair
    (registered 2026-08-26, v1.1.0) had no operating pilot until now -- only `ASIAN_LONDON`
    ran (`config/pilot/AG_POST_ASIAN_LONDON_PILOT_V1_0_1.yaml`'s own `inactive_cycle:
    [LONDON_NEWYORK]` note). `config/pilot/AG_POST_LONDON_NEWYORK_PILOT_V1_0_1.yaml`
    activates it as an independent, proposal-only pilot with its own `state_dir`
    (`journal/post_london_newyork_pilot/`) -- required because `post_asian_pilot.governor.
    DailyTradeLedger`'s capacity identity is `strategy_id + trading_date` only, not
    cycle-aware; a shared journal directory would let an `ASIAN_LONDON` slot silently
    consume `LONDON_NEWYORK`'s independent per-cycle quota for the same symbol/day. No
    strategy-file change. `PROPOSAL_ONLY`, no live/demo authorization change. See
    `tests/test_post_london_newyork_pilot.py`.

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
- **`REPLAY_METADATA_DECOUPLING_V1` (2026-09-02, no version bump — replay
  infrastructure, not strategy semantics):** the MT5-symbol-metadata replay gap
  disclosed in v1.0.6's own phase is now **resolved**. Owner authorized a
  dataset-fingerprint-bound historical `tick_size=0.00001` for
  `EURUSD_M5_202504211715_202607310000` only (`config/historical_datasets/`,
  `HISTORICAL_ANALYSIS_ONLY` scope, tagged `SYNTHETIC_RESEARCH`, never usable for
  execution). Wired into `historical_replay/data_source_patch.py`'s
  `historical_data_context` as an opt-in, backward-compatible parameter, patching the
  single shared call site (`market_structure.tiers.get_symbol_meta`) both C11's
  target adapter and M1's pre-existing inducement-candidate detection depend on. Live
  watcher behavior verified unchanged (structurally unreachable by this change). A
  corrected September 2025 replay shows exactly one changed combination cell (E1M1:
  now `M_CONFIRMED=1, ENTRY_ARRAY_CREATED=1, READY=1`, previously all zero) — every
  other cell byte-identical to the pre-fix run, classified
  `REPLAY_METADATA_CORRECTION`, not a regression. C10 remains the sole open blocker.
  See `docs/status/ST_LARGE_SMC_V1_REPLAY_METADATA_DECOUPLING_V1_STATUS.md`.
- **v1.0.6 (2026-09-02, `OUTCOME_LIFECYCLE_V1`):** post-READY pending-entry expiry
  **RESOLVED_BY_REUSE** -- `historical_replay/fill_simulator.py` (pre-existing,
  already tested, never wired to this strategy) already establishes no time-based
  expiry exists for this E/M pipeline; a pending entry is terminal only via `FILLED`
  or structural `INVALIDATED_BEFORE_FILL`, with `UNFILLED_AS_OF_DATA_END` as an honest
  data-boundary state, never a fabricated expiry. New
  `src/large_smc_research/pending_entry.py` (thin adapter, 7 new tests). C10 (broker
  stop) remains genuinely `UNSIGNED`/`BLOCKED` -- unaffected. **New finding, disclosed
  not fixed:** wiring the engine into a real historical replay revealed that C11's
  target-model adapter (and, project-wide, the pre-existing M1 inducement-candidate
  detection in `historical_replay/stage2.py`) depends on
  `market_structure.tiers.analyze_structure_tiers`, which requires a live MT5 terminal
  for symbol metadata that `historical_replay/data_source_patch.py` never patches --
  every historical replay has silently starved M1's inducement detection, previously
  misread as "M1 rarely qualifies." Fixed in this engine: a target-model failure for
  any reason other than the genuine `REJECT_NO_TARGET` outcome now fails closed to
  `DATA_ERROR`, never a silent `NO_TRADE`. The underlying gap itself is
  `SHARED_CHANGE_REQUIRED` (touches the live `SMC_CONDITIONAL_ENTRY_V2` watcher's own
  code path) and is deliberately not fixed this phase. Recommendation: `HOLD`. See
  `docs/status/ST_LARGE_SMC_V1_OUTCOME_LIFECYCLE_V1_STATUS.md` and
  `docs/status/ST_LARGE_SMC_V1_MT5_SYMBOL_METADATA_REPLAY_GAP.md`.
- **v1.0.7 (2026-09-07, `C10_STRUCTURAL_INVALIDATION_V1`):** C10 (broker stop-loss
  distance) **SIGNED and IMPLEMENTED** -- `src/large_smc_research/c10_stop_policy.py`.
  Owner-signed policy: buffer = `max(1.5 pips, 0.35 x ATR14(M5))`
  (`DYNAMIC_ATR_WITH_HARD_FLOOR`; ATR uses only closed M5 candles available at the
  decision timestamp, fetched via the same already-patched, replay-safe
  `stage2.get_latest_candles` seam target selection already uses -- no second MT5
  access pattern introduced; missing/insufficient ATR history fails closed
  (`ATR_NOT_READY`), never silently degrading to the floor alone); side-aware spread
  (LONG: anchor - buffer, no spread term; SHORT: anchor + buffer + verified live
  spread, protecting the structural anchor from Ask-side stop-trigger effects);
  broker-minimum-stop policy = `REJECT` (fail closed, never `WIDEN`). Structural
  anchor/direction/missing-anchor rules are unchanged, already-signed C10 facts
  (`SMCEntryCombinationResult.invalidation_price`, `EXACT_REUSE`). `engine.py`'s final
  decision branch now reaches `RESEARCH_QUALIFIED` (previously documented as
  "currently unreachable") with a real `simulated_broker_stop` when a candidate is
  READY and ATR/spread data are available; it still fails closed to `BLOCKED` on any
  C10 computation failure and to `DATA_ERROR` on a genuine market-data-fetch
  exception. Version bump follows the same precedent as v1.0.5 -> v1.0.6 (pending-entry
  expiry): resolving a previously-declared-BLOCKED unsigned contract gap that changes
  reachable decision states. No M1/M2/M3 detection, entry, candidate-selection, or C14
  semantics changed. 23 new focused unit tests
  (`tests/test_c10_stop_policy.py`) plus 5 new/updated engine-integration tests
  (`tests/test_large_smc_research_engine.py`); full pre-existing Large-SMC suite
  (execution boundary, occurrence identity, target model, golden vertical slice)
  re-verified passing. `proposal_generation_authorized` remains `false` --
  execution/demo/live authority is unaffected by this resolution (promotion eligibility
  is never execution authority). See
  `docs/status/AG_LARGE_SMC_V1_C10_STOP_POLICY_OWNER_DECISION_PACKET_V3_STATUS.md`.

## ST_LIQUIDITY_SWEEP_RETEST_V1 -- Liquidity Sweep + H1 Trend + M5 MSS + Retest (Forex + Crypto)

- **Registered:** 2026-08-30
- **Config:** `strategies/ST_LIQUIDITY_SWEEP_RETEST_V1.yaml`
- **Status:** ACTIVE_INCUBATION (v2.0.0) -- no live/demo execution authority for either
  profile. Forex profile: signal engine only, no operating pilot yet (unlike
  `ST_ASIAN_SWEEP_5R_V1`). Crypto profile: RESEARCH_ONLY / SHADOW / PROPOSAL_ONLY.
- **Family:** Liquidity_Sweep_MSS_Retest
- **Instruments:** EURUSD, GBPUSD (Forex profile); BTCUSDT (Crypto profile -- ETHUSDT is
  declared in the strategy YAML but out of scope for this phase, no adapter built for it).
- **Engine:** `src/strategy_engine/sweep_retest/` -- one asset-independent engine
  (`engine.py::evaluate_setup`), parameterized by `profile.py::MarketProfile`, shared
  unmodified by both profiles.
- **Binance USDT-M BTCUSDT market-data adapter added (2026-09-02):** the first real
  exchange integration in this repo. `src/execution_runtime/binance_usdtm_feed.py`
  implements `execution_runtime.crypto_feed.CryptoCandleFeed` against Binance's public
  `/fapi/v1/klines` + `/fapi/v1/exchangeInfo` REST endpoints (`requests`, no API key) --
  fail-closed on monotonicity, duplicates, gaps, OHLC consistency, NaN/negative/null
  fields, non-positive prices, negative volume, malformed/out-of-range timestamps, stale
  data, and unfinished/forming candles. `UNIT_TESTED` (fully offline/mocked); **live
  connectivity from this development environment is BLOCKED** -- Binance returns
  HTTP 451 ("Service unavailable from a restricted location") on both endpoints as of
  2026-09-02. Re-verify from the actual deployment environment before operational use.
  See `docs/status/AG_COMPLETE_TRADE_OPPORTUNITY_V1_REMEDIATION_STATUS.md`.
- **BTC research runtime added (2026-09-02):** `src/btc_sweep_research/` orchestrates
  fetch -> enumerate every qualifying same-day occurrence -> evaluate (via the existing,
  unmodified `SweepRetestRuntime`) -> record. Never imports
  `execution.executor`/`mt5.management_gateway`/`execution.coordinator`/
  `execution.adapter` (statically and behaviorally verified,
  `tests/test_btc_proposal_execution_boundary.py`). `BTCSweepResearchProposal` declares
  `execution_domain=CRYPTO_RESEARCH` / `execution_authority=DISABLED`.
- **Engine changes (2026-09-02, additive, both profiles share them):**
  - `evaluate_setup`'s `daily_loss_guard`/`open_position_guard` checks moved from before
    qualification to after it -- a setup that reaches full qualification (would be
    `ENTRY_READY`) but is guard-blocked now still reports `strategy_qualified=True` (new
    `SetupState` field) with a `tradability_blocked`/`tradability_reason` verdict,
    instead of the guard silently erasing all qualification evidence. A setup that never
    qualifies is unaffected -- the guard was never consulted for it either way. See
    `engine.py::evaluate_setup`'s own "Guard ordering" docstring.
  - New optional `sweep_search_after` parameter (default `None`, no behavior change for
    any existing caller) lets a caller evaluate a specific, later sweep candidate in the
    same window without re-discovering an earlier one -- the mechanism
    `occurrence_enumerator.py` builds on to let the BTC pipeline collect 0..N distinct
    same-day occurrences instead of being capped at one per symbol/day.
  - `_in_windows`/the H1-direction-to-sweep-direction mapping made public
    (`in_execution_windows`, `sweep_requirement_for_h1_direction`) so orchestration code
    can reuse the exact same window/direction logic without re-deriving it.
- **`execution.executor.execute()` hardened (2026-09-02):** now rejects any object that
  is not `execution.models.TradeCommand` with a typed `UnsupportedExecutionDomain`,
  checked before any field of the argument is read -- an explicit domain gate, not an
  incidental shape-mismatch error. No change to any TradeCommand-shaped call.
- **Not yet defined:** Forex profile has no operating pilot (unlike
  `ST_ASIAN_SWEEP_5R_V1`'s `ASIAN_LONDON`/`LONDON_NEWYORK` pilots) -- signal engine only.
  Crypto simulated-trade lifecycle (fill simulation, R outcome tracking) is not built;
  only the research-observation ledger exists. No live/demo execution authority exists
  for either profile.
