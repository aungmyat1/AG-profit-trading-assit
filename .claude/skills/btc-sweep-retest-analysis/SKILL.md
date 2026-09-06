---
name: btc-sweep-retest-analysis
description: Explain the ST_LIQUIDITY_SWEEP_RETEST_V1 CRYPTO_PERP (BTCUSDT) contract -- H1 trend gate, M5 sweep/MSS/retest, target geometry, BTC cost model, daily report window, Bybit data authority, and the research-only proposal boundary. Use when asked about BTC sweep/retest setups, the daily BTC report, or why a BTC observation is READY/WATCH/NO_TRADE/DATA_ERROR. Advisory only -- cannot itself produce a proposal or touch execution.
---

> **Ownership note:** This is `ST_LIQUIDITY_SWEEP_RETEST_V1`'s `CRYPTO_PERP` profile
> contract, running on the exact same asset-independent engine
> (`strategy_engine/sweep_retest/engine.py::evaluate_setup`) as that strategy's `FOREX`
> profile -- there is no separate BTC signal engine. Use the generic `liquidity` skill
> for non-strategy sweep/reclaim facts; use `sweep-detection-range-v2` for
> `ST_ASIAN_SWEEP_5R_V1`'s unrelated sweep rule (different strategy, different
> thresholds). See `strategies/ST_LIQUIDITY_SWEEP_RETEST_V1.yaml` and
> `docs/contracts/AG_BTC_DAILY_OBSERVATION_CONTRACT_V1.md`.

# BTC Sweep + Retest Research Contract (CRYPTO_PERP profile)

`strategy_id = ST_LIQUIDITY_SWEEP_RETEST_V1`, `version = 2.0.0`, `profile_id =
CRYPTO_PERP`, `instruments = [BTCUSDT, ETHUSDT]` (BTCUSDT is the only one with a data
adapter and daily report wired up). Market data authority: **Bybit** linear USDT
perpetual, public/read-only (`src/execution_runtime/bybit_linear_perp_feed.py`).
Research/proposal only -- `execution_domain=CRYPTO_RESEARCH`,
`execution_authority=DISABLED`; `CryptoExecutionAdapter` remains NOT_IMPLEMENTED. This
skill never places, authorizes, or implies a broker order.

## Pipeline (read-only description; implemented in `strategy_engine/sweep_retest/`)

1. **Reference box** -- Previous UTC calendar day's High/Low/Mid (`reference.kind:
   PREVIOUS_DAY`), strict `[00:00:00Z, next-day 00:00:00Z)` boundary
   (`profile.py::previous_utc_day_window`). Frozen once the day completes; never
   recomputed from later candles.
2. **H1 trend gate** (`trend.py`, wraps `market_structure.structural_breaks_for_candles`)
   -- bullish routes to LOW-sweep-only/LONG, bearish to HIGH-sweep-only/SHORT, neutral is
   `NO_TRADE_DIRECTION`.
3. **M5 sweep** (`sweep.py`) -- wick pierces the reference High/Low, candle closes back
   inside. A same-candle dual-side sweep is skipped (unresolved), not reported.
   `wick_ratio_filter: DISABLED` in v2.0.0 -- no wick-size threshold is enforced.
4. **M5 MSS confirmation** (`mss.py`, wraps `market_structure.smc_adapter.full_swings`)
   -- a subsequent CLOSED M5 candle must close beyond the located swing;
   intrabar penetration is not sufficient.
5. **M5 retest** (`retest.py`) -- must occur within `entry_ttl_m5_bars=3` closed M5
   candles after MSS confirmation, or the setup expires.
6. **Target geometry** (`targets.py`, asset-independent) -- SL = sweep extreme +/- a
   precomputed buffer (crypto: `stop_buffer.kind: TICK`, 10 ticks, from
   `crypto_symbols.py` -- BTCUSDT tick 0.1; never Forex pip math). TP1 = reference
   midpoint (50% close, remainder to breakeven), TP2 = reference High/Low, minimum
   `tp2_r_multiple = 1.5`. If TP1 lands on the wrong side of entry, or TP2 R multiple is
   below the floor, the **whole setup** is rejected (`NO_TRADE_TARGET_GEOMETRY`) -- no
   substitute single-TP exit exists for either profile.
7. **Guards** -- `execution.daily_loss_guard` / `execution.position_guard`, checked only
   after full qualification, and **combined across the Forex and Crypto profiles of this
   one strategy_id** (one open position, one -2.0R daily circuit for both). A
   guard-blocked setup still records `strategy_qualified=True`; only tradability
   differs.

## BTC-specific orchestration (`src/btc_sweep_research/`)

Never re-detects sweep/MSS/retest -- calls `SweepRetestRuntime.evaluate` (the same
engine) once per enumerated occurrence, then adds:

- **Costs** (`costs.py`): fees `CONFIGURED` (Binance USDT-M standard taker rate 0.05%,
  dated source checked 2026-09-02 -- reused as a documented proxy, not a Bybit-specific
  fee schedule), slippage `HARDCODED` (2 ticks/leg, documented placeholder, not
  measured), funding `HARDCODED` (placeholder rate per 8h interval, not live-fetched).
  Every figure carries its own `source_note`; nothing here is presented as a live rate.
- **Proposal** (`proposal.py`): `BTCSweepResearchProposal`, its own dataclass
  (deliberately *not* `execution.adapter.TradeProposal`), always carrying
  `execution_domain=CRYPTO_RESEARCH` / `execution_authority=DISABLED` /
  `authority=RESEARCH_ONLY`. Guard-blocked occurrences still get an `occurrence_id` and
  a ledger row (`tradability_allowed=False`), never erased.
- **Ledger** (`ledger.py`): keyed by `occurrence_id`
  (`strategy_engine.sweep_retest.occurrence_identity.btc_occurrence_id`); re-observing
  the same occurrence is a no-op, a genuinely different occurrence always gets its own
  row. This is an opportunity ledger, not a position/P&L ledger.
- **Daily report** (`daily_report.py`, `AG_BTC_DAILY_REPORT_V1`): `READY` / `WATCH` /
  `NO_TRADE` / `DATA_ERROR`. Governed by
  `docs/contracts/AG_BTC_DAILY_OBSERVATION_CONTRACT_V1.md` -- report target window
  **06:30-06:45 UTC** the day after the observation date (13:00-13:15 MMT); a run
  outside that window fails closed (`scripts/run_btc_daily_report.py` refuses to
  archive unless `--allow-outside-window --no-archive`, a non-counting diagnostic mode).
  Identical re-run for the same observation date is idempotent (same archived path,
  no duplicate); genuinely changed evidence produces a numbered, additive correction,
  never an overwrite.

## What this skill must never do

Change sweep/MSS/retest thresholds, override a `BLOCKED`/`NO_TRADE`/`DATA_ERROR`
result, invent or forward-fill missing candles, switch market-data provider, or
construct/authorize anything resembling an order. It only explains why the strategy
engine + BTC orchestration produced the decision that already exists.
