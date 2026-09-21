# AG PROFIT TRADING — MISSION 1 (FINAL): SSC ONE-YEAR REPLAY DATA AUTHORITY + WARMUP READINESS

> Consolidated from the reviewed revision + 5 verified amendments (marked **[ADDED]**).
> Verified against repo HEAD `c995f08` on 2026-09-21. Execute with one bounded agent mission.

## Mission

Prepare the repository for the first trustworthy one-year historical economic replay of:

ST_SESSION_SWEEP_CONTINUATION_V1@1.0.1

This mission stops BEFORE the economic replay.

Do not execute R6.
Do not evaluate economic performance.
Do not modify strategy semantics.
Do not optimize parameters.
Do not access HOLDOUT, OOS, or CONFIRM_001 content.
Do not grant Demo or Live authority.

Current governance already includes a SIGNED development economic gate:
AG_R6_ECONOMIC_GATE_CONTRACT_V1 (status: SIGNED, signed_by: OWNER, signed_at: 2026-09-20,
primary_friction_scenario: BASE_REPRESENTATIVE, sample.minimum_resolved_trades: 30).

Preserve it unchanged unless a concrete repository inconsistency proves remediation is required.

## Objective

Produce and freeze an admissible:

ONE_YEAR_REPLAY_STACK_V1

for:

2025-09-15T00:00:00Z
through
2026-09-14T23:59:59Z

with machine-verifiable:

DATA_COVERAGE_COMPLETE
CROSS_LEG_TIMEBASE_CONSISTENT
WARMUP_STABLE
PROTECTED_DATA_ACCESS_COUNT=0

## P0 — Preflight

Read AGENTS.md first.

Record:

branch
HEAD_BEFORE
git status
concurrent-writer state

Use config/agent_context.json routing.

Do not clean or modify unrelated WIP.

Identify current authoritative status docs and manifests before editing.

**[ADDED]** Environment: on non-Windows machines the portability patch
(`fix: make pip install and pytest collection work on non-Windows platforms`,
requirements.txt marker + probe guards) must be present for `pytest` to collect at all.
On the Windows dev box, verify `pip install -r requirements.txt` still installs
MetaTrader5 as before. Record which environment this mission runs in.

## P1 — Verify whether DEV002 remediation is still required

Inspect:

data/research/ssc_fresh_dev/SSC_V1_0_1_G2_DEV_002/raw/EURUSD_H1.csv
its dataset_manifest.json
tests/test_ssc_dev002_h1_metadata_manifest.py
V1_0_1_REMEDIATION artifacts

Recompute hashes from bytes.

**[ADDED]** Prior audit evidence to verify rather than rediscover:
committed file bytes = `sha256:9cb7c2da900e958ec092327d08e4506007146bda611c4b056c396f0e121dfa6f`;
manifest declares `sha256:93d27d8cbeb85c0b595ece7d18a43ac66219ae9fbb137e23a9826b84fc191c79`;
the file was added in single commit `f66d555` and `git show f66d555:<path>` hashes to the
same bytes it has now — the bytes never changed; the manifest was frozen against
pre-commit bytes. Confirm all four facts from bytes before acting.

If the committed H1 bytes remain stable while the manifest fingerprint is stale, implement
the additive DEV002_H1_MANIFEST_REMEDIATION_V1 described by the approved implementation plan.

Never silently rewrite historical evidence.

Record old hash, actual committed-byte hash, git proof, root cause and lineage.

**[ADDED]** Enumerate every downstream reference to the stale hash
(`grep -rn 93d27d8c artifacts/ data/ tests/ src/`) and RECORD the identity chain
(G2 population manifest, TD-8E event provenance reference DEV_002 content, which is
unchanged) in the remediation record — do not rewrite those artifacts.

DEV002 remains legacy development evidence and MUST NOT become a one-year replay input.
(It is additionally DST-mixed per the 2026-09-19 replay mission R3: winter bars aligned
at −1h, summer bars at 0h — one file, two offsets.)

If this remediation has already landed on current HEAD, verify it and do not duplicate it.

**[ADDED] P1.5 — Reconcile the stale governance test expectation**

`tests/test_external_candidate_governance_invariance.py::test_synthetic_oos_evidence_cannot_bypass_unsigned_r6_contract`
currently fails: it asserts `NOT_EVALUABLE_MISSING_SIGNED_THRESHOLDS` but the evaluator now
returns `EDGE_REJECTED`. The test was written assuming an UNSIGNED R6 contract; the contract
is now SIGNED (c995f08), so synthetic evidence is evaluable and gets rejected on merit.
Determine which is authoritative — (a) the test's premise is stale post-signature and the
fixture must construct a genuinely unsigned-threshold scenario, or (b) the evaluator drifted.
Fix intentionally with a dated note; this must be green before Mission 2 binds the R5
contract to AG_R6_ECONOMIC_GATE_CONTRACT_V1.

## P2 — Build canonical one-year replay stack

Prefer existing admitted assets rather than acquiring replacement data.

Expected candidate authorities:

SSC_V1_0_1_HIST_1Y_M1_001

and deterministic H1/M15 derivation:

SSC_V1_0_1_HIST_1Y_H1M15_DERIVED_001

**[ADDED]** and the pre-window H1 warmup source — the derived H1 starts
2025-09-14T21:00Z and cannot supply the required >= 1,000 closed H1 bars before the first
decision by itself. The proven aligned candidate from the 2026-09-19 R3 arbitration:
EXTERNAL_D_ROOT::EURUSD_H1_202501020000_202607310000.csv (+0h best shift, DST CONSISTENT,
exact-match rate 1.000000 against M1-derived H1 buckets). Package it as a declared
WARMUP_CONTEXT_ONLY dataset (model: SSC_HYP002_H1_WARMUP_CONTEXT manifest) — or verify a
better candidate exists and justify the choice.

Verify rather than assume these identities.

Create or complete:

scripts/build_ssc_v1_0_1_one_year_replay_stack.py

The resulting manifest must identify:

M1 = FILL_RESOLUTION_INPUT
M15 = STRATEGY_DECISION_INPUT
H1 = MARKET_BIAS_INPUT
warmup = WARMUP_CONTEXT_ONLY

Every input must include:

dataset ID
SHA-256
row count
UTC range
source lineage
role
timezone authority

**[ADDED]** and, per first-decision warmup bar counts against the SSC requirement
(minimum_required: 1,000 closed H1 bars, per the DEV_002 manifest's
`warmup_readiness` field and `historical_replay.warmup_readiness` actual-closed-bar counting).

H1 and M15 decision-window bars should be deterministic exact-bucket derivations from the
admitted M1 authority wherever the current repository design specifies this.

Do not manufacture or interpolate missing bars.

## P3 — Promote cross-leg timezone/DST consistency to an executable gate

Extend the existing one-year coverage audit
(`scripts/audit_ssc_v1_0_1_one_year_data_coverage.py` — already the manifest-declared
`coverage_gate`) rather than creating a competing validator.

Verify M1→M15 and M1→H1 exact OHLC bucket parity.

**[ADDED]** Parity MUST be cross-timeframe (candidate leg vs M1-derived buckets of the
canonical M1 authority). Never accept same-source parity (H1-vs-H1 from the same package):
that tautology is exactly how GEN_002's internally-inconsistent state passed its own
`parity_diagnostic` unnoticed (R3 finding, 2026-09-19).

Perform bounded whole-hour shift diagnostics sufficient to detect timezone displacement.

Evaluate winter and summer separately.

Fail closed for internally DST-inconsistent inputs.

Successful admission requires:

best_shift = +0h
DST classification = CONSISTENT
decision-window timebase = UTC_SINGLE_TIMEBASE

Add synthetic regression tests including:

correct UTC alignment
fixed-hour misalignment
winter/summer mixed offset
missing bucket
duplicate timestamp

## P4 — Warmup convergence

Before declaring the replay stack ready, implement/complete the VA2 warm-up convergence
proof using the existing historical_replay.warmup_readiness authority.

For representative SSC decision points, determine whether additional closed H1 history
changes the strategy-visible initialized context.

Do not tune strategy parameters.

The gate must distinguish:

WARMUP_STABLE
WARMUP_INSUFFICIENT
WARMUP_UNSTABLE

The declared warmup source may differ from the decision-window source only under
WARMUP_CONTEXT_ONLY lineage.

## P5 — Quarantine inadmissible GEN_002 if still required

Verify the current state of SSC_FRESH_DEV_GEN_002.

If its internal cross-leg UTC claim remains falsified (its own M1 matches canonical M1 at
only 0.795 under −3h while its manifest claims UTC persistence without transformation),
add an additive inadmissibility/quarantine record.

Do not rewrite the historical original manifest.

Future one-year replay admission must fail closed if GEN_002 is supplied as a replay stack.

## P6 — Protected-data firewall

Assert content access count remains zero for:

CONFIRM_001
HOLDOUT
OOS

Metadata-only inspection is allowed only where existing governance permits it.

Report exact access counters.

## P7 — Verification

Run focused tests first.

**[ADDED]** Expected focused green set after P1: the fingerprint chain that is currently red —
`tests/test_ssc_dev002_h1_metadata_manifest.py` (3 tests),
`tests/test_topdown_composer_replay.py` (7 tests),
`tests/test_td8e_shared_consumer_integration.py` (1 test),
plus the reconciled governance test from P1.5.

Then run the broadest environment-appropriate suite.

Linux/non-MT5 tests must distinguish intentionally marked live_mt5 tests from genuine failures.

Do not repair unrelated failures merely to obtain green output. Known out-of-scope categories
(record but do not fix unless trivial and directly adjacent): hardcoded `D:\ddev` paths in
test_market_data_readiness_scanner / test_m15_session_sweep_research_v1_parity; stale
frozen-scope git-diff baselines in the Large-SMC mission guards; unmarked runtime-MT5 tests.

Record exact commands and results.

## P8 — Freeze

Only if all admission gates pass, freeze:

ONE_YEAR_REPLAY_STACK_V1

with manifest SHA-256 and exact constituent hashes.

Update the appropriate dated status document and rolling status according to
LIVE_STATUS_MAINTENANCE.md.

Do NOT create or execute the R5/R6 economic campaign in this mission.

## Required final classification

Return exactly one primary classification:

ONE_YEAR_REPLAY_DATA_AUTHORITY_READY

or

BLOCKED_ONE_YEAR_REPLAY_DATA_AUTHORITY

If READY, also report:

HEAD_BEFORE
HEAD_AFTER
commit SHA
M1 dataset/hash/rows/range
M15 dataset/hash/rows/range
H1 dataset/hash/rows/range
warmup source/hash/bar count (per first decision, against the 1,000-bar minimum)
DATA_COVERAGE status
CROSS_LEG_TIMEBASE status
WARMUP status
protected-data access counts
focused test result
broad test result
stale governance test reconciled = YES | NO
strategy files changed = NONE
economic replay executed = NO
Demo authority changed = NO
Live authority changed = NO

If BLOCKED, identify the first falsified gate and stop rather than weakening it.

---

## After this mission returns READY

The next mission is deliberately small:

freeze R5 (binding explicitly to AG_R6_ECONOMIC_GATE_CONTRACT_V1, SIGNED) →
execute R6 once via `session_sweep_continuation.replay.run_replay` under
`historical_data_context` → independently reproduce R7 (identical population_hash +
ledger_sha256, else STOP — determinism defect, no metrics) → calculate R8–R13 with friction
declared MODELED → evaluate the already-signed economic gate → EDGE_VALIDATED or
EDGE_REJECTED, neither of which grants Demo/Live/optimization/holdout access.

A negative economic result is a SUCCESSFUL backtest-system milestone:
evidence-producing ✓ / strategy edge ✗ are independent verdicts.
