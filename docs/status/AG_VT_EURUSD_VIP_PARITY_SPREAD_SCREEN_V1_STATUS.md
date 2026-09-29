# VT EURUSD / EURUSD-VIP Parity + Preregistered Spread Screen V1 (2026-09-29)

**Classification:** `EVIDENCE_INSUFFICIENT_CONTINUE_MEASUREMENT` (owner decision option C)

This is research evidence only. It does not change strategy rules, the Canonical
Instrument Registry V1, authority, or SEALED_OOS.

| | |
|---|---|
| Base | `4b450ff36d9dc0940b0940613426d6e85e7c4450` (Unit G tip) |
| Preregistration commit | `25d43f01f25646eef63464445845d91e7756a4c6` (2026-09-29 17:26:50Z), before any result |
| Preregistration | [`../../artifacts/research/VT_EURUSD_VIP_PARITY_SPREAD_SCREEN_V1/PREREGISTRATION.yaml`](../../artifacts/research/VT_EURUSD_VIP_PARITY_SPREAD_SCREEN_V1/PREREGISTRATION.yaml) |
| Threshold | `MAX_FRICTION_TO_RISK = 0.25` (owner-set ex-ante; spread_pips / stop_pips) |

## Ordered gates

| Gate | Result |
|---|---|
| Threshold frozen before results | YES (`25d43f0`) |
| WP3A.1 provenance reconciliation | DONE (below) |
| Static metadata parity (read-only snapshot 17:33Z) | all required fields equal; only known-difference fields differ |
| Live interleaved parity capture, POST_ASIAN + POST_LONDON | **NOT_EVALUATED**: work finished at ~17:30Z, after POST_LONDON closed (15:00Z) and before POST_ASIAN opens (2026-09-30 07:00Z) |
| `EURUSD_VIP_PARITY` | `INSUFFICIENT_EVIDENCE` (minimum: 1 complete capture per session) |
| VIP spread authority | NOT_ESTABLISHED, so the analysis stops before the screen |
| `SPREAD_TO_DEV_STOP_R_SCREEN` | NOT_EVALUATED. The development-stop file was not opened for this screen |

## 1. WP3A.1 provenance reconciliation

Source: [`WP3A1_PROVENANCE_RECONCILIATION.json`](../../artifacts/research/VT_EURUSD_VIP_PARITY_SPREAD_SCREEN_V1/WP3A1_PROVENANCE_RECONCILIATION.json).
Every session file is listed with its sha256. No source file was moved or edited.

- `VANTAGE_VALID_DAYS` = 2026-09-16, 17, 18, 22, 23. That is 5 days and 2,400 valid
  observations, exactly the manifest minimum.
- Vantage incomplete days: 2026-09-21 (Window A has 6/120 valid) and 2026-09-24 (Window D
  only, no summary). Neither is counted as a day.
- `VT_SEPARATE_DAYS` = 2026-09-28 (Window C only) and 2026-09-29 (all 4 windows).
- `MIXED_ROWS_REJECTED_FROM_WP3A1` = **600** rows across 5 sessions, all VTMarkets-Demo.
- **Risk:** `scripts/aggregate_eurusd_friction_campaign.py` globs every session file in
  `sessions/`. Unless it filters on `broker_server`, it would mix VT rows into WP3A.1. The
  scheduled tasks will add one more VT day on 2026-09-30.

## 2. Symbol roles (no registry change, no aliasing)

| Symbol | trade_mode | Role |
|---|---|---|
| `EURUSD` | 0 DISABLED | ANALYSIS_FEED_REFERENCE |
| `EURUSD-VIP` | 4 FULL | EXECUTION_FRICTION_CANDIDATE |

Static snapshot: [`STATIC_METADATA_SNAPSHOT_20260929T1733Z.json`](../../artifacts/research/VT_EURUSD_VIP_PARITY_SPREAD_SCREEN_V1/STATIC_METADATA_SNAPSHOT_20260929T1733Z.json).

- **Equal:** digits 5, point 1e-5, tick size 1e-5, tick value 1.0, contract size 100000,
  EUR/USD/EUR currencies, calc mode, description, volume min/max/step, execution mode
  (MARKET), filling mode, and swaps.
- **Different:** `name`, `path` (`VT\Forex-VIP\EURUSD-VIP`) and `trade_mode`.

This snapshot is supplementary. The preregistered parity test requires live paired prices
and M1 bars.

## 3. Tooling ready for the next windows

- `scripts/research/capture_vt_vip_parity.py` captures 144 interleaved rounds of EURUSD
  then EURUSD-VIP at 5 s cadence over 720 s.
  - Row validity follows the Unit F `observe` semantics.
  - Symbol metadata is snapshotted at the start and end, and matched M1 bars are read.
  - Session containment matches Unit F R1: `OTHER` and unknown sessions are rejected, and
    the session is checked both before initialize and before the first sample.
  - Overdue rounds are skipped, never burst. Evidence files are write-once and
    sha256-pinned, and the evidence directory is pinned `* -text`.
  - `order_*`, `positions_*`, `trade_*` and `symbol_select` are blocked.
- `scripts/research/analyze_vt_vip_parity_screen.py` applies the preregistration
  mechanically.
  - Order: parity, then spread authority, then the screen. The development file is opened
    only after parity is PASS or PASS_WITH_KNOWN_DIFFERENCES.
  - The development file's hash is verified, and only `cycle` and `risk_distance` are read.
  - Median, P90 and P95 scenarios are always reported together.
- Tests: `python -m pytest -q tests/test_vt_vip_parity_screen.py` gives 21 passed. Together
  with `tests/test_fx_friction_capture.py`, 63 passed.

## Economic boundary

`SPREAD_ONLY_SCREEN = YES`, `COMMISSION_INCLUDED = NO`, `SLIPPAGE_INCLUDED = NO`,
`FULL_FRICTION_ESTIMATE = NO`, `ECONOMIC_QUALIFICATION = NO`. A screen PASS would not
grant proposal authority. Commission is UNKNOWN and slippage is UNKNOWN/INSUFFICIENT_SAMPLE.
PROPOSAL, DEMO and LIVE are all NONE. Broker order_check, order_send and mutation calls
were all 0.

## Next

Run the collector manually from a clean checkout of this branch:

```
python scripts/research/capture_vt_vip_parity.py --session POST_ASIAN    # 07:00-10:48Z start
python scripts/research/capture_vt_vip_parity.py --session POST_LONDON   # 12:00-14:48Z start
```

Commit the evidence, then run
`python scripts/research/analyze_vt_vip_parity_screen.py --write`. One capture per session
meets the parity minimum. Spread distributions stay `INITIAL` until 5 distinct days per
session.
