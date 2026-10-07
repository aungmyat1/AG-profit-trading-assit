# AG Readiness — Current Facts Snapshot (R3)

FACTS_DATE=2026-10-07
BASE_SHA=fc60cdbf603146b1408dba9184e6c146bdcf4ea5
BASE_TREE=adf5b0ea0ba43681ce7a2d4665e40559e56e4f33
(resolved live from `origin/main` at runtime; superseded any cached SHA)

PR45_STATE=OPEN (not draft), head `arena/3b8a0571-ag-profit-trading-assit` @ `24daa6bb91538b47cc73b8f9029ea5d49cced18e`
PR46_STATE=OPEN (draft), head `arena/d1cea83b-ag-profit-trading-assit` @ `9bb5560c3dbc46c570b0ef40a3db6b606886527e`
PR46_HEAD=9bb5560c3dbc46c570b0ef40a3db6b606886527e (tree `9bd2fff9813ef3c7ff4034e4164b5dd29b3fa250`) — matches PR #46's reported identity and `PREREG_SHA256=342482c9972d1029d85b5ce4ab4792d4d147617d110aa88a6b020e32b707912b` (re-hashed and confirmed against `research_external/candidate_factory/PREREG_CANDIDATE_FACTORY_R1.sha256.txt`). No discrepancy found.

## PR #45 — R4A/R4B verification (evidence read-only, not rerun)

```
R4A_PACKAGE_ID=AG_ASIAN_SWEEP_V1_2_BLIND_HANDOFF_001
R4A_PACKAGE_HASH=cfc8309dd9259fbe99b0f6ecc85c68f5864ce566e49f10a7c18e24b9812f69d6   (handoff_manifest.json PACKAGE_SHA256; matches prior session memory)
R4B_STATUS=NOT_RUN — artifacts/logic_verification/ST_ASIAN_SWEEP_5R_V1_2_0/r3_verification_report.json records
  blind_reference_isolation=BLOCKED_SEPARATE_AGENT_CONTEXT_UNAVAILABLE, reference_engine_parity=NOT_RUN,
  logic_verified=false, economic_status=NOT_VERIFIED, blockers=[BLIND_REFERENCE_ISOLATION_REQUIRED]
```

## PR #46 — infrastructure drift check

`src/external_candidate/` = NOT PRESENT in repo (confirmed via `git ls-tree -r origin/main` and `git grep`, no hits).
`performance/` = NOT PRESENT in repo (same check).
`INFRASTRUCTURE_DOC_DRIFT=TRUE` (pre-existing, several docs reference these paths; not repaired here — out of scope).

## PR46 governance consistency

```
PR46_PR_BEFORE_FIRST_PUSH=FAIL
```
Evidence: commit `9bb5560c` committer date `2026-10-07T08:00:59Z`; `gh pr view 46 --json createdAt` = `2026-10-07T08:01:11Z` (12s later). `gh pr create --head <branch>` requires the branch to already exist on `origin`, i.e. the push preceded PR creation. Session action log (prior memory) also records push (step 14) before `gh pr create` (step 15). Conflicting transcript statements are resolved by this chronology, not by narrative.

## Strategy identity table (one row per exact id@version; not combined)

| Strategy ID | Version | Contract/Spec | Engine | Runtime config | Runtime-selected | Instruments | Sessions | Logic status | Economic status | Proposal authority | Demo authority | Live authority | Latest evidence |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| ST_ASIAN_SWEEP_5R_V1 | 1.1.1 (registry/runtime) | `strategies/ST_ASIAN_SWEEP_5R_V1.yaml` | `strategy_engine` (this repo) | `strategies/ST_ASIAN_SWEEP_5R_V1.yaml` | 1.1.1 | per yaml (FX) | ASIAN_LONDON, LONDON_NEWYORK | NOT_VERIFIED (registry `logic_status: NOT_VERIFIED`) | NOT_EVALUATED | ticket_authority: MANUAL_ONLY | false | false | `strategies/registry.yaml` lines 13-30 |
| ST_ASIAN_SWEEP_5R_V1 | 1.2.0 (candidate, PR #45 only, not merged/runtime) | `strategies/ST_ASIAN_SWEEP_5R_V1_2_0.yaml` (PR #45) | `src/asian_sweep_v1_2/engine.py` (PR #45) | not wired to runtime (not on `main`) | NOT_SELECTED | per contract.yaml | scope claimed EURUSD/GBPUSD/USDJPY/XAUUSD + both cycles; **NOT independently re-verified this mission** | r3 funnel: 0 trades LOGIC_VERIFIED | NOT_VERIFIED | NOT_VERIFIED | not registered | false | false | `artifacts/logic_verification/ST_ASIAN_SWEEP_5R_V1_2_0/r3_verification_report.json` (PR #45) |
| SESSION_TRADE_V1 | (registry, no numeric version field) | `strategies/session_trade/contract.yaml` | external repo reference (`D:\ddev\Session Trade Codex`), not vendored | same | active=true | per contract | n/a (adapter not evaluated here) | NOT_VERIFIED | NOT_EVALUATED | MANUAL_ONLY | false | false | `strategies/registry.yaml` lines 32-48 |
| SESSION_TRADE_V2 | PR #33 only, not merged | `docs/specs/SESSION_TRADE_V2_SPEC.md` (PR #33) | `src/session_trade_v2/engine.py` (PR #33) | not on `main`, not registered | NOT_SELECTED | EURUSD (DEV replay only) | ASIAN_LONDON, LONDON_NEWYORK | PR #46 DEV screen: REJECTED (net-negative both cycles) | NOT_EVALUATED (DEV-only) | none | false | false | `research_external/candidate_factory/candidates/INT_C001.json` |
| ST_MTF_CONTROL_SHIFT_V1 | PR #34 only, not merged | `docs/specs/ST_MTF_CONTROL_SHIFT_V1_SPEC.md` (PR #34) | `src/mtf_control_shift/engine.py` (PR #34) | not on `main`, not registered | NOT_SELECTED | EURUSD (DEV replay only) | ASIAN_LONDON, LONDON_NEWYORK | PR #46 DEV screen: HOLD_SAMPLE_REQUIRED (0 signals, ~1yr) | NOT_EVALUATED | none | false | false | `research_external/candidate_factory/candidates/INT_C002.json` |
| ST_LARGE_SMC_V1 | 1.0.7 | `strategies/ST_LARGE_SMC_V1.yaml` | `src/large_smc_research/engine.py` (RESEARCH_ONLY) | same | registered, active=false | per yaml | per yaml | C10 stop policy SIGNED (v1.0.7); RESEARCH_QUALIFIED reachable; NOT LOGIC_VERIFIED at blind standard | NOT_EVALUATED | none (no proposal/demo/live authority) | false | false | `strategies/registry.yaml` lines 61-78; `strategies/STRATEGY_LEDGER.md` §ST_LARGE_SMC_V1 |
| ST_LARGE_SMC_V1 | 1.1.0 | `strategies/ST_LARGE_SMC_V1_1_1_0.yaml` | `src/large_smc_watch/` (watch/alerts only) | same | registered alongside 1.0.7 | EURUSD, GBPUSD, USDJPY, XAUUSD, BTCUSDT, ETHUSDT (note: **perpetual-style crypto symbol names**, not VT Markets CFD BTCUSD/ETHUSD) | per yaml | SHADOW_ALERTS_ONLY, no logic_verified claim | NOT_EVALUATED | proposal_generation_authorized=false, alerts ARCHIVE_ONLY | false | false | `strategies/registry.yaml` lines 73-78 |
| ST_LIQUIDITY_SWEEP_RETEST_V1 | 2.0.0 | `strategies/ST_LIQUIDITY_SWEEP_RETEST_V1.yaml` | `src/strategy_engine/sweep_retest/` (RESEARCH_ONLY) | FX: inactive (no pilot); Crypto: `src/btc_sweep_research/`, feed = Bybit perp (research) | ACTIVE_INCUBATION (crypto research only) | FOREX + CRYPTO_PERP profiles | n/a | NOT_VERIFIED | NOT_EVALUATED | none (static+behavioral boundary test confirms no execution path) | false | false | `strategies/registry.yaml` lines 79-110; `strategies/STRATEGY_LEDGER.md` tail |

Note (crypto venue conflation, found not created): `config/v1_tickets/crypto_ticket_v2.yaml` (ACTIVE) feeds the frozen 2.0.0 **CRYPTO_PERP-calibrated** engine with **VT Markets MT5 CFD** candles (BTCUSDT→BTCUSD, ETHUSDT→ETHUSD) for informational tickets only; `strategies/STRATEGY_LEDGER.md` explicitly records this CFD input as "a new, UNVALIDATED data source" whose perp cost model "do[es] not transfer to it." This is a pre-existing, already-documented gap (see T4/D_CRYPTO_VENUE), not introduced here.
