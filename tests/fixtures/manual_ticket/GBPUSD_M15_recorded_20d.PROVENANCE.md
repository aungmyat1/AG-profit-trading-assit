# GBPUSD_M15_recorded_20d.csv provenance

- sha256: `0a48dece178709d8ddb9699a78b102d6a0ec93d1fa624d1e6cae75495e16fd96`
  - computed over the committed git blob (LF line endings): `git show HEAD:tests/fixtures/manual_ticket/GBPUSD_M15_recorded_20d.csv | sha256sum`.
    `.gitattributes` marks this file `-text`, so no checkout (including Windows `core.autocrlf`) converts its line endings.
- capture date (UTC): 2026-10-10 10:27:47Z
- terminal/server: VTMarkets-Demo, server name read from the terminal journal log (logs/20261010.log; the capture's allowed MT5 calls cannot read it); terminal build 6063 (terminal `<HOST_SCRATCHPAD>/terminal64.exe`)
- symbol: GBPUSD; timeframe M15; window 00:00-15:45 UTC per day
- day set: 20 contiguous weekdays ending 2026-10-09, fixed before capture; dropped days are not replaced
- offset validity: authority for the offset change is the repository VT rule
  (`scripts/research/market_dataset.py::vt_server_wall_to_utc`: server midnight = 17:00 America/New_York),
  which moves the offset from +3h to +2h on 2026-11-01, when US DST ends. Offsets are always measured
  per day (method below), so this date is informational only; no capture reuses an assumed offset.
- relation: new 20-weekday file for LONDON_NEWYORK L2 evidence (trade session 12:00-15:00 GMT lies inside
  the 00:00-15:45 window). `GBPUSD_M15_recorded.csv` (10 days) is unchanged; its 640 rows are byte-identical
  to the last 640 rows of this file.
- offset method: per day, M1 rollover break located at 17:00 America/New_York on both edges of the day (open = D-1 17:00 NY, close = D 17:00 NY); offset = server label - UTC, whole hours, both edges must agree
- M1 cross-check: every M15 bar must equal OHLC aggregated from its 15 M1 bars (exact at symbol digits); every range read twice and must match
- capture script: scripts/capture_recorded_m15.py (peak working set 37.6 MB)

| date | kept | offset (open/close, h) | M15 bars | M1 bars | M1 cross-check | reason |
|---|---|---|---|---|---|---|
| 2026-09-14 | yes | 3/3 | 64 | 960 | PASS 64/64 |  |
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
