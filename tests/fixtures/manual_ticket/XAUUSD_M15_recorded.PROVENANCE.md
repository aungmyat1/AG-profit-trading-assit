# XAUUSD_M15_recorded.csv provenance

- sha256: `7945d96bc4f4950e643840409b77167137dacad33bb635e0e49d0373cd3047df`
  - computed over the committed git blob (LF line endings): `git show HEAD:tests/fixtures/manual_ticket/XAUUSD_M15_recorded.csv | sha256sum`.
    `.gitattributes` marks this file `-text`, so no checkout (including Windows `core.autocrlf`) converts its line endings.
- capture date (UTC): 2026-10-10 10:28:26Z
- terminal/server: VTMarkets-Demo, server name read from the terminal journal log (logs/20261010.log; the capture's allowed MT5 calls cannot read it); terminal build 6063 (terminal `<HOST_SCRATCHPAD>/terminal64.exe`)
- method: RECORDED_M15_V2 (window 00:00-15:45 UTC; day set weekdays; offset method reference-symbol:EURUSD; gaps drop the day)
- symbol: XAUUSD-VIP; timeframe M15; window 00:00-15:45 UTC per day
- day set: 10 contiguous weekdays ending 2026-10-09, fixed before capture; dropped days are not replaced
- offset validity: authority for the offset change is the repository VT rule
  (`scripts/research/market_dataset.py::vt_server_wall_to_utc`: server midnight = 17:00 America/New_York),
  which moves the offset from +3h to +2h on 2026-11-01, when US DST ends. Offsets are always measured
  per day (method below), so this date is informational only; no capture reuses an assumed offset.
- broker symbol: XAUUSD-VIP (`config/mt5.yaml` VT_MARKETS map; plain XAUUSD does not exist on this server).
- offset fallback: the unchanged rollover method on XAUUSD-VIP itself measured 0/10 days (open edge +4h
  because the metal maintenance break ends at server 01:00, close edge +3h; 2026-10-07 break not located).
  Per mission AGP-DATA-R2 the same-day EURUSD measured offset is used instead; it is measured, never assumed.
  Window, day set and gap rule are otherwise the unchanged V1 rules. The probe output was not retained.
- offset method: measured on EURUSD, never on XAUUSD-VIP and never assumed. Per EURUSD day, M1 rollover break located at 17:00 America/New_York on both edges (open = D-1 17:00 NY, close = D 17:00 NY); offset = server label - UTC, whole hours, both edges must agree. Weekdays use the same-day offset; Saturday/Sunday keep an offset only if the adjacent Friday and Monday offsets are both measured and agree (table shows Fri/Mon), else the day is dropped
- M1 cross-check: every M15 bar must equal OHLC aggregated from its 15 M1 bars (exact at symbol digits); every range read twice and must match
- capture script: scripts/capture_recorded_m15.py (peak working set 33.7 MB)

| date | kept | offset (open/close, h) | offset source | M15 bars | M1 bars | M1 cross-check | reason |
|---|---|---|---|---|---|---|---|
| 2026-09-28 | yes | 3/3 | EURUSD 2026-09-28 | 64 | 960 | PASS 64/64 |  |
| 2026-09-29 | yes | 3/3 | EURUSD 2026-09-29 | 64 | 960 | PASS 64/64 |  |
| 2026-09-30 | yes | 3/3 | EURUSD 2026-09-30 | 64 | 960 | PASS 64/64 |  |
| 2026-10-01 | yes | 3/3 | EURUSD 2026-10-01 | 64 | 960 | PASS 64/64 |  |
| 2026-10-02 | yes | 3/3 | EURUSD 2026-10-02 | 64 | 960 | PASS 64/64 |  |
| 2026-10-05 | yes | 3/3 | EURUSD 2026-10-05 | 64 | 960 | PASS 64/64 |  |
| 2026-10-06 | yes | 3/3 | EURUSD 2026-10-06 | 64 | 960 | PASS 64/64 |  |
| 2026-10-07 | yes | 3/3 | EURUSD 2026-10-07 | 64 | 960 | PASS 64/64 |  |
| 2026-10-08 | yes | 3/3 | EURUSD 2026-10-08 | 64 | 960 | PASS 64/64 |  |
| 2026-10-09 | yes | 3/3 | EURUSD 2026-10-09 | 64 | 960 | PASS 64/64 |  |
