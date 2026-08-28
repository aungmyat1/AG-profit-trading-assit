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
  - `entry_rules.{long,short}_setup.entry_order_type: MARKET_OR_LIMIT` does not specify
    which. `execution/intent_builder.py` treats this as undefined and fails closed with
    `ENTRY_EXECUTION_UNDEFINED` rather than choosing -- so this strategy cannot currently
    reach `READY_FOR_ORDER_CHECK` until this value is changed to `MARKET` or `LIMIT`
    (with a defined limit-price rule, if `LIMIT`).

## SESSION_TRADE_V1 -- Asian/London session trend-continuation & sweep strategy

- **Registered:** 2026-08-27
- **Contract:** `strategies/session_trade/contract.yaml` (this repo) -- **by reference**, not a
  code copy. The signed implementation, its own execution ledger, and its own test suite live in
  the separate repository `D:\ddev\Session Trade Codex` (`config/strategy.yaml`,
  `strategy_id: ASIAN_SESSION_V1`, `session_strategy/engine.py`). See
  `SESSION_TRADE_V1_SPEC.md` for the full frozen spec and
  `Session Trade Codex\SESSION_PAIR_STABILIZATION_STATUS.md` for that repo's own
  test/authority verification (313 passed / 4 failed there, independently maintained).
- **Status:** demo-authorized for one of its two execution cycles; see spec for exact gates.
- **Family:** Session reference-box trend-continuation / sweep / range-rejection (own classifier,
  NOT `ER_ONLY_V2` -- see `ARCHITECTURE_CONFLICT_AUDIT.md` for why these are two legitimately
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
