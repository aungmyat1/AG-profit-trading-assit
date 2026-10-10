# AGP-4H-A — ST_ASIAN_SWEEP_5R_V1@1.1.2, lane GBPUSD × ASIAN_LONDON (2026-10-10)

Logic verification only (rule conformance on recorded fixtures). No edge, demo or live authority.
ORDER_API_CALLS 0, broker calls 0. Registry **not** modified.

## Lane choice

Selected from `AGP_C3_ASW_V112_R2_60D_2026-10-10.json`. Every lane except EURUSD × ASIAN_LONDON
had 0 prefix and 0 future-mutation mismatches. GBPUSD × ASIAN_LONDON had the fewest L2 fail-ID
occurrences (96 across 40 failing days). USDJPY/XAUUSD lanes also carry the `R.max_spread`
pip-size block.

## Identity

- Fixture: `tests/fixtures/manual_ticket/GBPUSD_M15_recorded_spread_60d.csv`
  sha256 `aeaf0ba504569f1fa8b9867f2ac8992e8b33fc143a247644e48a34be16cf2a33` (verified, pinned in test)
- Contract hash `941dec5529f7e5008db9e5b0ae2e7417f7a95c5fe5f29752dd324bb7d4737d69`,
  engine hash `243c4ff13b1aabe6a5ccdd3fad0b847f15cbfae99e1608ee1636c4d31c07e959`,
  logic identity `d7a8ebe5b176e8089905c75a6b0223eebd893c2b9324ca61865aa135d2eec7d5` (unchanged)

## L2 failure classification (58 days, 47 with a signal)

| Rule(s) | Days | Class | Root cause |
|---|---|---|---|
| `R.entry_level` (ENTRY_NOT_AVAILABLE_AT_SIGNAL) | 34 | EXPECTED_NO_TRADE | Body edge is the pre-signal open; spec `entry_must_equal_close: true` fails closed |
| `R.target_order` | 28 | EXPECTED_NO_TRADE | 5R TP2 inside the opposite boundary; spec `FAIL_CLOSED_IF_TP1_BEYOND_TP2` |
| `R.max_spread_fraction` | 14 | EXPECTED_NO_TRADE | 0.2-pip test spread / small risk > 0.15 (declared rule; recorded spread not consumed) |
| `R.stop_loss` (risk 0) + `R.target_leg2` | 2 | EXPECTED_NO_TRADE | Wick extreme equals body edge; risk_distance ≤ 0 fails closed |
| `R.regime_branch`, `R.entry_trigger`, `R.stop_loss` (TREND) | 5 | EXPECTED_NO_TRADE | TREND branch is `FAIL_CLOSED` (ENTRY_LEVEL_NOT_MARKET_AT_SIGNAL) |
| `R.target_leg2` on TREND 2026-08-25 | 1 | LOGIC_DEFECT (gate) — fixed | `logic_gate._eq` half-point bound used `max()` with float slack, so a half-up rounded TP2 (1.35851 vs 1.358505) failed by float noise (diff 5.0000000001e-06) |

No SPEC_GAP / SPEC_AMBIGUITY found; no owner question raised. The frozen strategy and engine are unchanged.

**Fix:** `src/v1_tickets/logic_gate.py::_eq` now adds the float slack to the half-point bound.
Effect on the 60-day replay: `R.target_leg2` cleared on 15 TREND cases (EURUSD 8, GBPUSD 7) that
all still fail closed via `R.regime_branch`; no valid-entry count or gate verdict changed in any lane.

## Result (re-run on all 58 recorded days)

| Lane | L1 | L2 | L3 | L4 | L5 | L6 | Prefix / mutation mismatches | Valid entries |
|---|---|---|---|---|---|---|---|---|
| GBPUSD × ASIAN_LONDON | PASS | PASS | PASS | PASS | INSUFFICIENT | PASS | 0 / 0 (1150 mutations); inline every-bar prefix check 0 | 7 |

**Verdict: NOT_ADMITTED.** L5 is INSUFFICIENT (spread not consumed from the 60-day files,
commission unknown), so not all checks pass and `logic_verified_symbols` is unchanged. This
matches the existing decision not to adopt the harness's LOGIC_VERIFIED verdict while L5 is open.
To unblock: consume `spread_points` in the harness and supply commission metadata, or have the owner
rule L5 non-blocking for logic verification.

## Reproduction

```sh
python scripts/asw_v112_60d_replay.py --date 2026-10-10 --out <scratch>/after.json
python -m pytest -q tests/test_asw_v112_gbpusd_asian_london_lane.py tests/test_asian_sweep_v1_1_2_l2_closure.py \
  tests/test_asian_sweep_v1_1_2_logic_gate_both_cycles.py tests/test_manual_ticket_logic_gate.py tests/test_lsmc_v110_logic_gate.py
```

OSS-FIRST: L2 gate tolerance | existing `logic_gate._eq` | REUSED (one-line bound fix) | no new algorithm or dependency.
