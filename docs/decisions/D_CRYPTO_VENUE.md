# Owner Decision Packet: D_CRYPTO_VENUE

No recommendation made. Consequences only.

## Option A — VT Markets MT5 CFD (BTCUSD/ETHUSD)

- **Data**: `HOST_DATA_NOT_VERIFIED` for historical OHLC (none in this checkout; owner
  host may or may not have it — not assumed either way).
- **Symbols**: already has point-in-time metadata captured
  (`config/symbol_metadata/host_captured/BTCUSD...json`, `ETHUSD...json`).
- **Spread**: point-in-time snapshot only (BTCUSD=1702pts/$17.02, ETHUSD=250pts/$2.50,
  captured 2026-09-30T15:12Z) — not a historical series; stress/scenario use would need
  to be labeled as such, never treated as a backtest-grade cost model.
- **Commission**: UNKNOWN — must stay UNKNOWN, never defaulted to 0.
- **Swap/funding**: CFD overnight swap (swap_long=-20.0 BTC / -25.0 ETH, swap_short=0.0)
  — NOT a perpetual funding rate; must not reuse perpetual funding evidence.
- **Runtime**: `config/v1_tickets/crypto_ticket_v2.yaml` already exists and is ACTIVE,
  but feeds a CRYPTO_PERP-calibrated engine (`STRATEGY_LEDGER.md` flags this as
  "UNVALIDATED" for that reason).
- **Strategy identity**: would need a new, CFD-calibrated contract/identity — the
  existing 2.0.0 contract's validation evidence does not transfer.
- **Validation**: starts from zero for CFD-specific logic/economic verification.

## Option B — Exchange venue (e.g. Bybit linear perpetual / Binance USDT-M)

- **Data**: research feed already exists and is live
  (`src/execution_runtime/bybit_linear_perp_feed.py`, owner-approved scope per
  `AG_V1_0_3_BYBIT_QUALIFICATION_EXCEPTION`); Binance fallback is environment-blocked
  (HTTP 451) in this sandbox.
- **Symbols**: BTCUSDT/ETHUSDT (perpetual-style), already used by
  `ST_LIQUIDITY_SWEEP_RETEST_V1@2.0.0`'s existing calibration.
- **Spread/commission/funding**: perpetual-market conventions apply (funding rate, not
  CFD swap) — existing calibration was built for this venue originally.
- **Runtime**: `config/v1_tickets/crypto_ticket_v1.yaml` (PRESERVED, not ACTIVE) already
  encodes this path.
- **Strategy identity**: matches the existing 2.0.0 contract's original calibration
  target — less identity-transition work than Option A.
- **Validation**: inherits more of the existing research evidence, but produces
  decisions for an instrument the owner may not actually trade (perpetual vs CFD
  account).

This decision gates all of T4's downstream chain (historical-data acquisition, symbol
identity, cost authority, strategy contract compatibility). It should be made before any
new crypto data acquisition effort, since the two options are not interchangeable.
