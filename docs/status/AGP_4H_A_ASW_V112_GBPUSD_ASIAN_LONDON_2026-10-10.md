# AGP-4H-A — ST_ASIAN_SWEEP_5R_V1@1.1.2, lane GBPUSD × ASIAN_LONDON (2026-10-10)

Logic verification only (rule conformance on recorded fixtures). No edge, demo or live authority.
ORDER_API_CALLS 0, broker calls 0. Registry modified only by the OD1011 resume (scoped GBPUSD entry; see below).

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

No SPEC_GAP found. One SPEC_AMBIGUITY (price rounding mode) was raised in the AGP-LANE-A2 addendum below. The frozen strategy and engine are unchanged.

**Fix (4H-A, superseded by the A2 bound below):** `_eq` added float slack to the half-point bound.
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

## AGP-LANE-A2 addendum (base #142 head e4a00bd)

### 1. `_eq` bound

`_eq` snaps the expected price to the point grid and allows `EQ_EPS_POINTS = 1e-6` points of float
slack (1e-11 for GBPUSD, point 1e-05). Observed float noise is ~1e-16, five orders of magnitude below.
A half-point error against an on-grid expectation fails, and so does a one-point error (tested). On an exact
half-point tie (e.g. TP2 = 1.358505), either grid neighbour (1.35850 or 1.35851) is accepted, because the spec
declares no rounding mode. Re-run effect: 0 L2 verdict, valid-entry or rejection-label changes in any lane
compared with e4a00bd.

**SPEC_AMBIGUITY (owner decision; not chosen here):** `ST_ASIAN_SWEEP_5R_V1_1_1_2.yaml` declares no
rounding mode for derived prices (TP2 = entry ± 5 × risk; TREND mid entry). Proposed rule text:

- **A — ROUND_HALF_UP:** "Derived prices are rounded to the symbol point with ROUND_HALF_UP (ties away
  from zero)." This matches the engine's current output (2026-08-25: 1.358505 → 1.35851).
- **B — ROUND_HALF_EVEN:** "Derived prices are rounded to the symbol point with ROUND_HALF_EVEN (ties to
  the even point)." 1.358505 → 1.35850, so the engine would need a new candidate version.

Until the owner decides, the gate accepts either tie neighbour and nothing else.

### 2. L5 on recorded spread

L5 now reads the signal bar's `spread_points` from `*_M15_recorded_spread_60d.csv` and multiplies it by
`point` from `config/symbol_metadata/host_captured/<SYMBOL>.json` (sha256-verified via `load_record`).
L2 still uses the 0.2-pip harness test input. No FX commission source is configured, because only crypto
CFD has one, so commission is `NOT_AVAILABLE` and never 0.

GBPUSD × ASIAN_LONDON: 7 kept entries, 7 evaluated. spread_R min 0.0 / median 0.0189 / max 0.04; 0
entries at or above cost_warn_R 0.10 or cost_block_R 0.25. Lane L5 = **INSUFFICIENT(commission)**.
Data caveat: recorded per-bar spreads are 0–1 point, against 15 points in the host `symbol_info`
snapshot. One kept entry (2026-09-29) records 0 points. MqlRates `spread` is a per-bar field, not a
quote at a known instant, so cost_in_R may be understated.

### 3. Coverage (GBPUSD × ASIAN_LONDON, 58 VT recorded days; 11 no-signal)

| Direction | SWEEP kept | SWEEP blocked | TREND kept | TREND blocked | RANGE kept | RANGE blocked |
|---|---|---|---|---|---|---|
| LONG | 5 | 18 | NOT_EXERCISED (spec FAIL_CLOSED) | 2 | NOT_EXERCISED | NOT_EXERCISED |
| SHORT | 2 | 17 | NOT_EXERCISED (spec FAIL_CLOSED) | 3 | NOT_EXERCISED | NOT_EXERCISED |

NOT_EXERCISED: the RANGE_REJECTION branch, in both directions, kept and blocked, is not reached on any
recorded day (UNIT_ONLY, as before). TREND kept cannot occur by spec. Both directions are exercised on
the eligible SWEEP branch.

### 4. Verdict

L1–L4 and L6 PASS, 0 mismatches, both directions exercised. L5 is INSUFFICIENT(commission), which is
below WARN, so **NOT_ADMITTED**. The registry is unchanged. To unblock: an owner-set FX commission
source for GBPUSD-VIP, or an owner ruling on L5.

## AGP-LANE-A3 addendum (base #142 head 37e2410) — conservative L5 spread

MqlRates `spread` is treated as a per-bar lower bound. L5 now uses spread = max(signal-bar
`spread_points`, host-evidence spread) × host_captured `point`. Host evidence is the
`config/symbol_metadata/host_captured/<SYMBOL>.json` snapshot spread. Tick-derived spread evidence in the
repo (`scripts/collect_eurusd_spread_evidence.py`, Large-SMC friction campaign) covers EURUSD only, so
GBPUSD has none. A case with only a bar spread is `BAR_ONLY_LOWER_BOUND`, which makes lane L5
INSUFFICIENT(spread) and never PASS. Each case records `bar_spread_points`, `host_spread_points` and `source`.

GBPUSD × ASIAN_LONDON, 7 kept entries. Source = HOST_SNAPSHOT (15 pt) for all 7; bar spread was 0–1 pt.

| Date | Dir | bar pt | host pt | spread_R |
|---|---|---|---|---|
| 2026-07-23 | LONG | 1 | 15 | 0.3191 |
| 2026-08-21 | LONG | 1 | 15 | 0.2830 |
| 2026-08-31 | SHORT | 1 | 15 | 0.6000 |
| 2026-09-03 | SHORT | 1 | 15 | 0.1786 |
| 2026-09-10 | LONG | 1 | 15 | 0.4545 |
| 2026-09-22 | LONG | 1 | 15 | 0.2113 |
| 2026-09-29 | LONG | 0 | 15 | 0.2308 |

spread_R min 0.1786, median 0.2830, max 0.6000. All 7 are at or above cost_warn_R 0.10, and **4 of 7 are at
or above cost_block_R 0.25 on spread alone**, before commission. Lane L5 stays INSUFFICIENT(commission),
because commission is unknown and never 0. No L1–L4 verdict changed. Owner binding: `session_row` with kept
entries and no owner cost binding returns L5 FAIL (`OWNER_BINDING_MISSING`, tested).

**Pending owner decisions (not acted on):** (1) rounding mode A ROUND_HALF_UP / B ROUND_HALF_EVEN;
(2) the FX commission source for GBPUSD-VIP; (3) branch scope, i.e. whether logic verification is
SWEEP-only with RANGE_REJECTION and TREND fail-closed (RANGE is NOT_EXERCISED on recorded days).

## OD1011 resume (2026-10-11, base #142 head f257a9d) — owner decisions applied

Decisions: OD1011-COMMISSION, -ROUNDING, -SCOPE, -L5 (`docs/governance/OWNER_DECISION_REGISTER.md`, also #149).

- **Rounding:** `_eq` rounds the expectation ROUND_HALF_UP (ties away from zero) to the point grid. Slack is
  `EQ_EPS_POINTS` = 1e-6 point. The other tie neighbour, a half-point error and a one-point error all fail (tested).
- **Rounding finding (owner info, not fixed):** with tie acceptance removed, `R.target_leg2` now also fails on 8
  TREND cases (EURUSD AL 5, GBPUSD LN 3). The engine derives TREND TP2 from the **unrounded** box mid
  (e.g. 1.351395 + 5R = 1.35927 exactly). The gate rebuilds it from the rounded ticket entry (1.3514) and so
  sees a false half-point tie. It is TREND-only, TREND stays spec FAIL_CLOSED via `R.regime_branch`, and no lane
  verdict or kept entry changed. SWEEP levels are bar prices on the grid and are unaffected. Proposed follow-up:
  if TREND is ever verified, the gate should rebuild TREND TP2 from the box mid, not the ticket entry.
- **Commission:** the harness applies `commission: 0` from `config/owner_ticket.yaml` only when `source:
  OD1011-COMMISSION`, the value is exactly 0, `bound_server` equals the host-captured `server` (VTMarkets-Demo)
  and the symbol's asset class is listed. Otherwise it is None (INSUFFICIENT, tested). The account type
  (STANDARD_STP) is owner-stated and not in host evidence. The first demo deals' commission field must confirm it.
- **L5 (OD1011-L5):** lane PASS needs, for every kept entry, the conservative spread, a bound commission, and the
  owner-ticket cost gate (`build_manual_ticket`) reproducing cost_in_R and the 0.10 R warn / 0.25 R block.

GBPUSD × ASIAN_LONDON (58 days): L1 PASS · L2 PASS · L3 PASS (0 prefix/mutation mismatches) · L4 PASS ·
**L5 PASS** (7/7 cost-gate correct; actionability COST_BLOCKED 4, COST_WARN 3) · L6 PASS. Kept entries:
SWEEP LONG 5 / SHORT 2. **Verdict: LOGIC_VERIFIED for ASIAN_LONDON × RANGE_SWEEP (SWEEP) only.** The registry
entry is bound to contract `941dec55…`, logic identity `d7a8ebe5…` and this evidence. TREND and RANGE_REJECTION
stay fail-closed; LONDON_NEWYORK is not covered. No demo, live or edge authority; D6 READY stays OFF.

## Reproduction

```sh
python scripts/asw_v112_60d_replay.py --date 2026-10-10 --out <scratch>/after.json
python -m pytest -q tests/test_asw_v112_gbpusd_asian_london_lane.py tests/test_asian_sweep_v1_1_2_l2_closure.py \
  tests/test_asian_sweep_v1_1_2_logic_gate_both_cycles.py tests/test_manual_ticket_logic_gate.py tests/test_lsmc_v110_logic_gate.py
```

OSS-FIRST: L2 gate tolerance | existing `logic_gate._eq` | REUSED (bounded grid compare) | no new algorithm or dependency.
OSS-FIRST: L5 spread input | existing fixture column + `host_evidence.symbol_metadata.load_record` | REUSED | no new dependency.
