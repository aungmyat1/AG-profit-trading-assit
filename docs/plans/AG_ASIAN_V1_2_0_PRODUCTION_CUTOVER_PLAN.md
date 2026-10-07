# ST_ASIAN_SWEEP_5R_V1 1.1.1 → 1.2.0 Production Cutover Plan (R3, preparation only)

This plan does not rebuild PR #45. It reads PR #45's existing artifacts (via `git show`
against `origin/pull/45/head`) and does not modify or rerun them.

```
CURRENT_RUNTIME_VERSION=1.1.1 (strategies/ST_ASIAN_SWEEP_5R_V1.yaml, registry active=true)
V1_1_1_LOGIC_STATUS=NOT_VERIFIED (strategies/registry.yaml: logic_status: NOT_VERIFIED, logic_verified_identity: null)
V1_2_0_FREEZE_STATUS=FROZEN_CANDIDATE_ONLY — freeze_sha 6c483fd834e772f9f41179ef939dd4eb4d082286, freeze_identity_match=PASS
  (artifacts/logic_verification/ST_ASIAN_SWEEP_5R_V1_2_0/r3_verification_report.json, PR #45) — frozen as a candidate
  artifact inside PR #45, NOT merged to main, NOT registered in strategies/registry.yaml.
R4A_STATUS=PACKAGED — blind handoff package built, PACKAGE_SHA256=cfc8309dd9259fbe99b0f6ecc85c68f5864ce566e49f10a7c18e24b9812f69d6,
  HANDOFF_ID=AG_ASIAN_SWEEP_V1_2_BLIND_HANDOFF_001 (handoff_manifest.json, PR #45).
R4B_STATUS=NOT_RUN — blind_reference_isolation=BLOCKED_SEPARATE_AGENT_CONTEXT_UNAVAILABLE,
  reference_engine_parity=NOT_RUN, logic_verified=false (same report).
CUTOVER_READY=FALSE
```

`CUTOVER_READY` is FALSE because the required blind logic-verification (R4B) evidence has
not passed — it has not run at all, not failed a loosenable check. No threshold or scope
was relaxed to reach this conclusion.

## Verification-scope determination (do not infer from YAML lists alone)

The r3 dataset (`AG_ASIAN_SWEEP_V1_2_R3_LOGIC_PARITY_001`) admitted only 3 of 23 source
rows to ASIAN_LONDON scope (9 out-of-scope, 11 insufficient-data), yielding 3
logic-parity cases and 0 full-cost cases (`r3_verification_report.json`).

```
EURUSD scope evidenced       = PARTIAL (present among the 3 admitted rows; exact symbol
                                breakdown not re-extracted this mission — NOT_VERIFIED)
GBPUSD scope evidenced       = NOT_VERIFIED
USDJPY scope evidenced       = NOT_VERIFIED
XAUUSD scope evidenced       = NOT_VERIFIED
ASIAN_LONDON scope evidenced = PARTIAL (3 admitted cases, 1 CORE_LOGIC_PASS)
LONDON_NEWYORK scope evidenced = NOT_VERIFIED (dataset note says admitted set is
                                  ASIAN_LONDON only; no LONDON_NEWYORK case count found)
```

The contract/dataset covering 4 symbols × 2 windows does not by itself prove each
cell was blind-verified — only 3 total cases reached logic parity. Do not treat the
`ST_ASIAN_SWEEP_5R_V1_2_0.yaml` instrument list as verification-scope evidence.

## Cutover preparation items (not executed)

- **Config changes**: registry would need a new `ST_ASIAN_SWEEP_5R_V1` version pointer
  (today only 1.1.1 is registered); no edit made.
- **Strategy identity transition**: 1.1.1 and 1.2.0 must remain distinct ids/evidence
  trails until R4B passes — do not merge ledger history.
- **Ticket lineage**: existing 1.1.1 `MANUAL_ONLY` ticket_authority and
  `logic_verified_identity: null` must not be copied onto 1.2.0 by inference.
- **Archive continuity**: 1.1.1 evidence/archives stay in place; a cutover would add,
  not replace, history (see `strategies/STRATEGY_LEDGER.md` convention of additive entries).
- **Stale-ticket behavior**: NOT_VERIFIED — no stale-ticket-on-cutover test found this mission.
- **Rollback**: NOT_VERIFIED — no documented rollback runbook found for a 1.1.1→1.2.0
  registry swap; would need to be authored before any real cutover.
- **Code-SHA attribution**: PR #43 ("code-sha-provenance", already on `main` at base
  commit `fc60cdb`) suggests infrastructure exists; its applicability to 1.2.0 specifically
  is NOT_VERIFIED this mission.
- **Host acceptance requirements**: NOT_VERIFIED (not tested this mission).

## Blocking sequence (owner must resolve, in order)

1. Obtain a real separate-agent-context blind reference run (R4B) — currently architecturally
   blocked, not merely pending.
2. Re-run/extend r3 dataset coverage for GBPUSD/USDJPY/XAUUSD and LONDON_NEWYORK before
   claiming full-scope verification.
3. Only then: owner decision to register 1.2.0 and plan the cutover mechanics above.
