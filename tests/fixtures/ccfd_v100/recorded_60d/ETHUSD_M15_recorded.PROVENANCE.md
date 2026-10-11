# ETHUSD_M15_recorded.csv provenance

- sha256: `52b311f848cbd21cbaa0909fc151b483c814e2c47f23b362ea018f9daf93408a`
- capture date (UTC): 2026-10-10 17:20:20Z
- terminal/server: VTMarkets-Demo (terminal `default`)
- method: RECORDED_M15_V2 (window 00:00-23:45 UTC; day set calendar days; offset method reference-symbol:EURUSD; gaps listed, never filled)
- symbol: ETHUSD; timeframe M15; window 00:00-23:45 UTC per day
- day set: 60 contiguous calendar days ending 2026-10-09, fixed before capture; dropped days are not replaced
- offset method: measured on EURUSD, never on ETHUSD and never assumed. Per EURUSD day, M1 rollover break located at 17:00 America/New_York on both edges (open = D-1 17:00 NY, close = D 17:00 NY); offset = server label - UTC, whole hours, both edges must agree. Weekdays use the same-day offset; Saturday/Sunday keep an offset only if the adjacent Friday and Monday offsets are both measured and agree (table shows Fri/Mon), else the day is dropped
- M1 cross-check: every M15 bar must equal OHLC aggregated from its present M1 bars; an M1 bar without its M15 bar fails (exact at symbol digits); every range read twice and must match
- capture script: scripts/capture_recorded_m15.py (peak working set 59.4 MB)

| date | kept | offset (open/close, h) | offset source | M15 bars | M1 bars | M1 cross-check | reason |
|---|---|---|---|---|---|---|---|
| 2026-08-11 | yes | 3/3 | EURUSD 2026-08-11 | 96 | 1440 | PASS 96/96 |  |
| 2026-08-12 | yes | 3/3 | EURUSD 2026-08-12 | 96 | 1440 | PASS 96/96 |  |
| 2026-08-13 | yes | 3/3 | EURUSD 2026-08-13 | 96 | 1437 | PASS 96/96 |  |
| 2026-08-14 | yes | 3/3 | EURUSD 2026-08-14 | 84 | 1260 | PASS 84/84 |  |
| 2026-08-15 | yes | 3/3 | EURUSD Fri 2026-08-14 / Mon 2026-08-17 | 40 | 600 | PASS 40/40 |  |
| 2026-08-16 | yes | 3/3 | EURUSD Fri 2026-08-14 / Mon 2026-08-17 | 96 | 1440 | PASS 96/96 |  |
| 2026-08-17 | yes | 3/3 | EURUSD 2026-08-17 | 96 | 1440 | PASS 96/96 |  |
| 2026-08-18 | yes | 3/3 | EURUSD 2026-08-18 | 96 | 1439 | PASS 96/96 |  |
| 2026-08-19 | yes | 3/3 | EURUSD 2026-08-19 | 96 | 1440 | PASS 96/96 |  |
| 2026-08-20 | yes | 3/3 | EURUSD 2026-08-20 | 96 | 1440 | PASS 96/96 |  |
| 2026-08-21 | yes | 3/3 | EURUSD 2026-08-21 | 96 | 1439 | PASS 96/96 |  |
| 2026-08-22 | yes | 3/3 | EURUSD Fri 2026-08-21 / Mon 2026-08-24 | 96 | 1440 | PASS 96/96 |  |
| 2026-08-23 | yes | 3/3 | EURUSD Fri 2026-08-21 / Mon 2026-08-24 | 96 | 1439 | PASS 96/96 |  |
| 2026-08-24 | yes | 3/3 | EURUSD 2026-08-24 | 96 | 1440 | PASS 96/96 |  |
| 2026-08-25 | yes | 3/3 | EURUSD 2026-08-25 | 96 | 1440 | PASS 96/96 |  |
| 2026-08-26 | yes | 3/3 | EURUSD 2026-08-26 | 96 | 1440 | PASS 96/96 |  |
| 2026-08-27 | yes | 3/3 | EURUSD 2026-08-27 | 96 | 1440 | PASS 96/96 |  |
| 2026-08-28 | yes | 3/3 | EURUSD 2026-08-28 | 96 | 1425 | PASS 96/96 |  |
| 2026-08-29 | yes | 3/3 | EURUSD Fri 2026-08-28 / Mon 2026-08-31 | 52 | 780 | PASS 52/52 |  |
| 2026-08-30 | yes | 3/3 | EURUSD Fri 2026-08-28 / Mon 2026-08-31 | 95 | 1412 | PASS 95/95 |  |
| 2026-08-31 | yes | 3/3 | EURUSD 2026-08-31 | 96 | 1440 | PASS 96/96 |  |
| 2026-09-01 | yes | 3/3 | EURUSD 2026-09-01 | 96 | 1440 | PASS 96/96 |  |
| 2026-09-02 | yes | 3/3 | EURUSD 2026-09-02 | 96 | 1440 | PASS 96/96 |  |
| 2026-09-03 | yes | 3/3 | EURUSD 2026-09-03 | 96 | 1440 | PASS 96/96 |  |
| 2026-09-04 | yes | 3/3 | EURUSD 2026-09-04 | 96 | 1437 | PASS 96/96 |  |
| 2026-09-05 | yes | 3/3 | EURUSD Fri 2026-09-04 / Mon 2026-09-07 | 96 | 1440 | PASS 96/96 |  |
| 2026-09-06 | yes | 3/3 | EURUSD Fri 2026-09-04 / Mon 2026-09-07 | 96 | 1431 | PASS 96/96 |  |
| 2026-09-07 | yes | 3/3 | EURUSD 2026-09-07 | 96 | 1440 | PASS 96/96 |  |
| 2026-09-08 | yes | 3/3 | EURUSD 2026-09-08 | 96 | 1440 | PASS 96/96 |  |
| 2026-09-09 | yes | 3/3 | EURUSD 2026-09-09 | 96 | 1440 | PASS 96/96 |  |
| 2026-09-10 | yes | 3/3 | EURUSD 2026-09-10 | 96 | 1440 | PASS 96/96 |  |
| 2026-09-11 | yes | 3/3 | EURUSD 2026-09-11 | 96 | 1438 | PASS 96/96 |  |
| 2026-09-12 | yes | 3/3 | EURUSD Fri 2026-09-11 / Mon 2026-09-14 | 96 | 1440 | PASS 96/96 |  |
| 2026-09-13 | yes | 3/3 | EURUSD Fri 2026-09-11 / Mon 2026-09-14 | 96 | 1433 | PASS 96/96 |  |
| 2026-09-14 | yes | 3/3 | EURUSD 2026-09-14 | 96 | 1440 | PASS 96/96 |  |
| 2026-09-15 | yes | 3/3 | EURUSD 2026-09-15 | 96 | 1440 | PASS 96/96 |  |
| 2026-09-16 | yes | 3/3 | EURUSD 2026-09-16 | 96 | 1440 | PASS 96/96 |  |
| 2026-09-17 | yes | 3/3 | EURUSD 2026-09-17 | 96 | 1440 | PASS 96/96 |  |
| 2026-09-18 | yes | 3/3 | EURUSD 2026-09-18 | 96 | 1427 | PASS 96/96 |  |
| 2026-09-19 | yes | 3/3 | EURUSD Fri 2026-09-18 / Mon 2026-09-21 | 96 | 1440 | PASS 96/96 |  |
| 2026-09-20 | yes | 3/3 | EURUSD Fri 2026-09-18 / Mon 2026-09-21 | 96 | 1440 | PASS 96/96 |  |
| 2026-09-21 | yes | 3/3 | EURUSD 2026-09-21 | 96 | 1440 | PASS 96/96 |  |
| 2026-09-22 | yes | 3/3 | EURUSD 2026-09-22 | 96 | 1440 | PASS 96/96 |  |
| 2026-09-23 | yes | 3/3 | EURUSD 2026-09-23 | 96 | 1440 | PASS 96/96 |  |
| 2026-09-24 | yes | 3/3 | EURUSD 2026-09-24 | 96 | 1440 | PASS 96/96 |  |
| 2026-09-25 | yes | 3/3 | EURUSD 2026-09-25 | 96 | 1433 | PASS 96/96 |  |
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
| 2026-08-11 | yes | none | none |
| 2026-08-12 | yes | none | none |
| 2026-08-13 | yes | none | 21:36-21:37 (2), 21:40 |
| 2026-08-14 | yes | 21:00, 21:15, 21:30, 21:45, 22:00, 22:15, 22:30, 22:45, 23:00, 23:15, 23:30, 23:45 | 21:00-23:59 (180) |
| 2026-08-15 | yes | 00:00, 00:15, 00:30, 00:45, 01:00, 01:15, 01:30, 01:45, 02:00, 02:15, 02:30, 02:45, 03:00, 03:15, 03:30, 03:45, 04:00, 04:15, 04:30, 04:45, 05:00, 05:15, 05:30, 05:45, 06:00, 06:15, 06:30, 06:45, 07:00, 07:15, 07:30, 07:45, 08:00, 08:15, 08:30, 08:45, 09:00, 09:15, 09:30, 09:45, 10:00, 10:15, 10:30, 10:45, 11:00, 11:15, 11:30, 11:45, 12:00, 12:15, 12:30, 12:45, 13:00, 13:15, 13:30, 13:45 | 00:00-13:59 (840) |
| 2026-08-16 | yes | none | none |
| 2026-08-17 | yes | none | none |
| 2026-08-18 | yes | none | 21:41 |
| 2026-08-19 | yes | none | none |
| 2026-08-20 | yes | none | none |
| 2026-08-21 | yes | none | 21:42 |
| 2026-08-22 | yes | none | none |
| 2026-08-23 | yes | none | 01:58 |
| 2026-08-24 | yes | none | none |
| 2026-08-25 | yes | none | none |
| 2026-08-26 | yes | none | none |
| 2026-08-27 | yes | none | none |
| 2026-08-28 | yes | none | 14:29-14:41 (13), 21:46-21:47 (2) |
| 2026-08-29 | yes | 05:00, 05:15, 05:30, 05:45, 06:00, 06:15, 06:30, 06:45, 07:00, 07:15, 07:30, 07:45, 08:00, 08:15, 08:30, 08:45, 09:00, 09:15, 09:30, 09:45, 10:00, 10:15, 10:30, 10:45, 11:00, 11:15, 11:30, 11:45, 12:00, 12:15, 12:30, 12:45, 13:00, 13:15, 13:30, 13:45, 14:00, 14:15, 14:30, 14:45, 15:00, 15:15, 15:30, 15:45 | 05:00-15:59 (660) |
| 2026-08-30 | yes | 02:15 | 02:08-02:35 (28) |
| 2026-08-31 | yes | none | none |
| 2026-09-01 | yes | none | none |
| 2026-09-02 | yes | none | none |
| 2026-09-03 | yes | none | none |
| 2026-09-04 | yes | none | 21:08, 21:45-21:46 (2) |
| 2026-09-05 | yes | none | none |
| 2026-09-06 | yes | none | 01:29-01:37 (9) |
| 2026-09-07 | yes | none | none |
| 2026-09-08 | yes | none | none |
| 2026-09-09 | yes | none | none |
| 2026-09-10 | yes | none | none |
| 2026-09-11 | yes | none | 21:37, 21:59 |
| 2026-09-12 | yes | none | none |
| 2026-09-13 | yes | none | 02:27-02:33 (7) |
| 2026-09-14 | yes | none | none |
| 2026-09-15 | yes | none | none |
| 2026-09-16 | yes | none | none |
| 2026-09-17 | yes | none | none |
| 2026-09-18 | yes | none | 21:32-21:44 (13) |
| 2026-09-19 | yes | none | none |
| 2026-09-20 | yes | none | none |
| 2026-09-21 | yes | none | none |
| 2026-09-22 | yes | none | none |
| 2026-09-23 | yes | none | none |
| 2026-09-24 | yes | none | none |
| 2026-09-25 | yes | none | 21:38-21:44 (7) |
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
