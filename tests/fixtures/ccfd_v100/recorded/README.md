# Recorded CFD v1.0.0 corpus (AGP-DATA-R2 / R2b)

Recorded VT Markets Demo bars for BTCUSD and ETHUSD, read-only MT5 (`initialize`,
`symbol_info`, `copy_rates_range`, `shutdown`). Same 14 days (2026-09-26..2026-10-09),
offsets (+3h, EURUSD reference) and M1 gap list as the PR #128 M15 files.

| file | content |
|---|---|
| `<SYM>_m1.csv`, `_m5.csv`, `_h1.csv` | UTC bar opens, aware ISO; missing bars listed, never filled |
| `<SYM>_d1.csv` | broker day (server midnight = 17:00 New York = 21:00 UTC), at its own UTC open; not re-bucketed. Server day 2026-10-10 excluded (not closed at capture) |
| M15 | not duplicated: `../../manual_ticket/<SYM>_M15_recorded.csv` (PR #128), referenced by sha256 |
| `<SYM>_<tf>_meta.csv` | `spread_points` (MqlRates spread), `spread_price` (x host-captured point 0.01), `m1_check` (PASS / PARTIAL_M1_CHECK / D1 only: NOT_EVALUATED_OUTSIDE_M1_RANGE), D1 `server_date` |
| `<SYM>_provenance.json` | the PR #126 recorded provenance record, hashes of the shared files |
| `capture_report.json` | per-day capture checks, D1 alignment, live vs host point |
| `manifest.json` | 304 cases, one per M15 bar close inside the crypto window gate; `files` lists every sha256 |

M5/H1/M15 bars equal the aggregate of their M1 bars; bars with missing M1 bars are
PARTIAL_M1_CHECK (compared over the present M1 bars). `commission_R` is null in every case
(explicit gap, see `manifest.json` `gaps`). `expected_result`/`expected_direction` are null:
no capture-review assertion has been made, so L2 cannot pass until one is.

The PR #126 runner needs per-case files containing only bars closed at `now`. Materialize
them (every hash is verified first; nothing is written on a mismatch), then run it unchanged:

```sh
python scripts/ccfd_recorded_cases.py materialize --out-dir work/ccfd-recorded-cases
python scripts/ccfd_v100_logic_verification.py --fixtures work/ccfd-recorded-cases/manifest.json --out-dir work/ccfd-recorded
```

`python scripts/ccfd_recorded_cases.py build` regenerates `manifest.json` and the provenance
JSON from the committed files.
