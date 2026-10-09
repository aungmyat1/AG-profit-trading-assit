# AG_EDGE_DISCOVERY_ACCELERATION_R1 — C001 Freeze + Fast-Screen Pipeline + Candidate Factory V0

**Date:** 2026-10-03
**Classification:** Research-only. Grants no edge claim, proposal, risk, or execution authority.

## Phase 0 — Authority / lineage (verified against live remote)

```text
CURRENT_MAIN_SHA  = eb834dbd6f5eec23a05f2cda8ad6e19d5d32a3ec   (= frozen Message Router V1 SHA)
CURRENT_MAIN_TREE = 9d435bd9db1b1270eb70f60ddbd759a9afa34249   (= frozen Message Router V1 tree)

PR30_STATE    = OPEN (NOT merged; mergedAt = null; mergeable CLEAN)
PR30_HEAD_SHA = a5ce51d483b2a47cd723d64ab670eb42e0ed11f2
PR30_BASE     = main @ eb834dbd6f5eec23a05f2cda8ad6e19d5d32a3ec
PR30_MERGED   = FALSE

Candidate implementation SHA a5ce51d… verified: parent = eb834db… (current main),
tree = 0b88450fffe9c0af85fbc9e513b3481467e1c1a9. Worktree was byte-identical to it
before this mission started; no unrelated dirty worktree was touched.
```

Branch note: this session is platform-pinned to `arena/01a0fe6d-ag-profit-trading-assit`
(the PR #30 head). A separate `research/...` branch cannot be created from this session,
so R1 publishes as additional commits on the same research PR — recorded here instead of
silently ignored.

## Phase 1 — Contract audit

Audited: contract YAML, `src/crypto_cfd_contract/`, contract tests (30/30 pass),
registry, ledger, contract doc. Strategy remains fully deterministic.

Stop-buffer semantic authority corrected (commit `a4da287…`, documentation-only):

```text
STOP_BUFFER_POLICY_V1 = ZERO_PRICE_BUFFER
EPISTEMIC_STATUS      = PREREGISTERED_RESEARCH_HYPOTHESIS
```

The contract no longer reads as "tick_size=0 therefore zero buffer": the broker's zero
tick metadata is explicitly insufficient metadata, not economic justification, and the
zero-buffer stop's noise exposure is marked as the thing research must measure.
`STOP_BUFFER_POINTS`/`STOP_BUFFER_PRICE` and all executable rules are unchanged
(verified by the untouched 30-test contract suite before committing).

## Phase 2 — C001 frozen

```text
CANDIDATE_ID     = CRYPTO_CFD_C001
STRATEGY_ID      = ST_CRYPTO_CFD_SWEEP_RETEST_V1
STRATEGY_VERSION = 1.0.0
CONTRACT_SHA     = a4da28774035491112e63bdf90938b94fc8567de
CONTRACT_TREE    = 09e5340ece7bc3b09c913e3872576f856c106b53
EDGE_VERIFIED              = FALSE
FAST_SCREEN_STATUS         = NOT_EVALUATED
FULL_VERIFICATION_STATUS   = NOT_EVALUATED
```

Artifacts: `research/edge_discovery/candidates/CRYPTO_CFD_C001.yaml` (manifest,
created_before_results=true) + `CRYPTO_CFD_C001.freeze.json` (sha256 of the manifest
and of every contract file, byte-exact). Tests verify the freeze record against disk;
any later rule change must become C002+/new version.

## Phase 3 — Data authority inventory (`research/edge_discovery/datasets.yaml`)

| Dataset | Symbols | TFs | Span | Source | Quality | Current role |
|---|---|---|---|---|---|---|
| EURUSD_M5_S2R_RESEARCH | EURUSD | M5 | 2025-06-30 → 2026-09-11 | MT5 Vantage demo capture | sha256-verified parquet, cross-checked | TRAIN / VALIDATION / FINAL_HOLDOUT(locked) |
| SSC FX packages | EURUSD, GBPUSD | H1/M15/M5/M1 | 2024Q1 → 2026-09 | MT5 captures + manifests | manifest-verified | DEV / OOS per SSC governance |
| Bybit linear perp feed | BTCUSDT | on-demand | not stored | public REST, live fetch | no frozen partition | perp research input — **substitution forbidden** |
| BTCUSD_CFD_HISTORY | BTCUSD | — | — | **NONE in repo** | — | NONE_AVAILABLE |
| ETHUSD_CFD_HISTORY | ETHUSD | — | — | **NONE in repo** | — | NONE_AVAILABLE |

**Conclusion: `BLOCKED_INSUFFICIENT_RESEARCH_DATA`.** No uncontaminated BTCUSD/ETHUSD
CFD history exists in-repo and the MT5/Terminal-MCP data authority is unreachable from
this environment. Economic evaluation (Phases 8–10) STOPPED — no results were
fabricated, no perp data substituted, no holdout touched. Unblock path: a
provenance-verified BTCUSD/ETHUSD CFD M5 capture via `research_external/tooling/
mt5_capture.py` on the MT5 host, partitioned DEV/VALIDATION/HOLDOUT before first read.

## Phases 4–7, 9, 11, 12 — Candidate Factory V0 (implemented and tested)

| Piece | Where | State |
|---|---|---|
| Models (CandidateManifest, CandidateSource, CandidateStatus, ContractabilityResult, FastScreenResult, FrictionResult, PromotionDecision, DatasetAccessRecord) | `src/edge_discovery/models.py` | IMPLEMENTED — frozen dataclasses; PromotionDecision structurally cannot emit EDGE_VERIFIED |
| Contractability gate | `src/edge_discovery/contractability.py` | IMPLEMENTED — 11 deterministic checks, stable reason codes, fail closed, no scoring |
| C001 fast-replay adapter | `src/edge_discovery/replay_c001.py` | IMPLEMENTED — frozen contract verbatim; REPLAY_FILL_MODEL_V1 preregistered (pessimistic intrabar resolution); full event lineage per trade; no tunable strategy surface |
| Friction model | `src/edge_discovery/friction.py` | IMPLEMENTED — CRYPTO_CFD_SPREAD_SCENARIOS_V1: OBSERVED_LIVE_SPREAD snapshot (BTCUSD 17.02 / ETHUSD 2.50, 2026-10-02) × frozen BASE/STRESS/SEVERE (1×/2×/4×); explicitly NOT a historical cost model; screen scenario fixed to BASE before any result exists |
| Fast-screen metrics | `src/edge_discovery/fast_screen.py` | IMPLEMENTED — all Phase-8 metrics incl. time-bucket + H1-structure regime decomposition |
| Promotion policy | `src/edge_discovery/promotion.py` | IMPLEMENTED — FAST_SCREEN_PROMOTION_POLICY_V1 preregistered (INCONCLUSIVE if N<30; FAIL on net expectancy ≤0 / PF_net ≤1 / friction-destroyed gross edge); PASS → FROZEN_FOR_VERIFICATION, never EDGE_VERIFIED |
| Dataset-access ledger | `src/edge_discovery/dataset_ledger.py` + `research/edge_discovery/dataset_access_ledger.jsonl` | IMPLEMENTED — append-only JSONL; HOLDOUT/FINAL_OOS need governance approval id; reuse denied on same approval, never relabeled independent |
| Candidate queue (C002–C010 + FX-ready) | `research/edge_discovery/candidate_queue.yaml` | IMPLEMENTED — family placeholders only, no fabricated rules |

C001 gate outcome: every contract/logic check **PASS**; `required_data_available`
**FAIL** → overall `FAIL (REQUIRED_DATA_UNAVAILABLE)`, candidate_status stays
DISCOVERED. Perp datasets offered to the gate are explicitly flagged
`CROSS_INSTRUMENT_SUBSTITUTION_FORBIDDEN`, never consumed.

## Phase 13–14 — Validation & safety

```text
NEW_TESTS            = 28 (tests/test_edge_discovery_factory_v0.py) — full mission matrix
EXISTING_TESTS       = full repo suite: 928 passed, 4 skipped (live-MT5), 0 regressions
COMPILEALL           = PASS
STATIC_MUTATION_SCAN = 0 matches in src/edge_discovery/ (no order_send/management_gateway/
                       execution path, no mt5 import, no pip/session leakage, no USDT identity)
EXECUTION_AUTHORITY_ADDED = FALSE     BROKER_ORDERS_SENT = 0     MUTATING_TOOLS_EXECUTED = 0
STRATEGY_OPTIMIZED_AFTER_RESULTS = FALSE (no results exist)      RISK_POLICY_CHANGED = FALSE
```

## Verdict

```text
C001_FAST_SCREEN_STATUS = NOT_EVALUATED (BLOCKED_INSUFFICIENT_RESEARCH_DATA)
FINAL_VERDICT           = BLOCKED_INSUFFICIENT_RESEARCH_DATA
                          (factory infrastructure READY; economic screen awaits a
                          provenance-verified BTCUSD/ETHUSD CFD dataset)
```
