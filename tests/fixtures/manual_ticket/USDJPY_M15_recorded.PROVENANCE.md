# USDJPY_M15_recorded.csv provenance

- sha256: `378ea1b916401707e0036e59f59ba6c94ca649aa0b3bdce1241a1e8b0c6b723f`
  - computed over the committed git blob (LF line endings): `git show HEAD:tests/fixtures/manual_ticket/USDJPY_M15_recorded.csv | sha256sum`.
    `.gitattributes` marks this file `-text`, so no checkout (including Windows `core.autocrlf`) converts its line endings.
- capture date (UTC): 2026-10-10 10:28:24Z
- terminal/server: VTMarkets-Demo, server name read from the terminal journal log (logs/20261010.log; the capture's allowed MT5 calls cannot read it); terminal build 6063 (terminal `<HOST_SCRATCHPAD>/terminal64.exe`)
- symbol: USDJPY; timeframe M15; window 00:00-15:45 UTC per day
- day set: 10 contiguous weekdays ending 2026-10-09, fixed before capture; dropped days are not replaced
- offset validity: authority for the offset change is the repository VT rule
  (`scripts/research/market_dataset.py::vt_server_wall_to_utc`: server midnight = 17:00 America/New_York),
  which moves the offset from +3h to +2h on 2026-11-01, when US DST ends. Offsets are always measured
  per day (method below), so this date is informational only; no capture reuses an assumed offset.
- attempt history: a first run earlier on 2026-10-10 (same fixed day set, same method, same script)
  ended NOT_EVIDENCED: 4 kept, 2026-10-02..2026-10-09 dropped as `open/close rollover offsets disagree`;
  the script removed that output and no rows were retained. A single-read diagnostic afterwards measured
  USDJPY 3/3 on 2026-10-01, 10-02 and 10-06 (consistent with history still syncing during the first run).
  One retry with unchanged day set and method produced this file; no day was replaced or patched.
- offset method: per day, M1 rollover break located at 17:00 America/New_York on both edges of the day (open = D-1 17:00 NY, close = D 17:00 NY); offset = server label - UTC, whole hours, both edges must agree
- M1 cross-check: every M15 bar must equal OHLC aggregated from its 15 M1 bars (exact at symbol digits); every range read twice and must match
- capture script: scripts/capture_recorded_m15.py (peak working set 33.1 MB)

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
