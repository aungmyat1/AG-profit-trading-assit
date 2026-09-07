# BTC Research-to-Execution Economic Reconciliation -- Vantage BTCUSD (2026-09-07)

Read-only audit + owner-review reconciliation contract. No order placed, no execution
code changed, no routing authorized. Supersedes nothing in
`docs/status/AG_VTMARKETS_CRYPTO_MT5_EXECUTION_COMPATIBILITY_E1_STATUS.md` (preserved) --
adds the full symbol metadata (including swap fields, not captured in that earlier pass)
and the stop-distance model comparison this task requires.

## Venue identity (re-confirmed, not reopened)

Per `docs/status/AG_VTMARKETS_CRYPTO_MT5_EXECUTION_COMPATIBILITY_E1_STATUS.md` and the
concurrent owner-driven commits `ba804d7`/`bf4a0ea`/`a546b45` (`.env` credential keys
explicitly renamed to `VANTAGE-DEMO-*` twice by the owner), the confirmed execution
venue is **VantageMarkets-Demo**, not VT Markets. Not reopened here per this task's own
instruction (no contradictory new evidence appeared).

## Full Vantage BTCUSD metadata (live read, this session)

```text
digits              = 2
point                = 0.01
trade_tick_size      = 0.01
trade_tick_value     = 0.01
trade_contract_size  = 1.0
volume_min/max/step  = 0.01 / 100.0 / 0.01
trade_stops_level    = 0 (points; no broker-enforced minimum distance observed at capture time)
trade_freeze_level   = 0
currency_base         = BTC
currency_profit       = USD
currency_margin       = BTC   <-- inverse-style margining (margin denominated in BTC, not USD/USDT)
swap_long             = -20.0 (points/day, charged for a held LONG position)
swap_short            = 0.0 (points/day for a held SHORT position)
swap_mode             = 5 (raw MT5 enum value, not further decoded here -- see note below)
bid/ask (capture time) = 79377.65 / 79394.74 (spread ~1709 points = ~$17.09, ~2 bps)
```

**New finding versus the prior E1 audit**: BTCUSD carries a real, asymmetric overnight
swap (`swap_long=-20.0`, `swap_short=0.0` points/day at capture time) -- a materially
different financing mechanism from Bybit's BTCUSDT funding rate (paid/received every 8
hours, sign determined by the funding rate, symmetric in mechanism even if not in
realized value). `swap_mode=5` is reported as a raw metadata value; this document does
not claim to have decoded its exact MT5 enum meaning (a documented conversion would be
needed before this value could be used in any cost model) -- reported as `RAW_METADATA`,
not `INTERPRETED`, consistent with this task's "no guessing" instruction.

## Reconciliation contract (owner-review, not signed, no routing authorized)

```text
source_venue                = Bybit
source_symbol                = BTCUSDT
source_instrument_type       = linear perpetual future
source_quote_currency         = USDT

execution_venue               = VantageMarkets-Demo
execution_symbol              = BTCUSD
execution_instrument_type     = CFD
execution_quote_currency      = USD

source_reference_price        = Bybit's own order book / mark price (not re-queried this pass)
execution_reference_price     = Vantage bid/ask (captured above)

execution_point                = 0.01
execution_tick_size            = 0.01
execution_tick_value           = 0.01
execution_contract_size        = 1.0
execution_volume_min/max/step  = 0.01 / 100.0 / 0.01

execution_trade_stops_level    = 0 (at capture time -- not guaranteed constant; must be
                                 re-read at decision time, never cached indefinitely)
execution_freeze_level         = 0

account_currency                = USD (per `mt5.account_info().currency`, prior E1 audit)
profit_currency                 = USD
margin_currency                 = BTC (inverse-style -- NOT the same margin mechanism as
                                 Bybit's USDT-margined linear perpetual)

spread (observed, Vantage)      = ~1709 points (~$17.09) at capture time -- a point-in-time
                                 sample, not a distribution; varies with market conditions
commission                      = NOT CAPTURED this pass (would require account-level
                                 commission schedule, not exposed via symbol_info)
swap/funding                    = MATERIALLY DIFFERENT MECHANISMS (Vantage: daily
                                 asymmetric swap in points; Bybit: 8-hourly funding rate)
                                 -- not directly convertible without an explicit,
                                 signed conversion model

timestamp_authority              = MT5 server time (Vantage) vs. Bybit server time --
                                 not reconciled to a single authority this pass
staleness_policy                  = NOT DEFINED for cross-venue use (existing FX/BTC
                                 staleness checks are single-venue only)
mapping_version                   = UNVERSIONED (config/mt5.yaml's symbol_map has no
                                 version field; flagged as a gap, not fixed here)
```

## Stop-distance mapping models (compared, not selected)

Given a Bybit-referenced entry/stop pair (`source_entry`, `source_stop`) and a Vantage
reference price (`execution_reference_price`) at decision time:

### Model A -- Fractional distance
```text
source_fraction = abs(source_entry - source_stop) / source_entry
execution_stop_distance = execution_reference_price * source_fraction
```
Preserves the *relative* (percentage) risk distance across venues regardless of the
~2-bps price gap between Bybit's mark price and Vantage's mid. Assumes the two venues'
prices move proportionally, which is plausible for the same underlying asset but not
verified empirically this pass (would require a time-aligned price-correlation study,
not attempted here -- no such study exists in the repository).

### Model B -- Absolute quote-distance
```text
execution_stop_distance = abs(source_entry - source_stop)
```
Only valid if the two quote currencies are treated as directly fungible (both are
USD-denominated in practice: USDT ≈ USD in normal market conditions, though not
identical -- USDT can and does deviate from USD peg, a real, if usually small, additional
source of error this model ignores entirely).

### Model C -- Price-ratio transformed distance
```text
execution_stop_distance = source_stop_distance * (execution_reference_price / source_reference_price)
```
Algebraically, **Model C is identical to Model A** when `source_stop_distance` in Model
C is `abs(source_entry - source_stop)`: substituting shows
`execution_reference_price * (abs(source_entry - source_stop) / source_entry) `
equals Model A's formula only if `source_reference_price == source_entry` (i.e., the
"reference price" used for the ratio is the same as the entry price). If
`source_reference_price` is instead a separately-sampled live price (not the entry
price itself), Models A and C diverge because Model C's ratio then reflects
Bybit's own price drift since entry, layered on top of the venue-price-gap effect Model
A captures alone. **This distinction was not specified precisely enough in the
originating proposal to determine which case applies** -- flagged as an open question
for the owner, not resolved here.

**None of the three models incorporates the actual determinant of executable risk**:
`execution_tick_value`, `execution_contract_size`, and `account_currency` conversion.
All three only produce a *price distance*; converting that into an actual position size
and dollar risk still requires the full normalized-risk chain (tick value × contract
size × volume, per account currency) -- none of which is implemented in this repository
today for BTCUSD specifically (per the prior E1 audit, `execution/risk.py` is already
generic/broker-metadata-driven at the code level, but has never been exercised against
Vantage BTCUSD metadata).

## What this document does NOT do

- Does not select Model A, B, or C.
- Does not implement any cross-venue routing, sizing, or execution code.
- Does not authorize BTC execution of any kind. `ST_LIQUIDITY_SWEEP_RETEST_V1` remains
  `execution_authority=RESEARCH_ONLY`; `CryptoExecutionAdapter` remains
  `NOT_IMPLEMENTED`.
- Does not decode `swap_mode=5`'s exact MT5 enum semantics -- reported as raw metadata.
- Does not query or estimate commission (not exposed by `symbol_info`; would require
  account-level documentation or a live `order_check` dry-run, neither performed here).
