# USDJPY_M15_recorded_spread_60d.csv provenance

- sha256: `bbf37c8cd04e13e424419dc3fb3a3629ec5c8cea49229e25ee662d558ebbc918`
  - computed over the committed git blob (LF line endings): `git show HEAD:tests/fixtures/manual_ticket/USDJPY_M15_recorded_spread_60d.csv | sha256sum`.
    `.gitattributes` marks this file `-text`, so no checkout (including Windows `core.autocrlf`) converts its line endings.
- capture date (UTC): 2026-10-10 11:12:14Z
- terminal/server: VTMarkets-Demo, server name read from the terminal journal log (logs/20261010.log; the capture's allowed MT5 calls cannot read it); terminal build 6063 (terminal `<HOST_SCRATCHPAD>/terminal64.exe`)
- symbol: USDJPY; timeframe M15; window 00:00-15:45 UTC per day
- day set: 60 contiguous weekdays ending 2026-10-09, fixed before capture; dropped days are not replaced
- offset validity: authority for the offset change is the repository VT rule
  (`scripts/research/market_dataset.py::vt_server_wall_to_utc`: server midnight = 17:00 America/New_York),
  which moves the offset from +3h to +2h on 2026-11-01, when US DST ends. Offsets are always measured
  per day (method below), so this date is informational only; no capture reuses an assumed offset.
- relation: AGP-DATA-R3 extended set (60 contiguous weekdays, --with-spread). Existing `*_M15_recorded*.csv` fixtures are unchanged; the spread column is new, OHLC columns use the same format.
- offset method: per day, M1 rollover break located at 17:00 America/New_York on both edges of the day (open = D-1 17:00 NY, close = D 17:00 NY); offset = server label - UTC, whole hours, both edges must agree
- M1 cross-check: every M15 bar must equal OHLC aggregated from its 15 M1 bars (exact at symbol digits); every range read twice and must match
- capture script: scripts/capture_recorded_m15.py (peak working set 55.0 MB)

| date | kept | offset (open/close, h) | M15 bars | M1 bars | M1 cross-check | reason |
|---|---|---|---|---|---|---|
| 2026-07-20 | yes | 3/3 | 64 | 960 | PASS 64/64 |  |
| 2026-07-21 | yes | 3/3 | 64 | 960 | PASS 64/64 |  |
| 2026-07-22 | yes | 3/3 | 64 | 960 | PASS 64/64 |  |
| 2026-07-23 | yes | 3/3 | 64 | 960 | PASS 64/64 |  |
| 2026-07-24 | yes | 3/3 | 64 | 960 | PASS 64/64 |  |
| 2026-07-27 | yes | 3/3 | 64 | 960 | PASS 64/64 |  |
| 2026-07-28 | yes | 3/3 | 64 | 960 | PASS 64/64 |  |
| 2026-07-29 | yes | 3/3 | 64 | 960 | PASS 64/64 |  |
| 2026-07-30 | DROPPED | 3/3 | 64 | 953 | NOT_EVALUATED | M1 gap: 953/960 bars |
| 2026-07-31 | yes | 3/3 | 64 | 960 | PASS 64/64 |  |
| 2026-08-03 | yes | 3/3 | 64 | 960 | PASS 64/64 |  |
| 2026-08-04 | yes | 3/3 | 64 | 960 | PASS 64/64 |  |
| 2026-08-05 | yes | 3/3 | 64 | 960 | PASS 64/64 |  |
| 2026-08-06 | yes | 3/3 | 64 | 960 | PASS 64/64 |  |
| 2026-08-07 | yes | 3/3 | 64 | 960 | PASS 64/64 |  |
| 2026-08-10 | yes | 3/3 | 64 | 960 | PASS 64/64 |  |
| 2026-08-11 | yes | 3/3 | 64 | 960 | PASS 64/64 |  |
| 2026-08-12 | yes | 3/3 | 64 | 960 | PASS 64/64 |  |
| 2026-08-13 | yes | 3/3 | 64 | 960 | PASS 64/64 |  |
| 2026-08-14 | yes | 3/3 | 64 | 960 | PASS 64/64 |  |
| 2026-08-17 | yes | 3/3 | 64 | 960 | PASS 64/64 |  |
| 2026-08-18 | yes | 3/3 | 64 | 960 | PASS 64/64 |  |
| 2026-08-19 | yes | 3/3 | 64 | 960 | PASS 64/64 |  |
| 2026-08-20 | yes | 3/3 | 64 | 960 | PASS 64/64 |  |
| 2026-08-21 | yes | 3/3 | 64 | 960 | PASS 64/64 |  |
| 2026-08-24 | yes | 3/3 | 64 | 960 | PASS 64/64 |  |
| 2026-08-25 | yes | 3/3 | 64 | 960 | PASS 64/64 |  |
| 2026-08-26 | yes | 3/3 | 64 | 960 | PASS 64/64 |  |
| 2026-08-27 | yes | 3/3 | 64 | 960 | PASS 64/64 |  |
| 2026-08-28 | DROPPED | 3/3 | 64 | 947 | NOT_EVALUATED | M1 gap: 947/960 bars |
| 2026-08-31 | yes | 3/3 | 64 | 960 | PASS 64/64 |  |
| 2026-09-01 | yes | 3/3 | 64 | 960 | PASS 64/64 |  |
| 2026-09-02 | yes | 3/3 | 64 | 960 | PASS 64/64 |  |
| 2026-09-03 | yes | 3/3 | 64 | 960 | PASS 64/64 |  |
| 2026-09-04 | yes | 3/3 | 64 | 960 | PASS 64/64 |  |
| 2026-09-07 | yes | 3/3 | 64 | 960 | PASS 64/64 |  |
| 2026-09-08 | yes | 3/3 | 64 | 960 | PASS 64/64 |  |
| 2026-09-09 | yes | 3/3 | 64 | 960 | PASS 64/64 |  |
| 2026-09-10 | yes | 3/3 | 64 | 960 | PASS 64/64 |  |
| 2026-09-11 | yes | 3/3 | 64 | 960 | PASS 64/64 |  |
| 2026-09-14 | DROPPED | None/3 | - | - | NOT_EVALUATED | rollover break not located; offset unmeasured |
| 2026-09-15 | yes | 3/3 | 64 | 960 | PASS 64/64 |  |
| 2026-09-16 | yes | 3/3 | 64 | 960 | PASS 64/64 |  |
| 2026-09-17 | yes | 3/3 | 64 | 960 | PASS 64/64 |  |
| 2026-09-18 | yes | 3/3 | 64 | 960 | PASS 64/64 |  |
| 2026-09-21 | yes | 3/3 | 64 | 960 | PASS 64/64 |  |
| 2026-09-22 | yes | 3/3 | 64 | 960 | PASS 64/64 |  |
| 2026-09-23 | yes | 3/3 | 64 | 960 | PASS 64/64 |  |
| 2026-09-24 | yes | 3/3 | 64 | 960 | PASS 64/64 |  |
| 2026-09-25 | yes | 3/3 | 64 | 960 | PASS 64/64 |  |
| 2026-09-28 | yes | 3/3 | 64 | 960 | PASS 64/64 |  |
| 2026-09-29 | yes | 3/3 | 64 | 960 | PASS 64/64 |  |
| 2026-09-30 | yes | 3/3 | 64 | 960 | PASS 64/64 |  |
| 2026-10-01 | yes | 3/3 | 64 | 960 | PASS 64/64 |  |
| 2026-10-02 | yes | 3/3 | 64 | 960 | PASS 64/64 |  |
| 2026-10-05 | yes | 3/3 | 64 | 960 | PASS 64/64 |  |
| 2026-10-06 | yes | 3/3 | 64 | 960 | PASS 64/64 |  |
| 2026-10-07 | yes | 3/3 | 64 | 960 | PASS 64/64 |  |
| 2026-10-08 | yes | 3/3 | 64 | 960 | PASS 64/64 |  |
| 2026-10-09 | yes | 3/3 | 64 | 960 | PASS 64/64 |  |

## Spread (--with-spread)

- column `spread_points`: the MqlRates `spread` field of each M15 bar, an integer in points; price = spread_points x point. Point for USDJPY read with symbol_info at capture: 0.001. The value is the terminal's per-bar spread field; it is not a quote observed at a known instant.

## PARTIAL_M1_CHECK bars

M15 bars of kept days whose M1 cross-check covered fewer than 15 M1 bars:

- none (every kept M15 bar was checked against all 15 M1 bars)
