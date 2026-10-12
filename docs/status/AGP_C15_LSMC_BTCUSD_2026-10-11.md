# AGP-C15-LSMC: BTCUSD L1–L6 on recorded VT data

Mission C15-LSMC (`docs/governance/AGP_C15_THREE_STRATEGY_LOGIC_FIRST_2026-10-11.md`, PR #156). Off-host,
read-only. No rule, registry, READY, demo or live change. Alerts stay ARCHIVE_ONLY.

**Verdict: BTCUSD = NOT_VERIFIED.** Signal-layer L1–L4/L6 pass on every scan, but L5 is WARN, stop geometry is
NOT_APPLICABLE (no C10 pip evidence), and the operational lane rejects every OPPORTUNITY scan with `REJECT_NO_STOP`
(2,923/2,923), so BTCUSD cannot emit a deliverable opportunity under 1.1.0. Headline counts use only the 8,961 scans
with a full 30-bar D1 window (as on the host); the 5,572 earlier short-window scans are reported separately.

## Symbol choice (made before running)

BTCUSD and ETHUSD are the only candidates with VT-recorded M5, H1 and D1 on main
(`tests/fixtures/ccfd_v100/recorded_60d`, 60 days, per-bar spread); GBPUSD has only M1/M15/H1 and USDJPY/XAUUSD
have none. BTCUSD and ETHUSD tie on every completeness count (16,932 M5 / 1,412 H1 / 60 D1 bars, same M1 checks),
so BTCUSD was taken as first in the 1.1.0 contract's instrument list.

## Scope and identity

| Item | Value |
|---|---|
| Strategy / contract | `ST_LARGE_SMC_V1@1.1.0`, `strategies/ST_LARGE_SMC_V1_1_1_0.yaml` sha256 `78285f9f…` (= registry) |
| Detection files (`detect.py`, `contract.py`, `fx_discovery/features.py`) | unchanged since C1 (ce6f0f8) and identical to #144 (fe77be5): same basis as the EURUSD detection evidence |
| Engine sha256 (gate method) | `88dd9f1f…` ≠ registry `ec0b2f3d…` (**drift**, see WARN 1) |
| Symbol / venue | BTCUSD, VT Markets MT5 CFD, server VTMarkets-Demo, point 0.01 (host capture `d6db9283…`) |
| Timeframes / cadence | D1/H1/M5, host windows D1 30 / H1 200 / M5 300 incl. the forming bar; every M5 close |
| Scans | 14,533 (2026-08-20 01:00 → 2026-10-10 00:00 UTC): **8,961 full 30-bar D1 window (headline)**, 5,572 short D1 window (separate) |
| Branches exercised (full window) | LONG 21, SHORT 37 distinct opportunities (58); all scans: LONG 33, SHORT 57 (90) |

Dataset sha256: `BTCUSD_m5.csv` `60a9b5a4…`, `BTCUSD_h1.csv` `f1d7ba4b…`, `BTCUSD_d1.csv` `85110e81…`,
`BTCUSD_m5_meta.csv` `3d1b7559…`, `BTCUSD_h1_meta.csv` `e629f826…`, `BTCUSD_d1_meta.csv` `8ea6e7f2…`
(full values in the report).

## L1–L6 (scope: BTCUSD × D1/H1/M5 watch × LONG/SHORT, signal lane, full 30-bar D1 windows)

| Gate | Full D1 window (8,961 scans) | Short D1 window (5,572 scans) | Basis |
|---|---|---|---|
| L1 determinism + causality | PASS 8,961 | PASS 5,572 | two builds hash equal; forming-bar/future-OHLC input gives the same snapshot as closed-only input |
| L2 contract conformance | PASS 8,961 | PASS 5,572 | identity, no authority, VT universe, swing k, POI age, tie tolerance, sweep window, ATR band, day boundary, alert mapping, point source, C10 stop rule (`C10_PIP_SIZE_NOT_EVIDENCED`), C11 target / `REJECT_NO_TARGET` |
| L3 geometry | PASS 8,961 | PASS 5,572 | entry inside CHoCH bar, sweep extreme on loss side, target in trade direction; **stop checks NOT_APPLICABLE** |
| L4 data/state | PASS 8,961 | PASS 5,572 | evaluated, H1/M5 history, M5 freshness, STALE consistency |
| L5 cost (OD1011-L5) | **WARN** 8,961 | WARN 5,572 | spread evidence present; stop distance undefined; commission unbound off-host; no cost gate |
| L6 freshness fields | PASS 8,961 | PASS 5,572 | `expires_at`, stale/invalid rules set on every OPPORTUNITY |
| OPPORTUNITY scans → operational | 2,040 → `REJECT_NO_STOP` 2,040 | 883 → `REJECT_NO_STOP` 883 | |

Streaming/prefix parity (whole run): WatchTracker streaming vs 7 prefix cuts, 0 mismatches (signal 1,350 events,
operational 1,261).

Spread provenance: every M5 bar carries the recorded MqlRates spread (16,932/16,932) from VTMarkets-Demo; the host
`symbol_info` snapshot spread is 17.02 (1,702 points × 0.01). Conservative spread = max(bar, host snapshot); the bar
value alone is a lower bound.

## Unresolved WARNs

1. **Engine identity drift.** af2b3cf/f28e040 (2026-10-10) changed `src/large_smc_watch/watch.py`:
   `evaluate_snapshot` now applies a delivery gate (`gate_opportunity`, needing the host-only
   `config/local/actionability_policy.yaml`) inside the engine, so the engine hash no longer matches the registry
   record from C1. Detection is unchanged. This puts actionability inside the engine rather than the post-signal
   layer; not changed here (no rule changes).
2. **Stop geometry NOT_EVALUABLE.** The contract computes a C10 stop only where pip size is evidenced
   (`C10_PIP_SIZE`: EURUSD, GBPUSD). BTCUSD has none, so every opportunity has `stop_c10 = None` and the operational
   lane rejects all 2,923 OPPORTUNITY scans with `REJECT_NO_STOP`. Resolving it needs owner-approved BTCUSD pip/stop
   evidence (a contract input), not a code change.
3. **L5.** Missing: stop distance (WARN 2); OD1011-COMMISSION binding off-host (needs the host-local account login);
   a cost gate applying 0.10R warn / 0.25R block in the Large-SMC alert path (none exists in 1.1.0).
4. **D1 window.** 5,572 early scans had fewer than 30 D1 bars (dataset starts 2026-08-10); they are excluded from
   the headline counts. D1 feeds only the informational `d1_context`.

## Note: #144 baseline label (docs only; evidence not rewritten)

`research_external/oracles/runs/AGP_4H_C_EURUSD_DETECTION.json` `changes_vs_7e30138.baseline_fixture_sha256` reads
`a8bf11a9…`, which is the EURUSD fixture at 2908228, while the code compares against 7e30138 (`0d6297f0…`, vendored in
#160). The two fixtures differ: H1 (120) and M5 (600) are identical, but D1 differs (7e30138: 30 broker-day bars opening
21:00Z; 2908228: 24 bars opening 00:00Z, no common timestamps). #144's change attribution and its parity statements
("D1 extremes shifted 1–3 points on 7/30 days", "H1 changed on 35/120 bars") hold for **7e30138**; the H1 statement also
holds for 2908228. The label is a labelling error; correcting the evidence file needs owner approval.

## Reproduce

`python scripts/lsmc_c15_symbol_replay.py --symbol BTCUSD --out artifacts/logic_verification/ST_LARGE_SMC_V1_1_1_0/c15_btcusd_vt_recorded_60d/replay_report.json`
(about 25 minutes; the report has no wall-clock field and is byte-reproducible). Test:
`pytest -q tests/test_lsmc_c15_symbol_replay.py`.

OSS-FIRST: engine, gate, tracker and data loaders are existing repo code (REUSED); `smartmoneyconcepts` is not used
by this run; no new trading or indicator logic was written.
