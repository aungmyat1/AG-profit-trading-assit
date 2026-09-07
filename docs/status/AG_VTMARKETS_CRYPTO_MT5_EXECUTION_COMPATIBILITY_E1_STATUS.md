# AG_VTMARKETS_CRYPTO_MT5_EXECUTION_COMPATIBILITY_V1 -- E1 Read-Only Audit (2026-09-07)

Read-only broker inspection only. No `order_send`, no position open/close, no SL/TP
modification, no pending order, no account mutation was performed anywhere in this
audit -- only `mt5.initialize()`, `mt5.account_info()`, `mt5.terminal_info()`,
`mt5.symbols_get()`, `mt5.symbol_info()`, `mt5.symbol_info_tick()`.

## Critical finding: broker identity mismatch

**The only MT5 terminal available/connected in this environment is `VantageMarkets-Demo`
(Vantage Markets (Pty) Ltd), not VT Markets.** These are two distinct real-world
brokers with similar names. No VT Markets terminal, login, or connection was available
to audit. This report therefore does **not** confirm VT Markets crypto compatibility --
it audits the terminal that was actually reachable, under its own name, and
distinguishes that fact explicitly throughout. If VT Markets specifically is the
intended future execution venue, a VT Markets Demo login is required before E1 can be
completed for that broker.

```text
account.server  = VantageMarkets-Demo
account.company = Vantage Markets (Pty) Ltd
account.login    = 25972746
account.currency = USD
terminal.connected = True
```

## Symbol discovery (VantageMarkets-Demo, read-only)

1202 total symbols available. Crypto-adjacent names found:
`BTCUSD, ETHUSD, BTCBCH, BTCETH, BTCEUR, BTCLTC, ETHBCH, ETHEUR, ETHLTC, BTCJPY,
ETHJPY, BTCO, GBTC, BTCXAU, ETHXAU, NETH25.r` -- **not** `BTCUSDT`/`ETHUSDT` (no
USDT-quoted crypto symbol found; confirms section 22's instruction not to assume
`BTCUSDT` exists here).

### BTCUSD (this broker's canonical BTC/USD instrument)

```text
description          = Bitcoin
trade_mode            = 4 (SYMBOL_TRADE_MODE_FULL)
trade_calc_mode       = 5 (SYMBOL_CALC_MODE_EXCH_STOCKS_MOEX-class enumeration value on
                        this build; in practice a CFD-style non-Forex calc mode --
                        confirmed distinct from EURUSD's calc_mode=0/FOREX below)
digits / point         = 2 / 0.01
trade_tick_size        = 0.01
trade_tick_value       = 0.01
trade_contract_size    = 1.0
volume_min/max/step    = 0.01 / 100.0 / 0.01
trade_stops_level      = 0 (no broker-enforced minimum stop distance observed at capture time)
trade_freeze_level     = 0
filling_mode           = 2
currency_base/profit/margin = BTC / USD / BTC  <-- margined in BTC, quoted in USD
live bid/ask (capture time) = 79638.04 / 79655.06 (spread ~1702 points = ~$17.02, ~2 bps)
```

### ETHUSD

```text
description          = Ethereum
digits/point           = 2 / 0.01
trade_contract_size    = 1.0
currency_base/profit/margin = ETH / USD / ETH
live bid/ask            = 2496.58 / 2499.12 (spread ~254 points = ~$2.54)
```

### EURUSD / GBPUSD (protection check -- existing FX pipeline must remain unaffected)

```text
EURUSD: digits=5, point=1e-05, trade_contract_size=100000.0, tick_value=1.0, currency_margin=EUR
GBPUSD: digits=5, point=1e-05, trade_contract_size=100000.0, tick_value=1.0, currency_margin=GBP
```

Both confirmed **unchanged, standard 100,000-unit FX contracts** -- identical shape to
what the existing FX pilot pipeline already assumes. No FX regression risk observed
from this audit itself (read-only; nothing was modified).

## Cross-venue instrument reconciliation: MT5 BTCUSD (VantageMarkets-Demo) vs. Bybit
BTCUSDT linear perpetual (the strategy's existing market-data authority)

| Dimension | Bybit BTCUSDT (current data authority) | VantageMarkets-Demo BTCUSD |
|---|---|---|
| Quote currency | USDT | USD |
| Contract type | linear perpetual future (funding every 8h) | CFD (no funding mechanism found in symbol metadata) |
| Margin currency | USDT (linear) | **BTC** (inverse-style margining) |
| Price basis | Bybit's own order book/mark price | broker's own CFD price feed (a derived/aggregated quote, not the same order book) |
| Tick size | exchange-defined (sub-$ granularity) | 0.01 (~1 cent) |
| Spread (observed) | not separately re-queried this audit (out of scope -- no Bybit call made) | ~$17 (~2 bps) at capture time |
| Weekend/24-7 behavior | trades continuously, no weekend gap | CFD crypto often still quotes on weekends but under different liquidity conditions -- not verified this audit |
| Funding/financing | funding rate applies | not confirmed present or absent from symbol metadata alone; would need explicit broker documentation |

**These are not the same instrument and must not be treated as interchangeable without
an explicit, signed price-basis reconciliation.** `ST_LIQUIDITY_SWEEP_RETEST_V1`'s
existing sweep/MSS/retest geometry (reference highs/lows, sweep levels, retest zones)
is computed entirely from Bybit's own OHLCV series (`src/execution_runtime/
bybit_linear_perp_feed.py`). Executing against a structurally different CFD price feed
without reconciling basis risk, spread, and margining differences would silently change
the strategy's real-world economics versus what its own backtested/research evidence
describes. This is flagged as a genuine incompatibility requiring an owner decision, not
resolved here.

## Existing MT5 execution infrastructure audit (read-only inspection, no code changed)

- `src/mt5/symbol_resolver.py` -- **already broker-metadata-driven**, its own docstring:
  "no pip-value assumption baked in here." Confirmed generic.
- `src/execution/risk.py` -- **already generic**, its own docstring: "the same function
  sizes FX, metals, or anything else MT5 exposes ... rather than a hardcoded pip-value
  formula." Confirmed generic.
- `src/execution/executor.py:299` -- one narrow fallback: `point = symbol_meta.point if
  symbol_meta else 0.0001`. This defaults to an FX-scaled point size ONLY when
  `symbol_meta` is missing entirely; the primary path already reads the broker's real
  `point` value (confirmed 0.01 for BTCUSD above). Flagged as a small latent
  correctness note (an FX-shaped fallback exists in the missing-metadata path) --
  **not fixed here**, since E1 is audit-only and no defect was actually triggered
  (crypto proposals are expected to always carry a populated `symbol_meta`).
- No other hardcoded `100000`/`0.0001`/pip-specific logic was found in
  `src/execution/*.py` beyond the fallback above.

## E1 classification

```text
VTMARKETS_MT5_CRYPTO_EXECUTION_ASSESSMENT_INCOMPLETE
```

Reason: VT Markets itself was never reachable/auditable in this environment (broker
identity mismatch -- see above). The audit performed instead targets
`VantageMarkets-Demo`, the only connected terminal, and produces this conditional
finding for that broker specifically:

```text
IF VantageMarkets-Demo were the intended crypto demo venue:
  VTMARKETS_MT5_CRYPTO_EXECUTION_BLOCKED_BY_CROSS_VENUE_INSTRUMENT_MISMATCH
  (Bybit-referenced strategy geometry vs. broker CFD price/margin basis --
  requires an explicit owner-signed reconciliation before E2, not an
  engineering blocker in the existing MT5 execution code itself, which is
  already broker-metadata-generic).
```

## What this audit did NOT do

- Did not connect to, or find any way to connect to, an actual VT Markets terminal.
- Did not place, modify, or close any order or position.
- Did not change `execution/`, `mt5/`, or any strategy file.
- Did not authorize crypto execution, demo or otherwise. `ST_LIQUIDITY_SWEEP_RETEST_V1`
  remains `execution_authority=RESEARCH_ONLY`; `crypto_execution_adapter` remains
  `NOT_IMPLEMENTED`.
- Did not implement E2 (conditional on E1 confirming compatibility, which it did not).
- Did not attempt E3 (any demo order) -- explicitly out of scope for this task.
