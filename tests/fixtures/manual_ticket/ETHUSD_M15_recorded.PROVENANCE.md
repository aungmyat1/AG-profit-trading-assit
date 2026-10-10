# ETHUSD_M15_recorded.csv provenance

- sha256: `e28a10aa33919131a479cd3910fa238394ba8155d7500bd5b791c04fbc53a3ff`
  - computed over the committed git blob (LF line endings): `git show HEAD:tests/fixtures/manual_ticket/ETHUSD_M15_recorded.csv | sha256sum`.
    `.gitattributes` marks this file `-text`, so no checkout (including Windows `core.autocrlf`) converts its line endings.
- capture date (UTC): 2026-10-10 10:28:44Z
- terminal/server: VTMarkets-Demo, server name read from the terminal journal log (logs/20261010.log; the capture's allowed MT5 calls cannot read it); terminal build 6063 (terminal `<HOST_SCRATCHPAD>/terminal64.exe`)
- method: RECORDED_M15_V2 (window 00:00-23:45 UTC; day set calendar days; offset method reference-symbol:EURUSD; gaps listed, never filled)
- symbol: ETHUSD; timeframe M15; window 00:00-23:45 UTC per day
- day set: 14 contiguous calendar days ending 2026-10-09, fixed before capture; dropped days are not replaced
- offset validity: authority for the offset change is the repository VT rule
  (`scripts/research/market_dataset.py::vt_server_wall_to_utc`: server midnight = 17:00 America/New_York),
  which moves the offset from +3h to +2h on 2026-11-01, when US DST ends. Offsets are always measured
  per day (method below), so this date is informational only; no capture reuses an assumed offset.
- offset span: the 00:00-23:45 UTC window extends past D 17:00 NY (21:00 UTC); the close-edge measurement
  is the offset of that server midnight, and both edges agree on every kept day, so one offset covers the window.
- gap note: BTCUSD and ETHUSD show identical M1 gap sets (feed-wide, not per symbol); no M15 bar is missing.
- offset method: measured on EURUSD, never on ETHUSD and never assumed. Per EURUSD day, M1 rollover break located at 17:00 America/New_York on both edges (open = D-1 17:00 NY, close = D 17:00 NY); offset = server label - UTC, whole hours, both edges must agree. Weekdays use the same-day offset; Saturday/Sunday keep an offset only if the adjacent Friday and Monday offsets are both measured and agree (table shows Fri/Mon), else the day is dropped
- M1 cross-check: every M15 bar must equal OHLC aggregated from its present M1 bars; an M1 bar without its M15 bar fails (exact at symbol digits); every range read twice and must match
- capture script: scripts/capture_recorded_m15.py (peak working set 35.0 MB)

| date | kept | offset (open/close, h) | offset source | M15 bars | M1 bars | M1 cross-check | reason |
|---|---|---|---|---|---|---|---|
| 2026-09-26 | yes | 3/3 | EURUSD Fri 2026-09-25 / Mon 2026-09-28 | 96 | 1433 | PASS 96/96 |  |
| 2026-09-27 | yes | 3/3 | EURUSD Fri 2026-09-25 / Mon 2026-09-28 | 96 | 1438 | PASS 96/96 |  |
| 2026-09-28 | yes | 3/3 | EURUSD 2026-09-28 | 96 | 1440 | PASS 96/96 |  |
| 2026-09-29 | yes | 3/3 | EURUSD 2026-09-29 | 96 | 1440 | PASS 96/96 |  |
| 2026-09-30 | yes | 3/3 | EURUSD 2026-09-30 | 96 | 1440 | PASS 96/96 |  |
| 2026-10-01 | yes | 3/3 | EURUSD 2026-10-01 | 96 | 1440 | PASS 96/96 |  |
| 2026-10-02 | yes | 3/3 | EURUSD 2026-10-02 | 96 | 1437 | PASS 96/96 |  |
| 2026-10-03 | yes | 3/3 | EURUSD Fri 2026-10-02 / Mon 2026-10-05 | 96 | 1440 | PASS 96/96 |  |
| 2026-10-04 | yes | 3/3 | EURUSD Fri 2026-10-02 / Mon 2026-10-05 | 96 | 1440 | PASS 96/96 |  |
| 2026-10-05 | yes | 3/3 | EURUSD 2026-10-05 | 96 | 1440 | PASS 96/96 |  |
| 2026-10-06 | yes | 3/3 | EURUSD 2026-10-06 | 96 | 1440 | PASS 96/96 |  |
| 2026-10-07 | yes | 3/3 | EURUSD 2026-10-07 | 96 | 1439 | PASS 96/96 |  |
| 2026-10-08 | yes | 3/3 | EURUSD 2026-10-08 | 96 | 1440 | PASS 96/96 |  |
| 2026-10-09 | yes | 3/3 | EURUSD 2026-10-09 | 96 | 1439 | PASS 96/96 |  |

## Gaps (UTC bar opens; missing bars are never filled)

| date | kept | missing M15 | missing M1 |
|---|---|---|---|
| 2026-09-26 | yes | none | 02:05-02:11 (7) |
| 2026-09-27 | yes | none | 01:39-01:40 (2) |
| 2026-09-28 | yes | none | none |
| 2026-09-29 | yes | none | none |
| 2026-09-30 | yes | none | none |
| 2026-10-01 | yes | none | none |
| 2026-10-02 | yes | none | 22:14-22:16 (3) |
| 2026-10-03 | yes | none | none |
| 2026-10-04 | yes | none | none |
| 2026-10-05 | yes | none | none |
| 2026-10-06 | yes | none | none |
| 2026-10-07 | yes | none | 21:00 |
| 2026-10-08 | yes | none | none |
| 2026-10-09 | yes | none | 23:26 |

## PARTIAL_M1_CHECK bars (annotation added by AGP-DATA-R2b; CSV unchanged)

M15 bars with at least one missing M1 bar. Each was compared with the aggregate of its present
M1 bars and matched exactly (re-verified 2026-10-10 by `scripts/capture_recorded_ccfd_tfs.py`);
the check is partial because the missing minutes cannot be checked.

| M15 bar open (UTC) |
|---|
| 2026-09-26 02:00:00 |
| 2026-09-27 01:30:00 |
| 2026-10-02 22:00:00 |
| 2026-10-02 22:15:00 |
| 2026-10-07 21:00:00 |
| 2026-10-09 23:15:00 |
