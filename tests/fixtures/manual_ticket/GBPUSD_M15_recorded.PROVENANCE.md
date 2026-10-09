# GBPUSD_M15_recorded.csv provenance

- sha256: `f0b15f864a8bea72ad287427109106996f431047e2b283ad0777e804133b0cfe`
  - computed over the committed git blob (LF line endings): `git show HEAD:tests/fixtures/manual_ticket/GBPUSD_M15_recorded.csv | sha256sum`.
    `.gitattributes` marks this file `-text`, so no checkout (including Windows `core.autocrlf`) converts its line endings.
- capture date (UTC): 2026-10-09 21:04:48Z
- terminal/server: VTMarkets-Demo, server name read from the terminal journal log (logs/20261010.log; the capture's allowed MT5 calls cannot read it); terminal build 6063 (terminal `<HOST_SCRATCHPAD>/terminal64.exe`)
- symbol: GBPUSD; timeframe M15; window 00:00-15:45 UTC per day
- day set: 10 contiguous weekdays ending 2026-10-09, fixed before capture; dropped days are not replaced
- offset validity: the measured +3h applies only to captures before 2026-10-25. Any later capture must
  re-measure the offset per day with the method below; never reuse +3h. (The repo VT rule, server midnight =
  17:00 New York, puts the switch to +2h at the US DST end on 2026-11-01; 2026-10-25 is the conservative cutoff.)
- offset method: per day, M1 rollover break located at 17:00 America/New_York on both edges of the day (open = D-1 17:00 NY, close = D 17:00 NY); offset = server label - UTC, whole hours, both edges must agree
- M1 cross-check: every M15 bar must equal OHLC aggregated from its 15 M1 bars (exact at symbol digits); every range read twice and must match
- capture script: scripts/capture_recorded_m15.py (peak working set 35.1 MB)

| date | kept | offset (open/close, h) | M15 bars | M1 bars | M1 cross-check | reason |
|---|---|---|---|---|---|---|
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
