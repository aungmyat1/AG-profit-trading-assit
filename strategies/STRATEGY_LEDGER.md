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
