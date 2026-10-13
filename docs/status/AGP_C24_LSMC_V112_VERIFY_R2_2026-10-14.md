---
class: evidence
state: DESIGN
owner_reviewed: null
review_by: 2026-11-07
---
# C24 Large-SMC 1.1.2 verification (2026-10-14)

Mission AGP-C24-LSMC-V112-VERIFY-R2, owner amendment: **60 days only**.
Evidence and proposal scope; no engine, contract, registry, READY, scheduler or flag change.
Base at replay start: `726b16a40d79fa84ed2848bfecba4576a9db6a3f` (contains #209).
Integrated latest main `93e8c2b5233b269ae8e5d0eac244b76af5eeee58` (#211), without conflicts.
Environment: Linux managed sandbox, Python 3.12, committed VTMarkets-Demo fixtures only.
Broker contact / order API calls / mutations: **0**. Economic edge: NOT_EVALUATED.

## Verdict and scope matrix

| Symbol | Full 60d L1–L6 verdict | Oracle | Registration eligible |
|---|---|---|---|
| BTCUSD | **NOT_RUN_RESOURCE**; bounded C11 ENGINE_DEFECT found | Completed, reference divergent | No |
| ETHUSD | **NOT_RUN_RESOURCE**; replay not reached before termination | Completed, reference divergent | No |
| EURUSD | PENDING_D1; L1–L6 NOT_RUN | NOT_RUN | No |
| GBPUSD | PENDING_D1; L1–L6 NOT_RUN | NOT_RUN | No |
| USDJPY | PENDING_D1; L1–L6 NOT_RUN | NOT_RUN | No |
| XAUUSD | PENDING_D1; L1–L6 NOT_RUN | NOT_RUN | No |

P1 used `tests/fixtures/ccfd_v100/recorded_60d`: each crypto symbol has D1=60,
H1=1,412, M5=16,932, covering recorded M5 dates 2026-08-11 through 2026-10-09.
Provenance and all required core-file hashes passed. Recorded gaps remain unchanged;
no interpolation, replacement, bid/ask or volume was invented.

The managed environment restarted while P1 ran. Its session disappeared and PID 29382
was observed defunct. The atomic checkpoint retained 1,700 BTC scans; flushed CSV
retained 1,730/16,932 (last close 2026-08-17T17:10Z). ETH replay never started.
All full-window verdicts remain NOT_RUN_RESOURCE. A prior planned auditor restart,
before this termination, is not represented as a completed run.
The owned R1 lock was explicitly released after recording termination evidence.

Partial BTC gates: L1/L2/L3/L6 PASS 1,730 each; L4 PASS 1,371 and FAIL 359
(insufficient-history bootstrap); L5 WARN 1,730 (declared incomplete cost evidence).
These counts are **partial observations, not full-scope PASS**.
Ten observed branches, including short-D1 LONG/SHORT, FVG/OB_PIVOT/OB_SHADOW,
primary/H1 fallback and warmup, are enumerated in `partial_branch_matrix.json`;
unreached full-D1 branches and every ETH branch are NOT_RUN.
Signals and scan-level plans are retained; 359 gate mismatches are
EXPECTED_INSUFFICIENT_HISTORY. Supplemental mismatch: C24-C11-STATIC-ROLLING-WINDOW.

P3 end-of-P1/P2 gate: no PR titled “data(vt): recorded 60d FX M5/H1/D1 (D1-R2)”
was found (search `"D1-R2" in:title`); `tests/fixtures/vt_recorded_60d_fx`
is absent from integrated main. **P3=PENDING_D1**. Legacy M15 captures cannot supply
missing M5/H1/D1 evidence. No 180d data or full-window expansion is used.

## P2 pinned oracle comparison

Command (one worker under R1 resource_guard):
```sh
PYTHONPATH=src python -m research_external.oracles.lsmc_detection_run --c24-recorded --out artifacts/logic_verification/ST_LARGE_SMC_V1_1_1_2/c24_r2/p2_oracle/oracle.json
```

`smartmoneyconcepts==0.0.27` is already pinned in requirements; its installed
distribution license is MIT. All D1/H1/M5 bars for both symbols were compared.
OB comparison is H1 only, per contract. This is retrospective detection reference
evidence; it does not certify oracle causality or replace P1.

Agreement is exact normalized-event **Jaccard intersection/union**, weighted across
applicable timeframes. Empty union is NOT_APPLICABLE, never 100%.
Origin index identifies swings/FVG/OB; BrokenIndex identifies BOS/CHOCH; actual
Swept index identifies liquidity sweeps. Unconfirmed library bookend swings are
excluded explicitly. No timing/price tolerance is silently added.
Recorded CSVs lack volume; the existing dataframe adapter supplies zero.
OB geometry is compared, never volume strength.

| Symbol | Swings | BOS/CHOCH | FVG | OB (H1) | Liquidity sweeps |
|---|---:|---:|---:|---:|---:|
| BTCUSD | 78.896577% | 0.938449% | 99.745870% | 0.000000% | 0.000000% |
| ETHUSD | 78.155693% | 1.362319% | 99.838300% | 0.000000% | 0.000000% |

Every one of **16,372** symmetric-difference events has a row in
`oracle_divergences.jsonl`, classified SPEC_DIFFERENCE with rule citation, side,
bar index, time and normalized signature. ORACLE_DEFECT=0; detection-level
ENGINE_DEFECT=0 under the documented necessary contract checks.
This does **not** negate the separate C11 engine defect.

Declared definitions explain the differences: strict k=2 fractals rather than
alternating rolling extrema; latest confirmed unconsumed swing plus five-point
close tolerance rather than four-swing BOS/CHOCH labeling; three-candle gaps
without middle-body filtering; AG_ORDER_BLOCK_V1 expressly excludes SMC_OB;
wick-and-close reclaim of the latest confirmed swing differs from equal-level
cluster sweeps. Every local event, including matches, is checked for required
geometry/confirmation conditions; the checker does not claim exhaustive model
equivalence. Oracle outputs never alter runtime decisions.

## Oracle divergence counts by element (C24-R3 completion)

| Element | SPEC_DIFFERENCE | ORACLE_DEFECT | ENGINE_DEFECT |
|---|---:|---:|---:|
| BOS_CHOCH | 6992 | 0 | 0 |
| FVG | 19 | 0 | 0 |
| OB | 318 | 0 | 0 |
| liquidity_sweeps | 6683 | 0 | 0 |
| swings | 2360 | 0 | 0 |

The separate C11 target-selection defect has three native adjacent-scan witnesses;
it is not an oracle detection divergence. Replay remains **PARTIAL / NOT_RUN_RESOURCE**.
Per-symbol counts are in `p2_oracle/divergence_counts_by_element.json`.

## ENGINE_DEFECT: C24-C11-STATIC-ROLLING-WINDOW

Rule: `strategies/ST_LARGE_SMC_V1_1_1_2.yaml:138,177`,
STATIC_AT_OPPORTUNITY_EVALUATION and retarget_after_selection=false.
Implementation: `src/large_smc_v112/watch.py:264`.

Minimal recorded witness: BTC M5 rows 1271 and 1272, closes 2026-08-16T03:00Z
and 03:05Z. Opportunity ID and trigger remain identical; target changes
**63238.30 primary → 63113.99 H1 fallback**, entry remains 63099.68.
The current 300-bar rolling M5 window loses the earlier primary target source.
Recomputing selection from that clipped window does not preserve the selected
static target. Two more adjacent pairs reproduce the same mechanism:
1487→1488 and 1633→1634. One defect, three witnesses.

`static_target_repro.json` includes complete observed opportunity records,
window starts/counts, input hashes, source location and reproduction command:
```sh
python scripts/lsmc_v112_c24_static_target_repro.py --scans artifacts/logic_verification/ST_LARGE_SMC_V1_1_1_2/c24_r2/p1_crypto/scans.csv --out /tmp/c24-static-repro.json
```
These calls use the original evaluator, **no feature or snapshot memo**.
The two adjacent host-window inputs are reconstructed directly from committed
CSV rows. No engine fix is made in this evidence mission.

## Identity, audit method and proposal

Contract SHA256: `1f9b6cace2e1be33e5b3572e2c13e3e526b992478f91c8f09955b0f44b73024f`.
Engine SHA256: `7f218a9001cb7ffa069e02a101accd53ab86b2b2c8989c73939671fb624f0d7a`.
Exact declared structural rule diff: **77 paths, PASS, zero undeclared drift**.
All tracked src/config/strategies files were hashed before replay and rechecked
after interruption; no protected bytes changed.

P1 command:
```sh
python scripts/lsmc_v112_logic_audit.py --out artifacts/logic_verification/ST_LARGE_SMC_V1_1_1_2/c24_r2/p1_crypto/audit.json
```
The existing canonical L1–L6 gates run at every recorded M5 close; host windows
are D1=30/H1=200/M5=300. No sampling. The auditor memoizes only immutable H1 POI
facts keyed by full closed-bar and break inputs, bounded to 32 entries. Cloned
function namespaces use unchanged code objects; engine globals are never
modified. Snapshot and check results are not cached. Uncached native snapshots
are compared at every H1-window change and every new opportunity plan; any
mismatch fails the run. Harness tests check this parity and interrupted status.
The interrupted campaign remains unverified regardless of partial parity.

**P4: NO PROPOSAL.** No completed eligible scope with zero ENGINE_DEFECT exists.
`docs/proposals/C24_LSMC_V112_REGISTRATION.md` is not created; proposed registry
diff is none, applied registry diff is none. Existing C21 proposal is historical.
Owner review of C11 static retention and a fresh complete R1 replay are needed;
neither engine repair nor replay PASS is inferred here.

## OSS-FIRST

| COMPONENT | OSS_CANDIDATE | DECISION | REASON |
|---|---|---|---|
| Replay/gates/detection | Existing repo lsmc audit + L1–L6 + frozen detectors | REUSED | Same authority and committed inputs |
| Independent detection oracle | smartmoneyconcepts 0.0.27 (MIT) | WRAPPED | Pinned reference, distinct models documented |
| Recorded windows/events | Python stdlib csv/bisect/json | WRAPPED | Existing audit host-window convention; no trading rules added |
| Repeated H1 features | Existing immutable h1_pois | REUSED | Auditor-only bounded memo, native snapshot parity guards |

## Checks and evidence

Focused `python -m pytest -q tests/test_lsmc_v112_60d_replay.py tests/test_lsmc_c24_oracle.py`:
**9 passed**, 3.74s, Linux/off-host, R1 lock released.
Final default suite `python -m pytest -q`: **2,944 passed, 5 skipped**,
5 warnings, 513.03s, Linux/off-host, one worker, R1 lock released. New-test lint
and `git diff --check`: PASS. Remote CI is attributed to the final head on
[PR #213](https://github.com/aungmyat1/AG-profit-trading-assit/pull/213), not to the replay verdict.
Explicit slow/live-host checks are NOT_RUN; default-suite skips remain visible.
Artifact root: `artifacts/logic_verification/ST_LARGE_SMC_V1_1_1_2/c24_r2/`.
Per-phase logs, divergence inventory, branch matrix, signal events, scan plans,
resource interruption/release and machine campaign summary remain attributable
to their original inputs and incomplete/completed status.
