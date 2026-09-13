# AG Vantage MT5 Crypto Venue V1

Date: 2026-09-13

Status: **LIVE_VERIFIED (READ-ONLY) / UNIT_TESTED / ORDER SEND NOT EXERCISED**

Companion to `docs/status/AG_WEB_VANTAGE_DEMO_EXECUTION_BRIDGE_V1.md` (2026-09-10),
which this document does not supersede. That document describes the FX manual
demo-execution bridge; this one records extending the same bridge to the Vantage Demo
MT5 account's crypto CFDs (`BTCUSD`, `ETHUSD`; canonical `BTCUSDT`, `ETHUSDT`).

No strategy's `demo_authorized` or `live_authorized` flag was read-modified. No LIVE
credential path was added: `src/mt5/config.py` still refuses `MT5_ENVIRONMENT=LIVE`.
No broker order was submitted during this work.

## What the trace found

The backend chain was already asset-class agnostic end to end. Traced:
`scripts/web_execute_trade.py` -> `assistant.commands.execute_command()` ->
`execution.executor.execute()` -> `trade_management.pretrade_engine` (geometry +
sizing) -> `execution.mt5_gateway.order_open()` -> `mt5.account_guard`.

- `mt5/broker_symbol_resolver.py` is config-driven and already maps
  `BTCUSDT -> BTCUSD` / `ETHUSDT -> ETHUSD` under `VANTAGE` in `config/mt5.yaml`.
- `mt5/symbol_resolver.py::get_symbol_meta()` reads `trade_tick_size` /
  `trade_tick_value` / `trade_contract_size` / `volume_*` directly, with no FX constant
  anywhere, and already selects a symbol into Market Watch if it is not visible.
- `trade_management/sizing.py` derives volume from `tick_value / tick_size`, not from a
  pip-value formula, so the crypto contract shape sizes correctly with no change.
- `trade_management/geometry.py` and `execution/validator.py` use relative SL/TP sign
  rules and report distance in the symbol's own `point`; neither embeds an FX scale.
- `execution/mt5_gateway.py` and `mt5/account_guard.py` take no symbol argument in their
  authorization paths, so there is no per-symbol branch a crypto order could take around
  the Demo-account and broker-identity checks.
- `execution/executor.py`'s module constant `SUPPORTED_EXECUTION_DOMAIN = "MT5_FX"`
  appears only in the message of the `UnsupportedExecutionDomain` error; the actual gate
  is `isinstance(command, TradeCommand)`. A crypto `TradeCommand` is therefore already
  accepted, and a `CryptoTradeCommand`/BTC research proposal is still rejected.

One genuine asset-class-specific defect was found and fixed (see below). The manual
bridge script itself required no change.

### Gate semantics (unchanged, and identical for crypto and FX)

The manual bridge's `ExecutionSource.USER_EXPLICIT_ORDER` path is **not** gated by any
strategy's `demo_authorized` flag, for crypto or for FX. Its gates are:
`user_confirmed=True` supplied per individual order; `config/trading.demo.yaml`'s
`mode: TRADING` + `execution.allow_order_check/allow_order_send`; the account guard's
broker-identity and Demo classification checks; `account.allow_live_trading: false`;
geometry/sizing validation; duplicate-command and broker-reconciliation checks. Crypto
now passes through that exact list, with no crypto-specific bypass and no crypto-specific
extra gate.

The separate ticket-based gateway (`POST /api/tickets/{approval_id}/authorize-demo` ->
`src/api/execution_service.py::authorize_demo_execution`) **is** gated by
`strategies/registry.yaml`'s `demo_authorized`, and that is unchanged: no crypto strategy
is demo-authorized there, so no automated crypto proposal can execute. This work did not
touch that gate.

## Live verification (read-only)

Performed against the connected terminal on 2026-09-13. Account read back as login
`26088035`, server `VantageMarkets-Demo`, `trade_mode=0` (Demo).

| Canonical | Broker symbol | `trade_mode` | contract_size | tick_size | tick_value | vol min/step | digits |
|---|---|---|---|---|---|---|---|
| EURUSD | EURUSD | 4 (FULL) | 100000 | 1e-05 | 1.0 | 0.01 / 0.01 | 5 |
| GBPUSD | GBPUSD | 4 (FULL) | 100000 | 1e-05 | 1.0 | 0.01 / 0.01 | 5 |
| BTCUSDT | BTCUSD | 4 (FULL) | 1.0 | 0.01 | 0.01 | 0.01 / 0.01 | 2 |
| ETHUSDT | ETHUSD | 4 (FULL) | 1.0 | 0.01 | 0.01 | 0.01 / 0.01 | 2 |

`get_symbol_meta()` returned valid metadata for `BTCUSD`/`ETHUSD` with no code change.
After selection into Market Watch, both quoted normally (`BTCUSD` bid 77292.86 / ask
77309.92; `ETHUSD` bid 2522.72 / ask 2525.20) and returned M15 candles.

`1 lot BTCUSD = 1 BTC` (`tick_value / tick_size = 1.0` USD per 1.0 price unit per lot),
so a $1,000 stop risks $1,000 per lot. FX lot-size intuition does not transfer; size with
the risk calculator.

Not verified live: order submission. `NOT_EVALUATED`; no order was sent.

## Defect found and fixed: zero quote on a freshly selected symbol

`BTCUSD`/`ETHUSD` are not in the Vantage Demo terminal's default Market Watch, whereas
`EURUSD`/`GBPUSD` always are. Observed live: immediately after the existing select-once
path adds such a symbol, `mt5.symbol_info_tick()` can return `bid=0.0 / ask=0.0` with a
non-zero tick time. `mt5/market_data.py::get_tick()` only rejected `tick.time == 0`, so a
`0.0` would have flowed into `execution.executor._resolve_entry_price()` as a real market
price and been rejected further downstream by geometry with a misleading reason code
(`INVALID_LONG_STOP`) rather than an accurate one.

`get_tick()` now also rejects a non-positive Bid/Ask with the existing `DATA_MISSING`
reason code. This is an added rejection only; no previously valid tick becomes invalid,
and FX behaviour is unaffected (an FX quote is never zero with a non-zero tick time).

## Changes

Backend:
- `src/mt5/market_data.py` — `get_tick()` rejects a non-positive Bid/Ask (`DATA_MISSING`).
- `src/execution/crypto_router.py` — added `DOMAIN_MT5_CRYPTO` with `DEMO`/`REAL` cells,
  mirroring the `MT5_FX` cells' shape (`base_url=None`). Purely additive labeling: this
  module has no production caller in the repository (only its own test imports `route()`),
  so the cells grant no authority to anything. The manual MT5 bridge deliberately does not
  consult this router, for crypto or FX — it is the Binance-oriented automated crypto
  pipeline's domain-labeling concept, not an execution prerequisite. The original four
  cells are unchanged and now pinned by a regression test.

Frontend:
- `web/src/data/marketData.ts` — added `MT5_CRYPTO_VENUE_SYMBOLS` (an explicit
  `canonical -> brokerSymbol` allow-list mirroring `config/mt5.yaml`), plus
  `isMt5CryptoVenueSymbol()` / `canonicalCryptoSymbol()`.
- `web/server.ts` — `POST /api/execution/execute` previously rejected **every**
  `category === 'CRYPTO'` symbol with `CRYPTO_EXECUTION_BLOCKED`, a gate FX did not have.
  It now applies that block only to crypto symbols the MT5 broker map does **not**
  contain, so `BTCUSD`/`ETHUSD` are treated exactly like an FX symbol and other crypto
  venues stay fail-closed. This grants no broker authority: the real-mode branch of that
  route is still retired (`410 EXECUTION_ROUTE_RETIRED`, WP0A containment) for crypto and
  FX alike, so the only path opened for crypto is the same non-broker simulation FX had.
- `web/src/components/Execution/ExecutionCockpit.tsx` — `BTCUSD`/`ETHUSD` now use the
  existing confirmation-modal flow instead of a hardcoded disabled button; the outdated
  "Binance/Bybit blocked" incubation notice is replaced, for those two symbols only, by a
  venue notice naming the Vantage Demo MT5 account and the differing contract shape. A
  crypto symbol outside the venue map keeps the original disabled button verbatim.

Tests:
- `tests/test_vantage_mt5_crypto_venue.py` (new) — canonical-symbol resolution;
  `get_symbol_meta` on a crypto-shaped contract and its fail-closed path; the Market
  Watch select-once path; crypto sizing/geometry via `evaluate_trade_management`;
  below-min-volume fail-closed; the new `get_tick` guard; `execute_command()` gate parity
  (unconfirmed crypto rejects with the same `EXECUTION_NOT_AUTHORIZED` FX gets, confirmed
  crypto reaches the gateway with symbol/volume/SL intact and is stopped by the gateway's
  own fail-closed default, bad crypto geometry rejects with the same code FX gets,
  account guard provably symbol-independent); plus `live_mt5`-marked read-only checks
  against the real terminal.
- `tests/test_crypto_router.py` — added a pin on the original four cells' exact values,
  coverage of the new `MT5_CRYPTO` cells, and more unknown-combination rejection cases.
- `web/tests/vantage_mt5_crypto_venue.test.ts` (new) — venue-map unit assertions
  (including that unmapped crypto and FX symbols are excluded) and HTTP parity: mock mode
  accepts `BTCUSD`/`ETHUSD` exactly as it accepts `EURUSD` and still flags the result
  simulated; real mode still returns `410 EXECUTION_ROUTE_RETIRED` for crypto;
  `user_confirmed` is still required. Added to `web/package.json`'s `test` script.

## Research authority vs. execution venue (added during integration review, 2026-09-13)

This venue addition is an **execution** capability only. It does not change, and must
never be read as changing, `ST_LIQUIDITY_SWEEP_RETEST_V1`'s research data authority:

```text
BTC research / edge validation  = Bybit (see PROJECT_STATUS.md "CRYPTO DATA ADAPTER")
BTC manual Demo execution       = Vantage MT5 (this document)
```

These are, and must remain, two independent venues that may differ in symbol naming,
price, spread, fees, funding, contract semantics, and liquidity — a Bybit-derived
research price, spread, or contract size is never a substitute for a fresh Vantage MT5
quote/`symbol_info()` read, and vice versa. `1 lot BTCUSD = 1 BTC` on Vantage; Bybit's
BTCUSDT perpetual has its own separate contract/funding shape.

This separation is already enforced technically, not just documented: every
`BTCSweepResearchProposal` (the Bybit/Binance-research-derived object) is a distinct
dataclass from `execution.executor`'s `TradeCommand`, and
`tests/test_btc_proposal_execution_boundary.py` statically asserts `src/btc_sweep_research/`
never imports `execution.executor`, `mt5.management_gateway`, `execution.coordinator`, or
`execution.adapter` — so no BTC research proposal's geometry can reach an MT5 order
without a human manually re-entering fresh values through the same
`scripts/web_execute_trade.py` bridge FX uses, which itself always re-reads a live
Vantage quote and `symbol_info()` (never a cached/research price) before sizing or
sending. Adding the Vantage MT5 crypto venue does not weaken or bypass that boundary in
any way.

## Remaining for the owner (manual)

1. Open MetaTrader 5, confirm the configured Vantage Demo account is logged in, and add
   `BTCUSD` and `ETHUSD` to Market Watch (they are not there by default).
2. Confirm automated trading is permitted in the terminal.
3. Optionally close the loop with one explicitly confirmed micro-lot crypto order through
   the same manual bridge FX uses (`python scripts/web_execute_trade.py --symbol BTCUSD
   --side BUY --volume 0.01 --sl <below entry> --confirm`), then verify the resulting
   ticket in the terminal and close it. This has deliberately not been done automatically.

Note for step 3: `src/.env` is gitignored and is not present in a git worktree checkout,
so `mt5.account_guard` returns `CONFIG_ERROR` there. Run the bridge from the main
checkout, not from a worktree.
