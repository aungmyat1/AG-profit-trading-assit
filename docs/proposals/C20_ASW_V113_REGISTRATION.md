# C20 proposal — register ST_ASIAN_SWEEP_5R_V1 1.1.3 as a candidate identity

Mission AGP-C20-VERIFICATION-LEDGER-R2 (T3). Proposal only: no registry, READY, runtime-binding, demo or live
change. Summary: `artifacts/verification_ledger/c20_rerun_summary.json` (`t3_asw_1_1_3_60d`).

## Re-run (60 weekdays, clean main worktree 5e686f37)
- All 8 scope rows (EURUSD/GBPUSD/USDJPY/XAUUSD × ASIAN_LONDON/LONDON_NEWYORK) are identical to the recorded
  #186/#193 run (`asw_v113_60d_run1.json`); the only difference is the run's `verification_code_sha`.
- L1 fails on exactly one check for every symbol: `registry_identity_matches` (v1.1.3 is unregistered). All
  other L1 checks pass.
- Logic identity: **`7e2324296ab6cb56147f6709aae5f8e1633e9c32475ee0f8b3988ea31adfedc9`**.

## Expected verdicts after a candidate-only registration (L1 then PASS)

| Pair | Session | L1 | L2 | L3 | L4 | L5 | L6 |
|---|---|---|---|---|---|---|---|
| EURUSD | ASIAN_LONDON | PASS | PASS | PASS | PASS | PASS | PASS |
| EURUSD | LONDON_NEWYORK | PASS | PASS | PASS | PASS | PASS | PASS |
| GBPUSD | ASIAN_LONDON | PASS | PASS | PASS | PASS | PASS | PASS |
| GBPUSD | LONDON_NEWYORK | PASS | PASS | PASS | PASS | PASS | PASS |
| USDJPY | both | PASS | INSUFFICIENT | PASS | INSUFFICIENT | FAIL | PASS |
| XAUUSD | both | PASS | INSUFFICIENT | PASS | INSUFFICIENT | FAIL | PASS |

## Proposed registry diff (candidate-only, not applied)

```yaml
ST_ASIAN_SWEEP_5R_V1:
  candidate_versions:
    "1.1.3":
      config_source: strategies/ST_ASIAN_SWEEP_5R_V1_1_1_3.yaml
      status: CANDIDATE_PENDING_OWNER_CONFIRM
      logic_status: NOT_VERIFIED          # until the scope entries below are separately recorded
      logic_verified_identity: 7e2324296ab6cb56147f6709aae5f8e1633e9c32475ee0f8b3988ea31adfedc9
      economic_status: NOT_EVALUATED
      edge_verified: false
      ticket_ready: PAUSED_PENDING_OWNER_CONFIRM
```

No change to `config_source` (runtime stays v1.1.1), the v1.1.2 entry, S1 or `ready_authority.yaml`.

## Separate question — EURUSD × ASIAN_LONDON rebind
The v1.1.2 EURUSD × ASIAN_LONDON scope is SUSPENDED (L3 repaint). v1.1.3 passes L3 there (0/25 future-mutation
mismatches on 2026-07-31). Whether to verify and bind that scope on v1.1.3 is a separate owner decision after
registration; the report lane already evaluates it on v1.1.3 as NOT_VERIFIED (OD1014-FAST D3).

## Owner decisions required
1. Register 1.1.3 as a candidate with identity `7e232429…` (turns L1 to PASS)?
2. Separately: rebind EURUSD × ASIAN_LONDON to v1.1.3 scope verification?
