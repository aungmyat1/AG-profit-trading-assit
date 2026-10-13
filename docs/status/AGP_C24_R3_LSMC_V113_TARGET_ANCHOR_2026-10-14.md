---
class: evidence
state: DESIGN
owner_reviewed: null
review_by: 2026-11-07
---
# C24-R3 Large-SMC 1.1.3 target anchor (2026-10-14)

Owner C24-R3 authorizes an append-only candidate fixing C11 selection; it does not
authorize registration, READY, demo/live, broker contact or a report-version switch.
Base: `93e8c2b5233b269ae8e5d0eac244b76af5eeee58` (main contains #209).
Predecessor evidence [PR #213](https://github.com/aungmyat1/AG-profit-trading-assit/pull/213):
head `6d9cad2bcceaa6b71c5ecef95886e1905d4f0fdb`, CI green, ready for review;
replay remains PARTIAL / NOT_RUN_RESOURCE. Its C11 defect has three native witnesses.

## Candidate and fixed rule

New `strategies/ST_LARGE_SMC_V1_1_1_3.yaml`, `src/large_smc_v113/`,
`src/v1_tickets/lsmc_v113_logic_gate.py` and evidence-only sharded auditor.
Frozen 1.1.0/1.1.2 engine/contract bytes are re-hashed against base; existing
registry and `config/lsmc_report_lane.yaml` remain byte-identical, version **1.1.2**.
Candidate inactive, unregistered, NOT_VERIFIED; no runtime selection wiring.

C11 candidate search ends at the opportunity's **M5 CHoCH creation-bar close**.
Fixed closed-bar lookbacks: M5=300, H1=200, anchored to creation, not the current
scan. Current detection still receives unchanged host windows D1=30/H1=200/M5=300.
A separate target-history input supplies recorded H1/M5 and declared capture-start
UTC timestamps. Initial short capture is allowed only when its first input bar
equals that declared start; clipped creation history fails closed with
C11_CREATION_HISTORY_NOT_EVIDENCED. No later H1 fallback substitutes for lost
primary evidence. Future bars are ignored before candidate selection.
Primary and fallback selectors themselves are reused unchanged from 1.1.2.
No engine state or retained target cache is required.

Three native regression pairs preserve original selected primaries:
BTC rows 1271→1272, 1487→1488 and 1633→1634. Same opportunity identity and full
target-selection record remain unchanged. A native property walk tests **every
later scan before each expiry**, with nonvacuous matching IDs; growing later
prefixes and arbitrary future-price mutations also preserve selection.
Missing/clipped history fails closed. Seven focused engine/property tests passed
in 24.98s; six shard guard tests passed across targeted runs after harness fixes.
These are logic regressions, not economic evidence.

Contract SHA256: `e5f04912695967fdc95178e0f862d9c2af47f56529f8c97b1a8a104198f1aa7b`.
Engine SHA256: `279ef511e6e94cb4ea571c28bc30146a7c49c205282d6eb2883007ac66e34bfe`.
Exact declared parsed diff: **14 paths** vs 1.1.2; undeclared drift fails closed.
No threshold, C10 convention, POI age, cost evidence or authority is changed.

## 60-day sharded replay

Six approximately 10-day shards per crypto symbol, one R1-locked worker at a time.
Committed source: `tests/fixtures/ccfd_v100/recorded_60d`; all 16,932 recorded
M5 closes per symbol are assigned exactly once. Recorded gaps are retained.
Warmup includes current host lookbacks and the full creation lookback before the
oldest possible active creation bar, using real preceding fixture rows.
Every shard boundary compares complete snapshots on an overlapping reference
interval (12 recorded M5 bars each side), using the unmodified evaluator:
warmed shard inputs vs independent full-recorded-history reference inputs.
Boundary mismatch, identity drift or undeclared rule drift is FAIL.

The auditor memoizes only immutable H1 POI and creation-selection facts in
separate function namespaces (bounded 32/256 entries). It never changes engine
globals or caches snapshots/check results. Pure keys include all relevant closed
OHLC/time/volume, break/creation fields and capture starts. Native parity checks
run on every H1-window change and new opportunity/C11/eligibility plan. C10 is
always recomputed. Native regression/property and boundary calls use no memo.

Killed shard = NOT_RUN_RESOURCE, never PASS; merge preserves any failure or
missing shard and requires all six nonoverlapping cores for a completed symbol.
Cross-shard opportunity IDs are checked for identical target-selection hashes.
L5 retains its declared cost WARN; no contemporaneous quote/account cost is
invented. Owner R3's all-L1–L6-PASS proposal condition will be reported literally.
FX remains PENDING_D1, `tests/fixtures/vt_recorded_60d_fx`, 60 days only.

Replay artifacts will be recorded under
`artifacts/logic_verification/ST_LARGE_SMC_V1_1_1_3/c24_r3/`.
Full default suite, merged shard matrix, proposal eligibility and final remote CI
are pending at this initial draft; no completed full-window PASS is claimed.

## OSS-FIRST

| COMPONENT | OSS_CANDIDATE | DECISION | REASON |
|---|---|---|---|
| C11 candidates | Existing 1.1.2 primary/H1 selector | REUSED | Only causal input windows change |
| Detection and L1–L6 | Existing frozen detectors and gate pattern | REUSED | Append-only version, original rules retained |
| Shards and boundary oracle | Existing C24 auditor + Python stdlib | WRAPPED | Real overlaps, native reference, no sampled PASS |
| External SMC reference | smartmoneyconcepts 0.0.27 (MIT) | REUSED | Existing pinned dependency and #213 detection evidence; no authority |

Broker contact/order calls/mutations: **0**. Economics: NOT_EVALUATED.
