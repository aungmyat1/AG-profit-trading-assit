# out.csv provenance

- sha256: `4aaf25f100c3868d3466c94025d3d7a17ec8bdfeffe3a15ad2790492903c18fa`
- capture date (UTC): 2026-10-10 09:00:00Z
- terminal/server: FAKE-Server (terminal `<HOST_SCRATCHPAD>/terminal64.exe`)
- symbol: EURUSD; timeframe M15; window 00:00-15:45 UTC per day
- day set: 10 contiguous weekdays ending 2026-10-09, fixed before capture; dropped days are not replaced
- offset method: per day, M1 rollover break located at 17:00 America/New_York on both edges of the day (open = D-1 17:00 NY, close = D 17:00 NY); offset = server label - UTC, whole hours, both edges must agree
- M1 cross-check: every M15 bar must equal OHLC aggregated from its 15 M1 bars (exact at symbol digits); every range read twice and must match
- capture script: scripts/capture_recorded_m15.py (peak working set 12.3 MB)

| date | kept | offset (open/close, h) | M15 bars | M1 bars | M1 cross-check | reason |
|---|---|---|---|---|---|---|
| 2026-09-28 | yes | 3/3 | 64 | 960 | PASS 64/64 |  |
| 2026-09-29 | yes | 3/3 | 64 | 960 | PASS 64/64 |  |
| 2026-09-30 | yes | 3/3 | 64 | 960 | PASS 64/64 |  |
| 2026-10-01 | DROPPED | 3/3 | 64 | 960 | FAIL 1/64 | M15 != M1 aggregate at 10:00 |
| 2026-10-02 | yes | 3/3 | 64 | 960 | PASS 64/64 |  |
| 2026-10-05 | yes | 3/3 | 64 | 960 | PASS 64/64 |  |
| 2026-10-06 | DROPPED | 3/3 | 64 | 959 | NOT_EVALUATED | M1 gap: 959/960 bars |
| 2026-10-07 | yes | 3/3 | 64 | 960 | PASS 64/64 |  |
| 2026-10-08 | yes | 3/3 | 64 | 960 | PASS 64/64 |  |
| 2026-10-09 | yes | 3/3 | 64 | 960 | PASS 64/64 |  |
