# Synthetic CFD v1.0.0 replay corpus

All prices, commission and quotes here are **SYNTHETIC**. Never use them as VT,
live, edge or authorization evidence. Eight cases cover BTCUSD/ETHUSD × LONG/SHORT
× WEEKDAY/WEEKEND, using the production swing length 5 and close-break setting.
The compact existing contract-test examples were expanded before the sweep to
satisfy the production swing lookback; previous-day reference grids contain all
288 M5 bars. No strategy or market-structure rule was changed.

Run from the repo root:

```sh
python scripts/ccfd_v100_logic_verification.py --out-dir work/ccfd-synthetic
```

DATA-R2 recorded rerun (one command; replace the fixture directory):

```sh
python scripts/ccfd_v100_logic_verification.py --fixtures /path/to/AGP-DATA-R2/manifest.json --out-dir work/ccfd-recorded
```

The recorded manifest follows `manifest.json` here, with `source` set to
`MT5_VT_MARKETS_DEMO` and `mission` set to `AGP-DATA-R2`. Each case names a
capture-side `provenance` JSON path, relative to the manifest, containing:

```json
{
  "source": "MT5_VT_MARKETS_DEMO",
  "mission": "AGP-DATA-R2",
  "symbol": "BTCUSD",
  "recorded": true,
  "captured_at_utc": "<capture UTC timestamp>",
  "sha256": {"d1": "<raw file hash>", "h1": "<raw file hash>",
             "m15": "<raw file hash>", "m5": "<raw file hash>"}
}
```

CSV fields: `timestamp_utc,open,high,low,close`. Times must be aware UTC bar-open
timestamps; every supplied bar must have fully closed at case `now`. Required
case fields: `id`, `symbol`, `window`, `now`, `paths` for D1/H1/M15/M5,
`expected_result`, `expected_direction` for entries, `spread`, `commission_R`,
`quote_time`. Expected results/directions are capture-review assertions, never
inferred from the engine being tested. Use recorded spreads, commission and
quote times for recorded cases; unknown commission remains WARN and cannot yield
`LOGIC_VERIFIED`. No broker connection or metadata fetch occurs in this runner.

Only hash-valid recorded cases passing every gate can cover the required eight
instrument/direction/window combinations. Missing coverage or WARN/FAIL blocks
`LOGIC_VERIFIED`. Relabelled bundled synthetic files are rejected. Provenance is
a capture-side assertion with integrity hashes, not cryptographic proof of venue.
Exit 0 means either full synthetic PASS or recorded `LOGIC_VERIFIED`; inspect the
verdict to distinguish them. Incomplete verification exits 1. The result never
changes registry, admission, readiness or demo/live authorization.
