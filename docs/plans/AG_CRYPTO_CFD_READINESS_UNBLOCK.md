# Crypto (BTCUSD/ETHUSD) CFD Readiness Unblock Plan — R3

PR #46 already established candidate discovery is not the bottleneck
(`OSS_CRYPTO_C001`/`OSS_CRYPTO_C002` both `HOLD_DATA`). This plan does not search for
more strategies; it builds the dependency chain and records current state per link.

```
D_CRYPTO_VENUE
      ↓ NOT_DECIDED (see docs/decisions/D_CRYPTO_VENUE.md)
historical-data authority
      ↓ HOST_DATA_NOT_VERIFIED
symbol/venue identity
      ↓ PARTIAL (VT Markets CFD symbol metadata exists; perpetual feed also exists but is a
        DIFFERENT venue/instrument)
cost authority
      ↓ PARTIAL (point-in-time spread snapshot only; commission/swap UNKNOWN or scenario-only)
strategy contract compatibility
      ↓ FAIL (ST_LIQUIDITY_SWEEP_RETEST_V1 2.0.0 is CRYPTO_PERP-calibrated, not CFD-calibrated)
DEV replay
      ↓ BLOCKED (no admissible BTC/ETH OHLC in this checkout)
candidate freeze
      ↓ NOT_REACHED
logic verification
      ↓ NOT_REACHED
economic verification
      ↓ NOT_REACHED
possible production authority
      ↓ NOT_REACHED
```

## BTCUSD / ETHUSD facts (re-verified, not re-discovered)

```
HISTORICAL_OHLC    = NONE found in this git checkout for BTCUSD/ETHUSD CFD
                      (research_external/candidate_factory/data_capability_matrix.json, PR #46)
TIMEFRAMES         = N/A (no OHLC present)
DATE_RANGE         = N/A
SOURCE             = HOST_DATA_NOT_VERIFIED — config/historical_datasets/*.yaml reference a
                      D:\ host path not present in this sandbox checkout (cannot confirm
                      existence or non-existence on the owner's host)
VENUE (data)        = Bybit V5 linear perpetual (research feed, `src/execution_runtime/
                      bybit_linear_perp_feed.py`) + Binance USDT-M fallback (env-blocked) —
                      BOTH are PERPETUAL venues, not VT Markets CFD
VENUE (tickets)     = VT Markets MT5 demo CFD (`config/v1_tickets/crypto_ticket_v2.yaml`,
                      BTCUSDT→BTCUSD, ETHUSDT→ETHUSD symbol mapping)
SPREAD_MODEL        = VT Markets host-captured point-in-time snapshot only: BTCUSD=1702pts
                      ($17.02), ETHUSD=250pts ($2.50) (`config/symbol_metadata/host_captured/*.json`,
                      captured 2026-09-30T15:12Z) — a snapshot, not a historical spread series
COMMISSION_MODEL    = UNKNOWN (never defaulted to zero, per PR #46 friction convention)
SWAP_MODEL          = VT Markets CFD overnight swap: swap_long=-20.0 (BTC) / -25.0 (ETH),
                      swap_short=0.0 (`config/symbol_metadata/host_captured/*.json`)
FUNDING_MODEL       = N/A for the CFD venue (CFD swap ≠ perpetual funding rate; the perpetual
                      research feed's funding-rate behavior must NOT be reused as CFD evidence)
SYMBOL_METADATA     = PRESENT for the CFD venue (point-in-time only); NOT PRESENT as a
                      historical series
```

`STRATEGY_LEDGER.md` already documents the core conflation risk explicitly: the v2 ticket
runner "feeds the SAME frozen 2.0.0 CRYPTO_PERP engine with VT Markets MT5 demo CFD
candles... The MT5 CFD input is a new, UNVALIDATED data source for informational tickets
only: the perp-calibrated cost model and all validation evidence are unchanged and do not
transfer to it." This plan treats that as the standing, unresolved gap — it is not
repaired here.

## What would unblock each link (no selection made)

1. **D_CRYPTO_VENUE decision** (owner, see `docs/decisions/D_CRYPTO_VENUE.md`) — must be
   made before acquiring more data, since perpetual vs CFD data/cost/symbol identity differ.
2. **Historical-data acquisition** for whichever venue is chosen (HOST_DATA_NOT_VERIFIED
   must be resolved to either a confirmed source or a confirmed absence — do not guess).
3. A **new, CFD-specific strategy contract/calibration** (or an owner-approved derived
   candidate id) if VT Markets CFD is chosen, since the existing 2.0.0 contract is
   perp-calibrated.
4. Only after 1–3: DEV replay against the preregistered-style process already used in
   PR #46 (no economic promotion implied by that alone).
